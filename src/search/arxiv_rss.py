"""
arXiv RSS 批量获取模块

通过 RSS feed 一次性拉取指定分类下的所有新论文，
避免逐条 API 查询导致的 429 限速问题。
"""
import re
import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ARXIV_RSS_BASE = "http://rss.arxiv.org/rss"

# 默认拉取的 arXiv 分类（机器人操控相关）
DEFAULT_CATEGORIES = ["cs.RO", "cs.AI", "cs.CV", "cs.LG"]

# 基础相关性过滤（与 arxiv_search.py 保持一致）
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
    """基础相关性过滤：论文是否与机器人操控相关"""
    combined = (title + " " + abstract).lower()
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


def _parse_rss(xml_content: str) -> list[dict]:
    """解析 arXiv RSS XML，返回论文列表"""
    soup = BeautifulSoup(xml_content, "xml")
    papers = []

    for item in soup.find_all("item"):
        title_tag = item.find("title")
        if not title_tag:
            continue
        # arXiv RSS 标题末尾常带分类标记如 "(arXiv:2507.01234v1 [cs.RO])"
        title = re.sub(r'\s*\(arXiv:[^)]+\)\s*$', '', title_tag.text.strip())

        link_tag = item.find("link")
        link = link_tag.text.strip() if link_tag else ""

        # 提取 arXiv ID
        arxiv_id = ""
        if link:
            match = re.search(r'(\d{4}\.\d{4,5})', link)
            if match:
                arxiv_id = match.group(1)

        if not arxiv_id:
            continue

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

        # 描述字段包含摘要
        desc_tag = item.find("description")
        abstract = ""
        if desc_tag and desc_tag.string:
            desc_soup = BeautifulSoup(desc_tag.string, "html.parser")
            abstract = desc_soup.get_text().strip()
        elif desc_tag:
            abstract = desc_tag.get_text().strip()

        papers.append({
            "title": title,
            "authors": [],  # RSS 不含作者详情
            "abstract": abstract,
            "published": "",  # RSS 不含精确日期，靠评分系统的 recency 不依赖此字段
            "updated": "",
            "arxiv_id": arxiv_id,
            "pdf_url": pdf_url,
            "source": "arxiv_rss",
            "doi": None,
            "institutions": [],
            "citations": 0,
        })

    return papers


def fetch_arxiv_rss(categories: list = None) -> list[dict]:
    """
    从 arXiv RSS 批量获取最新论文。

    每个分类只需 1 次 HTTP 请求（替代原来的 26 次逐条查询）。

    Args:
        categories: arXiv 分类列表，默认 cs.RO/AI/CV/LG

    Returns:
        论文字典列表
    """
    if categories is None:
        categories = DEFAULT_CATEGORIES

    all_papers = []
    seen_ids = set()

    for cat in categories:
        url = f"{ARXIV_RSS_BASE}/{cat}"
        logger.info(f"Fetching arXiv RSS: {cat}")

        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                logger.warning(f"  RSS {cat} returned status {resp.status_code}")
                continue

            papers = _parse_rss(resp.content)
            new_count = 0
            for paper in papers:
                aid = paper["arxiv_id"]
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    if _is_relevant(paper["title"], paper["abstract"]):
                        all_papers.append(paper)
                        new_count += 1

            logger.info(f"  {cat}: {len(papers)} papers fetched, {new_count} relevant & new")

        except Exception as e:
            logger.error(f"  Failed to fetch RSS {cat}: {e}")

    logger.info(f"arXiv RSS total: {len(all_papers)} relevant papers (from {len(categories)} feeds)")
    return all_papers
