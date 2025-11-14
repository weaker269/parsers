"""文件解析器模块

提供统一的文件解析接口，支持多种文档格式：
- Markdown (.md, .markdown)
- PDF (.pdf)
- Word (.docx, .doc)
- PowerPoint (.pptx)

使用工厂模式创建对应的解析器实例。
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# 确保导入 parsers 时自动加载根目录下的 .env
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env", override=False)


def _configure_parser_logging():
    """为 parser 模块创建独立的日志配置"""
    parser_logger = logging.getLogger(__name__)  # __name__ == "parsers"

    if getattr(parser_logger, "_parser_logging_configured", False):
        return

    log_dir = os.getenv("PARSER_LOG_DIR", "./logs")
    log_file = os.getenv("PARSER_LOG_FILE", "parser.log")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(process)d - %(thread)d - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    parser_logger.addHandler(file_handler)
    parser_logger.addHandler(stream_handler)
    parser_logger.setLevel(os.getenv("PARSER_LOG_LEVEL", "INFO").upper())

    # 保持独立日志文件，避免回传到根 logger
    parser_logger.propagate = False
    parser_logger._parser_logging_configured = True  # type: ignore[attr-defined]


_configure_parser_logging()

from .models import ParseResult, ParseMetadata
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .md_parser import MarkdownParser
from .pptx_parser import PptxParser


def create_parser(file_ext: str):
    """根据文件扩展名创建解析器（工厂函数）

    Args:
        file_ext: 文件扩展名（如 '.pdf', '.md'），不区分大小写

    Returns:
        对应的解析器实例

    Raises:
        ValueError: 不支持的文件格式

    Example:
        >>> parser = create_parser('.pdf')
        >>> text = parser.parse(pdf_content)
    """
    # 解析器映射表
    parsers = {
        '.pdf': PDFParser,
        '.md': MarkdownParser,
        '.markdown': MarkdownParser,
        '.docx': DocxParser,
        '.doc': DocxParser,
        '.pptx': PptxParser,
    }

    # 不区分大小写
    parser_cls = parsers.get(file_ext.lower())

    if not parser_cls:
        supported = ", ".join(parsers.keys())
        raise ValueError(f"不支持的文件格式：{file_ext}。支持的格式：{supported}")

    return parser_cls()


# 导出公共 API
__all__ = ['create_parser', 'ParseResult', 'ParseMetadata', 'PDFParser', 'DocxParser', 'MarkdownParser', 'PptxParser']
