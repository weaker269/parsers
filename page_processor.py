"""
页面级进程池管理器

用于实现 PPTX 和 PDF 的页面级并发处理。
参考 WeKnora 的动态 worker 计算和并行处理逻辑。
"""

import logging
import multiprocessing
import os
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 全局页面级进程池实例（单例模式）
_page_process_pool: Optional[ProcessPoolExecutor] = None


def _get_page_process_pool() -> ProcessPoolExecutor:
    """获取全局页面级进程池实例（单例模式）

    关键配置：
    1. 进程池大小：min(cpu_count() - 2, 32)
       - 保留 2 核给 OCR 进程池
       - 限制最大 32，避免内存过高（每进程约 200-500MB）
       - 32 个 worker 足够高效处理大多数场景
    2. 启动模式：spawn（与 OCR 进程池一致，避免 fork 模式的内存损坏）
    3. 多文件共享：所有文件解析任务排队到同一进程池，避免资源过度分配

    Returns:
        ProcessPoolExecutor: 全局页面级进程池实例

    Note:
        - 单例模式：多次调用返回同一实例
        - 首次调用会创建进程池并预热子进程
        - 多文件并发时共享进程池，自动负载均衡
        - 资源可控：避免多文件同时创建独立进程池导致资源竞争
    """
    global _page_process_pool

    if _page_process_pool is None:
        import os

        # 从环境变量读取进程池配置
        max_workers = int(os.getenv("PARSER_PAGE_POOL_MAX_WORKERS", "0"))

        if max_workers == 0:
            # 自动计算：保留核心数 - 最大上限
            cpu_count = multiprocessing.cpu_count()
            reserved_cores = int(os.getenv("PARSER_PAGE_POOL_RESERVED_CORES", "2"))
            max_limit = int(os.getenv("PARSER_PAGE_POOL_MAX_LIMIT", "32"))
            num_processes = min(cpu_count - reserved_cores, max_limit)
        else:
            # 使用用户指定的值
            num_processes = max_workers
            cpu_count = multiprocessing.cpu_count()

        # 确保至少有 1 个 worker（容错）
        num_processes = max(1, num_processes)

        # 显式获取 spawn 上下文（确保使用 spawn 模式）
        mp_context = multiprocessing.get_context("spawn")

        logger.info(
            f"创建全局页面级进程池（大小: {num_processes}, "
            f"启动模式: spawn, CPU核心: {cpu_count}）"
        )

        # 创建进程池
        _page_process_pool = ProcessPoolExecutor(
            max_workers=num_processes,
            mp_context=mp_context
        )

        logger.info(f"全局页面级进程池创建成功（{num_processes} 个子进程）")

    return _page_process_pool


def _shutdown_page_process_pool():
    """关闭全局页面级进程池（优雅关闭）

    关闭策略：
    1. 等待所有正在执行的任务完成（wait=True）
    2. 取消所有未开始的任务（cancel_futures=False，保留任务）
    3. 关闭后将全局变量重置为 None

    使用场景：
    - 应用关闭时调用（FastAPI shutdown event）
    - 测试完成后清理资源
    - 进程池重启

    Note:
        - 关闭是阻塞操作，会等待所有任务完成
        - 关闭后进程池不可再使用，需要重新创建
        - 与 OCR 进程池独立，互不影响
    """
    global _page_process_pool

    if _page_process_pool is not None:
        logger.info("关闭全局页面级进程池...")

        # 注意：ProcessPoolExecutor.shutdown 在 Python 3.11 不支持 timeout 参数
        # 因此这里采用默认行为，等待任务完成
        _page_process_pool.shutdown(wait=True, cancel_futures=False)
        logger.info("全局页面级进程池已关闭")

        # 重置全局变量
        _page_process_pool = None


@dataclass
class PageData:
    """页面数据结构（通用）"""
    page_num: int  # 页码或 Slide 索引
    content_parts: List[Tuple[str, str, int]]  # [(类型, 内容, 顺序索引)]
    image_paths: List[str]  # 临时图像文件路径列表
    metadata: Optional[Dict[str, Any]] = None  # 额外元数据


class PagePoolManager:
    """页面级进程池管理器

    负责并行处理页面、管理临时文件。
    使用全局进程池单例，避免多文件并发时资源过度分配。
    """

    @staticmethod
    def process_pages_parallel(
        page_indices: List[int],
        worker_func: Callable,
        worker_args: Dict[str, Any]
    ) -> List[PageData]:
        """并行处理多个页面（使用全局进程池）

        【核心变更】使用全局进程池单例，避免多文件并发时资源过度分配。

        修复前问题：
        - 每次调用创建独立进程池
        - 多文件并发时：两个50页文件 → 100 worker > 80 核
        - 导致 CPU 过度订阅、内存压力、调度延迟

        修复后架构：
        - 所有文件共享全局进程池（32 worker）
        - 任务自动排队，负载均衡
        - 资源可控：32 页面进程 + 2 OCR 进程 = 34 进程

        Args:
            page_indices: 页面索引列表
            worker_func: Worker 函数（必须是顶层函数，可 pickle 序列化）
            worker_args: Worker 函数的公共参数（字典）

        Returns:
            按页码排序的 PageData 列表

        Note:
            - 进程池大小在创建时固定（32 worker）
            - 多文件并发时自动排队，无需手动控制并发数
            - 进程池生命周期由应用管理，无需手动清理
        """
        if not page_indices:
            return []

        # 【关键变更】不再动态创建进程池，使用全局单例
        logger.info(
            f"开始并行处理 {len(page_indices)} 个页面，"
            f"使用全局页面级进程池"
        )

        results: List[PageData] = []
        failed_pages: List[int] = []

        # 【关键变更】使用全局进程池，移除 with 语句
        executor = _get_page_process_pool()

        # 提交所有任务
        future_to_page = {
            executor.submit(worker_func, page_idx, **worker_args): page_idx
            for page_idx in page_indices
        }

        # 异步收集结果
        for future in as_completed(future_to_page):
            page_idx = future_to_page[future]
            try:
                page_data = future.result(timeout=300)  # 单页超时 5 分钟
                results.append(page_data)
                logger.debug(f"页面 {page_idx} 处理完成")
            except Exception as e:
                logger.error(
                    f"页面 {page_idx} 处理失败: {e}",
                    exc_info=True
                )
                failed_pages.append(page_idx)

        if failed_pages:
            logger.warning(
                f"共有 {len(failed_pages)} 个页面处理失败: {failed_pages}"
            )

        # 按页码排序
        results.sort(key=lambda x: x.page_num)

        logger.info(
            f"页面并行处理完成: 成功 {len(results)}, 失败 {len(failed_pages)}"
        )

        return results

    @staticmethod
    def cleanup_temp_files(temp_dir: Optional[str] = None) -> None:
        """清理临时文件和目录

        Args:
            temp_dir: 临时目录路径（None 则跳过）
        """
        if not temp_dir:
            return

        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.debug(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {temp_dir}, 错误: {e}")

    @staticmethod
    def create_temp_dir(prefix: str = "page_processor_") -> str:
        """创建临时目录

        Args:
            prefix: 目录名前缀

        Returns:
            临时目录路径
        """
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logger.debug(f"创建临时目录: {temp_dir}")
        return temp_dir
