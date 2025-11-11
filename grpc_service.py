"""gRPC 解析器服务实现

通过 gRPC 客户端调用远程解析服务，支持自动降级到本地解析。

降级策略：
- gRPC 调用失败时，自动回退到本地解析
- 降级触发条件：连接失败、超时、服务不可用
- 降级日志：记录降级原因，便于监控和排查
"""

import logging
from typing import Dict, Any

from parsers.service_interface import ParserServiceInterface
from parsers.grpc.client import get_grpc_client
from parsers.local_service import LocalParserService

logger = logging.getLogger(__name__)


class GrpcParserService(ParserServiceInterface):
    """gRPC 解析器服务实现

    通过 gRPC 客户端调用远程 Parser 服务，支持自动降级。

    优势：
    - 统一部署：所有项目共享一个 Parser 服务
    - 内存节省：OCR 模型只加载一次（节省 70-80% 内存）
    - 版本管理：升级 Parser 服务，所有项目自动受益
    - 跨语言支持：Python/Go/Java/Node.js 项目均可调用

    降级策略：
    - gRPC 调用失败时，自动回退到本地解析
    - 确保服务高可用（gRPC 服务宕机不影响业务）
    """

    def __init__(self, enable_fallback: bool = True):
        """初始化 gRPC 解析器服务

        Args:
            enable_fallback: 是否启用降级策略，默认 True
        """
        self.enable_fallback = enable_fallback
        self._fallback_service = LocalParserService() if enable_fallback else None

    def parse_file(self, file_path: str, **options) -> Dict[str, Any]:
        """解析文件（gRPC 调用）

        Args:
            file_path: 文件路径（绝对路径）
            **options: 解析选项（enable_ocr, enable_caption 等）

        Returns:
            Dict[str, Any]: 解析结果，包含：
                - content: 解析后的文本内容
                - metadata: 元数据（页数、图像数、表格数、耗时等）

        Raises:
            Exception: gRPC 调用失败且降级策略未启用时抛出
        """
        try:
            # 尝试 gRPC 调用
            logger.info(f"gRPC 解析文件: {file_path}")

            client = get_grpc_client()
            result = client.parse_file(file_path, **options)

            logger.info(
                f"gRPC 解析成功: {file_path}, "
                f"耗时 {result['metadata']['parse_time_ms']:.2f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"gRPC 调用失败: {e}")

            # 降级到本地解析
            if self.enable_fallback and self._fallback_service:
                logger.warning(f"降级到本地解析: {file_path}")

                try:
                    result = self._fallback_service.parse_file(file_path, **options)
                    logger.info(f"降级解析成功: {file_path}")
                    return result

                except Exception as fallback_error:
                    logger.error(f"降级解析失败: {fallback_error}")
                    raise

            else:
                # 降级策略未启用，直接抛出异常
                logger.error("降级策略未启用，无法回退到本地解析")
                raise
