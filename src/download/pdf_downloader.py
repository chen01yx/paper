"""
PDF download module
"""
import os
import re
import requests
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PaperBot/1.0)"
}


def _resolve_arxiv_id_from_url(pdf_url: str) -> str | None:
    """Extract arXiv ID from URL (format: 2607.xxxxx)."""
    if not pdf_url:
        return None
    # Match patterns like 2607.03941, cs.DC/0606100, etc.
    patterns = [
        r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})',
        r'doi\.org/\S*(\d{4}\.\d{4,5})\b',
        r'10\.48550/arxiv\.(\d{4}\.\d{4,5})',
        r'(\d{4}\.\d{4,5})[^\w]',
    ]
    for pat in patterns:
        m = re.search(pat, pdf_url)
        if m:
            return m.group(1)
    return None


def download_pdf(pdf_url: str, save_path: str) -> str | None:
    """
    Download PDF from url to save_path.
    Returns the saved path on success, None on failure.

    Handles:
    - Direct PDF URLs
    - DOI links (resolves via HEAD request, follows redirect)
    - Fallback to arXiv raw URL if DOI/cloudflare blocks
    """
    if not pdf_url:
        return None
    try:
        logger.info(f"  Downloading PDF: {pdf_url}")

        # --- Try original URL first ---
        resp = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")

        # If we got HTML (likely Cloudflare block), try alternatives
        if "text/html" in content_type:
            logger.warning(f"  Got HTML instead of PDF (status={resp.status_code}, content-type={content_type})")

            arxiv_id = _resolve_arxiv_id_from_url(pdf_url)
            if arxiv_id:
                # Try direct arXiv PDF URL
                fallback_url = f"https://arxiv.org/pdf/{arxiv_id}"
                logger.info(f"  Retrying with arXiv URL: {fallback_url}")
                resp = requests.get(
                    fallback_url, headers=HEADERS, timeout=60,
                    stream=True, allow_redirects=True
                )
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")

            if "application/pdf" not in content_type:
                logger.warning(f"  Still not a PDF after retry: {content_type}. Skipping.")
                return None

        # Save the PDF
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = os.path.getsize(save_path) / 1024
        logger.info(f"  Saved PDF: {save_path} ({size_kb:.0f} KB)")
        return save_path

    except Exception as e:
        logger.error(f"  Failed to download PDF from {pdf_url}: {e}")
        return None
