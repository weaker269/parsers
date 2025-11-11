#!/usr/bin/env python
"""测试 gRPC 服务端启动和健康检查

这是一个简单的测试脚本，用于验证：
1. gRPC 服务端能够正常启动
2. 健康检查接口正常工作
"""

import sys
import time
import grpc
from parsers.grpc.generated import parser_pb2, parser_pb2_grpc


def test_health_check(host='localhost', port=50051, timeout=5.0):
    """测试健康检查接口

    Args:
        host: 服务器地址
        port: 服务器端口
        timeout: 超时时间（秒）

    Returns:
        bool: 健康检查是否成功
    """
    try:
        print(f"正在连接到 {host}:{port}...")
        channel = grpc.insecure_channel(f'{host}:{port}')

        # 等待通道就绪
        grpc.channel_ready_future(channel).result(timeout=timeout)

        # 创建 stub
        stub = parser_pb2_grpc.ParserServiceStub(channel)

        # 调用健康检查
        print("发送健康检查请求...")
        request = parser_pb2.HealthCheckRequest(service="parser.ParserService")
        response = stub.HealthCheck(request, timeout=timeout)

        # 检查响应
        if response.status == parser_pb2.HealthCheckResponse.SERVING:
            print("✅ 健康检查成功！服务状态: SERVING")
            return True
        else:
            print(f"❌ 健康检查失败！服务状态: {response.status}")
            return False

    except grpc.RpcError as e:
        print(f"❌ gRPC 调用失败: {e.code()}: {e.details()}")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    finally:
        try:
            channel.close()
        except:
            pass


if __name__ == '__main__':
    print("=" * 60)
    print("gRPC 服务端健康检查测试")
    print("=" * 60)

    # 等待服务启动
    print("\n等待服务启动（3 秒）...")
    time.sleep(3)

    # 执行健康检查
    success = test_health_check()

    # 返回退出码
    sys.exit(0 if success else 1)
