"""文件解析器基类

基于 WeKnora 项目的设计理念，提供统一的解析器接口和智能编码检测。
"""

from abc import ABC, abstractmethod
import asyncio
import logging
import multiprocessing
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from .models import ParseResult, ParseMetadata

logger = logging.getLogger(__name__)

# 全局进程池实例（单例模式）
_process_pool: Optional[ProcessPoolExecutor] = None


def _get_process_pool() -> ProcessPoolExecutor:
    """获取全局进程池实例（单例模式）

    关键配置：
    1. 进程池大小：min(cpu_count(), 2) - 每进程约 500MB 内存
    2. 启动模式：spawn（显式指定，避免 fork 模式的内存损坏）
    3. 初始化器：init_ocr_worker（子进程启动时独立初始化 Paddle）

    技术背景：
    - Linux 默认 fork 模式会继承父进程的半初始化状态
    - PaddleOCR C++ 底层在 fork 模式下有线程安全问题
    - spawn 模式创建全新进程，完全独立的内存空间

    Returns:
        ProcessPoolExecutor: 全局进程池实例

    Note:
        - 单例模式：多次调用返回同一实例
        - 首次调用会创建进程池并预热子进程
        - 进程池大小限制为 min(cpu_count(), 2)，避免内存占用过高
    """
    global _process_pool

    if _process_pool is None:
        from parsers.ocr_worker import init_ocr_worker

        # 计算进程池大小（限制为 min(cpu_count(), 5)）
        # 每个子进程约占用 500MB 内存，5 个进程约 2.5GB
        num_processes = min(multiprocessing.cpu_count(), 5)

        # 显式获取 spawn 上下文（确保使用 spawn 模式）
        mp_context = multiprocessing.get_context("spawn")

        logger.info(
            f"创建全局进程池（大小: {num_processes}, 启动模式: spawn）"
        )

        # 创建进程池
        _process_pool = ProcessPoolExecutor(
            max_workers=num_processes,
            mp_context=mp_context,
            initializer=init_ocr_worker  # 子进程启动时调用初始化器
        )

        logger.info(f"全局进程池创建成功（{num_processes} 个子进程）")

    return _process_pool


def _shutdown_process_pool():
    """关闭全局进程池（优雅关闭）

    关闭策略：
    1. 等待所有正在执行的任务完成（wait=True）
    2. 超时时间：30 秒
    3. 关闭后将全局变量重置为 None

    使用场景：
    - 应用关闭时调用（FastAPI shutdown event）
    - 测试完成后清理资源
    - 进程池重启

    Note:
        - 关闭是阻塞操作，会等待所有任务完成
        - 如果任务未能在 30 秒内完成，会强制终止
        - 关闭后进程池不可再使用，需要重新创建
    """
    global _process_pool

    if _process_pool is not None:
        logger.info("关闭全局进程池...")

        # 注意：ProcessPoolExecutor.shutdown 在 Python 3.11 不支持 timeout 参数
        # 因此这里采用默认行为，等待任务完成
        _process_pool.shutdown(wait=True, cancel_futures=False)
        logger.info("全局进程池已关闭")

        # 重置全局变量
        _process_pool = None


