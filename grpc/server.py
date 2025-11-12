"""gRPC Parser 服务端实现

基于 WeKnora 项目的微服务架构设计，提供文件解析 gRPC 服务。

核心功能：
- ParseFile: 解析文件并返回文本内容
- HealthCheck: 健康检查（Kubernetes 友好）

性能优化：
- OCR 引擎预加载（避免首次调用延迟）
- 单例进程池（避免重复创建进程）
- 详细的性能监控日志
"""

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    # 直接运行 python grpc/server.py 时补齐项目根目录，避免相对导入失败
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import grpc
from concurrent import futures
import logging
import time
import signal
import uuid
import os
import asyncio
from typing import Optional

from parsers.grpc.generated import parser_pb2, parser_pb2_grpc
from parsers import create_parser
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

logger = logging.getLogger(__name__)


class ParserServiceServicer(parser_pb2_grpc.ParserServiceServicer):
    """解析器 gRPC 服务实现"""

    def ParseFile(self, request, context):
        """解析文件（核心接口）

        Args:
            request: ParseRequest 消息
            context: gRPC 上下文

        Returns:
            ParseResponse: 解析响应，包含内容和元数据
        """
        # 生成请求追踪 ID
        request_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(f"[{request_id}] 收到解析请求: {request.file_name}")

        try:
            # 1. 参数验证
            if not request.file_content:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("file_content 不能为空")
                logger.error(f"[{request_id}] 参数验证失败: file_content 为空")
                return parser_pb2.ParseResponse()

            if not request.file_name:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("file_name 不能为空")
                logger.error(f"[{request_id}] 参数验证失败: file_name 为空")
                return parser_pb2.ParseResponse()

            # 2. 从文件名检测文件格式
            file_format = Path(request.file_name).suffix
            if not file_format:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(f"无法从文件名 {request.file_name} 中识别格式")
                logger.error(f"[{request_id}] 文件格式识别失败: {request.file_name}")
                return parser_pb2.ParseResponse()

            logger.info(f"[{request_id}] 文件: {request.file_name}, 格式: {file_format}, 大小: {len(request.file_content)} bytes")

            # 3. 创建解析器
            try:
                parser = create_parser(file_format)
            except ValueError as e:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(str(e))
                logger.error(f"[{request_id}] 不支持的文件格式: {file_format}")
                return parser_pb2.ParseResponse(error_message=str(e))

            # 4. 配置解析选项
            # TODO: 支持 request.options（OCR、Caption 等）
            # 当前版本：使用默认配置

            # 5. 执行解析
            logger.info(f"[{request_id}] 开始解析文件: {request.file_name}")
            parse_start = time.time()

            # 调用异步 parse 方法
            content = asyncio.run(parser.parse(request.file_content))

            parse_duration = time.time() - parse_start
            logger.info(f"[{request_id}] 解析完成，耗时 {parse_duration*1000:.2f}ms")

            # 6. 构造响应
            total_duration = (time.time() - start_time) * 1000

            metadata = parser_pb2.ParseMetadata(
                page_count=getattr(parser, 'page_count', 0),
                image_count=getattr(parser, 'image_count', 0),
                table_count=getattr(parser, 'table_count', 0),
                ocr_count=getattr(parser, 'ocr_count', 0),
                caption_count=getattr(parser, 'caption_count', 0),
                parse_time_ms=total_duration,
            )

            logger.info(
                f"[{request_id}] 解析完成: {request.file_name}, "
                f"耗时 {total_duration:.2f}ms, "
                f"页数 {metadata.page_count}, "
                f"图像 {metadata.image_count}, "
                f"表格 {metadata.table_count}, "
                f"OCR {metadata.ocr_count}"
            )

            return parser_pb2.ParseResponse(
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"[{request_id}] 解析失败: {request.file_name}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return parser_pb2.ParseResponse(
                error_message=str(e)
            )

    def HealthCheck(self, request, context):
        """健康检查

        Args:
            request: HealthCheckRequest 消息
            context: gRPC 上下文

        Returns:
            HealthCheckResponse: 健康状态
        """
        logger.debug("收到健康检查请求")
        return parser_pb2.HealthCheckResponse(
            status=parser_pb2.HealthCheckResponse.SERVING
        )


def _preload_ocr_engine():
    """通过进程池并行预热 OCR"""
    try:
        from parsers.base import _get_process_pool
        from parsers.ocr_worker import ocr_worker
        from PIL import Image
        import io

        logger.info("预加载 OCR 引擎（进程池模式）...")

        # 构造一张内存里的纯白示例图，触发 OCR 模型加载
        image = Image.new('RGB', (64, 64), color='white')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        dummy_bytes = buffer.getvalue()

        pool = _get_process_pool()  # 创建并预热全局进程池

        futures = [pool.submit(ocr_worker, dummy_bytes) for _ in range(2)]
        for idx, future in enumerate(futures, start=1):
            future.result(timeout=180)
            logger.info(f"✅ OCR 子进程 {idx}/{len(futures)} 预热完成")

        logger.info("🚀 OCR 引擎预热成功，服务已就绪")
    except Exception as e:
        logger.warning(f"OCR 引擎预加载失败（首次请求将触发初始化）: {e}", exc_info=True)


def serve(port: int = 50051, max_workers: int = 10, preload_ocr: bool = True):
    """启动 gRPC 服务器

    Args:
        port: 监听端口，默认 50051
        max_workers: 最大工作线程数，默认 10
        preload_ocr: 是否预加载 OCR 引擎，默认 True
    """
    # 预加载 OCR 引擎（可选）
    if preload_ocr:
        _preload_ocr_engine()

    # 创建 gRPC 服务器
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB
        ]
    )

    # 注册服务
    parser_pb2_grpc.add_ParserServiceServicer_to_server(
        ParserServiceServicer(), server
    )

    # 注册健康检查服务
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(
        "parser.ParserService",
        health_pb2.HealthCheckResponse.SERVING
    )

    # 启动服务器
    server.add_insecure_port(f'[::]:{port}')
    server.start()

    logger.info(f"🚀 Parser gRPC 服务已启动，端口: {port}")
    logger.info(f"   - 最大工作线程数: {max_workers}")
    logger.info(f"   - 最大消息大小: 50MB")
    logger.info(f"   - OCR 引擎预加载: {'已启用' if preload_ocr else '已禁用'}")

    # 优雅关闭处理
    def handle_sigterm(signum, frame):
        logger.info("收到 SIGTERM 信号，正在关闭服务...")
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("收到停止信号（Ctrl+C），正在关闭服务...")
        server.stop(grace=5)


if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(process)d - %(thread)d - %(filename)s:%(lineno)d - %(message)s'
    )

    # 从环境变量读取配置
    port = int(os.getenv('PARSER_GRPC_PORT', '50051'))
    max_workers = int(os.getenv('PARSER_GRPC_MAX_WORKERS', '10'))
    preload_ocr = os.getenv('PARSER_GRPC_PRELOAD_OCR', 'true').lower() == 'true'

    # 启动服务
    serve(port=port, max_workers=max_workers, preload_ocr=preload_ocr)
