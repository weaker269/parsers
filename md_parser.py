"""Markdown 文档解析器

Markdown 文件无需额外解析，直接解码为文本即可。
保留所有 Markdown 格式标记（#, **, - 等）。
"""

from .base import BaseParser
from .models import ParseResult, ParseMetadata


class MarkdownParser(BaseParser):
    """Markdown 文档解析器

    最简单的解析器实现，直接使用智能编码检测解码 Markdown 内容。
    不做任何格式转换，保留原始 Markdown 标记。
    """

    async def parse(self, content: bytes) -> ParseResult:
        """直接解码为文本（Markdown 无需额外解析）

        Args:
            content: Markdown 文件的二进制内容

        Returns:
            ParseResult: 包含解码后的 Markdown 文本和空元数据

        Note:
            虽然内部是同步操作，但为了接口一致性，此方法为异步方法
        """
        text_content = self.decode_bytes(content)

        # Markdown 文件无结构化信息，元数据全部为 0
        metadata = ParseMetadata(
            page_count=0,
            image_count=0,
            table_count=0,
            ocr_count=0,
            caption_count=0,
            parse_time_ms=0.0  # 由服务端计算
        )

        return ParseResult(content=text_content, metadata=metadata)
