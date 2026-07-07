"""
OpenAlex 论文检索模块

使用 OpenAlex 免费开放 API 替代 Semantic Scholar，
不限速、元数据更全，每页最多 25 条结果。
"""
import requests
import logging
import time

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org/works"

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
    """基础相关性过滤"""
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


def _reconstruct_abstract(inverted_index: dict) -> str:
    """从 OpenAlex 倒排索引格式重建摘要文本"""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def search_openalex(query: str, limit: int = 5, year_from: int = 2024) -> list[dict]:
    """
    通过 OpenAlex API 搜索论文。

    免费、不限速（合理使用），每页最多 25 条。
    mailto 参数可获得更快的响应（polite pool）。

    Args:
        query: 搜索关键词
        limit: 返回结果数（最大 25）
        year_from: 起始年份

    Returns:
        论文字典列表
    """
    logger.info(f"Searching OpenAlex for: {query}")

    params = {
        "search": query,
        "per-page": min(limit, 25),
        "filter": f"from_publication_date:{year_from}-01-01",
        "sort": "publication_date:desc",
        "mailto": "paperbot@example.com",  # polite pool
    }

    papers = []
    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                logger.info(f"  OpenAlex retry attempt {attempt+1}/{max_attempts}...")
                time.sleep(5)

            resp = requests.get(OPENALEX_API, params=params, timeout=30)

            if resp.status_code != 200:
                logger.warning(f"  OpenAlex returned status {resp.status_code}")
                continue

            data = resp.json()
            for item in data.get("results", []):
                title = item.get("title", "")
                abstract = _reconstruct_abstract(
                    item.get("abstract_inverted_index") or {}
                )

                # PDF URL: 优先 Open Access，否则用 arXiv
                pdf_url = None
                oa_url = item.get("open_access", {}).get("oa_url")
                if oa_url:
                    pdf_url = oa_url

                # arXiv ID 提取
                arxiv_id = None
                doi = item.get("doi", "")
                if doi and "arxiv" in doi.lower():
                    import re
                    match = re.search(r'(\d{4}\.\d{4,5})', doi)
                    if match:
                        arxiv_id = match.group(1)
                        if not pdf_url:
                            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

                # 如果 DOI 指向 arXiv，提取 ID
                ids = item.get("ids", {})
                if not arxiv_id:
                    openalex_url = ids.get("openalex", "")
                    # OpenAlex 有时在 locations 里有 arxiv 链接
                    for loc in item.get("locations", []):
                        landing = loc.get("landing_page_url", "")
                        if "arxiv.org" in landing:
                            import re
                            match = re.search(r'(\d{4}\.\d{4,5})', landing)
                            if match:
                                arxiv_id = match.group(1)
                                if not pdf_url:
                                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                                break

                # 作者和机构
                authors = []
                institutions = []
                for authorship in item.get("authorships", []):
                    author = authorship.get("author", {})
                    name = author.get("display_name", "")
                    if name:
                        authors.append(name)
                    for inst in authorship.get("institutions", []):
                        inst_name = inst.get("display_name", "")
                        if inst_name and inst_name not in institutions:
                            institutions.append(inst_name)

                paper = {
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "published": item.get("publication_date", ""),
                    "source": "openalex",
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "pdf_url": pdf_url,
                    "citations": item.get("cited_by_count", 0),
                    "institutions": institutions,
                }

                if title and _is_relevant(title, abstract):
                    papers.append(paper)

            logger.info(f"  Found {len(papers)} papers on OpenAlex")
            return papers

        except requests.exceptions.ReadTimeout:
            logger.warning(f"  OpenAlex request timed out (attempt {attempt+1}/{max_attempts})")
            continue
        except Exception as e:
            logger.error(f"  OpenAlex search failed for '{query}': {e}")
            return papers

    return papers
