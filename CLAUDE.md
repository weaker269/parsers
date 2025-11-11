# CLAUDE.md - Parsers gRPC 微服务

这是一个独立的文档解析器 gRPC 微服务项目，为 Claude Code 提供项目指导。

## 项目概述

**Parsers gRPC Service** 是一个高性能的文档解析微服务，将研究报告（PDF、DOCX、PPTX、Markdown）转换为结构化文本。核心特性包括：

- ✅ **多格式支持**：PDF、DOCX、PPTX、Markdown
- ✅ **表格转 Markdown**：统一转换为 LLM 友好的 Markdown 格式
- ✅ **OCR 文字识别**：基于 PaddleOCR PP-OCRv4，支持扫描版文档
- ✅ **双层并发优化**：页面级 + OCR 级并发，性能提升 6-15x
- ✅ **gRPC 微服务化**：跨语言支持，资源集中管理
- ✅ **容器化部署**：Docker Compose 一键启动

## 技术栈

### 核心依赖
- **文档解析**：pdfplumber, python-docx, python-pptx
- **OCR 引擎**：PaddleOCR 2.10.0+, PaddlePaddle 3.0.0+
- **gRPC 框架**：grpcio 1.60.0+, grpcio-tools, grpcio-health-checking
- **并发处理**：multiprocessing (spawn 模式), ProcessPoolExecutor

### 环境要求
- **Python**: 3.11+
- **内存**: 最低 2GB（推荐 4GB）
- **CPU**: 支持 AVX 指令集（可选，性能优化）
- **存储**: ~500MB（OCR 模型）

## 项目结构

```
parsers/                          # 项目根目录（可独立移动）
├── pyproject.toml               # 独立的依赖管理
├── CLAUDE.md                    # 本文档
├── README.md                    # 快速开始指南
├── .gitignore                   # Git 忽略规则
├── .env.example                 # 环境变量模板
├── Dockerfile                   # Docker 镜像构建
├── docker-compose.yml           # 容器编排配置
│
├── scripts/                     # 工具脚本
│   ├── generate_proto.sh        # Proto 代码生成
│   ├── grpc_health_check.sh     # 健康检查
│   ├── start_grpc_server.sh     # 启动服务
│   └── docker_start.sh          # Docker 启动
│
├── grpc/                        # gRPC 服务实现
│   ├── server.py                # gRPC 服务端（主入口）
│   ├── client.py                # gRPC 客户端（测试/集成）
│   ├── protos/                  # Proto 协议定义
│   │   └── parser.proto         # ParserService 定义
│   └── generated/               # 自动生成的代码（不提交）
│       ├── parser_pb2.py        # Protobuf 消息类型
│       └── parser_pb2_grpc.py   # gRPC 服务存根
│
├── 核心模块（解析器）
├── __init__.py                  # 工厂函数 create_parser()
├── base.py                      # BaseParser 抽象基类
├── service_interface.py         # ParserServiceInterface 抽象
├── local_service.py             # 本地解析服务实现
├── grpc_service.py              # gRPC 解析服务实现
│
├── 文档解析器
├── pdf_parser.py                # PDF 解析器（双层并发）
├── docx_parser.py               # DOCX 解析器（图文混排）
├── pptx_parser.py               # PPTX 解析器（双层并发）
├── md_parser.py                 # Markdown 解析器
│
├── 并发优化模块
├── ocr_engine.py                # OCR 引擎（PaddleOCR 单例）
├── ocr_worker.py                # OCR 子进程 worker
├── page_processor.py            # 页面级进程池管理器
└── narrative_optimizer.py       # 叙述性优化器（PPTX 专用）
```

## 核心架构

### 1. 双层并发架构（性能核心）

**设计目标**：突破 PaddleOCR 线程不安全限制，实现真正的并发解析

