"""
Paper Bot 主入口
支持多类别分类存储：output/category/yyyy/mm/dd/
"""
import os
import sys
import re
import logging
import json
import math
import random
from datetime import datetime, date
from collections import OrderedDict  # kept for potential future use

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CATEGORIES, PAPERS_PER_CATEGORY, OUTPUT_DIR,
    INSTITUTION_KEYWORDS,
)
from src.search.arxiv_rss import fetch_arxiv_rss
from src.search.openalex import search_openalex
from src.download.pdf_downloader import download_pdf
from src.read.summarizer import summarize_paper
from src.organize.file_organizer import create_paper_dir, save_summary

# === Logging ===
os.makedirs(OUTPUT_DIR, exist_ok=True)
log_path = os.path.join(OUTPUT_DIR, "paper_bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# === Dedup: track processed paper titles ===
HISTORY_FILE = os.path.join(OUTPUT_DIR, "processed_papers.json")


def load_history() -> set:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return set(data)
    return set()


def save_history(titles: set):
    with open(HISTORY_FILE, "w") as f:
        json.dump(sorted(titles), f, indent=2)


def normalize_title(title: str) -> str:
    """Lowercase, remove non-alphanumeric for dedup."""
    return re.sub(r'[^a-z0-9一-鿿]', '', title.lower().strip())


# 类别特定的硬性关键词过滤
CATEGORY_MANDATORY_KEYWORDS = {
    "main": {
        # 必须包含机器人操控相关词（排除纯LLM论文）
        "robot": ["robot manipulation", "robotic manipulation", "robot grasping",
                  "robotic grasping", "robot gripper", "manipulation robot",
                  "grasping robot", "gripper robot", "robot arm",
                  "vision-language-action robot", "vla robot", "vla policy",
                  "embodied robot", "robot policy", "robot control",
                  "generalist robot", "robot foundation model"],
    },
    "egobench": {
        # 必须包含灵巧手/触觉/双臂/视频训练等核心词
        "core": ["dexterous", "dexterity", "multi-finger", "anthropomorphic hand",
                 "in-hand manipulation", "robotic hand", "bimanual", "dual-arm",
                 "tactile", "haptic", "teleoperation", "teleoperated",
                 "egocentric", "human video", "human demonstration",
                 "sim2real", "simulation benchmark manipulation"],
    },
    "tacvla": {
        # 必须包含核心触觉词（必须是明确的触觉感知技术）
        "tactile": ["tactile sensing", "tactile feedback", "tactile sensor",
                    "gelsight", "tactile glove", "digit tactile",
                    "visuo-tactile", "visual-tactile", "tactile vision",
                    "haptic sensing", "haptic feedback", "touch sensor",
                    "force-torque sensing", "ft sensor", "contact sensing"],
        # 并且必须包含机器人操作词
        "robot": ["robot manipulation", "robotic grasping", "robot gripper",
                  "manipulation robot", "grasping robot", "gripper",
                  "robotic manipulation", "robotic", "manipulation",
                  "grasping", "robot arm", "manipulator", "dexterous"],
    },
}


def score_paper(paper: dict, required_keywords: list, deprioritize_keywords: list, category: str = "main") -> float:
    """
    Score papers for ranking. Higher = more relevant/priority.
    Papers without mandatory keywords are heavily penalized.
    """
    score = 0.0

    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    combined = (title + " " + abstract).lower()

    # === Category-specific hard filter ===
    mandatory = CATEGORY_MANDATORY_KEYWORDS.get(category, CATEGORY_MANDATORY_KEYWORDS["main"])

    # Check each mandatory group
    for group_name, keywords in mandatory.items():
        has_keyword = any(kw in combined for kw in keywords)
        if not has_keyword:
            score -= 100  # Strong penalty for missing mandatory group

    # === Positive keywords boost ===
    required_match_count = 0
    for kw in required_keywords:
        if kw.lower() in combined:
            required_match_count += 1
            score += 8

    if required_match_count == 0:
        score -= 30

    # Recency (newer = better)
    try:
        pub_date = datetime.strptime(paper.get("published", ""), "%Y-%m-%d")
        days_old = (datetime.now() - pub_date).days
        score += max(0, 30 - days_old)
    except (ValueError, TypeError):
        pass

    # Citations (Semantic Scholar)
    citations = paper.get("citations", 0) or 0
    score += min(citations * 0.5, 10)

    # Institution bonus
    institutions = paper.get("institutions", []) or []
    inst_text = " ".join(institutions).lower()
    inst_score = 0
    for kw in INSTITUTION_KEYWORDS:
        if kw.lower() in inst_text:
            inst_score += 2
    score += min(inst_score, 10)

    # Has PDF
    if paper.get("pdf_url"):
        score += 3

    # Has abstract
    if len(abstract) > 200:
        score += 2

    # === Deprioritize less relevant topics ===
    dep_score = 0
    for kw in deprioritize_keywords:
        if kw.lower() in combined:
            dep_score += 25  # Strong penalty
    score -= dep_score

    return score


# === Probabilistic paper selection ===
# Uses soft-max weights so high-scored papers are picked more often,
# but older / lower-scored papers still have a non-zero chance — giving
# multiple daily runs a shot at accumulating more diverse papers.

def pick_papers_from_pool(
    scored_papers: list[dict], target: int, temperature: float = 0.5
) -> list[str]:
    """
    Softmax-weighted random sampling without replacement.

    Returns a list of normalised titles that were picked.
    """
    # Filter out already-selected papers (those already processed this run)
    remaining = [p for p in scored_papers if p["_title_key"] not in _picked_titles]

    if not remaining:
        return []

    # If too few candidates remain, just take them all
    if len(remaining) <= target:
        _picked_titles.update(p["_title_key"] for p in remaining)
        return [normalize_title(p["title"]) for p in remaining]

    # Build soft-max weights
    scores = [p["_score"] for p in remaining]
    shifted = [s - max(scores) for s in scores]  # numerical stability
    scaled = [s / temperature for s in shifted]
    exp_scores = [math.exp(s) for s in scaled]
    total = sum(exp_scores)
    probs = [e / total for e in exp_scores]

    # Sample without replacement (accept-reject approximation via repeated weighted sampling)
    indices = set()
    attempts = 0
    while len(indices) < min(target, len(probs)) and attempts < len(probs) * 20:
        idx = random.choices(range(len(probs)), weights=probs, k=1)[0]
        if idx not in indices:
            indices.add(idx)
        attempts += 1

    picked = []
    for idx in sorted(indices):
        p = remaining[idx]
        _picked_titles.add(p["_title_key"])
        picked.append(normalize_title(p["title"]))
    return picked


_picked_titles: set[str] = set()       # per-run tracking of already-selected papers


def get_existing_paper_count(category: str, today_str: str) -> int:
    """Count how many papers already exist in today's date directory for a category."""
    parts = today_str.split('-')
    date_path = os.path.join(OUTPUT_DIR, category, parts[0], parts[1], parts[2])
    if not os.path.exists(date_path):
        return 0
    return len([d for d in os.listdir(date_path) if re.match(r'^\d{3}-', d)])


def scan_existing_paper_titles() -> set:
    """Scan all existing paper folders across all categories and extract titles."""
    existing_titles = set()
    if not os.path.exists(OUTPUT_DIR):
        return existing_titles

    for category_dir in os.listdir(OUTPUT_DIR):
        category_path = os.path.join(OUTPUT_DIR, category_dir)
        if not os.path.isdir(category_path) or category_dir in ["processed_papers.json", "paper_bot.log"]:
            continue

        for year_dir in os.listdir(category_path):
            year_path = os.path.join(category_path, year_dir)
            if not os.path.isdir(year_path) or not re.match(r'^\d{4}$', year_dir):
                continue
            for month_dir in os.listdir(year_path):
                month_path = os.path.join(year_path, month_dir)
                if not os.path.isdir(month_path) or not re.match(r'^\d{2}$', month_dir):
                    continue
                for day_dir in os.listdir(month_path):
                    day_path = os.path.join(month_path, day_dir)
                    if not os.path.isdir(day_path) or not re.match(r'^\d{2}$', day_dir):
                        continue
                    for paper_dir in os.listdir(day_path):
                        if re.match(r'^\d{3}-', paper_dir):
                            title_part = paper_dir[4:]
                            existing_titles.add(normalize_title(title_part))
    return existing_titles


def fetch_paper_pool(categories_config: dict) -> list[dict]:
    """
    一次性获取所有论文候选（替代原来的逐条 API 查询）。

    - arXiv RSS: 每个分类 1 次请求（cs.RO/AI/CV/LG 共 4 次）
    - OpenAlex: 每个 paper bot 类别 2 条查询（共 6 次）
    总计 ~10 次 HTTP 请求（原来 ~30+ 次且频繁 429）
    """
    pool = []
    seen_titles = set()

    def _add_papers(papers):
        for paper in papers:
            key = normalize_title(paper["title"])
            if key and key not in seen_titles:
                seen_titles.add(key)
                pool.append(paper)

    # 1. arXiv RSS 批量获取（4 次请求拿到数百篇论文）
    logger.info("--- Fetching arXiv RSS feeds ---")
    rss_papers = fetch_arxiv_rss()
    _add_papers(rss_papers)

    # 2. OpenAlex 补充（每个类别取前 4 条 query 搜索）
    logger.info("--- Searching OpenAlex for supplementary papers ---")
    for cat_name, cat_config in categories_config.items():
        queries = cat_config["queries"][:4]
        for query in queries:
            results = search_openalex(query, limit=5)
            _add_papers(results)

    logger.info(f"Paper pool: {len(pool)} unique candidate papers")
    return pool


def process_category(category: str, category_config: dict, today_str: str, history: set, existing_folder_titles: set, paper_pool: list):
    """Process a single category: search, download, summarize, save."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing category: {category}")
    logger.info(f"Description: {category_config['description']}")
    logger.info(f"{'='*60}")

    queries = category_config["queries"]
    required_keywords = category_config["required_keywords"]
    deprioritize_keywords = category_config["deprioritize_keywords"]

    # 从论文池中本地过滤（不再发 API 请求）
    all_papers = []
    history_normalized = {normalize_title(t) for t in history}

    logger.info(f"Filtering from paper pool ({len(paper_pool)} candidates)...")
    for paper in paper_pool:
        key = normalize_title(paper["title"])
        if not key or key in history_normalized or key in existing_folder_titles:
            continue

        combined = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()

        # 检查是否匹配该类别的任一搜索关键词
        for query in queries:
            # 提取查询中的关键词（保留引号内短语，忽略短词）
            terms = [t.strip('"') for t in re.findall(r'"[^"]*"|\w+', query.lower())]
            terms = [t for t in terms if len(t) > 2]
            if terms and all(t in combined for t in terms):
                all_papers.append(paper)
                break
    logger.info(f"Total unique papers found for {category}: {len(all_papers)}")

    # Score and sort
    for paper in all_papers:
        paper["_score"] = score_paper(paper, required_keywords, deprioritize_keywords, category)
    all_papers.sort(key=lambda x: x["_score"], reverse=True)

    # Filter out papers with negative score (missing mandatory keywords)
    valid_papers = [p for p in all_papers if p["_score"] >= 0]
    logger.info(f"Papers passing mandatory filter: {len(valid_papers)} / {len(all_papers)}")
    all_papers = valid_papers


    # Pre-compute _title_key so pick_papers_from_pool can reference it
    for p in all_papers:
        p["_title_key"] = normalize_title(p["title"])

    # Use softmax-weighted random sampling instead of taking Top-N or all.
    # Higher-scored papers are picked more often, but older/lower-scored
    # papers still have a non-zero chance — giving multiple daily runs a
    # shot at accumulating more diverse papers.
    if len(all_papers) == 0:
        logger.info(f"No valid papers found for {category} after filtering, skipping.")
        return

    selected_titles = pick_papers_from_pool(all_papers, target=PAPERS_PER_CATEGORY, temperature=0.5)
    if not selected_titles:
        logger.info(f"No papers selected for {category} after weighted sampling.")
        return

    # Map picked titles back to paper dicts
    history_and_existing = history_normalized | existing_folder_titles
    selected = [p for p in all_papers if p["_title_key"] in selected_titles]
    logger.info(f"Selected {len(selected)} papers out of {len(all_papers)} candidates for {category} (weighted random, target={PAPERS_PER_CATEGORY})")

    # Create category output directory
    parts = today_str.split('-')
    category_output_dir = os.path.join(OUTPUT_DIR, category, parts[0], parts[1], parts[2])
    os.makedirs(category_output_dir, exist_ok=True)

    # Process papers (index starts from existing count so files are numbered correctly)
    existing_count = get_existing_paper_count(category, today_str)
    paper_index = existing_count
    for i, paper in enumerate(selected):
        title = paper["title"]
        logger.info(f"\n--- Processing paper {i+1}/{len(selected)}: {title[:80]} ---")

        pdf_url = paper.get("pdf_url")
        if not pdf_url and paper.get("arxiv_id"):
            arxiv_id = paper["arxiv_id"]
            if "v" in arxiv_id.split("/")[-1]:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            else:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        if not pdf_url:
            logger.warning("  No PDF URL available, skipping")
            continue

        abstract_summary = paper.get("abstract", "")[:200]
        folder_hint = abstract_summary.replace("\n", " ")[:60]

        paper_index += 1
        paper_dir = create_paper_dir(today_str, folder_hint, paper_index, category_output_dir)

        pdf_filename = "paper.pdf"
        pdf_path = os.path.join(paper_dir, pdf_filename)
        saved_pdf = download_pdf(pdf_url, pdf_path)

        if saved_pdf:
            paper_info = {
                "pdf_url": pdf_url,
                "arxiv_id": paper.get("arxiv_id"),
                "doi": paper.get("doi"),
            }
            summary = summarize_paper(saved_pdf, paper_info=paper_info)

            if summary:
                save_summary(paper_dir, summary)
                from src.organize.file_organizer import sanitize_filename
                actual_name = sanitize_filename(summary.strip().split('\n')[0], max_len=60)
                new_dir_name = f"{paper_index:03d}-{actual_name}"
                new_dir_path = os.path.join(os.path.dirname(paper_dir), new_dir_name)
                if os.path.dirname(paper_dir) != new_dir_path and not os.path.exists(new_dir_path):
                    os.rename(paper_dir, new_dir_path)
                    logger.info(f"  Renamed dir to: {new_dir_path}")
            else:
                fallback = f"**标题**: {title}\n**摘要**: {abstract_summary}"
                save_summary(paper_dir, fallback)
        else:
            fallback = f"**标题**: {title}\n**来源**: {paper.get('source')}\n**摘要**: {abstract_summary}"
            save_summary(paper_dir, fallback)
            logger.warning("  PDF download failed, saved abstract only")

        history.add(normalize_title(title))

    logger.info(f"Finished processing {category}: {paper_index} papers")


def main():
    today_str = date.today().strftime("%Y-%m-%d")
    logger.info(f"=== Paper Bot started: {today_str} ===")

    history = load_history()
    existing_folder_titles = scan_existing_paper_titles()
    logger.info(f"Found {len(existing_folder_titles)} existing paper folders across all categories")

    # 一次性获取论文候选池（替代原来每个类别逐条查询）
    paper_pool = fetch_paper_pool(CATEGORIES)

    # Reset per-run picked set once at the start of this entire run
    _picked_titles.clear()

    # Process each category
    for category, category_config in CATEGORIES.items():
        process_category(category, category_config, today_str, history, existing_folder_titles, paper_pool)

    # Save history
    save_history(history)

    logger.info(f"\n=== Paper Bot finished for {today_str} ===")


if __name__ == "__main__":
    main()