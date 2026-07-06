"""
Paper Bot 配置文件
"""
import os
from datetime import datetime

# === Anthropic API (论文总结用) ===
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://test-llm-gateway.galbot.work")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

# === 保存路径 ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# === 类别配置 ===
# 每个类别每天的论文数量
PAPERS_PER_CATEGORY = 2

# 类别定义：名称 -> (搜索关键词列表, 必要关键词列表)
CATEGORIES = {
    "main": {
        "description": "具身智能相关文章（必须是机器人操控，排除纯LLM）",
        "queries": [
            '"embodied AI" robot manipulation',
            '"embodied intelligence" robot learning',
            "embodied agent robot manipulation",
            "vision-language-action robot",
            "generalist robot policy manipulation",
            "robot foundation model manipulation",
        ],
        "required_keywords": [
            # 必须包含机器人操控词
            "robot manipulation", "robotic manipulation", "robot grasping",
            "robotic grasping", "robot gripper", "manipulation robot",
            "grasping robot", "gripper", "robot arm",
            "vision-language-action", "vla policy", "robot policy",
            "generalist robot", "robot foundation model",
        ],
        "deprioritize_keywords": [
            # 运动类
            "locomotion", "legged robot", "quadruped", "walking robot",
            # 自动驾驶
            "self-driving", "autonomous driving", "vehicle planning",
            # 纯LLM/语言模型训练（强烈排除）
            "language model", "llm", "large language model", "NLP",
            "rlvr", "verifiable rewards", "reward hacking",
            "reasoning model", "llm training", "text generation",
            # 图像生成
            "diffusion model", "image generation", "text-to-image", "text-to-video",
            # 博弈论/多智能体
            "game theory", "nash equilibrium", "multi-agent game", "auction", "bidding",
            # 其他不相关领域
            "brain decoding", "fMRI", "medical imaging", "drug discovery",
        ],
    },
    "egobench": {
        "description": "灵巧手操作、人类视频训练、仿真评测、触觉策略",
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
        ],
        "required_keywords": [
            "dexterous", "dexterity", "multi-finger", "anthropomorphic hand",
            "in-hand manipulation", "robotic hand", "hand manipulation",
            "bimanual", "two-arm", "dual-arm",
            "tactile", "touch", "haptic", "force sensing",
            "teleoperation", "teleoperated", "human demonstration",
            "egocentric", "ego-centric", "human video",
            "sim2real", "dexterous simulation",
            "manipulation policy", "control policy",
        ],
        "deprioritize_keywords": [
            # 腿式机器人/运动（强烈排除）
            "locomotion", "loco-manipulation", "legged robot", "quadruped",
            "pedipulation", "foot manipulation", "walking robot", "bipedal",
            "buoyancy-assisted", "morphology design",
            # 自动驾驶
            "self-driving", "autonomous driving",
            # 纯语言模型
            "language model", "llm", "large language model",
            # 图像生成
            "diffusion model", "image generation",
            # 其他
            "brain decoding", "fMRI", "NLP",
        ],
    },
    "tacvla": {
        "description": "触觉感知+机器人操作（必须包含tactile/haptic等明确触觉技术）",
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
            # 必须包含核心触觉词
            "tactile sensing", "tactile feedback", "tactile sensor",
            "gelsight", "tactile glove",
            "visuo-tactile", "visual-tactile",
            "haptic sensing", "haptic feedback",
            "touch sensor", "touch-based manipulation",
            # 并且必须包含机器人操作词
            "robot manipulation", "robotic grasping", "robot gripper",
        ],
        "deprioritize_keywords": [
            # 自动驾驶
            "self-driving", "autonomous driving", "autonomous vehicle", "av", "car", "drone",
            # 纯LLM/语言模型
            "language model", "llm", "large language model", "agentic", "context-aware rl",
            "neural dynamics", "variational dynamics",
            # 腿式机器人/运动
            "locomotion", "legged robot", "quadruped", "walking", "floating-base",
            # 导航/无人机
            "navigation", "drone racing", "path planning",
            # 脑机接口/EEG
            "brain-computer interface", "bci", "eeg", "neuro",
            # 其他不相关
            "diffusion model", "image generation", "brain decoding", "fMRI",
            "medical imaging", "drug discovery", "world model",
        ],
    },
}

# === 检索源配置 ===
ARXIV_MAX_RESULTS_PER_QUERY = 5
SEMANTIC_SCHOLAR_LIMIT = 3

# 大型研究机构（用于优先级加分）
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