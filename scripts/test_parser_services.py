#!/usr/bin/env python
"""测试解析器服务抽象层

验证本地服务和 gRPC 服务的接口一致性。
"""

import sys
from pathlib import Path

from parsers.service_interface import ParserServiceInterface
from parsers.local_service import LocalParserService
from parsers.grpc_service import GrpcParserService


def test_service_interface():
    """测试服务接口抽象层"""
    print("=" * 60)
    print("测试解析器服务抽象层")
    print("=" * 60)

    # 测试 1：验证接口继承
    print("\n[测试 1] 验证接口继承")
    assert issubclass(LocalParserService, ParserServiceInterface)
    assert issubclass(GrpcParserService, ParserServiceInterface)
    print("✅ LocalParserService 和 GrpcParserService 都实现了 ParserServiceInterface")

    # 测试 2：验证方法签名
    print("\n[测试 2] 验证方法签名")
    local_service = LocalParserService()
    grpc_service = GrpcParserService(enable_fallback=False)

    assert hasattr(local_service, 'parse_file')
    assert hasattr(grpc_service, 'parse_file')
    print("✅ 两个服务都实现了 parse_file() 方法")

    # 测试 3：验证降级策略
    print("\n[测试 3] 验证降级策略")
    grpc_with_fallback = GrpcParserService(enable_fallback=True)
    grpc_without_fallback = GrpcParserService(enable_fallback=False)

    assert grpc_with_fallback.enable_fallback is True
    assert grpc_without_fallback.enable_fallback is False
    assert grpc_with_fallback._fallback_service is not None
    assert grpc_without_fallback._fallback_service is None
    print("✅ 降级策略配置正常")

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_service_interface()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
