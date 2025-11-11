"""解析器服务接口（抽象层）

提供统一的解析器服务接口，支持多种实现：
- LocalParserService: 本地解析器服务（直接调用 parsers 模块）
- GrpcParserService: gRPC 解析器服务（通过 gRPC 调用远程服务）

基于依赖倒置原则（DIP），上层模块（FastAPI）依赖抽象接口，
不依赖具体实现，支持运行时配置切换。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class ParserServiceInterface(ABC):
    """解析器服务接口（抽象层）

    定义统一的文件解析接口，具体实现可以是：
    - 本地解析：直接调用 parsers 模块
    - gRPC 调用：通过 gRPC 客户端调用远程服务

    这样设计的好处：
    1. 解耦：上层模块不依赖具体实现
    2. 可测试：可以轻松 mock 服务实现
    3. 灵活切换：通过配置切换本地/gRPC 模式
    4. 降级策略：gRPC 失败时可降级到本地解析
    """

    @abstractmethod
    def parse_file(self, file_path: str, **options) -> Dict[str, Any]:
        """解析文件

        Args:
            file_path: 文件路径（绝对路径）
            **options: 解析选项（enable_ocr, enable_caption 等）

        Returns:
            Dict[str, Any]: 解析结果，包含：
                - content: 解析后的文本内容
                - metadata: 元数据（页数、图像数、表格数、耗时等）

        Raises:
            Exception: 解析失败
        """
        pass
