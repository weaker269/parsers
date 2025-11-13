#!/bin/bash
# Parser gRPC 服务停止脚本
# 优雅关闭服务，确保清理所有子进程

set -e  # 遇到错误立即退出

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 配置文件路径
PID_FILE="${PROJECT_ROOT}/logs/server.pid"
LOG_FILE="${PROJECT_ROOT}/logs/run.out"

echo -e "${YELLOW}🛑 停止 Parser gRPC 服务...${NC}"

# 检查 PID 文件是否存在
if [ ! -f "${PID_FILE}" ]; then
    echo -e "${YELLOW}⚠️  服务未运行（未找到 PID 文件）${NC}"
    exit 0
fi

# 读取 PID
PID=$(cat "${PID_FILE}")

# 检查进程是否存在
if ! ps -p "${PID}" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  进程 ${PID} 不存在，清理残留文件...${NC}"
    rm -f "${PID_FILE}"
    exit 0
fi

echo -e "${GREEN}📋 服务信息:${NC}"
echo "   PID: ${PID}"
echo "   日志: ${LOG_FILE}"

# 获取进程组 ID（包括所有子进程）
PGID=$(ps -o pgid= -p "${PID}" | tr -d ' ')

echo -e "${YELLOW}🔧 发送 SIGTERM 信号（优雅关闭）...${NC}"

# 发送 SIGTERM 到整个进程组
if [ -n "${PGID}" ]; then
    kill -TERM -"${PGID}" 2>/dev/null || kill -TERM "${PID}" 2>/dev/null || true
else
    kill -TERM "${PID}" 2>/dev/null || true
fi

# 等待进程结束（最多 30 秒）
echo -e "${YELLOW}⏳ 等待服务关闭...${NC}"
WAIT_TIME=0
MAX_WAIT=30

while ps -p "${PID}" > /dev/null 2>&1; do
    sleep 1
    WAIT_TIME=$((WAIT_TIME + 1))

    # 每 5 秒显示进度
    if [ $((WAIT_TIME % 5)) -eq 0 ]; then
        echo -e "   已等待 ${WAIT_TIME}秒..."
    fi

    # 超时检查
    if [ "${WAIT_TIME}" -ge "${MAX_WAIT}" ]; then
        echo -e "${RED}⚠️  优雅关闭超时，强制终止进程...${NC}"

        # 强制终止整个进程组
        if [ -n "${PGID}" ]; then
            kill -KILL -"${PGID}" 2>/dev/null || kill -KILL "${PID}" 2>/dev/null || true
        else
            kill -KILL "${PID}" 2>/dev/null || true
        fi

        sleep 2
        break
    fi
done

# 确保所有子进程都被清理
if [ -n "${PGID}" ]; then
    # 查找并清理残留的子进程
    CHILD_PIDS=$(pgrep -g "${PGID}" 2>/dev/null || true)
    if [ -n "${CHILD_PIDS}" ]; then
        echo -e "${YELLOW}🧹 清理残留子进程...${NC}"
        echo "${CHILD_PIDS}" | xargs kill -KILL 2>/dev/null || true
        sleep 1
    fi
fi

# 最终验证
if ps -p "${PID}" > /dev/null 2>&1; then
    echo -e "${RED}❌ 进程 ${PID} 仍在运行，无法停止${NC}"
    echo -e "   请手动检查: ps -p ${PID}"
    exit 1
fi

# 清理 PID 文件
rm -f "${PID_FILE}"

echo -e "${GREEN}✅ 服务已成功停止${NC}"

# 显示最后几行日志
if [ -f "${LOG_FILE}" ]; then
    echo ""
    echo -e "${GREEN}📄 最后日志:${NC}"
    tail -n 5 "${LOG_FILE}" || true
fi
