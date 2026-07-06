"""
飞书推送模块 - 发送 PDF 文件到飞书群
"""
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_CHAT_ID,
    FEISHU_AUTH_URL,
    FEISHU_UPLOAD_URL,
    FEISHU_MESSAGE_URL,
    PAPER_OUTPUT_DIR,
)


def get_tenant_access_token():
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        FEISHU_AUTH_URL,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def upload_pdf(token: str, pdf_path: str, file_name: str) -> str:
    """上传 PDF 文件，返回 file_key"""
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            FEISHU_UPLOAD_URL,
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_type": "pdf",
                "file_name": file_name,
            },
            files={"file": f},
        )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"上传文件失败: {data}")
    return data["data"]["file_key"]


def send_file_message(token: str, file_key: str) -> dict:
    """发送文件消息到群"""
    resp = requests.post(
        f"{FEISHU_MESSAGE_URL}?receive_id_type=chat_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": FEISHU_CHAT_ID,
            "msg_type": "file",
            "content": f'{{"file_key":"{file_key}"}}',
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"发送消息失败: {data}")
    return data["data"]


def send_text_message(token: str, text: str) -> dict:
    """发送文本消息到群"""
    import json
    resp = requests.post(
        f"{FEISHU_MESSAGE_URL}?receive_id_type=chat_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": FEISHU_CHAT_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"发送消息失败: {data}")
    return data["data"]


def extract_pdf_link_from_summary(summary_path: str) -> str:
    """从 summary.md 中提取 PDF 链接"""
    if not summary_path or not os.path.exists(summary_path):
        return None
    with open(summary_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 查找 **PDF**: 行
    for line in content.split("\n"):
        if "**PDF**:" in line or "**来源**:" in line:
            # 提取链接
            import re
            match = re.search(r'https?://[^\s\)]+', line)
            if match:
                return match.group(0)
    return None


def push_pdf_to_feishu(pdf_path: str, display_name: str) -> dict:
    """推送单个 PDF 到飞书群"""
    token = get_tenant_access_token()
    file_key = upload_pdf(token, pdf_path, display_name)
    result = send_file_message(token, file_key)
    print(f"已发送: {display_name}")
    return result


def get_paper_folders(date_str: str) -> list:
    """获取指定日期的所有论文文件夹"""
    # date_str 格式: "2026/04/23"
    date_dir = Path(PAPER_OUTPUT_DIR) / date_str
    if not date_dir.exists():
        return []

    folders = []
    for folder in sorted(date_dir.iterdir()):
        if folder.is_dir():
            pdf_path = folder / "paper.pdf"
            summary_path = folder / "summary.md"
            if pdf_path.exists():
                # 从文件夹名提取标题（去掉序号前缀）
                folder_name = folder.name
                # 格式: 001-title-of-paper
                parts = folder_name.split("-", 1)
                title_part = parts[1] if len(parts) > 1 else folder_name
                folders.append({
                    "pdf_path": str(pdf_path),
                    "folder_name": folder_name,
                    "title_part": title_part,
                    "summary_path": str(summary_path) if summary_path.exists() else None,
                })
    return folders


def push_papers_for_date(date_str: str) -> int:
    """推送指定日期的所有论文到飞书群"""
    folders = get_paper_folders(date_str)
    if not folders:
        print(f"没有找到 {date_str} 的论文")
        return 0

    # 解析日期用于文件名
    date_parts = date_str.split("/")
    date_prefix = f"{date_parts[0][-2:]}{date_parts[1]}{date_parts[2]}"  # 260423

    # 飞书文件上传限制 (30MB)
    MAX_FILE_SIZE = 30 * 1024 * 1024

    token = get_tenant_access_token()
    count = 0
    for folder in folders:
        pdf_path = folder["pdf_path"]

        # 文件名格式: 260423-title-of-paper.pdf
        display_name = f"{date_prefix}-{folder['title_part']}.pdf"

        # 检查文件大小
        file_size = os.path.getsize(pdf_path)
        if file_size > MAX_FILE_SIZE:
            # 文件过大，发送链接
            pdf_link = extract_pdf_link_from_summary(folder["summary_path"])
            if pdf_link:
                message = f"📄 {display_name} (文件过大 {file_size / 1024 / 1024:.1f}MB)\n下载链接: {pdf_link}"
                try:
                    send_text_message(token, message)
                    print(f"已发送链接: {display_name}")
                    count += 1
                except Exception as e:
                    print(f"发送链接失败 {folder['folder_name']}: {e}")
            else:
                print(f"跳过 {folder['folder_name']}: 文件过大且未找到链接")
            continue

        try:
            file_key = upload_pdf(token, pdf_path, display_name)
            send_file_message(token, file_key)
            print(f"已发送: {display_name}")
            count += 1
        except Exception as e:
            print(f"发送失败 {folder['folder_name']}: {e}")

    return count


def push_yesterday_papers() -> int:
    """推送昨天的论文"""
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%Y/%m/%d")
    print(f"推送 {date_str} 的论文...")
    return push_papers_for_date(date_str)


def push_all_past_papers(end_date_str: str = "2026/04/23") -> int:
    """推送截止到指定日期的所有历史论文"""
    output_dir = Path(PAPER_OUTPUT_DIR)
    count = 0

    # 遍历年份目录
    for year_dir in sorted(output_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        year = year_dir.name

        # 遍历月份目录
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            month = month_dir.name

            # 遍历日期目录
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                day = day_dir.name

                date_str = f"{year}/{month}/{day}"

                # 只推送截止到 end_date_str 的论文
                if date_str <= end_date_str:
                    print(f"\n--- 推送 {date_str} ---")
                    count += push_papers_for_date(date_str)

    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="推送论文 PDF 到飞书群")
    parser.add_argument("--date", type=str, help="指定日期，格式: 2026/04/23")
    parser.add_argument("--yesterday", action="store_true", help="推送昨天的论文")
    parser.add_argument("--all-past", action="store_true", help="推送所有历史论文（截止到 2026/04/23）")
    parser.add_argument("--end-date", type=str, default="2026/04/23", help="历史论文截止日期")

    args = parser.parse_args()

    if args.date:
        push_papers_for_date(args.date)
    elif args.yesterday:
        push_yesterday_papers()
    elif args.all_past:
        push_all_past_papers(args.end_date)
    else:
        # 默认推送昨天的论文
        push_yesterday_papers()