```
主进程 (gRPC Server)
  ↓
Layer 1: 页面级并发 (ProcessPoolExecutor + spawn 模式)
  ├── 页面解析子进程 1 → 提取文本/表格/图像路径
  ├── 页面解析子进程 2 → 提取文本/表格/图像路径
  └── 页面解析子进程 N → 提取文本/表格/图像路径
  ↓ (图像路径列表)
Layer 2: OCR 级并发 (独立 OCR 子进程池)
  ├── OCR 子进程 1 → 识别图像文字
  ├── OCR 子进程 2 → 识别图像文字
  └── OCR 子进程 M → 识别图像文字
```

**关键技术决策**：
- **Spawn 模式**：`multiprocessing.set_start_method("spawn")` 避免 OpenCV 死锁
- **两层分离**：页面解析（CPU 密集） + OCR 识别（CPU 密集）独立并发
- **IPC 优化**：传递文件路径，不传递 PIL Image 对象（避免大对象序列化）
- **背景图过滤**：自动过滤装饰性背景图（减少 40% IPC 传输）

**性能提升**：
- 单层并发：3-5x（受 OCR 串行限制）
- 双层并发：6-15x（真正的并发瓶颈突破）
- 示例：50 页 PPTX 串行 180s → 双层并发 12-15s

### 2. gRPC 服务架构

**Proto 协议定义** (`grpc/protos/parser.proto`):
```protobuf
service ParserService {
  rpc ParseFile(ParseRequest) returns (ParseResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}

message ParseRequest {
  string file_path = 1;
  string file_format = 2;
  ParseOptions options = 3;
}

message ParseOptions {
  bool enable_ocr = 1;
  bool enable_caption = 2;
  int32 max_image_size = 3;
  string language = 4;
}

message ParseResponse {
  string content = 1;
  ParseMetadata metadata = 2;
  string error_message = 3;
}
```

**服务启动流程**：
1. 预加载 OCR 引擎（单例模式，~500MB 内存）
2. 注册 ParserService 和 HealthService
3. 启动 gRPC 服务器（默认端口 50051）
4. 优雅关闭：等待当前请求完成（5 秒超时）

### 3. 解析器工厂模式

**工厂函数** (`__init__.py:create_parser()`):
```python
def create_parser(file_path: str) -> BaseParser:
    """根据文件扩展名选择解析器"""
    ext = Path(file_path).suffix.lower()
    parsers = {
        ".pdf": PDFParser,
        ".docx": DOCXParser,
        ".pptx": PPTXParser,
        ".md": MarkdownParser,
    }
    return parsers[ext](file_path)
```

**解析器接口** (`base.py:BaseParser`):
- `parse() -> str`: 主解析方法，返回 Markdown 格式文本
- `extract_tables() -> List[str]`: 提取表格（转 Markdown）
- `extract_images() -> List[bytes]`: 提取图像
- `ocr_images() -> List[str]`: OCR 文字识别

## 开发指南

### 快速启动

#### 1. 环境设置
```bash
# 克隆或移动项目
cd /home/wenct/zhengqi/parsers

# 创建虚拟环境
uv venv

# 安装依赖
uv sync

# 首次运行会自动下载 OCR 模型（~150MB）
# 模型存储在 ~/.paddleocr/
```

#### 2. 生成 gRPC 代码
```bash
# 执行 Proto 代码生成
chmod +x scripts/generate_proto.sh
./scripts/generate_proto.sh

# 验证生成的代码
ls -lh grpc/generated/
# 应该看到：parser_pb2.py, parser_pb2_grpc.py
```

#### 3. 启动 gRPC 服务
```bash
# 方法 1：直接启动
uv run python -m grpc.server

# 方法 2：使用脚本
chmod +x scripts/start_grpc_server.sh
./scripts/start_grpc_server.sh

# 方法 3：Docker Compose
docker-compose up --build

# 验证服务运行
# 日志应该显示："🚀 Parser gRPC 服务已启动，端口: 50051"
```

