"""
Paper Bot 主入口
支持多类别分类存储：output/category/yyyy/mm/dd/
"""
import os
import sys
import re
import logging
import json
from datetime import datetime, date
from collections import OrderedDict

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CATEGORIES, PAPERS_PER_CATEGORY, OUTPUT_DIR,
    INSTITUTION_KEYWORDS,
)
from src.search.arxiv_search import search_arxiv
from src.search.semantic_scholar import search_semantic_scholar
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
                  "manipulation robot", "grasping robot", "gripper"],
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


def process_category(category: str, category_config: dict, today_str: str, history: set, existing_folder_titles: set):
    """Process a single category: search, download, summarize, save."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing category: {category}")
    logger.info(f"Description: {category_config['description']}")
    logger.info(f"{'='*60}")

    queries = category_config["queries"]
    required_keywords = category_config["required_keywords"]
    deprioritize_keywords = category_config["deprioritize_keywords"]

    all_papers = []

    logger.info(f"Searching with {len(queries)} queries...")
    for query in queries:
        arxiv_results = search_arxiv(query)
        all_papers.extend(arxiv_results)

        # Only call Semantic Scholar for every 3rd query to reduce API calls
        if queries.index(query) % 3 == 0:
            ss_results = search_semantic_scholar(query, limit=3)
            all_papers.extend(ss_results)

    # Deduplicate
    seen = OrderedDict()
    history_normalized = {normalize_title(t) for t in history}
    for paper in all_papers:
        key = normalize_title(paper["title"])
        if key and key not in seen and key not in history_normalized and key not in existing_folder_titles:
            seen[key] = paper

    all_papers = list(seen.values())
    logger.info(f"Total unique papers found for {category}: {len(all_papers)}")

    # Score and sort
    for paper in all_papers:
        paper["_score"] = score_paper(paper, required_keywords, deprioritize_keywords, category)
    all_papers.sort(key=lambda x: x["_score"], reverse=True)

    # Filter out papers with negative score (missing mandatory keywords)
    valid_papers = [p for p in all_papers if p["_score"] >= 0]
    logger.info(f"Papers passing mandatory filter: {len(valid_papers)} / {len(all_papers)}")
    all_papers = valid_papers

    # Check existing count
    existing_count = get_existing_paper_count(category, today_str)
    papers_needed = PAPERS_PER_CATEGORY - existing_count
    if papers_needed <= 0:
        logger.info(f"Already have {existing_count} papers for {category} today, skipping.")
        return

    if len(all_papers) == 0:
        logger.info(f"No valid papers found for {category} after filtering, skipping.")
        return

    selected = all_papers[:papers_needed]
    logger.info(f"Already have {existing_count} papers, selecting top {len(selected)} new ones")

    # Create category output directory
    parts = today_str.split('-')
    category_output_dir = os.path.join(OUTPUT_DIR, category, parts[0], parts[1], parts[2])
    os.makedirs(category_output_dir, exist_ok=True)

    # Process papers
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

    # Process each category
    for category, category_config in CATEGORIES.items():
        process_category(category, category_config, today_str, history, existing_folder_titles)

    # Save history
    save_history(history)

    logger.info(f"\n=== Paper Bot finished for {today_str} ===")


if __name__ == "__main__":
    main()