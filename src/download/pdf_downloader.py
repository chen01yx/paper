"""
PDF 下载模块
"""
import os
import requests
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PaperBot/1.0)"
}


def download_pdf(pdf_url: str, save_path: str) -> str | None:
    """
    Download PDF from url to save_path.
    Returns the saved path on success, None on failure.
    """
    if not pdf_url:
        return None
    try:
        logger.info(f"  Downloading PDF: {pdf_url}")
        resp = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        # Check content type
        content_type = resp.headers.get("Content-Type", "")
        if "application/pdf" not in content_type and not pdf_url.endswith(".pdf"):
            logger.warning(f"  Not a PDF content type: {content_type}")
            return None
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = os.path.getsize(save_path) / 1024
        logger.info(f"  Saved PDF: {save_path} ({size_kb:.0f} KB)")
        return save_path
    except Exception as e:
        logger.error(f"  Failed to download PDF from {pdf_url}: {e}")
        return None
