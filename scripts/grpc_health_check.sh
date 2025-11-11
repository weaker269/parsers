#!/bin/bash
# gRPC 健康检查脚本（用于 Docker healthcheck）
#
# 功能：调用 ParserGrpcClient 的 health_check 方法检查服务健康状态
# 返回值：
#   - 0: 服务健康（SERVING）
#   - 1: 服务不健康或连接失败

uv run python -c "
import sys
from parsers.grpc.client import ParserGrpcClient

try:
    # 创建客户端连接到本地服务
    client = ParserGrpcClient(host='localhost', port=50051)

    # 执行健康检查
    if client.health_check():
        print('✅ Parser gRPC 服务健康：SERVING')
        sys.exit(0)
    else:
        print('❌ Parser gRPC 服务不健康')
        sys.exit(1)

except Exception as e:
    print(f'❌ 健康检查失败: {e}')
    sys.exit(1)
"