#### 4. 测试 gRPC 服务
```bash
# 使用 Python 客户端测试
uv run python -c "
from grpc.client import ParserGrpcClient

with ParserGrpcClient() as client:
    result = client.parse_file('test.pdf')
    print(f'解析成功：{len(result[\"content\"])} 字符')
"

# 健康检查
uv run python -c "
from grpc.client import ParserGrpcClient
client = ParserGrpcClient()
print('健康状态:', '正常' if client.health_check() else '异常')
"
```

### 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_parsers.py

# 运行双层并发性能测试
uv run pytest tests/test_page_level_concurrency.py -v

# 生成覆盖率报告
uv run pytest --cov=. --cov-report=term-missing

# 过滤 OCR 相关测试
uv run pytest -k "ocr" -v
```

### Docker 部署

```bash
# 构建镜像
docker build -f Dockerfile -t parsers-grpc:latest .

# 运行容器
docker run -d \
  -p 50051:50051 \
  --name parsers-service \
  parsers-grpc:latest

# 查看日志
docker logs -f parsers-service

# 健康检查
docker exec parsers-service ./scripts/grpc_health_check.sh

# 停止服务
docker stop parsers-service
```

### Docker Compose 部署

```bash
# 启动服务（单副本）
docker-compose up -d

# 启动服务（多副本，负载均衡）
docker-compose up -d --scale parser-service=3

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f parser-service

# 停止服务
docker-compose down
```

## 核心功能说明

### 1. 文件格式支持

#### PDF 解析 (`pdf_parser.py`)
- **表格检测**：先检测表格边界 → 提取非表格文本 → 转换表格 → 提取图像 OCR
- **OCR 支持**：扫描版 PDF 自动 OCR 识别
- **双层并发**：页面级 + OCR 级并发（6-15x 性能提升）
- **错误回退**：表格检测失败时自动回退到简化模式

#### DOCX 解析 (`docx_parser.py`)
- **图文混排**：遍历 `document.element.body`，保持段落/表格/图像原始顺序
- **表格转 Markdown**：统一转换为 LLM 友好格式
- **内嵌图像 OCR**：自动识别 Word 文档中的图像文字
- **兼容性**：仅支持 python-docx 1.2.0+（不使用已废弃的 xpath namespaces 参数）

#### PPTX 解析 (`pptx_parser.py`)
- **页面级并发**：并行处理每个幻灯片页面
- **OCR 级并发**：并行识别所有图像文字
- **叙述性优化**：自动优化页面上下文顺序，提升 LLM 理解能力
- **背景图过滤**：自动过滤装饰性背景图（减少 40% IPC 传输）

#### Markdown 解析 (`md_parser.py`)
- **直接解码**：UTF-8 → GB18030 → GBK → latin-1 自动降级
- **无需额外处理**：已经是 LLM 友好格式

### 2. OCR 文字识别

**OCR 引擎** (`ocr_engine.py`):
- **单例模式**：全局只有一个 OCR 引擎实例（节省 ~500MB 内存）
- **模型版本**：PP-OCRv4 server 模型（准确率 >90%）
- **CPU 优化**：自动检测 AVX 指令集，启用 MKL-DNN 加速
- **智能预处理**：自动缩放（最大 4096px）、格式转换
- **过滤策略**：跳过小图像（<5KB 或 <50px），避免处理装饰性图标

**OCR 子进程** (`ocr_worker.py`):
- **独立进程池**：4 个 OCR 子进程（每个 ~500MB 内存）
- **spawn 模式**：避免 OpenCV 死锁（PaddleOCR 依赖 OpenCV）
- **IPC 优化**：传递图像文件路径，不传递 PIL Image 对象
- **错误隔离**：单个图像 OCR 失败不影响整体文档解析

### 3. 表格处理

**表格转 Markdown 策略**：
- **PDF**：pdfplumber 检测表格边界 → 提取单元格 → 转 Markdown
- **DOCX**：python-docx 遍历表格对象 → 读取单元格文本 → 转 Markdown
- **PPTX**：python-pptx 遍历表格对象 → 读取单元格文本 → 转 Markdown
- **原因**：LLM 对 Markdown 表格理解更好，Token 效率更高

**错误处理**：
- 表格检测失败 → 记录 warning，继续处理其他内容
- 单元格合并处理 → 自动展开为多列
- 空单元格处理 → 保留空格占位

## 配置选项

### 环境变量 (`.env`)

```bash
# OCR 配置
PADDLEOCR_SHOW_LOG=False           # 关闭 PaddleOCR 详细日志
OCR_MAX_IMAGE_SIZE=4096            # 图像最大尺寸（像素）
OCR_LANGUAGE=ch                    # OCR 语言（ch/en）

