"""OCR 引擎模块

基于 PaddleOCR 的 OCR 引擎实现，支持 CPU 指令集检测和图像预处理。
采用单例模式确保全局只有一个 OCR 引擎实例。
"""

import logging
import platform
import subprocess
from typing import Optional, Tuple
from io import BytesIO

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class OCREngine:
    """PaddleOCR 引擎封装（单例模式）

    特性：
    1. 单例模式：全局只有一个实例，避免重复加载模型
    2. CPU 指令集检测：自动检测 AVX 支持
    3. 智能配置：根据硬件能力选择最优配置
    4. 图像预处理：自动缩放、格式转换
    """

    _instance: Optional['OCREngine'] = None
    _initialized: bool = False

    # 图像尺寸限制（避免内存溢出）
    MAX_IMAGE_SIZE = 4096  # 最大边长 4096 像素
    MIN_IMAGE_SIZE = 32    # 最小边长 32 像素

    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化 OCR 引擎（只执行一次）"""
        if not OCREngine._initialized:
            self._initialize_engine()
            OCREngine._initialized = True

    def _initialize_engine(self):
        """初始化 PaddleOCR 引擎

        配置优化：
        - PP-OCRv4 server 模型（准确率更高）
        - 根据 CPU 指令集选择最优配置
        - 关闭 GPU（避免依赖 CUDA）
        """
        import os
        logger.info("初始化 OCR 引擎... (进程 PID: %d)", os.getpid())

        # 检测 CPU 指令集支持
        use_avx = self._check_avx_support()
        if not use_avx:
            logger.warning("CPU 不支持 AVX 指令集，OCR 性能可能受限")

        try:
            from paddleocr import PaddleOCR

            # PaddleOCR 配置
            self.ocr = PaddleOCR(
                lang='ch',                                   # 中文识别
                device='cpu',                                # 强制使用 CPU
                enable_mkldnn=use_avx,                       # 有 AVX 时启用 MKL-DNN
                ocr_version='PP-OCRv4',                      # 指定 OCR 版本
                use_textline_orientation=True,               # 启用方向分类功能
                text_detection_model_name='PP-OCRv4_server_det',    # 强制使用 Server 检测模型
                text_recognition_model_name='PP-OCRv4_server_rec',  # 强制使用 Server 识别模型
                textline_orientation_model_name='PP-LCNet_x1_0_textline_ori',  # 方向分类模型
                doc_orientation_classify_model_name='PP-LCNet_x1_0_doc_ori',    # 文档方向分类模型
            )

            logger.info(f"OCR 引擎初始化成功 (进程 PID: {os.getpid()}, AVX: {use_avx}, 模型: PP-OCRv4)")

        except Exception as e:
            logger.error(f"OCR 引擎初始化失败: {e}")
            raise RuntimeError(f"无法初始化 PaddleOCR: {e}")

    def _check_avx_support(self) -> bool:
        """检测 CPU 是否支持 AVX 指令集

        AVX (Advanced Vector Extensions) 是 Intel/AMD 的 SIMD 指令集扩展，
        PaddlePaddle 在支持 AVX 的 CPU 上性能更好。

        Returns:
            bool: True 表示支持 AVX，False 表示不支持
        """
        system = platform.system()

        try:
            if system == "Linux":
                # Linux: 读取 /proc/cpuinfo
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read()
                    return 'avx' in cpuinfo.lower()

            elif system == "Darwin":  # macOS
                # macOS: 使用 sysctl 命令
                result = subprocess.run(
                    ['sysctl', '-a'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return 'avx' in result.stdout.lower()

            elif system == "Windows":
                # Windows: 使用 wmic 命令（如果可用）
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'caption'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # Windows 检测较为简化，默认假设现代 CPU 支持 AVX
                return True

            else:
                logger.warning(f"未知操作系统 {system}，无法检测 AVX 支持")
                return False

        except Exception as e:
            logger.warning(f"AVX 检测失败: {e}")
            return False

    def preprocess_image(self, image_data: bytes) -> np.ndarray:
        """图像预处理

        处理步骤：
        1. 解码图像（支持常见格式：PNG, JPEG, BMP 等）
        2. 转换为 RGB 格式（PaddleOCR 要求）
        3. 自动缩放（避免过大或过小）
        4. 转换为 NumPy 数组

        Args:
            image_data: 图像二进制数据

        Returns:
            np.ndarray: 预处理后的图像数组 (H, W, C)

        Raises:
            ValueError: 图像数据无效或无法解码
        """
        try:
            # 解码图像
            image = Image.open(BytesIO(image_data))

            # 转换为 RGB（如果是 RGBA、灰度图等格式）
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # 自动缩放
            image = self._resize_if_needed(image)

            # 转换为 NumPy 数组
            image_array = np.array(image)

            logger.debug(f"图像预处理完成: shape={image_array.shape}, dtype={image_array.dtype}")
            return image_array

        except Exception as e:
            # 区分格式不支持（降级为WARNING）和真正的错误（保持ERROR）
            error_msg = str(e).lower()
            if "cannot find loader" in error_msg or "cannot identify image" in error_msg:
                logger.warning(f"图像格式不支持或无法识别: {e}")
            else:
                logger.error(f"图像预处理失败: {e}")
            raise ValueError(f"无法处理图像数据: {e}")

    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        """智能缩放图像

        缩放策略：
        - 如果任一边 > MAX_IMAGE_SIZE，等比例缩小
        - 如果任一边 < MIN_IMAGE_SIZE，保持原尺寸（避免过度放大）
        - 保持宽高比

        Args:
            image: PIL Image 对象

        Returns:
            Image.Image: 缩放后的图像
        """
        width, height = image.size

        # 计算缩放比例
        scale = 1.0

        if width > self.MAX_IMAGE_SIZE or height > self.MAX_IMAGE_SIZE:
            # 需要缩小
            scale = min(
                self.MAX_IMAGE_SIZE / width,
                self.MAX_IMAGE_SIZE / height
            )
            logger.debug(f"图像过大 ({width}x{height})，缩小至 {scale:.2f} 倍")

        elif width < self.MIN_IMAGE_SIZE and height < self.MIN_IMAGE_SIZE:
            # 图像太小，保持原尺寸（不放大）
            logger.debug(f"图像较小 ({width}x{height})，保持原尺寸")
            return image

        # 执行缩放
        if scale != 1.0:
            new_width = int(width * scale)
            new_height = int(height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"图像已缩放至 {new_width}x{new_height}")

        return image

    def recognize(self, image_array: np.ndarray) -> str:
        """执行 OCR 识别（基于 PaddleOCR 3.x 新接口）

        Args:
            image_array: 预处理后的图像数组

        Returns:
            str: 识别出的文本内容

        Raises:
            RuntimeError: OCR 识别失败
        """
        try:
            results = self.ocr.predict(image_array)
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            raise RuntimeError(f"OCR 识别错误: {e}")

        if not results:
            logger.warning("OCR 未识别到文本")
            return ""

        extracted_texts: list[str] = []

        for item in results:
            # OCRResult 对象兼容字典访问
            rec_texts = item.get("rec_texts") if hasattr(item, "get") else None
            if rec_texts:
                for text in rec_texts:
                    if isinstance(text, str):
                        cleaned = text.strip()
                        if cleaned:
                            extracted_texts.append(cleaned)
                continue

            text_blocks = item.get("text_blocks") if hasattr(item, "get") else None
            if text_blocks:
                for block in text_blocks:
                    if isinstance(block, dict):
                        content = block.get("text") or block.get("content")
                        if isinstance(content, str):
                            cleaned = content.strip()
                            if cleaned:
                                extracted_texts.append(cleaned)
                    elif isinstance(block, (list, tuple)):
                        for maybe_text in block:
                            if isinstance(maybe_text, str):
                                cleaned = maybe_text.strip()
                                if cleaned:
                                    extracted_texts.append(cleaned)
                continue

            text_words = item.get("text_word") if hasattr(item, "get") else None
            if text_words:
                for words in text_words:
                    if isinstance(words, (list, tuple)):
                        for word in words:
                            if isinstance(word, str):
                                cleaned = word.strip()
                                if cleaned:
                                    extracted_texts.append(cleaned)

        if not extracted_texts:
            logger.warning("OCR 未识别到有效文本内容")
            return ""

        ocr_text = "\n".join(extracted_texts)
        logger.debug(f"OCR 识别成功: {len(extracted_texts)} 条文本")
        return ocr_text


# 全局单例访问函数
_engine_instance: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    """获取全局 OCR 引擎实例（单例）

    Returns:
        OCREngine: OCR 引擎实例

    Example:
        >>> engine = get_ocr_engine()
        >>> image_array = engine.preprocess_image(image_bytes)
        >>> text = engine.recognize(image_array)
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = OCREngine()
    return _engine_instance
