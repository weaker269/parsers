"""本地解析器服务实现

直接调用 parsers 模块进行文件解析，不依赖 gRPC 服务。
适用于单机部署、开发环境、或作为 gRPC 模式的降级方案。
"""

import logging
from pathlib import Path
from typing import Dict, Any

from parsers.service_interface import ParserServiceInterface
from parsers import create_parser

logger = logging.getLogger(__name__)


class LocalParserService(ParserServiceInterface):
    """本地解析器服务实现

    直接调用 parsers 模块的 create_parser 工厂函数，
    在当前进程内完成文件解析。

    优势：
    - 无网络开销（0ms 延迟）
    - 无需额外部署 gRPC 服务
    - 适合单机部署、开发环境

    劣势：
    - 每个进程独立加载 OCR 模型（内存占用高）
    - 无法跨语言调用
    - 版本管理困难（多项目场景）
    """

    def parse_file(self, file_path: str, **options) -> Dict[str, Any]:
        """解析文件（本地调用）

        Args:
            file_path: 文件路径（绝对路径）
            **options: 解析选项（当前版本忽略，使用默认配置）

        Returns:
            Dict[str, Any]: 解析结果，包含：
                - content: 解析后的文本内容
                - metadata: 元数据（页数、图像数、表格数等）

        Raises:
            ValueError: 不支持的文件格式
            Exception: 解析失败
        """
        logger.info(f"本地解析文件: {file_path}")

        # 检测文件格式
        file_path_obj = Path(file_path)
        file_format = file_path_obj.suffix

        # 创建解析器
        parser = create_parser(file_format)

        # 执行解析
        content = parser.parse(str(file_path))

        # 构造响应（与 gRPC 响应格式一致）
        result = {
            "content": content,
            "metadata": {
                "page_count": getattr(parser, 'page_count', 0),
                "image_count": getattr(parser, 'image_count', 0),
                "table_count": getattr(parser, 'table_count', 0),
                "ocr_count": getattr(parser, 'ocr_count', 0),
                "caption_count": getattr(parser, 'caption_count', 0),
                "parse_time_ms": 0,  # 本地调用不统计耗时
            }
        }

        logger.info(
            f"本地解析完成: {file_path}, "
            f"页数 {result['metadata']['page_count']}, "
            f"图像 {result['metadata']['image_count']}, "
            f"表格 {result['metadata']['table_count']}"
        )

        return result
