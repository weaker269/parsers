#!/bin/bash
# Parser gRPC 服务启动脚本
# 支持从上层目录或本层目录运行

set -e  # 遇到错误立即退出

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PARENT_DIR="$(cd "${PROJECT_ROOT}/.." && pwd)"

# 配置文件路径
PID_FILE="${PROJECT_ROOT}/logs/server.pid"
LOG_FILE="${PROJECT_ROOT}/logs/run.out"
LOCK_FILE="${PROJECT_ROOT}/logs/server.lock"
ENV_FILE="${PROJECT_ROOT}/.env"

# 确保日志目录存在
mkdir -p "${PROJECT_ROOT}/logs"

echo -e "${GREEN}🚀 启动 Parser gRPC 服务...${NC}"

# 检查是否已经运行
if [ -f "${PID_FILE}" ]; then
    PID=$(cat "${PID_FILE}")
    if ps -p "${PID}" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  服务已经运行 (PID: ${PID})${NC}"
        echo -e "   如需重启，请先运行: ./scripts/stop.sh"
        exit 1
    else
        echo -e "${YELLOW}⚠️  发现残留 PID 文件，清理中...${NC}"
        rm -f "${PID_FILE}"
    fi
fi

# 创建锁文件，防止并发启动
if ! mkdir "${LOCK_FILE}" 2>/dev/null; then
    echo -e "${RED}❌ 无法创建锁文件，可能有其他启动进程正在运行${NC}"
    exit 1
fi
trap "rmdir ${LOCK_FILE} 2>/dev/null || true" EXIT

# 读取 .env（如果存在），以便使用用户配置覆盖默认值
if [ -f "${ENV_FILE}" ]; then
    echo -e "${GREEN}📦 加载环境变量: ${ENV_FILE}${NC}"
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

# 环境变量配置
: "${PARSER_GRPC_PORT:=50051}"
: "${PARSER_GRPC_MAX_WORKERS:=10}"
: "${PARSER_GRPC_PRELOAD_OCR:=true}"
: "${PARSER_LOG_DIR:=${PROJECT_ROOT}/logs}"
: "${PARSER_LOG_LEVEL:=INFO}"
export PARSER_GRPC_PORT PARSER_GRPC_MAX_WORKERS PARSER_GRPC_PRELOAD_OCR PARSER_LOG_DIR PARSER_LOG_LEVEL

# 设置 PYTHONPATH 指向父目录，让 Python 可以找到 parsers 包
export PYTHONPATH="${PARENT_DIR}:${PYTHONPATH}"

echo -e "${GREEN}📋 配置信息:${NC}"
echo "   项目根目录: ${PROJECT_ROOT}"
echo "   PYTHONPATH: ${PARENT_DIR}"
echo "   监听端口: ${PARSER_GRPC_PORT}"
echo "   工作线程: ${PARSER_GRPC_MAX_WORKERS}"
echo "   预加载OCR: ${PARSER_GRPC_PRELOAD_OCR}"
echo "   日志文件: ${LOG_FILE}"

# 切换到项目根目录（可以在 parsers/ 目录内工作）
cd "${PROJECT_ROOT}"

# 检查 Python 模块是否可用
if ! uv run python -c "from parsers.grpc_service import server" 2>/dev/null; then
    echo -e "${RED}❌ 无法导入 parsers.grpc_service.server 模块${NC}"
    echo "   请确保已安装依赖: uv sync"
    exit 1
fi

# 后台启动服务（使用 -m 模式，从 parsers/ 目录内启动）
echo -e "${GREEN}🔧 启动服务进程...${NC}"
nohup uv run python -m parsers.grpc_service.server > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!

# 保存 PID
echo "${SERVER_PID}" > "${PID_FILE}"

# 等待服务启动
echo -e "${YELLOW}⏳ 等待服务启动...${NC}"
sleep 2

# 验证进程是否还在运行
if ps -p "${SERVER_PID}" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 服务启动成功!${NC}"
    echo -e "   PID: ${SERVER_PID}"
    echo -e "   端口: ${PARSER_GRPC_PORT}"
    echo -e "   日志: ${LOG_FILE}"
    echo ""
    echo -e "${GREEN}📝 查看日志:${NC}"
    echo "   tail -f ${LOG_FILE}"
    echo ""
    echo -e "${GREEN}🛑 停止服务:${NC}"
    echo "   ./scripts/stop.sh"
    echo ""

    # 显示最后几行日志
    echo -e "${GREEN}📄 最近日志:${NC}"
    tail -n 5 "${LOG_FILE}" || true
else
    echo -e "${RED}❌ 服务启动失败!${NC}"
    echo -e "   请查看日志: ${LOG_FILE}"
    rm -f "${PID_FILE}"
    exit 1
fi