class BaseParser(ABC):
    """文件解析器抽象基类

    所有文件解析器必须继承此类并实现 parse 方法。
    提供智能编码检测功能，支持多种中文编码。
    """

    @abstractmethod
    async def parse(self, content: bytes) -> ParseResult:
        """解析文件内容为文本（异步方法）

        Args:
            content: 文件二进制内容

        Returns:
            ParseResult: 包含解析后的文本内容和元数据

        Raises:
            Exception: 解析失败时抛出异常

        Note:
            此方法为异步方法，调用时需要使用 await
        """
        pass

    def decode_bytes(self, content: bytes) -> str:
        """智能编码检测（继承自 WeKnora）

        尝试多种编码方式解码文本，优先使用 UTF-8，
        然后尝试常见的中文编码格式。

        尝试顺序：UTF-8 → GB18030 → GBK → latin-1

        Args:
            content: 待解码的字节内容

        Returns:
            解码后的文本字符串

        Note:
            latin-1 作为最终回退，因为它可以解码任何字节序列
        """
        encodings = ["utf-8", "gb18030", "gbk", "latin-1"]

        for encoding in encodings:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue

        # 最终回退到 latin-1（永远不会失败）
        return content.decode("latin-1")

    def perform_ocr(self, image_data: bytes) -> str:
        """对图像执行 OCR 识别

        Args:
            image_data: 图像二进制数据

        Returns:
            识别出的文本内容

        Raises:
            RuntimeError: OCR 识别失败
        """
        try:
            # 延迟导入 OCR 引擎（避免启动时加载）
            from .ocr_engine import get_ocr_engine

            engine = get_ocr_engine()

            # 图像预处理
            image_array = engine.preprocess_image(image_data)

            # 执行 OCR 识别
            text = engine.recognize(image_array)

            return text

        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            raise RuntimeError(f"OCR 处理错误: {e}")

    def _resize_image_if_needed(self, image_data: bytes) -> bytes:
        """智能缩放图像（如果需要）

        Note:
            此方法已被整合到 ocr_engine.preprocess_image() 中，
            保留此方法是为了保持 API 兼容性。

        Args:
            image_data: 原始图像二进制数据

        Returns:
            处理后的图像二进制数据
        """
        # 实际上在 perform_ocr 中已经通过 preprocess_image 处理
        # 这里直接返回原始数据
        return image_data

    @classmethod
    def get_ocr_engine(cls):
        """获取 OCR 引擎实例（类方法）

        Returns:
            OCREngine: OCR 引擎单例实例

        Example:
            >>> engine = BaseParser.get_ocr_engine()
            >>> text = engine.recognize(image_array)
        """
        from .ocr_engine import get_ocr_engine
        return get_ocr_engine()

    async def process_image_async(
        self,
        image_data: bytes,
        image_index: int = 0,
        timeout: float = 60.0
    ) -> Tuple[int, str]:
        """异步处理单个图像的 OCR 识别（多进程版本）

        使用进程池而非线程池，解决 PaddleOCR 的线程安全问题。

        Args:
            image_data: 图像二进制数据
            image_index: 图像索引（用于日志和结果标识）
            timeout: 单个 OCR 任务的超时时间（秒），默认 60 秒（大图需要更长时间）

        Returns:
            元组 (image_index, ocr_text)

        Raises:
            asyncio.TimeoutError: OCR 任务超时
            RuntimeError: OCR 识别失败

        技术细节：
        - 使用 ProcessPoolExecutor 而非 ThreadPoolExecutor
        - 调用 ocr_worker 函数（模块级函数，可被 pickle 序列化）
        - spawn 模式启动子进程（避免 fork 模式的内存损坏）
        - 超时时间增加到 60 秒（大图 OCR 需要更长时间）
        """
        try:
            from parsers.ocr_worker import ocr_worker

            # 使用 run_in_executor 在进程池中执行同步的 OCR 操作
            loop = asyncio.get_event_loop()

            # 使用 wait_for 添加超时控制
            ocr_text = await asyncio.wait_for(
                loop.run_in_executor(
                    _get_process_pool(),  # 使用全局进程池（而非线程池）
                    ocr_worker,           # 调用 worker 函数（而非 self.perform_ocr）
                    image_data
                ),
                timeout=timeout
            )

            return (image_index, ocr_text)

        except asyncio.TimeoutError:
            logger.warning(f"图像 {image_index} OCR 识别超时（>{timeout}秒）")
            raise
        except Exception as e:
            logger.error(f"图像 {image_index} 异步 OCR 处理失败: {e}")
            raise

    async def process_images_async(
        self,
        images_data: List[bytes],
        max_concurrent: int = 5,
        timeout_per_image: float = 180.0
    ) -> List[Tuple[int, str]]:
        """批量异步处理多个图像的 OCR 识别（多进程版本）

        使用 Semaphore 限制并发数，使用 asyncio.gather 并发执行多个任务。
        使用进程池而非线程池，解决 PaddleOCR 的线程安全问题。

        Args:
            images_data: 图像二进制数据列表
            max_concurrent: 最大并发数，默认 5
            timeout_per_image: 单个图像的超时时间（秒），默认 60 秒（大图需要更长时间）

        Returns:
            成功识别的图像列表，每个元素为 (image_index, ocr_text)
            失败的图像会被跳过，不在结果中

        Note:
            - 使用 Semaphore 控制并发数，避免资源耗尽
            - 单个图像识别失败不影响其他图像
            - 返回的列表按照原始索引排序
        """
        if not images_data:
            return []

        logger.info(f"开始异步批量处理 {len(images_data)} 个图像（最大并发数: {max_concurrent}）")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(image_data: bytes, index: int):
            """在信号量保护下处理单个图像"""
            async with semaphore:
                try:
                    return await self.process_image_async(
                        image_data,
                        image_index=index,
                        timeout=timeout_per_image
                    )
                except Exception as e:
                    logger.warning(f"图像 {index} 处理失败: {e}")
                    return None

        # 创建所有任务
        tasks = [
            process_with_semaphore(image_data, idx)
            for idx, image_data in enumerate(images_data, start=1)
        ]

        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # 过滤掉失败的结果（None）
        successful_results = [r for r in results if r is not None]

        logger.info(
            f"异步批量处理完成，成功: {len(successful_results)}/{len(images_data)} 个图像"
        )

        return successful_results
