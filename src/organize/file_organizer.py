"""
文件组织模块 — 按类别和日期创建目录结构
目录结构: output/category/yyyy/mm/dd/NNN-short-summary/
"""
import os
import re
import logging

logger = logging.getLogger(__name__)


def sanitize_filename(name: str, max_len: int = 50) -> str:
    """
    Create a safe folder name from summary text.
    Strips markdown labels like '**标题**:' and extracts the actual title.
    """
    # Strip markdown label prefixes like "**标题**:" or "标题:"
    name = re.sub(r'\*\*[^*]+\*\*\s*[:：]\s*', '', name)
    name = re.sub(r'^[一-鿿]+\s*[:：]\s*', '', name)
    # Remove remaining markdown and special chars
    name = re.sub(r'[^\w\s一-鿿-]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', '-', name)
    # Truncate
    if len(name) > max_len:
        name = name[:max_len].rsplit('-', 1)[0]
    return name.strip('-').lower() or 'paper'


def create_paper_dir(date_str: str, summary: str, paper_index: int, base_output_dir: str) -> str:
    """
    Create directory: base_output_dir/NNN-short-summary/
    base_output_dir should already include category path: output/category/yyyy/mm/dd/
    Returns the created directory path.
    """
    first_line = summary.strip().split('\n')[0] if summary else 'unknown-paper'
    folder_name = sanitize_filename(first_line, max_len=60)

    dir_name = f"{paper_index:03d}-{folder_name}"
    paper_dir = os.path.join(base_output_dir, dir_name)

    os.makedirs(paper_dir, exist_ok=True)
    logger.info(f"  Created paper dir: {paper_dir}")
    return paper_dir


def save_summary(paper_dir: str, summary: str):
    """Save summary as markdown file in the paper directory."""
    summary_path = os.path.join(paper_dir, "summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    logger.info(f"  Saved summary: {summary_path}")