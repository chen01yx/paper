"""
Feishu push configuration
"""
import os

# Feishu app credentials (loaded from .env environment variables)
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")

# API endpoints
FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/files"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# Paper output directory (relative to paper folder)
PAPER_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
