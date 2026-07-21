"""
Paper Bot configuration file
"""
import os
from datetime import datetime

# === Anthropic API (for paper summarization) ===
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://test-llm-gateway.galbot.work")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

# === Output paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# === Category configuration ===
# Number of papers per category per day
PAPERS_PER_CATEGORY = 2

# Category definitions: name -> (search queries list, required keywords list)
CATEGORIES = {
    "main": {
        "description": "Embodied AI articles (must be robot manipulation, excluding pure LLM)",
        "queries": [
            '"embodied AI" robot manipulation',
            '"embodied intelligence" robot learning',
            "embodied agent robot manipulation",
            "vision-language-action robot",
            "generalist robot policy manipulation",
            "robot foundation model manipulation",
        ],
        "required_keywords": [
            # Must include robot manipulation terms
            "robot manipulation", "robotic manipulation", "robot grasping",
            "robotic grasping", "robot gripper", "manipulation robot",
            "grasping robot", "gripper", "robot arm",
            "vision-language-action", "vla policy", "robot policy",
            "generalist robot", "robot foundation model",
        ],
        "deprioritize_keywords": [
            # Locomotion-related
            "locomotion", "legged robot", "quadruped", "walking robot",
            # Autonomous driving
            "self-driving", "autonomous driving", "vehicle planning",
            # Pure LLM / language model training (strongly excluded)
            "language model", "llm", "large language model", "NLP",
            "rlvr", "verifiable rewards", "reward hacking",
            "reasoning model", "llm training", "text generation",
            # Image generation
            "diffusion model", "image generation", "text-to-image", "text-to-video",
            # Game theory / multi-agent
            "game theory", "nash equilibrium", "multi-agent game", "auction", "bidding",
            # Other unrelated fields
            "brain decoding", "fMRI", "medical imaging", "drug discovery",
        ],
    },
    "egobench": {
        "description": "Dexterous hand manipulation, human video training, simulation evaluation, tactile policies",
        "queries": [
            '"dexterous hand manipulation" robot',
            '"robotic hand" manipulation learning',
            "bimanual dexterous manipulation",
            "human video robot learning",
            "ego4k robot manipulation",
            "egocentric video robot",
            "dexterous manipulation simulation",
            "tactile policy robot learning",
            "teleoperation robot manipulation",
            "multi-finger robotic grasping",
            # real2sim / real2sim2real simulation training
            '"real2sim2real" robot',
            "real2sim robot manipulation",
            "real-to-sim robot learning",
            # scene reconstruction / simulation evaluation
            "scene reconstruction robot manipulation",
            "simulation benchmark manipulation",
            "egocentric data robot",
        ],
        "required_keywords": [
            "dexterous", "dexterity", "multi-finger", "anthropomorphic hand",
            "in-hand manipulation", "robotic hand", "hand manipulation",
            "bimanual", "two-arm", "dual-arm",
            "tactile", "touch", "haptic", "force sensing",
            "teleoperation", "teleoperated", "human demonstration",
            "egocentric", "ego-centric", "human video", "egocentric data",
            "sim2real", "dexterous simulation",
            # real2sim / scene reconstruction / simulation evaluation
            "real2sim", "real2sim2real", "real-to-sim",
            "scene reconstruction", "3d reconstruction",
            "simulation benchmark", "simulation evaluation",
            "manipulation policy", "control policy",
        ],
        "deprioritize_keywords": [
            # Legged robots / locomotion (strongly excluded)
            "locomotion", "loco-manipulation", "legged robot", "quadruped",
            "pedipulation", "foot manipulation", "walking robot", "bipedal",
            "buoyancy-assisted", "morphology design",
            # Autonomous driving
            "self-driving", "autonomous driving",
            # Pure language models
            "language model", "llm", "large language model",
            # Image generation
            "diffusion model", "image generation",
            # Other
            "brain decoding", "fMRI", "NLP",
        ],
    },
    "tacvla": {
        "description": "Tactile perception + robot manipulation (must include explicit tactile tech like tactile/haptic)",
        "queries": [
            '"tactile sensing" robot manipulation',
            '"tactile feedback" robotic grasping',
            '"visuo-tactile" robot manipulation',
            '"gelsight" robot',
            '"haptic feedback" robot gripper',
            '"tactile sensor" robotic',
            "tactile policy robot learning",
            "tactile perception robot grasping",
            "touch-based robot manipulation",
            "tactile-based manipulation",
        ],
        "required_keywords": [
            # Must include core tactile terms
            "tactile sensing", "tactile feedback", "tactile sensor",
            "gelsight", "tactile glove",
            "visuo-tactile", "visual-tactile",
            "haptic sensing", "haptic feedback",
            "touch sensor", "touch-based manipulation",
            # And must include robot manipulation terms
            "robot manipulation", "robotic grasping", "robot gripper",
        ],
        "deprioritize_keywords": [
            # Autonomous driving
            "self-driving", "autonomous driving", "autonomous vehicle", "av", "car", "drone",
            # Pure LLM / language models
            "language model", "llm", "large language model", "agentic", "context-aware rl",
            "neural dynamics", "variational dynamics",
            # Legged robots / locomotion
            "locomotion", "legged robot", "quadruped", "walking", "floating-base",
            # Navigation / drones
            "navigation", "drone racing", "path planning",
            # BCI / EEG
            "brain-computer interface", "bci", "eeg", "neuro",
            # Other unrelated
            "diffusion model", "image generation", "brain decoding", "fMRI",
            "medical imaging", "drug discovery", "world model",
        ],
    },
}

# === Search source configuration ===
ARXIV_MAX_RESULTS_PER_QUERY = 5
SEMANTIC_SCHOLAR_LIMIT = 3

# Large research institutions (for priority bonus)
INSTITUTION_KEYWORDS = [
    "MIT", "Stanford", "CMU", "Berkeley", "Harvard", "Google",
    "DeepMind", "Meta", "Microsoft", "NVIDIA", "ETH", "Oxford", "Cambridge",
    "Imperial", "MPI", "Max Planck", "UC Berkeley", "Columbia",
    "Princeton", "Cornell", "UPenn", "Northwestern", "Caltech",
    "UCLA", "UIUC", "Georgia Tech", "Univ. of Michigan",
    "Tsinghua", "Peking", "SJTU", "Zhejiang", "CUHK",
    "HKUST", "NUS", "NTU", "Tokyo", "Osaka",
    "KAIST", "Seoul National", "TUM", "EPFL", "KTH",
    "TU Delft", "Toronto", "Montreal", "Mila", "Vector",
]

# === 论文总结 prompt ===
SUMMARY_PROMPT = """你是一个机器人研究助手。请阅读以下论文内容，用中文输出简洁的技术总结。

要求:
1. 所有内容尽量用中文输出
2. 标题可以保留英文
3. 总结涵盖: 研究背景/动机、核心方法/技术、实验设置、主要结果/贡献
4. 如果论文涉及以下方向请高亮: 灵巧手、布料/可变形物体操纵、触觉感知、视觉控制、双臂协作、卡片/薄物体操纵
5. 提到作者和所属机构
6. 不超过400字，具体且有技术深度

格式:
**标题**: [英文标题]
**作者/机构**: [作者, 机构]
**总结**: [中文总结]
**关键词**: [3-5个关键词]
**相关性**: [与本研究方向的相关性评分 1-10 及理由]
**来源**: [论文URL，由系统自动填充]
**PDF**: [PDF下载链接，由系统自动填充]
"""