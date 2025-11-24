FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 安装系统依赖（PaddleOCR 需要）
RUN apt-get update && apt-get install -y \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录（直接在 parsers 目录内运行）
WORKDIR /app/parsers

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 复制依赖文件和构建所需元数据
COPY pyproject.toml README.md ./
# 如果存在 uv.lock，也复制它
COPY uv.lock* ./

# 安装依赖（使用 frozen 模式确保版本一致，不安装开发依赖）
RUN uv sync --frozen --no-dev || uv sync --no-dev

# 复制项目代码（parsers 项目所有文件）
COPY . /app/parsers/

# 生成 gRPC 代码
RUN chmod +x ./scripts/generate_proto.sh && ./scripts/generate_proto.sh

# 预下载 OCR 模型（减少首次启动时间）
# 这会触发 PaddleOCR 模型下载到 ~/.paddleocr/ 目录
RUN uv run python -c "from ocr_engine import get_ocr_engine; get_ocr_engine()" || echo "OCR 模型预加载失败，将在首次运行时下载"

# 暴露端口
EXPOSE 50051

# 启动 gRPC 服务（在 parsers/ 目录内使用 -m 模式）
CMD ["uv", "run", "python", "-m", "parsers.grpc_service.server"]
