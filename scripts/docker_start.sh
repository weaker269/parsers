#!/bin/bash
# Docker Compose 启动脚本
#
# 功能：启动 Parser gRPC 服务和 FastAPI 应用
# 用法：
#   ./scripts/docker_start.sh                 # 启动标准配置（1个 Parser 副本）
#   ./scripts/docker_start.sh --scale 3      # 启动 3 个 Parser 副本

set -e  # 遇到错误立即退出

# 解析命令行参数
SCALE=1
while [[ $# -gt 0 ]]; do
    case $1 in
        --scale)
            SCALE="$2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: $0 [--scale N]"
            exit 1
            ;;
    esac
done

echo "========================================="
echo "🚀 启动 Parser gRPC 微服务"
echo "========================================="

# 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "⚠️  警告: .env 文件不存在"
    echo "📝 请复制 .env.docker 为 .env 并填写实际配置："
    echo "   cp .env.docker .env"
    echo "   vi .env  # 编辑配置"
    echo ""
    read -p "是否使用 .env.docker 作为默认配置？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.docker .env
        echo "✅ 已复制 .env.docker 为 .env"
        echo "⚠️  请确保 QWEN_API_KEY 已正确配置！"
    else
        echo "❌ 启动中止"
        exit 1
    fi
fi

# 检查 QWEN_API_KEY 是否配置
if ! grep -q "QWEN_API_KEY=sk-" .env 2>/dev/null; then
    echo "⚠️  警告: QWEN_API_KEY 可能未正确配置"
    echo "📝 请编辑 .env 文件并设置有效的 API Key"
fi

echo ""
echo "📦 构建并启动服务（Parser 副本数: $SCALE）..."
echo ""

# 启动服务（带构建）
if [ "$SCALE" -gt 1 ]; then
    docker-compose up -d --build --scale parser-service=$SCALE
else
    docker-compose up -d --build
fi

echo ""
echo "⏳ 等待服务启动（健康检查中）..."
echo "   - Parser 服务需要加载 OCR 模型（约 30-60 秒）"
echo "   - FastAPI 应用等待 Parser 服务健康后启动"
echo ""

# 等待服务健康（最多 120 秒）
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # 检查所有服务是否都在运行
    if docker-compose ps | grep -q "Up (healthy)"; then
        echo ""
        echo "✅ 服务启动成功！"
        break
    fi

    echo -n "."
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo ""
    echo "⚠️  警告: 服务启动超时"
    echo "请检查服务状态："
    docker-compose ps
    exit 1
fi

echo ""
echo "========================================="
echo "🔍 服务状态"
echo "========================================="
docker-compose ps

echo ""
echo "========================================="
echo "🎉 服务启动完成！"
echo "========================================="
echo ""
echo "📍 服务访问地址："
echo "   - Parser gRPC:  localhost:50051"
echo "   - FastAPI:      http://localhost:19998"
echo "   - API 文档:     http://localhost:19998/docs"
echo "   - ReDoc:        http://localhost:19998/redoc"
echo ""
echo "📊 查看日志："
echo "   docker-compose logs -f                # 所有服务日志"
echo "   docker-compose logs -f parser-service # Parser 服务日志"
echo "   docker-compose logs -f fastapi        # FastAPI 应用日志"
echo ""
echo "🛑 停止服务："
echo "   docker-compose down                   # 停止并删除容器"
echo "   docker-compose stop                   # 仅停止容器"
echo ""
echo "🔄 扩展 Parser 副本："
echo "   docker-compose up -d --scale parser-service=3"
echo ""
echo "========================================="
