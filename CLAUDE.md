# Paper Bot - 论文自动爬取系统

## 项目概述

自动爬取最新机器人相关论文，按类别分类存储，每天早上8点定时运行。

## 目录结构

```
paper/
├── config.py          # 类别配置、关键词、排除词
├── src/
│   ├── main.py        # 主程序入口
│   ├── search/        # arXiv和Semantic Scholar检索
│   ├── download/      # PDF下载
│   ├── read/          # 论文总结（调用LLM API）
│   └── organize/      # 文件组织
├── output/
│   ├── main/          # 具身智能相关
│   ├── egobench/      # 灵巧手、仿真评测、触觉策略
│   ├── tacvla/        # 触觉+机器人操作（核心：必须包含触觉关键词）
│   └── processed_papers.json  # 去重历史
├── run.sh             # 运行脚本
└── feishu/            # 飞书推送（可选）
```

## 类别定义

### main - 具身智能
- 搜索关键词：embodied AI, VLA, vision-language-action, robot foundation model
- 必须包含：robot/manipulation/gripper + embodied/vla相关词

### egobench - 灵巧手/仿真/视频训练
- 搜索关键词：dexterous hand, bimanual, teleoperation, egocentric video, tactile policy
- 必须包含：dexterous/bimanual/multi-finger/tactile/teleoperation等核心词
- 排除：四足机器人、行走、pedipulation、buoyancy-assisted

### tacvla - 触觉+机器人操作
- **核心定位**：使用触觉感知进行机器人操作
- 搜索关键词：tactile sensing, visuo-tactile, haptic feedback, gelsight, force sensing
- **硬性要求**：必须同时包含触觉词(tactile/touch/haptic/gelsight)和机器人词(robot/manipulation/gripper)
- 排除：LLM、自动驾驶、脑机接口、导航、无人机等

## 定时任务

```bash
# crontab配置：每天早上8点
0 8 * * * /home/galbot/chenyuxing/app/claude_code/paper/run.sh >> /home/galbot/chenyuxing/app/claude_code/paper/output/cron.log 2>&1
```

## 运行方式

```bash
# 手动运行
cd paper && ./run.sh

# 或直接运行Python
conda activate agent312
python src/main.py

## 环境安装

```bash
conda activate agent312
pip install -r requirements.txt
```
```

## 注意事项

1. 每个类别每天爬取2篇论文
2. 论文存储路径：output/category/yyyy/mm/dd/NNN-title/
3. 每篇论文包含：paper.pdf + summary.md
4. API rate limit问题可能导致运行时间较长
5. **tacvla类别必须严格过滤触觉相关**，不能混入LLM/导航等不相关内容