"""解析结果数据模型

定义解析器返回的结构化数据类型。
"""

from dataclasses import dataclass


@dataclass
class ParseMetadata:
    """解析元数据

    包含解析过程中收集的统计信息和性能指标。

    Attributes:
        page_count: 文档页数（PDF/PPTX），DOCX/Markdown 为 0
        image_count: 提取的图像总数
        table_count: 提取的表格总数
        ocr_count: OCR 识别的图像数量
        caption_count: VLM Caption 生成的图像数量
        parse_time_ms: 解析耗时（毫秒）
    """
    page_count: int = 0
    image_count: int = 0
    table_count: int = 0
    ocr_count: int = 0
    caption_count: int = 0
    parse_time_ms: float = 0.0


@dataclass
class ParseResult:
    """解析结果

    包含解析后的文本内容和元数据。

    Attributes:
        content: 解析后的文本内容（Markdown 格式）
        metadata: 解析元数据
    """
    content: str
    metadata: ParseMetadata
