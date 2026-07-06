"""
arXiv 论文检索模块 — 使用 requests 直接调用，避免 arxiv 库的激进重试
"""
import time
import requests
import logging
from bs4 import BeautifulSoup
from config import ARXIV_MAX_RESULTS_PER_QUERY

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"


# Strong single keywords (specific enough to robotics)
STRONG_KEYWORDS = [
    "robotic", "robot", "grasp", "grasping", "grasped",
    "dexterous", "tactile", "finger", "gripper", "end-effector", "bimanual",
    "deformable object",
    "teleoperation", "teleoperated", "haptic", "anthropomorphic",
]

# Compound phrases — specific to our research area
PHRASES = [
    "robotic hand", "robot hand", "robot arm", "robotic arm",
    "robotic manipulation", "robot learning", "reinforcement learning",
    "motion planning", "motion control", "physics engine",
    "force feedback", "force sensing", "soft object",
    "end effector", "multi-finger", "multi finger", "dexterous hand",
    "robotic finger", "robotic gripper", "vision-based control",
    "visuo-tactile", "visual-tactile", "vision control",
    "sim-to-real", "sim2real", "sim to real", "domain randomization",
    "embodied ai", "embodied intelligence",
    "manipulation robot", "manipulation learning", "bimanual robot",
    "cloth manipulation", "fabric manipulation", "deformable manipulation",
    "card manipulation", "paper manipulation", "thin object manipulation",
    "robotic grasping", "grasp planning", "grasp detection", "grasp synthesis",
]

# Single words that must be paired with another robot indicator
WEAK_KEYWORDS = [
    "actuator", "kinematic", "kinematics", "collision", "contact model",
    "perception", "simulation", "trajectory",
]

def _is_relevant(title: str, abstract: str) -> bool:
    combined = (title + " " + abstract).lower()
    title_lower = title.lower()

    # Strong keyword in title = automatic pass
    if any(kw in title_lower for kw in STRONG_KEYWORDS):
        return True

    # Compound phrase anywhere = pass
    if any(ph in combined for ph in PHRASES):
        return True

    # Weak keyword: need it to co-occur with at least one strong robot indicator
    weak_hit = any(kw in combined for kw in WEAK_KEYWORDS)
    if weak_hit:
        robot_indicators = ["robot", "manipul", "grasp", "dexter",
                           "reinforcement", "policy", "gripper"]
        if any(ind in combined for ind in robot_indicators):
            return True

    return False

def search_arxiv(query: str) -> list[dict]:
    """
    Search arXiv for papers matching the query.
    Returns list of paper dicts.
    Uses requests directly for full control over retries.
    """
    logger.info(f"Searching arXiv for: {query}")
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": 0,
        "max_results": ARXIV_MAX_RESULTS_PER_QUERY,
    }
    papers = []
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                logger.info(f"  arXiv retry attempt {attempt+1}/{max_attempts}...")
                time.sleep(20 * (attempt + 1))
            resp = requests.get(ARXIV_API, params=params, timeout=60)
            if resp.status_code == 429:
                logger.warning(f"  arXiv rate limited (HTTP 429)")
                continue
            if resp.status_code != 200:
                logger.warning(f"  arXiv returned status {resp.status_code}")
                return papers

            # Parse Atom XML
            soup = BeautifulSoup(resp.content, "xml")
            entries = soup.find_all("entry")
            for entry in entries:
                title_tag = entry.find("title")
                title = title_tag.text.strip().replace("\n", " ") if title_tag else ""
                summary_tag = entry.find("summary")
                summary = summary_tag.text.strip().replace("\n", " ") if summary_tag else ""
                published_tag = entry.find("published")
                published = published_tag.text[:10] if published_tag else ""
                updated_tag = entry.find("updated")
                updated = updated_tag.text[:10] if updated_tag else ""
                id_tag = entry.find("id")
                entry_id = id_tag.text if id_tag else ""
                arxiv_id = entry_id.split("/")[-1] if entry_id else ""

                # PDF URL
                pdf_link = ""
                for link in entry.find_all("link"):
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                        pdf_link = link.get("href", "")
                        break
                if not pdf_link and arxiv_id:
                    pdf_link = f"https://arxiv.org/pdf/{arxiv_id}"

                authors = []
                for author in entry.find_all("author"):
                    name_tag = author.find("name")
                    if name_tag:
                        authors.append(name_tag.text.strip())

                paper = {
                    "title": title,
                    "authors": authors,
                    "abstract": summary,
                    "published": published,
                    "updated": updated,
                    "arxiv_id": arxiv_id,
                    "pdf_url": pdf_link,
                    "source": "arxiv",
                    "doi": None,
                    "institutions": [],
                    "citations": 0,
                }
                if title and _is_relevant(title, summary):
                    papers.append(paper)

            if papers:
                logger.info(f"  Found {len(papers)} papers on arXiv")
                return papers
        except requests.exceptions.ReadTimeout:
            logger.warning(f"  arXiv request timed out (attempt {attempt+1}/{max_attempts})")
            continue
        except Exception as e:
            logger.error(f"  arXiv search failed for '{query}': {e}")
            return papers
    logger.warning(f"  arXiv search failed after {max_attempts} attempts for '{query}'")
    return papers
