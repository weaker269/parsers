# Parsers gRPC 微服务

**高性能文档解析 gRPC 服务** - 支持 PDF、DOCX、PPTX、Markdown 格式，内置 OCR 文字识别和双层并发优化。

## ✨ 核心特性

- ✅ **多格式支持**：PDF、DOCX、PPTX、Markdown
- ✅ **表格转 Markdown**：统一转换为 LLM 友好格式
- ✅ **OCR 文字识别**：基于 PaddleOCR PP-OCRv4（准确率 >90%）
- ✅ **双层并发优化**：页面级 + OCR 级并发，性能提升 6-15x
- ✅ **gRPC 微服务**：跨语言支持，资源集中管理
- ✅ **容器化部署**：Docker Compose 一键启动

## 🚀 快速开始

### 1. 环境要求

- **Python**: 3.11+
- **内存**: 最低 2GB（推荐 4GB）
- **CPU**: 支持 AVX 指令集（可选，性能优化）
- **存储**: ~500MB（OCR 模型）

### 2. 本地开发模式

```bash
# 克隆或移动项目
cd /path/to/parsers

# 创建虚拟环境
uv venv

# 安装依赖
uv sync

# 生成 gRPC 代码
chmod +x scripts/generate_proto.sh
./scripts/generate_proto.sh

# 启动 gRPC 服务
chmod +x scripts/start_grpc_server.sh
./scripts/start_grpc_server.sh

# 验证服务运行
# 日志应该显示："🚀 Parser gRPC 服务已启动，端口: 50051"
```

### 3. Docker 部署模式

```bash
# 单副本启动
docker-compose up -d

# 多副本启动（负载均衡）
docker-compose up -d --scale parser-service=3

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f parser-service

# 停止服务
docker-compose down
```

### 4. 测试服务

```bash
# 使用 Python 客户端测试
uv run python -c "
from grpc.client import ParserGrpcClient

with ParserGrpcClient() as client:
    # 健康检查
    is_healthy = client.health_check()
    print(f'健康状态: {\"正常\" if is_healthy else \"异常\"}')

    # 解析文件（客户端读取本地文件并上传二进制内容）
    result = client.parse_file('/path/to/test.pdf')
    print(f'解析成功：{len(result[\"content\"])} 字符')
    print(f'页数：{result[\"metadata\"][\"page_count\"]}')
"
```

## 📖 使用示例

### Python 客户端

```python
from grpc.client import ParserGrpcClient

# 方法 1：上下文管理器（推荐）
# 客户端会自动读取本地文件并上传二进制内容
with ParserGrpcClient(host="localhost", port=50051) as client:
    result = client.parse_file("/path/to/research_paper.pdf")
    content = result["content"]
    metadata = result["metadata"]

# 方法 2：手动管理连接
client = ParserGrpcClient()
client.connect()
result = client.parse_file("/path/to/document.docx")
client.close()
```

### Go 客户端（示例）

```go
// TODO: 提供 Go 客户端示例
```

### Java 客户端（示例）

```java
// TODO: 提供 Java 客户端示例
```

## 🔧 配置说明

### 环境变量配置

复制 `.env.example` 为 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

**主要配置项**：

```bash
# OCR 配置
OCR_LANGUAGE=ch                    # OCR 语言（ch/en）
OCR_MAX_IMAGE_SIZE=4096            # 图像最大尺寸（像素）

# 并发配置
PAGE_POOL_MAX_WORKERS=4            # 页面级进程池大小
OCR_POOL_MAX_WORKERS=4             # OCR 级进程池大小

# gRPC 配置
GRPC_PORT=50051                    # gRPC 服务端口
GRPC_MAX_WORKERS=10                # gRPC 服务线程池大小
```

### Docker Compose 扩容

```bash
# 启动 3 个副本（自动负载均衡）
docker-compose up -d --scale parser-service=3

# 查看副本状态
docker-compose ps
```

## 📊 性能基准

**测试场景**：50 页 PPTX，每页 2 张图像（共 100 张图像）

| 模式 | 页面解析 | OCR 识别 | 总耗时 | 性能提升 |
|-----|---------|---------|--------|---------|
| 串行（单进程） | 90s | 90s | 180s | 1x（基准） |
| 单层并发（仅页面级） | 20s | 90s | 110s | 1.6x |
| **双层并发（页面 + OCR）** | **12s** | **10s** | **22s** | **8.2x** |

**资源占用**：
- 内存：~2.5GB（4 OCR 进程 + 页面进程池 + 主进程）
- CPU：自动适配核心数（推荐 2-4 核心）

## 🛠️ 开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_parsers.py

# 运行双层并发性能测试
uv run pytest tests/test_page_level_concurrency.py -v

# 生成覆盖率报告
uv run pytest --cov=. --cov-report=term-missing
```

### Proto 代码生成

```bash
# 修改 grpc/protos/parser.proto 后重新生成代码
./scripts/generate_proto.sh

# 验证生成的代码
ls -lh grpc/generated/
```

### 日志查看

```bash
# 实时查看日志
tail -f logs/parser_service.log

# 查看最近 50 行日志
tail -n 50 logs/parser_service.log

# 过滤 OCR 相关日志
grep "OCR" logs/parser_service.log
```

## 🐛 故障排查

### OCR 引擎初始化失败

**症状**：启动时卡住，日志显示"加载 OCR 模型..."

**解决**：
```bash
# 手动下载模型
python -c "from ocr_engine import get_ocr_engine; get_ocr_engine()"

# 检查模型目录
ls ~/.paddleocr/
```

### gRPC 服务无法启动

**症状**：端口 50051 被占用

**解决**：
```bash
# 查找占用端口的进程
lsof -i :50051

# 杀死进程
kill -9 <PID>

# 或者修改端口
export GRPC_PORT=50052
./scripts/start_grpc_server.sh
```

### Docker 容器健康检查失败

**症状**：`docker-compose ps` 显示 unhealthy

**解决**：
```bash
# 查看容器日志
docker-compose logs parser-service

# 手动执行健康检查
docker exec <container_id> ./scripts/grpc_health_check.sh
```

更多故障排查请参考 [CLAUDE.md](./CLAUDE.md#故障排查)。

## 📚 架构文档

详细的架构说明、开发指南、性能优化建议，请参考：

- **[CLAUDE.md](./CLAUDE.md)** - 完整的项目文档（用于 Claude Code）
- **[PLAN.md](./PLAN.md)** - 开发计划和进度跟踪

## 🤝 贡献指南

### 提交代码前

```bash
# 运行所有测试
uv run pytest

# 检查代码覆盖率
uv run pytest --cov=. --cov-report=html
open htmlcov/index.html
```

### 提交信息规范

```
feat: 新增 VLM Caption 集成
fix: 修复 PPTX 双层并发死锁问题
docs: 更新 README 文档
perf: 优化 OCR 并发性能（8.2x 提升）
test: 添加双层并发性能测试
chore: 更新依赖版本
```

## 📄 许可证

MIT License

---

**维护者**: 待填写
**项目主页**: 待填写
**最后更新**: 2025-01-11
