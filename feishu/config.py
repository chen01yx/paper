"""
飞书推送配置
"""
import os

# 飞书应用凭证（从 .env 环境变量加载）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")

# API 地址
FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/files"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# 论文输出目录（相对于 paper 目录）
PAPER_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")