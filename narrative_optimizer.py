"""叙述性内容优化器

轻量级规则引擎，用于优化 PPTX 提取的碎片化内容。
将关键词列表、公式符号、图片占位符等转换为更适合 LLM 理解的叙述性文本。

设计理念：
- 规则驱动，无额外依赖（不使用 Transformers/Spacy）
- 性能优先（<100ms/文件）
- PPTX 专用优化，不影响 PDF/DOCX
"""

import re
import logging

logger = logging.getLogger(__name__)


class NarrativeOptimizer:
    """叙述性优化器（静态方法集合）

    提供一系列规则来优化碎片化内容，使其更适合 Quiz 生成。
    """

    @staticmethod
    def optimize(text: str) -> str:
        """应用所有优化规则

        Args:
            text: 原始提取的文本内容

        Returns:
            优化后的文本内容

        Note:
            优化顺序很重要，某些规则依赖于前面规则的输出
        """
        if not text or not text.strip():
            return text

        logger.debug(f"开始叙述性优化，原始文本长度: {len(text)} 字符")

        # 应用优化规则（按顺序）
        text = NarrativeOptimizer._optimize_keyword_separators(text)
        text = NarrativeOptimizer._optimize_slide_separators(text)
        text = NarrativeOptimizer._optimize_formula_notation(text)
        text = NarrativeOptimizer._optimize_image_placeholders(text)
        text = NarrativeOptimizer._optimize_punctuation(text)

        logger.debug(f"叙述性优化完成，优化后文本长度: {len(text)} 字符")

        return text

    @staticmethod
    def _optimize_keyword_separators(text: str) -> str:
        """优化关键词分隔符：`/` → `、`

        将斜杠分隔的关键词列表转换为更自然的中文表达。

        Examples:
            "神经元/激活函数/前向传播" → "神经元、激活函数、前向传播等内容"
            "machine learning / deep learning" → "machine learning, deep learning 等内容"

        Args:
            text: 原始文本

        Returns:
            优化后的文本

        Note:
            - 检测连续的关键词（2个或以上）用斜杠分隔
            - 保留斜杠在其他上下文中的使用（如路径、分数）
            - 中文用顿号，英文用逗号
        """
        # 模式1: 中文关键词（至少2个，用斜杠分隔）
        # 例如："神经元/激活函数/前向传播"
        pattern_zh = r'([\u4e00-\u9fa5]{2,}(?:/[\u4e00-\u9fa5]{2,})+)'

        def replace_zh(match):
            keywords = match.group(1)
            # 替换斜杠为顿号
            optimized = keywords.replace('/', '、')
            # 添加"等内容"后缀
            return f"{optimized}等内容"

        text = re.sub(pattern_zh, replace_zh, text)

        # 模式2: 英文关键词（至少2个，用斜杠+空格分隔）
        # 例如："neural network / activation function / forward propagation"
        pattern_en = r'([a-zA-Z]+(?:\s+[a-zA-Z]+)*\s*/\s*(?:[a-zA-Z]+(?:\s+[a-zA-Z]+)*\s*/\s*)*[a-zA-Z]+(?:\s+[a-zA-Z]+)*)'

        def replace_en(match):
            keywords = match.group(1)
            # 检查是否真的是关键词列表（至少有一个斜杠）
            if '/' not in keywords:
                return keywords
            # 替换斜杠为逗号
            optimized = re.sub(r'\s*/\s*', ', ', keywords)
            # 添加"等内容"后缀
            return f"{optimized} 等内容"

        text = re.sub(pattern_en, replace_en, text)

        return text

    @staticmethod
    def _optimize_slide_separators(text: str) -> str:
        """优化 Slide 分隔符

        标准化不同格式的 Slide 分隔符为统一的 Markdown 格式。

        Examples:
            "@@@Slide_1@@@" → "## Slide 1"
            "===Slide 2===" → "## Slide 2"
            "--- Slide 3 ---" → "## Slide 3"

        Args:
            text: 原始文本

        Returns:
            优化后的文本

        Note:
            pptx_parser.py 已经使用 `## Slide N` 格式，
            此方法主要处理其他可能的格式变体
        """
        # 模式1: @@@Slide_N@@@
        text = re.sub(r'@@@\s*Slide[_\s]+(\d+)\s*@@@', r'## Slide \1', text, flags=re.IGNORECASE)

        # 模式2: ===Slide N===
        text = re.sub(r'={3,}\s*Slide\s+(\d+)\s*={3,}', r'## Slide \1', text, flags=re.IGNORECASE)

        # 模式3: ---Slide N---
        text = re.sub(r'-{3,}\s*Slide\s+(\d+)\s*-{3,}', r'## Slide \1', text, flags=re.IGNORECASE)

        # 模式4: [Slide N] 或 (Slide N)
        text = re.sub(r'[\[\(]\s*Slide\s+(\d+)\s*[\]\)]', r'## Slide \1', text, flags=re.IGNORECASE)

        return text

    @staticmethod
    def _optimize_formula_notation(text: str) -> str:
        """公式说明化：检测公式符号，添加"公式："前缀

        帮助 LLM 识别公式内容，生成更好的 Quiz。

        Examples:
            "y = wx + b" → "公式：y = wx + b"
            "σ(x) = 1/(1+e^-x)" → "公式：σ(x) = 1/(1+e^-x)"

        Args:
            text: 原始文本

        Returns:
            优化后的文本

        Note:
            检测包含以下特征的行：
            - 等号（=）
            - 求和符号（∑）
            - 希腊字母（α, β, γ, δ, ε, θ, λ, μ, σ, π 等）
            - 上标下标符号（^, _）
        """
        lines = text.split('\n')
        optimized_lines = []

        # 公式特征符号
        formula_indicators = [
            '=',  # 等号
            '∑', '∏', '∫',  # 求和、求积、积分
            'α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', 'θ', 'ι', 'κ', 'λ', 'μ',
            'ν', 'ξ', 'ο', 'π', 'ρ', 'σ', 'τ', 'υ', 'φ', 'χ', 'ψ', 'ω',
            '±', '≈', '≠', '≤', '≥',  # 数学符号
        ]

        for line in lines:
            stripped = line.strip()

            # 跳过已经有"公式："前缀的行
            if stripped.startswith('公式：'):
                optimized_lines.append(line)
                continue

            # 跳过 Markdown 标题、列表等
            if stripped.startswith('#') or stripped.startswith('-') or stripped.startswith('*'):
                optimized_lines.append(line)
                continue

            # 检测是否包含公式特征
            has_formula = False
            for indicator in formula_indicators:
                if indicator in stripped:
                    # 进一步验证：包含等号或希腊字母的行
                    if '=' in stripped or any(c in stripped for c in 'αβγδεθλμσπ∑∏∫'):
                        has_formula = True
                        break

            # 如果检测到公式特征，添加前缀
            if has_formula and len(stripped) > 3:  # 避免处理过短的行
                # 保持原有缩进
                indent = len(line) - len(line.lstrip())
                optimized_lines.append(' ' * indent + f"公式：{stripped}")
            else:
                optimized_lines.append(line)

        return '\n'.join(optimized_lines)

    @staticmethod
    def _optimize_image_placeholders(text: str) -> str:
        """优化图片占位符

        将技术性的占位符转换为更自然的表达。

        Examples:
            "[图像 1 OCR 内容]:" → "[图片 1 内容]："
            "Image 1 Text:" → "[图片 1 内容]："

        Args:
            text: 原始文本

        Returns:
            优化后的文本
        """
        # 模式1: [图像 N OCR 内容]:
        text = re.sub(r'\[图像\s+(\d+)\s+OCR\s+内容\]\s*[:：]', r'[图片 \1 内容]：', text)

        # 模式2: Image N Text:
        text = re.sub(r'Image\s+(\d+)\s+Text\s*:', r'[图片 \1 内容]：', text, flags=re.IGNORECASE)

        # 模式3: [Image N]:
        text = re.sub(r'\[Image\s+(\d+)\]\s*[:：]?', r'[图片 \1]：', text, flags=re.IGNORECASE)

        return text

    @staticmethod
    def _optimize_punctuation(text: str) -> str:
        """分句优化：补充基本标点符号

        为缺少标点的句子添加基本标点，提高可读性。

        Args:
            text: 原始文本

        Returns:
            优化后的文本

        Note:
            - 只处理明显缺少标点的情况
            - 避免过度干预，保持原文结构
            - 主要针对 PPTX 中常见的短句
        """
        lines = text.split('\n')
        optimized_lines = []

        for line in lines:
            stripped = line.strip()

            # 跳过空行、Markdown 标题、列表
            if not stripped or stripped.startswith('#') or stripped.startswith('-') or stripped.startswith('*'):
                optimized_lines.append(line)
                continue

            # 跳过已经有标点的行
            if stripped[-1] in '。！？；，、：）】」':
                optimized_lines.append(line)
                continue

            # 跳过英文标点结尾
            if stripped[-1] in '.!?;:)]}':
                optimized_lines.append(line)
                continue

            # 跳过表格行（包含多个 |）
            if stripped.count('|') >= 2:
                optimized_lines.append(line)
                continue

            # 跳过公式行
            if '=' in stripped or '公式：' in stripped:
                optimized_lines.append(line)
                continue

            # 对于中文内容，长度 > 5 的句子补充句号
            if any('\u4e00' <= c <= '\u9fa5' for c in stripped):
                if len(stripped) > 5:
                    # 保持原有缩进
                    indent = len(line) - len(line.lstrip())
                    optimized_lines.append(' ' * indent + stripped + '。')
                else:
                    optimized_lines.append(line)
            else:
                # 英文内容，长度 > 10 的句子补充句号
                if len(stripped) > 10:
                    indent = len(line) - len(line.lstrip())
                    optimized_lines.append(' ' * indent + stripped + '.')
                else:
                    optimized_lines.append(line)

        return '\n'.join(optimized_lines)
