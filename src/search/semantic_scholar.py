"""
Semantic Scholar 论文检索模块
"""
import requests
import logging
import time

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,abstract,publicationDate,externalIds,citationCount,authors.name,authors.affiliations,journal,isOpenAccess,openAccessPdf"

STRONG_KEYWORDS = [
    "robotic", "robot", "grasp", "grasping", "grasped",
    "dexterous", "tactile", "finger", "gripper", "end-effector", "bimanual",
    "deformable object",
    "teleoperation", "teleoperated", "haptic", "anthropomorphic",
]

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

WEAK_KEYWORDS = [
    "actuator", "kinematic", "kinematics", "collision", "contact model",
    "perception", "simulation", "trajectory",
]

def _is_relevant(title: str, abstract: str) -> bool:
    combined = (title + " " + (abstract or "")).lower()
    title_lower = title.lower()

    if any(kw in title_lower for kw in STRONG_KEYWORDS):
        return True
    if any(ph in combined for ph in PHRASES):
        return True
    weak_hit = any(kw in combined for kw in WEAK_KEYWORDS)
    if weak_hit:
        robot_indicators = ["robot", "manipul", "grasp", "dexter",
                           "reinforcement", "policy", "gripper"]
        if any(ind in combined for ind in robot_indicators):
            return True
    return False


def search_semantic_scholar(query: str, limit: int = 3, year_from: int = 2024) -> list[dict]:
    """
    Search Semantic Scholar for papers matching the query.
    Returns list of paper dicts.
    """
    # Add delay before each request to avoid rate limiting (100 req/5min limit)
    time.sleep(3)

    logger.info(f"Searching Semantic Scholar for: {query}")
    papers = []
    params = {
        "query": query,
        "limit": limit,
        "fields": FIELDS,
        "year": f"{year_from}-",
        "sort": "relevance",
    }
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                logger.info(f"  SS retry attempt {attempt+1}/{max_attempts}...")
                time.sleep(20 * (attempt + 1))  # Longer wait on retry
            resp = requests.get(SEMANTIC_SCHOLAR_API, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    pdf_url = None
                    oa = item.get("openAccessPdf")
                    if oa and oa.get("url"):
                        pdf_url = oa["url"]
                    elif item.get("isOpenAccess"):
                        ext_ids = item.get("externalIds", {})
                        if "ArXiv" in ext_ids:
                            pdf_url = f"https://arxiv.org/pdf/{ext_ids['ArXiv']}.pdf"

                    authors_info = item.get("authors", [])
                    author_names = [a.get("name", "") for a in authors_info if a.get("name")]
                    institutions = []
                    for a in authors_info:
                        institutions.extend(a.get("affiliations", []))

                    paper = {
                        "title": item.get("title", ""),
                        "authors": author_names,
                        "abstract": item.get("abstract", ""),
                        "published": item.get("publicationDate", ""),
                        "source": "semantic_scholar",
                        "doi": item.get("externalIds", {}).get("DOI"),
                        "arxiv_id": item.get("externalIds", {}).get("ArXiv"),
                        "pdf_url": pdf_url,
                        "citations": item.get("citationCount", 0),
                        "institutions": institutions,
                        "journal": item.get("journal"),
                    }
                    if item.get("title") and _is_relevant(item.get("title", ""), item.get("abstract", "")):
                        papers.append(paper)
                logger.info(f"  Found {len(papers)} papers on Semantic Scholar")
                return papers
            elif resp.status_code == 429:
                logger.warning(f"  Semantic Scholar rate limited, waiting...")
                if attempt < max_attempts - 1:
                    time.sleep(10 * (attempt + 1))
                    continue
                return papers
            else:
                logger.warning(f"  Semantic Scholar API returned status {resp.status_code}")
                return papers
        except requests.exceptions.ReadTimeout:
            logger.warning(f"  SS request timed out (attempt {attempt+1}/{max_attempts})")
            continue
        except Exception as e:
            logger.error(f"  Semantic Scholar search failed for '{query}': {e}")
            return papers
    return papers
