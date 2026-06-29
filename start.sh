#!/bin/bash
# ==============================
# tOS Quality Workbench 启动脚本
# ==============================

set -e

echo "=========================================="
echo "  tOS Quality Workbench 启动中..."
echo "=========================================="

# 检查环境变量
if [ -z "$FEISHU_APP_ID" ] || [ -z "$FEISHU_APP_SECRET" ]; then
    echo "⚠️  警告: 飞书应用配置未设置（FEISHU_APP_ID, FEISHU_APP_SECRET）"
    echo "   飞书相关功能将不可用"
fi

# 设置数据目录
export APP_DIR=${APP_DIR:-/data/.tos_quality_workbench}
mkdir -p "$APP_DIR"

# 启动后端
echo "🚀 启动后端服务..."
cd /app/backend
python run.py
