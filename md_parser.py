"""Markdown 文档解析器

Markdown 文件无需额外解析，直接解码为文本即可。
保留所有 Markdown 格式标记（#, **, - 等）。
"""

from .base import BaseParser


class MarkdownParser(BaseParser):
    """Markdown 文档解析器

    最简单的解析器实现，直接使用智能编码检测解码 Markdown 内容。
    不做任何格式转换，保留原始 Markdown 标记。
    """

    async def parse(self, content: bytes) -> str:
        """直接解码为文本（Markdown 无需额外解析）

        Args:
            content: Markdown 文件的二进制内容

        Returns:
            解码后的 Markdown 文本，保留所有格式标记

        Note:
            虽然内部是同步操作，但为了接口一致性，此方法为异步方法
        """
        return self.decode_bytes(content)