# 并发配置
PAGE_POOL_MAX_WORKERS=4            # 页面级进程池大小（默认 CPU 核心数）
OCR_POOL_MAX_WORKERS=4             # OCR 级进程池大小
OCR_TIMEOUT=300                    # OCR 超时时间（秒）

# gRPC 配置
GRPC_PORT=50051                    # gRPC 服务端口
GRPC_MAX_WORKERS=10                # gRPC 服务线程池大小
GRPC_MAX_MESSAGE_LENGTH=52428800   # 最大消息长度（50MB）

# 日志配置
LOG_LEVEL=INFO                     # 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_FILE=logs/parser_service.log  # 日志文件路径
```

### Docker Compose 配置 (`docker-compose.yml`)

```yaml
services:
  parser-service:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "50051:50051"
    environment:
      - PADDLEOCR_SHOW_LOG=False
      - OCR_LANGUAGE=ch
      - GRPC_PORT=50051
    deploy:
      replicas: 2                   # 多副本部署
      resources:
        limits:
          memory: 1G                # 内存限制
          cpus: '2'                 # CPU 限制
    healthcheck:
      test: ["CMD", "./scripts/grpc_health_check.sh"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s             # OCR 模型加载需要时间
    restart: unless-stopped
```

## 性能优化

### 双层并发性能基准

**测试场景**：50 页 PPTX，每页 2 张图像（共 100 张图像）

| 模式 | 页面解析 | OCR 识别 | 总耗时 | 性能提升 |
|-----|---------|---------|--------|---------|
| 串行（单进程） | 90s | 90s | 180s | 1x（基准） |
| 单层并发（仅页面级） | 20s | 90s | 110s | 1.6x |
| 双层并发（页面 + OCR） | 12s | 10s | 22s | 8.2x |

**资源占用**：
- Layer 1 进程池：CPU 核心数（默认）
- Layer 2 OCR 池：4 个 OCR 子进程（每个 ~500MB 内存）
- 总内存：~2.5GB（4 OCR 进程 + 页面进程池 + 主进程）

### 优化建议

1. **内存优化**：
   - 减少 OCR 进程池大小（`OCR_POOL_MAX_WORKERS=2`）
   - 降低图像最大尺寸（`OCR_MAX_IMAGE_SIZE=2048`）
   - 过滤小图像（默认 <5KB）

2. **CPU 优化**：
   - 确保支持 AVX 指令集（性能提升 2-3x）
   - 调整页面进程池大小（`PAGE_POOL_MAX_WORKERS=CPU核心数`）
   - 使用 Docker CPU 限制（`cpus: '2'`）

3. **网络优化**：
   - 调整 gRPC 最大消息长度（`GRPC_MAX_MESSAGE_LENGTH`）
   - 启用 gRPC 压缩（客户端配置）
   - 使用 gRPC 连接池（客户端复用）

## 故障排查

### OCR 引擎初始化失败

**症状**：启动时卡住，日志显示"加载 OCR 模型..."

**原因**：
- 首次启动需要下载模型（~150MB）
- 网络连接问题导致下载失败

**解决**：
```bash
# 手动下载模型
python -c "from ocr_engine import get_ocr_engine; get_ocr_engine()"

# 检查模型目录
ls ~/.paddleocr/

# 设置代理（如果需要）
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

### 双层并发死锁

**症状**：解析 PPTX 时卡住，无任何输出

**原因**：
- 使用 fork 模式（默认），OpenCV 不支持
- 子进程启动失败（spawn 模式未正确设置）

**解决**：
```python
# 在主进程启动前设置 spawn 模式
import multiprocessing
multiprocessing.set_start_method("spawn", force=True)

# 验证 spawn 模式
print(multiprocessing.get_start_method())  # 应该输出 "spawn"
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
uv run python -m grpc.server
```

### Docker 容器健康检查失败

**症状**：`docker-compose ps` 显示 unhealthy

**解决**：
```bash
# 查看容器日志
docker-compose logs parser-service

# 手动执行健康检查
docker exec parsers-service ./scripts/grpc_health_check.sh

# 检查 OCR 模型是否加载完成
docker exec parsers-service ls ~/.paddleocr/
```

### OCR 识别准确率低

**原因**：
- 图像质量差（分辨率低、模糊）
- 文字倾斜或旋转
- 语言设置错误

**解决**：
```bash
# 调整 OCR 语言
export OCR_LANGUAGE=en  # 英文文档

# 调整图像最大尺寸（保留更多细节）
export OCR_MAX_IMAGE_SIZE=6144

# 检查 CPU 指令集支持
python -c "
import numpy as np
print('AVX 支持:', hasattr(np.core._multiarray_umath, '__cpu_features__'))
"
```

## 性能监控

### 日志分析

```bash
# 查看 OCR 识别统计
grep "OCR 识别完成" logs/parser_service.log | awk '{sum+=$NF} END {print "平均耗时:", sum/NR, "ms"}'

# 查看页面解析统计
grep "页面解析完成" logs/parser_service.log | wc -l

# 查看错误统计
grep "ERROR" logs/parser_service.log | sort | uniq -c
```

### gRPC 性能指标

```python
# 在客户端代码中添加性能监控
import time

start = time.time()
result = client.parse_file("test.pdf")
elapsed = time.time() - start

print(f"解析耗时: {elapsed:.2f}s")
print(f"文档长度: {len(result['content'])} 字符")
print(f"页数: {result['metadata']['page_count']}")
print(f"图像数: {result['metadata']['image_count']}")
print(f"OCR 识别: {result['metadata']['ocr_count']}")
```

## 代码风格注意事项

- **使用中文注释**：符合项目习惯
- **日志优先使用 logger**：禁止使用 print
- **类型注解**：所有函数都应有完整的类型注解
- **异常处理**：捕获具体异常，记录详细日志
- **无状态设计**：所有 RPC 方法独立处理请求，无副作用
- **资源清理**：使用 `try-finally` 确保临时文件清理
- **单例模式**：OCR 引擎使用单例，避免重复加载模型

## 开发计划

当前项目已完成阶段 1-3，正在进行阶段 4（VLM Caption 集成）。详细计划请参考 `PLAN.md`。

### 已完成阶段
- ✅ **阶段 1（Week 1，5天）**：Proto 协议设计 + gRPC 服务端实现 + FastAPI 客户端集成
- ✅ **阶段 2（Week 1.5，3天）**：PPTX 格式支持 + 叙述性优化
- ✅ **阶段 3（Week 2，2天）**：双层并发优化（页面级 + OCR 级）

### 进行中阶段
- ⏳ **阶段 4（Week 3，3天）**：VLM Caption 集成（外部 API，asyncio 并发）

## 贡献指南

### 提交代码前
```bash
# 运行所有测试
uv run pytest

# 检查代码覆盖率
uv run pytest --cov=. --cov-report=html
open htmlcov/index.html

# 代码风格检查（如果配置了）
uv run ruff check .

# 类型检查（如果配置了）
uv run mypy .
```

### 提交信息规范
```
feat: 新增 VLM Caption 集成
fix: 修复 PPTX 双层并发死锁问题
docs: 更新 CLAUDE.md 文档
perf: 优化 OCR 并发性能（8.2x 提升）
test: 添加双层并发性能测试
chore: 更新依赖版本
```

## 许可证

MIT License

---

**最后更新**：2025-01-11
**维护者**：待填写
**项目主页**：待填写
