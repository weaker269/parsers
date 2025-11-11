#!/bin/bash
# 启动 gRPC Parser 服务端（开发模式）

echo "🚀 启动 Parser gRPC 服务..."

# 设置环境变量
export PARSER_GRPC_PORT=50051
export PARSER_GRPC_MAX_WORKERS=10
export PARSER_GRPC_PRELOAD_OCR=false  # 开发模式，跳过 OCR 预加载（加快启动）

# 启动服务
uv run python -m grpc.server

echo "✅ gRPC 服务已停止"
