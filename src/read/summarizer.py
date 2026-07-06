"""
论文总结模块 — 调用 Anthropic API 生成中文摘要
"""
import logging
import pymupdf
from anthropic import Anthropic
from config import ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, SUMMARY_PROMPT

logger = logging.getLogger(__name__)

client = Anthropic(
    base_url=ANTHROPIC_BASE_URL,
    api_key=ANTHROPIC_AUTH_TOKEN,
)


def extract_text_from_pdf(pdf_path: str, max_pages: int = 10) -> str:
    """
    Extract text from PDF, limited to max_pages.
    """
    try:
        doc = pymupdf.open(pdf_path)
        texts = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            text = page.get_text()
            if text.strip():
                texts.append(text)
        doc.close()
        full_text = "\n".join(texts)
        # Truncate if too long for context window
        if len(full_text) > 20000:
            full_text = full_text[:20000]
        return full_text
    except Exception as e:
        logger.error(f"  Failed to extract text from {pdf_path}: {e}")
        return ""


def summarize_paper(pdf_path: str, paper_info: dict | None = None) -> str | None:
    """
    Read PDF and generate a Chinese summary using Claude API.
    paper_info: dict with url, arxiv_id, doi etc. for embedding in summary.
    Returns the summary text, or None on failure.
    """
    text = extract_text_from_pdf(pdf_path)
    if not text:
        logger.warning("  No text extracted from PDF, trying with abstract only")
        return None

    # Build URL line
    url_line = ""
    if paper_info:
        if paper_info.get("arxiv_id"):
            url_line = f"**论文链接**: https://arxiv.org/abs/{paper_info['arxiv_id']}\n"
        elif paper_info.get("doi"):
            url_line = f"**论文链接**: https://doi.org/{paper_info['doi']}\n"
        if paper_info.get("pdf_url"):
            url_line += f"**PDF下载**: {paper_info['pdf_url']}\n"

    logger.info(f"  Generating summary for {pdf_path}")
    try:
        prompt_with_url = f"{SUMMARY_PROMPT}\n{url_line}\n--- 论文正文内容（前10页） ---\n\n{text[:18000]}"
        message = client.messages.create(
            model="qwen3.6-plus",
            max_tokens=1024,
            system="你是一个机器人研究助手，请用中文输出所有内容。",
            messages=[
                {"role": "user", "content": prompt_with_url}
            ],
        )
        # Extract text from response (skip thinking blocks)
        summary_parts = []
        for block in message.content:
            if hasattr(block, 'text'):
                summary_parts.append(block.text)
            elif isinstance(block, str):
                summary_parts.append(block)
            elif hasattr(block, 'type') and block.type == 'thinking':
                pass  # Skip thinking blocks
            else:
                logger.debug(f"  Skipping unknown block type: {type(block)}")
        summary = "\n".join(summary_parts)
        logger.info("  Summary generated successfully")
        return summary
    except Exception as e:
        logger.error(f"  Failed to generate summary: {e}")
        return None
