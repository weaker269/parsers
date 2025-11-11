# Parsers 项目独立化迁移指南

本文档说明如何将 `parsers/` 目录从 `generate_quizzes` 项目中分离出来，成为一个完全独立的 gRPC 微服务项目。

## 🎯 迁移目标

将 `/home/wenct/zhengqi/quiz/generate_quizzes/parsers/` 移动到 `/home/wenct/zhengqi/parsers`，使其成为一个自包含的独立项目。

## ✅ 已完成的准备工作

以下文件和配置已经准备就绪，可以直接移动：

### 1. 项目配置文件
- ✅ `pyproject.toml` - 独立的依赖管理
- ✅ `.env.example` - 环境变量模板
- ✅ `.gitignore` - Git 忽略规则

### 2. 文档文件
- ✅ `README.md` - 快速开始指南
- ✅ `CLAUDE.md` - Claude Code 专属文档
- ✅ `PLAN.md` - 开发计划和进度跟踪

### 3. 部署配置
- ✅ `Dockerfile` - Docker 镜像构建（已调整路径）
- ✅ `docker-compose.yml` - 容器编排配置（独立部署）

### 4. 脚本文件
- ✅ `scripts/generate_proto.sh` - Proto 代码生成（已调整路径）
- ✅ `scripts/start_grpc_server.sh` - 启动服务（已调整路径）
- ✅ `scripts/grpc_health_check.sh` - 健康检查
- ✅ `scripts/docker_start.sh` - Docker 启动

### 5. 源代码
- ✅ 所有解析器代码（pdf_parser.py, docx_parser.py, pptx_parser.py, md_parser.py）
- ✅ gRPC 服务实现（grpc/server.py, grpc/client.py）
- ✅ Proto 协议定义（grpc/protos/parser.proto）
- ✅ OCR 引擎和并发优化（ocr_engine.py, ocr_worker.py, page_processor.py）

## 🚀 迁移步骤

### 方法 1：直接移动（推荐）

```bash
# 1. 移动整个 parsers 目录
mv /home/wenct/zhengqi/quiz/generate_quizzes/parsers /home/wenct/zhengqi/parsers

# 2. 进入新目录
cd /home/wenct/zhengqi/parsers

# 3. 初始化 Git 仓库（可选）
git init
git add .
git commit -m "feat: 初始化 Parsers gRPC 微服务项目"

# 4. 创建虚拟环境
uv venv

# 5. 安装依赖
uv sync

# 6. 生成 gRPC 代码
chmod +x scripts/generate_proto.sh
./scripts/generate_proto.sh

# 7. 启动服务测试
chmod +x scripts/start_grpc_server.sh
./scripts/start_grpc_server.sh
```

### 方法 2：复制后清理（保守）

```bash
# 1. 复制 parsers 目录到新位置
cp -r /home/wenct/zhengqi/quiz/generate_quizzes/parsers /home/wenct/zhengqi/parsers

# 2. 清理编译缓存
cd /home/wenct/zhengqi/parsers
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 3. 创建虚拟环境
uv venv

# 4. 安装依赖
uv sync

# 5. 生成 gRPC 代码
./scripts/generate_proto.sh

# 6. 测试服务
./scripts/start_grpc_server.sh
```

## 📋 迁移后检查清单

迁移完成后，请确认以下项目：

### 基础功能测试

```bash
# 1. 进入项目目录
cd /home/wenct/zhengqi/parsers

# 2. 检查虚拟环境
ls .venv
# 应该看到 bin/, lib/, pyvenv.cfg

# 3. 检查依赖安装
uv run python -c "import grpc; print('gRPC 导入成功')"
uv run python -c "from paddleocr import PaddleOCR; print('PaddleOCR 导入成功')"

# 4. 检查 gRPC 代码生成
ls grpc/generated/
# 应该看到：__init__.py, parser_pb2.py, parser_pb2_grpc.py

# 5. 测试模块导入
uv run python -c "from grpc.server import serve; print('gRPC 服务器模块导入成功')"
uv run python -c "from ocr_engine import get_ocr_engine; print('OCR 引擎模块导入成功')"
```

### gRPC 服务测试

```bash
# 1. 启动服务（后台）
./scripts/start_grpc_server.sh &

# 2. 等待服务启动（约 10-15 秒，OCR 模型加载）
sleep 15

# 3. 健康检查
./scripts/grpc_health_check.sh
# 应该输出："健康检查成功"

# 4. 停止服务
pkill -f "grpc.server"
```

### Docker 部署测试

```bash
# 1. 构建镜像
docker build -t parsers-grpc:latest .

# 2. 启动容器
docker-compose up -d

# 3. 检查容器状态
docker-compose ps
# 应该显示 "Up (healthy)"

# 4. 查看日志
docker-compose logs parser-service

# 5. 停止容器
docker-compose down
```

## ⚠️ 注意事项

### 1. 环境变量配置

迁移后需要创建 `.env` 文件：

```bash
cp .env.example .env
# 根据实际情况修改 .env 中的配置
```

### 2. OCR 模型下载

首次运行会自动下载 PaddleOCR 模型（~150MB），需要：
- 稳定的网络连接
- ~/.paddleocr/ 目录有写权限
- 等待 10-15 秒下载和加载

### 3. 依赖版本兼容性

如果遇到依赖冲突，检查 Python 版本：

```bash
python --version
# 应该是 Python 3.11+
```

### 4. 端口占用

默认使用端口 50051，如果被占用：

```bash
# 方法 1：修改环境变量
export GRPC_PORT=50052

# 方法 2：修改 .env 文件
echo "GRPC_PORT=50052" >> .env
```

### 5. 权限问题

确保脚本有执行权限：

```bash
chmod +x scripts/*.sh
```

## 🔗 与原项目的集成

如果原 `generate_quizzes` 项目需要调用 parsers 服务，有两种方式：

### 方式 1：gRPC 客户端调用（推荐）

在 `generate_quizzes` 项目中使用 gRPC 客户端：

```python
# generate_quizzes/parsers/grpc_service.py
from parsers.grpc.client import ParserGrpcClient

class GrpcParserService:
    def parse_file(self, file_path: str, **options):
        client = ParserGrpcClient(host="localhost", port=50051)
        return client.parse_file(file_path, **options)
```

### 方式 2：本地导入（临时方案）

在 `generate_quizzes` 项目中保留 parsers 的本地副本，但定期同步更新。

## 📊 迁移验证

运行完整测试套件验证迁移成功：

```bash
# 1. 单元测试
uv run pytest tests/test_parsers.py -v

# 2. gRPC 服务测试
uv run pytest tests/test_grpc_server.py -v

# 3. 双层并发性能测试
uv run pytest tests/test_page_level_concurrency.py -v

# 4. 覆盖率报告
uv run pytest --cov=. --cov-report=term-missing
```

## 🎉 迁移完成

如果所有检查都通过，恭喜！Parsers 项目已经成功独立化。

现在您可以：
- ✅ 作为独立的 gRPC 微服务部署
- ✅ 被多个项目通过 gRPC 调用
- ✅ 独立维护和版本控制
- ✅ 水平扩展（多副本部署）

## 📞 问题反馈

如果迁移过程中遇到问题，请检查：
1. `logs/parser_service.log` - 服务运行日志
2. `docker-compose logs` - 容器日志
3. `CLAUDE.md` - 完整文档和故障排查

---

**创建日期**：2025-01-11
**最后更新**：2025-01-11
