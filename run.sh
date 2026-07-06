#!/bin/bash
# Paper Bot 运行脚本
# 用法: ./run.sh

cd "$(dirname "$0")"

# 从 .env 加载密钥和环境变量
set -a
source .env
set +a

# 激活 conda 环境并运行
source /home/galbot/miniconda3/etc/profile.d/conda.sh
conda activate agent312

python src/main.py
