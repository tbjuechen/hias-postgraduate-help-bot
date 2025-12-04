#!/bin/sh
set -e

echo "=================================================="
echo "🚀 Starting Hias Bot Container Entrypoint"
echo "=================================================="

# 1. 等待数据库迁移
echo "Step 1: Running database migrations..."
# nb orm upgrade 会加载 NoneBot 插件，这会导致大量日志输出
# 我们将其标准输出重定向到 /dev/null，只保留错误输出，以减少干扰
nb orm upgrade > /dev/null
echo "✅ Database migrations completed."
echo "--------------------------------------------------"

# 2. 构建知识库 (如果尚未构建)
INIT_FLAG="/app/data/.knowledge_base_initialized"

# 允许通过环境变量 FORCE_REBUILD_KB=true 强制重建
if [ "$FORCE_REBUILD_KB" = "true" ]; then
    echo "Force rebuild requested. Removing init flag..."
    rm -f "$INIT_FLAG"
fi

if [ ! -f "$INIT_FLAG" ]; then
    echo "Step 2: Initializing knowledge base..."
    echo "This may take a while depending on the document size."
    
    # 运行构建脚本
    python scripts/build_knowledge_base.py
    
    touch "$INIT_FLAG"
    echo "✅ Knowledge base initialized successfully."
else
    echo "Step 2: Knowledge base already initialized."
    echo "Skipping build. (Delete /app/data/.knowledge_base_initialized to force rebuild)"
fi
echo "--------------------------------------------------"

# 3. 启动 Bot
echo "Step 3: Starting bot process..."
echo "=================================================="
exec python3 bot.py
