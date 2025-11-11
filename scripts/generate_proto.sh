#!/bin/bash
# 生成 Python gRPC 代码

PROTO_DIR="grpc/protos"
OUTPUT_DIR="grpc/generated"

# 创建输出目录
mkdir -p $OUTPUT_DIR

# 生成 Python 代码
uv run python -m grpc_tools.protoc \
  --proto_path=$PROTO_DIR \
  --python_out=$OUTPUT_DIR \
  --grpc_python_out=$OUTPUT_DIR \
  $PROTO_DIR/parser.proto

# 创建 __init__.py
touch $OUTPUT_DIR/__init__.py

# 修复导入路径（相对导入）
sed -i 's/import parser_pb2 as parser__pb2/from . import parser_pb2 as parser__pb2/g' $OUTPUT_DIR/parser_pb2_grpc.py

echo "✅ Proto 代码生成完成！"
echo "   - parser_pb2.py （消息类型）"
echo "   - parser_pb2_grpc.py （gRPC 存根）"
