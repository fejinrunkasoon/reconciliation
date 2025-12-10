#!/bin/bash
# 安装所有依赖的脚本

echo "正在激活虚拟环境并安装依赖..."
source venv/bin/activate
pip install streamlit pandas openpyxl

echo ""
echo "验证安装..."
python check_dependencies.py

