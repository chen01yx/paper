"""
Run Paper Bot for a specific date (not today).
Usage: python run_for_date.py YYYY-MM-DD
"""
import os
import sys
import re
import json
import logging
from datetime import datetime
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SEARCH_QUERIES, MAX_PAPERS_PER_DAY, OUTPUT_DIR,
    INSTITUTION_KEYWORDS, DEPRIORITIZE_KEYWORDS, REQUIRED_KEYWORDS,
)
from src.search.arxiv_search import search_arxiv
from src.search.semantic_scholar import search_semantic_scholar
from src.download.pdf_downloader import download_pdf
from src.read.summarizer import summarize_paper
from src.organize.file_organizer import create_paper_dir, save_summary

# === Logging ===
os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

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
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', title.lower().strip())


def get_existing_paper_count(date_str: str) -> int:
    parts = date_str.split('-')
    date_path = os.path.join(OUTPUT_DIR, parts[0], parts[1], parts[2])
    if not os.path.exists(date_path):
        return 0
    return len([d for d in os.listdir(date_path) if re.match(r'^\d{3}-', d)])


def scan_existing_paper_titles() -> set:
    """Scan all existing paper folders and extract titles from directory names."""
    existing_titles = set()
    if not os.path.exists(OUTPUT_DIR):
        return existing_titles

    for year_dir in os.listdir(OUTPUT_DIR):
        year_path = os.path.join(OUTPUT_DIR, year_dir)
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


def score_paper(paper: dict) -> float:
    """Score papers for ranking with keyword boost/penalty."""
    score = 0.0

    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    combined = (title + " " + abstract).lower()

    # === Positive keywords boost ===
    required_match_count = 0
    for kw in REQUIRED_KEYWORDS:
        if kw.lower() in combined:
            required_match_count += 1
            score += 8

    if required_match_count == 0:
        score -= 30

    try:
        pub_date = datetime.strptime(paper.get("published", ""), "%Y-%m-%d")
        days_old = (datetime.now() - pub_date).days
        score += max(0, 30 - days_old)
    except (ValueError, TypeError):
        pass
    citations = paper.get("citations", 0) or 0
    score += min(citations * 0.5, 10)
    institutions = paper.get("institutions", []) or []
    inst_text = " ".join(institutions).lower()
    inst_score = 0
    for kw in INSTITUTION_KEYWORDS:
        if kw.lower() in inst_text:
            inst_score += 2
    score += min(inst_score, 10)
    if paper.get("pdf_url"):
        score += 3
    if len(abstract) > 200:
        score += 2
    dep_score = 0
    for kw in DEPRIORITIZE_KEYWORDS:
        if kw.lower() in combined:
            dep_score += 15
    score -= dep_score
    return score


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_for_date.py YYYY-MM-DD")
        sys.exit(1)

    target_date = sys.argv[1]
    logger.info(f"=== Paper Bot started for date: {target_date} ===")

    history = load_history()
    existing_folder_titles = scan_existing_paper_titles()
    logger.info(f"Found {len(existing_folder_titles)} existing paper folders")

    all_papers = []

    logger.info(f"Searching with {len(SEARCH_QUERIES)} queries across 2 sources...")
    for query in SEARCH_QUERIES:
        arxiv_results = search_arxiv(query)
        all_papers.extend(arxiv_results)
        if SEARCH_QUERIES.index(query) % 2 == 0:
            ss_results = search_semantic_scholar(query, limit=3)
            all_papers.extend(ss_results)

    seen = OrderedDict()
    history_normalized = {normalize_title(t) for t in history}
    for paper in all_papers:
        key = normalize_title(paper["title"])
        if key and key not in seen and key not in history_normalized and key not in existing_folder_titles:
            seen[key] = paper

    all_papers = list(seen.values())
    logger.info(f"Total unique papers found: {len(all_papers)}")

    for paper in all_papers:
        paper["_score"] = score_paper(paper)
    all_papers.sort(key=lambda x: x["_score"], reverse=True)

    existing_count = get_existing_paper_count(target_date)
    papers_needed = MAX_PAPERS_PER_DAY - existing_count
    if papers_needed <= 0:
        logger.info(f"Already have {existing_count} papers for {target_date}, skipping.")
        return
    selected = all_papers[:papers_needed]
    logger.info(f"Already have {existing_count} papers for {target_date}, selecting top {len(selected)} new ones")

    paper_index = existing_count
    for i, paper in enumerate(selected):
        title = paper["title"]
        logger.info(f"\n--- Processing paper {paper_index+i+1}: {title[:80]} ---")

        pdf_url = paper.get("pdf_url")
        if not pdf_url and paper.get("arxiv_id"):
            arxiv_id = paper["arxiv_id"]
            if "v" in arxiv_id.split("/")[-1]:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            else:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        if not pdf_url:
            logger.warning("  No PDF URL, skipping")
            continue

        abstract_summary = (paper.get("abstract", "") or "").replace("\n", " ")[:60]
        paper_idx = paper_index + i + 1
        paper_dir = create_paper_dir(target_date, abstract_summary, paper_idx, OUTPUT_DIR)

        pdf_path = os.path.join(paper_dir, "paper.pdf")
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
                new_dir_name = f"{paper_idx:03d}-{actual_name}"
                new_dir_path = os.path.join(os.path.dirname(paper_dir), new_dir_name)
                if not os.path.exists(new_dir_path):
                    os.rename(paper_dir, new_dir_path)
            else:
                fallback = f"**标题**: {title}\n**摘要**: {abstract_summary}"
                save_summary(paper_dir, fallback)
        else:
            fallback = f"**标题**: {title}\n**来源**: {paper.get('source')}\n**摘要**: {abstract_summary}"
            save_summary(paper_dir, fallback)
            logger.warning("  PDF download failed, saved abstract only")

        history.add(normalize_title(title))

    save_history(history)
    logger.info(f"\n=== Paper Bot finished for {target_date}. Processed {len(selected)} papers. ===")


if __name__ == "__main__":
    main()
