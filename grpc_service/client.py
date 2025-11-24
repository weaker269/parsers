"""gRPC Parser 客户端封装

提供统一的 gRPC 客户端接口，支持：
- 连接管理和复用
- 自动重试机制
- 健康检查
- 上下文管理器（with 语句）

"""

import grpc
import logging
import time
import os
from typing import Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录的 .env（兼容直接运行脚本的场景）
ROOT_DIR = Path(__file__).resolve().parents[1]
PARENT_DIR = ROOT_DIR.parent

# 添加父目录到 sys.path，确保可以导入 parsers 包
import sys
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

load_dotenv(ROOT_DIR / ".env", override=False)

from parsers.grpc_service.generated import parser_pb2, parser_pb2_grpc

logger = logging.getLogger(__name__)


class ParserGrpcClient:
    """Parser gRPC 客户端封装

    提供文件解析的 gRPC 调用接口，支持连接复用和自动重试。

    使用示例：
        # 方式 1：手动管理连接
        client = ParserGrpcClient(host="localhost", port=50051)
        client.connect()
        result = client.parse_bytes(content, filename)
        client.close()

        # 方式 2：上下文管理器（推荐）
        with ParserGrpcClient() as client:
            result = client.parse_bytes(content, filename)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        """初始化 gRPC 客户端

        Args:
            host: gRPC 服务器地址，默认 localhost
            port: gRPC 服务器端口，默认 50051
            timeout: 请求超时时间（秒），默认 300 秒
            max_retries: 最大重试次数，默认 3 次
        """
        self.address = f"{host}:{port}"
        self.timeout = timeout
        self.max_retries = max_retries
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[parser_pb2_grpc.ParserServiceStub] = None

    def connect(self):
        """建立 gRPC 连接

        创建 gRPC 通道和存根，配置最大消息大小为 50MB。
        """
        if self._channel is None:
            self._channel = grpc.insecure_channel(
                self.address,
                options=[
                    ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
                    ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB
                ]
            )
            self._stub = parser_pb2_grpc.ParserServiceStub(self._channel)
            logger.info(f"已连接到 Parser gRPC 服务: {self.address}")

    def close(self):
        """关闭 gRPC 连接"""
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("已断开 Parser gRPC 服务连接")

    def parse_bytes(
        self,
        file_content: bytes,
        file_name: str,
        enable_ocr: bool = True,
        enable_caption: bool = False,
        max_image_size: int = 4096,
        language: str = "ch",
    ) -> Dict[str, Any]:
        """解析二进制文件内容（用于已上传的文件）

        Args:
            file_content: 文件二进制内容
            file_name: 文件名（用于格式检测，如 "report.pdf"）
            enable_ocr: 是否启用 OCR，默认 True
            enable_caption: 是否启用 VLM Caption，默认 False
            max_image_size: 最大图像尺寸（px），默认 4096
            language: OCR 语言，默认 "ch"（中文）

        Returns:
            Dict[str, Any]: 解析结果，包含：
                - content: 解析后的文本内容
                - metadata: 元数据（页数、图像数、表格数、耗时等）

        Raises:
            RuntimeError: 解析失败或服务端返回错误
            grpc.RpcError: gRPC 调用失败（重试后仍失败）
        """
        self.connect()

        logger.info(f"解析文件内容: {file_name}, 大小: {len(file_content)} bytes")

        # 构造请求
        request = parser_pb2.ParseRequest(
            file_content=file_content,
            file_name=file_name,
            options=parser_pb2.ParseOptions(
                enable_ocr=enable_ocr,
                enable_caption=enable_caption,
                max_image_size=max_image_size,
                language=language,
            )
        )

        # 执行 RPC 调用（带重试）
        for attempt in range(self.max_retries):
            try:
                logger.info(f"调用 gRPC 解析 (尝试 {attempt + 1}/{self.max_retries}): {file_name}")

                response = self._stub.ParseFile(
                    request,
                    timeout=self.timeout
                )

                # 检查错误
                if response.error_message:
                    raise RuntimeError(response.error_message)

                # 返回结果
                logger.info(
                    f"解析成功: {file_name}, "
                    f"耗时 {response.metadata.parse_time_ms:.2f}ms, "
                    f"页数 {response.metadata.page_count}"
                )

                return {
                    "content": response.content,
                    "metadata": {
                        "page_count": response.metadata.page_count,
                        "image_count": response.metadata.image_count,
                        "table_count": response.metadata.table_count,
                        "ocr_count": response.metadata.ocr_count,
                        "caption_count": response.metadata.caption_count,
                        "parse_time_ms": response.metadata.parse_time_ms,
                    }
                }

            except grpc.RpcError as e:
                logger.warning(
                    f"gRPC 调用失败 (尝试 {attempt + 1}/{self.max_retries}): "
                    f"{e.code()}: {e.details()}"
                )

                # 最后一次尝试失败，抛出异常
                if attempt == self.max_retries - 1:
                    raise

                # 重试前等待（指数退避）
                wait_time = 1 * (attempt + 1)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

    def health_check(self) -> bool:
        """健康检查

        Returns:
            bool: 服务是否健康（True: SERVING, False: 其他状态或连接失败）
        """
        try:
            self.connect()
            request = parser_pb2.HealthCheckRequest(service="parser.ParserService")
            response = self._stub.HealthCheck(request, timeout=5.0)

            is_healthy = response.status == parser_pb2.HealthCheckResponse.SERVING

            if is_healthy:
                logger.debug("健康检查成功: SERVING")
            else:
                logger.warning(f"健康检查失败: {response.status}")

            return is_healthy

        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

    def __enter__(self):
        """上下文管理器：进入"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：退出"""
        self.close()


# 全局连接池（单例模式）
_client_pool: Optional[ParserGrpcClient] = None


def get_grpc_client() -> ParserGrpcClient:
    """获取全局 gRPC 客户端实例（单例模式）

    从环境变量读取配置：
    - PARSER_GRPC_HOST: 服务器地址，默认 localhost
    - PARSER_GRPC_PORT: 服务器端口，默认 50051
    - PARSER_GRPC_TIMEOUT: 请求超时（秒），默认 300
    - PARSER_GRPC_MAX_RETRIES: 最大重试次数，默认 3

    Returns:
        ParserGrpcClient: 全局客户端实例

    注意：
        - 单例模式：多次调用返回同一实例
        - 自动连接复用，无需手动 connect/close
        - 适用于 FastAPI 等长期运行的应用
    """
    global _client_pool

    if _client_pool is None:
        host = os.getenv("PARSER_GRPC_HOST", "localhost")
        port = int(os.getenv("PARSER_GRPC_PORT", "50051"))
        timeout = float(os.getenv("PARSER_GRPC_TIMEOUT", "300.0"))
        max_retries = int(os.getenv("PARSER_GRPC_MAX_RETRIES", "3"))

        _client_pool = ParserGrpcClient(
            host=host,
            port=port,
            timeout=timeout,
            max_retries=max_retries
        )

        logger.info(
            f"创建全局 gRPC 客户端: {host}:{port}, "
            f"超时 {timeout}s, 重试 {max_retries} 次"
        )

    return _client_pool
