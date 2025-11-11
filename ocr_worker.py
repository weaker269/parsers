"""OCR Worker 模块

用于多进程并发执行 OCR 识别任务。
采用 spawn 模式启动子进程，避免 fork 模式的线程安全问题。

核心功能：
1. init_ocr_worker(): 子进程初始化器，独立初始化 PaddleOCR 引擎
2. ocr_worker(): 顶层 worker 函数，执行 OCR 识别
3. is_background_image(): 背景图检测，过滤装饰性大图
"""

import logging
import os
from io import BytesIO
from typing import Optional

from PIL import Image

# 设置子进程日志级别（避免重复日志）
logger = logging.getLogger(__name__)


def init_ocr_worker():
    """子进程初始化器（在每个子进程启动时调用）

    关键特性：
    1. 在子进程中独立初始化 PaddleOCR 引擎
    2. spawn 模式下，子进程不会继承父进程的 Paddle 状态（避免内存损坏）
    3. 设置子进程日志级别为 WARNING（减少日志噪音）
    4. 捕获初始化异常并记录

    技术背景：
    - Linux 默认 fork 模式会继承父进程的半初始化状态
    - PaddleOCR C++ 底层在 fork 模式下有线程安全问题
    - spawn 模式创建全新进程，完全独立的内存空间
    """
    # 设置子进程日志级别为 WARNING（减少日志输出）
    logging.basicConfig(level=logging.WARNING)
    logger.setLevel(logging.WARNING)

    try:
        # 导入 OCR 引擎（会触发单例初始化）
        from parsers.ocr_engine import get_ocr_engine

        # 初始化 OCR 引擎（在子进程中独立加载模型）
        engine = get_ocr_engine()
        logger.info(f"子进程 {os.getpid()} OCR 引擎初始化成功")

    except Exception as e:
        logger.error(f"子进程 {os.getpid()} OCR 引擎初始化失败: {e}", exc_info=True)
        # 不抛出异常，让进程池能够正常启动
        # 后续 OCR 调用会失败并返回空字符串


def ocr_worker(image_bytes: bytes) -> str:
    """OCR Worker 函数（必须是模块级函数，用于 pickle 序列化）

    在子进程中执行 OCR 识别任务。

    Args:
        image_bytes: 图像二进制数据

    Returns:
        str: 识别出的文本内容（失败时返回空字符串）

    技术细节：
    1. 必须是顶层函数（pickle 序列化要求）
    2. 不能是类方法或闭包函数
    3. 异常处理：返回空字符串而非抛出异常（避免进程崩溃）
    4. 调用全局单例 OCR 引擎（在 init_ocr_worker 中初始化）

    错误处理策略：
    - 图像预处理失败 → 返回 ""
    - OCR 识别失败 → 返回 ""
    - 未捕获异常 → 返回 ""
    """
    try:
        from parsers.ocr_engine import get_ocr_engine

        # 获取 OCR 引擎实例（子进程中的单例）
        engine = get_ocr_engine()

        # 预处理图像
        image_array = engine.preprocess_image(image_bytes)

        # 执行 OCR 识别
        text = engine.recognize(image_array)

        logger.debug(f"子进程 {os.getpid()} OCR 识别成功: {len(text)} 字符")
        return text

    except ValueError as e:
        # 图像预处理失败（图像数据无效）
        logger.warning(f"子进程 {os.getpid()} 图像预处理失败: {e}")
        return ""

    except RuntimeError as e:
        # OCR 识别失败
        logger.warning(f"子进程 {os.getpid()} OCR 识别失败: {e}")
        return ""

    except Exception as e:
        # 其他未预期异常
        logger.error(f"子进程 {os.getpid()} OCR Worker 异常: {e}", exc_info=True)
        return ""


def is_background_image(
    image_bytes: bytes,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> bool:
    """检测是否为背景图（装饰性大图）

    背景图特征：
    1. 文件大小 > 300KB（高分辨率装饰图）
    2. 尺寸 > 1600x900（全屏或接近全屏）

    过滤背景图的原因：
    - 减少 IPC 数据传输量（序列化 + 反序列化开销）
    - 避免无效 OCR（装饰图通常不包含有用文本）
    - 防止超时（大图 OCR 可能耗时 30-60 秒）

    Args:
        image_bytes: 图像二进制数据
        width: 图像宽度（像素），如果已知可传入
        height: 图像高度（像素），如果已知可传入

    Returns:
        bool: True 表示是背景图（应跳过），False 表示是内容图（应处理）

    过滤策略：
    - 文件大小 > 300KB → 跳过
    - 宽度 > 1600 且 高度 > 900 → 跳过
    - 其他情况 → 处理

    Example:
        >>> # PPTX 场景：1920x1080 的幻灯片背景图
        >>> is_background_image(image_bytes, width=1920, height=1080)
        True
        >>> # PDF 场景：200x100 的小图标
        >>> is_background_image(image_bytes, width=200, height=100)
        False
    """
    try:
        # 检查 1: 文件大小
        size_kb = len(image_bytes) / 1024
        if size_kb > 300:
            logger.debug(f"背景图检测: 文件过大 ({size_kb:.1f}KB > 300KB)")
            return True

        # 检查 2: 图像尺寸（如果已知）
        if width is not None and height is not None:
            if width > 1600 and height > 900:
                logger.debug(f"背景图检测: 尺寸过大 ({width}x{height} > 1600x900)")
                return True
            # 尺寸已知且不是背景图
            return False

        # 检查 3: 尺寸未知，尝试解析图像获取尺寸
        try:
            image = Image.open(BytesIO(image_bytes))
            img_width, img_height = image.size

            if img_width > 1600 and img_height > 900:
                logger.debug(f"背景图检测: 尺寸过大 ({img_width}x{img_height} > 1600x900)")
                return True

        except Exception as e:
            # 图像解析失败，保守策略：不过滤（可能是有效图像）
            logger.warning(f"背景图检测: 无法解析图像尺寸 ({e})，默认不过滤")
            return False

        # 通过所有检查，不是背景图
        return False

    except Exception as e:
        # 检测过程异常，保守策略：不过滤
        logger.error(f"背景图检测异常: {e}", exc_info=True)
        return False
