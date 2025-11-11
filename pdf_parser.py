"""PDF 文档解析器

基于 pdfplumber 的 PDF 解析实现，支持：
- 文本提取
- 表格检测和转换为 Markdown
- Try-Fallback 表格检测策略（继承自 WeKnora）
- 多页文档处理
- 异步并发图像 OCR（性能优化）
"""

import tempfile
import os
import logging
import asyncio
import pdfplumber
from .base import BaseParser

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF 文档解析器（基于 WeKnora 设计）

    使用 pdfplumber 进行 PDF 解析，支持复杂表格检测和转换。
    表格统一转换为 Markdown 格式，便于 LLM 理解。

    内部使用异步并发处理图像 OCR，显著提升多图场景性能。
    """

    async def parse(self, content: bytes) -> str:
        """使用双层并发解析 PDF 文档（内部异步实现）

        第一层：页面级并发（解析并发）
        - 多个子进程并行处理不同页面
        - 每个子进程提取文本、表格、图像路径（不执行 OCR）

        第二层：OCR 级并发（识别并发）
        - 主进程收集所有图像路径
        - 统一调度到 OCR 进程池（复用现有 ocr_worker）
        - 异步并发识别所有图像

        Args:
            content: PDF 文件的二进制内容

        Returns:
            解析后的文本内容，包含表格的 Markdown 表示

        Note:
            - 性能提升：约 6-15x（解析并发 3-5x × OCR 并发 2-3x）
            - 临时文件自动清理（finally 块保证）
        """
        temp_dir = None
        temp_pdf_path = None

        try:
            from .page_processor import PagePoolManager, PageData

            # 1. 保存 PDF 到临时文件
            temp_dir = PagePoolManager.create_temp_dir(prefix="pdf_multiprocess_")
            temp_pdf_path = os.path.join(temp_dir, "document.pdf")

            with open(temp_pdf_path, "wb") as f:
                f.write(content)

            logger.info(f"PDF 已保存到临时文件: {temp_pdf_path}")

            # 2. 快速扫描获取页面数量
            with pdfplumber.open(temp_pdf_path) as pdf:
                page_count = len(pdf.pages)

            logger.info(f"开始双层并发解析 PDF，共 {page_count} 页")

            # 3. 并行处理所有页面（使用全局进程池）
            page_indices = list(range(page_count))
            worker_args = {
                "pdf_path": temp_pdf_path,
                "temp_dir": temp_dir
            }

            page_results = PagePoolManager.process_pages_parallel(
                page_indices=page_indices,
                worker_func=process_pdf_page_worker,
                worker_args=worker_args
            )

            logger.info(f"页面并行处理完成，共 {len(page_results)} 页")

            # 5. 收集所有图像路径
            all_image_paths = []
            image_to_page_map = {}  # {image_path: (page_num, image_num)}

            for page_data in page_results:
                for image_path in page_data.image_paths:
                    all_image_paths.append(image_path)
                    # 图像编号
                    image_num = len([p for p in page_data.image_paths if p <= image_path]) + 1
                    image_to_page_map[image_path] = (page_data.page_num, image_num)

            logger.info(f"收集到 {len(all_image_paths)} 个图像，准备统一 OCR")

            # 6. 统一 OCR 处理（复用现有异步 OCR）
            ocr_results_map = {}  # {image_path: ocr_text}

            if all_image_paths:
                # 读取所有图像数据
                images_data = []
                valid_image_paths = []

                for img_path in all_image_paths:
                    try:
                        with open(img_path, "rb") as f:
                            image_data = f.read()
                            images_data.append(image_data)
                            valid_image_paths.append(img_path)
                    except Exception as e:
                        logger.warning(f"读取图像失败: {img_path}, 错误: {e}")
                        continue

                # 异步并发 OCR
                logger.info(f"开始异步并发 OCR，共 {len(images_data)} 个图像")
                ocr_results_list = await self.process_images_async(
                    images_data,
                    max_concurrent=5,
                    timeout_per_image=180.0  # 单个图像超时 180 秒（首次请求包含模型加载）
                )

                # 构建结果映射
                for result_index, ocr_text in ocr_results_list:
                    if 0 < result_index <= len(valid_image_paths):
                        img_path = valid_image_paths[result_index - 1]
                        if ocr_text.strip():
                            ocr_results_map[img_path] = ocr_text
                            logger.debug(f"图像 OCR 成功: {img_path}, {len(ocr_text)} 字符")

                logger.info(f"OCR 处理完成，成功识别 {len(ocr_results_map)} 个图像")

            # 7. 合并 OCR 结果到对应页面
            all_pages = []

            for page_data in page_results:
                page_parts = []

                # 按顺序组装内容
                for content_type, content, order_idx in sorted(
                    page_data.content_parts,
                    key=lambda x: x[2]  # 按顺序索引排序
                ):
                    if content_type == "text":
                        page_parts.append(content)
                    elif content_type == "table":
                        page_parts.append(content)
                    elif content_type == "image_placeholder":
                        # 查找对应的 OCR 结果
                        image_path = content  # 这里 content 存储的是 image_path
                        if image_path in ocr_results_map:
                            page_num, image_num = image_to_page_map[image_path]
                            ocr_text = ocr_results_map[image_path]
                            page_parts.append(f"[图像 {image_num} OCR 内容]:\n{ocr_text}")
                        else:
                            logger.debug(f"图像未识别到文字: {image_path}")

                if page_parts:
                    all_pages.append("\n\n".join(page_parts))
                else:
                    all_pages.append("")  # 空页面

            logger.info(f"PDF 双层并发解析完成，成功处理 {len(all_pages)} 页")

            # 8. 用分页符连接所有页面
            return "\n\n--- Page Break ---\n\n".join(all_pages)

        except Exception as e:
            logger.error(f"PDF 双层并发解析失败: {e}", exc_info=True)
            raise RuntimeError(f"PDF 文档双层并发解析错误: {e}")

        finally:
            # 清理临时文件
            if temp_dir:
                PagePoolManager.cleanup_temp_files(temp_dir)



# ============================================================
# 页面级并发 Worker 函数（顶层函数，可被 pickle 序列化）
# ============================================================

def process_pdf_page_worker(page_num: int, pdf_path: str, temp_dir: str):
    """处理单个 PDF 页面的 Worker 函数（子进程中执行）

    这是一个顶层函数，必须在模块级定义以便 pickle 序列化。

    Args:
        page_num: 页面索引（从 0 开始）
        pdf_path: PDF 文件路径
        temp_dir: 临时目录路径

    Returns:
        PageData 对象，包含页面的文本、表格、图像路径

    Note:
        - 在子进程中独立加载 PDF 文件
        - 只提取文本、表格、图像路径，不执行 OCR
        - 图像保存到临时文件，路径返回给主进程
    """
    import pdfplumber
    from .page_processor import PageData
    from .ocr_worker import is_background_image
    import logging
    import tempfile

    logger = logging.getLogger(__name__)

    try:
        # 1. 在子进程中加载 PDF，并在整个页面处理期间保持文件句柄有效
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]

            logger.debug(f"子进程处理页面 {page_num}, PID: {os.getpid()}")

            # 2. 提取内容（按顺序）
            content_parts = []
            image_paths = []
            order_idx = 0

            # 2.1 检测表格（使用 Try-Fallback 策略）
            tables = _find_tables_with_fallback_worker(page)
            table_bboxes = [t.bbox for t in tables]

            # 2.2 提取非表格文本
            def not_in_table(obj):
                """过滤器：排除表格区域内的文本对象"""
                obj_center_y = (obj["top"] + obj["bottom"]) / 2
                for bbox in table_bboxes:
                    if bbox[1] <= obj_center_y <= bbox[3]:
                        return False
                return True

            text = page.filter(not_in_table).extract_text() or ""
            if text.strip():
                content_parts.append(("text", text, order_idx))
                order_idx += 1

            # 2.3 表格转 Markdown
            for table in tables:
                markdown_table = _table_to_markdown_worker(table.extract())
                if markdown_table:
                    content_parts.append(("table", markdown_table, order_idx))
                    order_idx += 1

            # 2.4 提取图像
            page_images = page.images
            if page_images:
                logger.debug(f"页面 {page_num} 检测到 {len(page_images)} 个图像")

                for img_index, img_obj in enumerate(page_images):
                    try:
                        # 检测是否为有意义的图像
                        img_width = img_obj["width"]
                        img_height = img_obj["height"]

                        # 跳过小图像
                        MIN_IMAGE_SIZE = 50  # 最小边长 50 像素
                        if img_width < MIN_IMAGE_SIZE or img_height < MIN_IMAGE_SIZE:
                            logger.debug(f"页面 {page_num} 跳过小图像 (尺寸: {img_width}x{img_height})")
                            continue

                        # 提取图像对象
                        image_obj = page.within_bbox(img_obj["bbox"]).to_image()

                        # 保存为临时文件
                        image_filename = f"page_{page_num}_image_{img_index}.png"
                        image_path = os.path.join(temp_dir, image_filename)
                        image_obj.save(image_path)

                        # 读取图像数据用于背景图检测
                        with open(image_path, 'rb') as f:
                            image_data = f.read()

                        # 背景图检测
                        if is_background_image(image_data, img_width, img_height):
                            logger.debug(
                                f"页面 {page_num} 跳过背景图 "
                                f"(尺寸: {img_width}x{img_height})"
                            )
                            os.remove(image_path)  # 删除背景图
                            continue

                        image_paths.append(image_path)
                        # 记录图像占位符（OCR 结果稍后填充）
                        content_parts.append(("image_placeholder", image_path, order_idx))
                        order_idx += 1

                        logger.debug(f"页面 {page_num} 保存图像: {image_path}")

                    except Exception as e:
                        logger.warning(f"页面 {page_num} 提取图像 {img_index} 失败: {e}")
                        continue

            logger.debug(
                f"页面 {page_num} 处理完成: "
                f"内容 {len(content_parts)} 个, 图像 {len(image_paths)} 个"
            )

            return PageData(
                page_num=page_num,
                content_parts=content_parts,
                image_paths=image_paths
            )

    except Exception as e:
        logger.error(f"页面 {page_num} 处理失败: {e}", exc_info=True)
        # 返回空结果而非抛出异常（容错）
        return PageData(
            page_num=page_num,
            content_parts=[],
            image_paths=[]
        )


def _find_tables_with_fallback_worker(page):
    """表格检测 Try-Fallback 策略（Worker 版本）

    Args:
        page: pdfplumber 页面对象

    Returns:
        检测到的表格对象列表
    """
    # 默认策略：基于线条检测
    tables = page.find_tables({
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines"
    })

    if not tables:
        # 回退策略：基于文本检测
        tables = page.find_tables({
            "vertical_strategy": "text",
            "horizontal_strategy": "text"
        })

    return tables


def _table_to_markdown_worker(table_data: list) -> str:
    """将表格数据转换为 Markdown 格式（Worker 版本）

    这是 _table_to_markdown 的简化版本，用于子进程。

    Args:
        table_data: 表格数据，二维列表格式

    Returns:
        Markdown 格式的表格字符串
    """
    if not table_data or not table_data[0]:
        return ""

    # 清理单元格
    def clean(cell):
        if cell is None:
            return ""
        return str(cell).replace("\n", "<br>").strip()

    # 表头
    header = [clean(c) for c in table_data[0]]
    if not header or all(not cell for cell in header):
        return ""

    num_columns = len(header)

    # 生成 Markdown
    md = "| " + " | ".join(header) + " |\n"
    md += "| " + " | ".join(["---"] * num_columns) + " |\n"

    # 数据行
    for row in table_data[1:]:
        if not row:
            continue
        cells = [clean(c) for c in row]
        if len(cells) != num_columns or all(not cell for cell in cells):
            continue
        md += "| " + " | ".join(cells) + " |\n"

    return md
