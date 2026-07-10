"""
Feishu push module — send PDF files to Feishu group
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
    """Get Feishu tenant_access_token"""
    resp = requests.post(
        FEISHU_AUTH_URL,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"Failed to get token: {data}")
    return data["tenant_access_token"]


def upload_pdf(token: str, pdf_path: str, file_name: str) -> str:
    """Upload PDF file, returns file_key"""
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
        raise Exception(f"File upload failed: {data}")
    return data["data"]["file_key"]


def send_file_message(token: str, file_key: str) -> dict:
    """Send file message to group"""
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
        raise Exception(f"Message send failed: {data}")
    return data["data"]


def send_text_message(token: str, text: str) -> dict:
    """Send text message to group"""
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
        raise Exception(f"Message send failed: {data}")
    return data["data"]


def extract_pdf_link_from_summary(summary_path: str) -> str:
    """Extract PDF link from summary.md"""
    if not summary_path or not os.path.exists(summary_path):
        return None
    with open(summary_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Look for **PDF**: line
    for line in content.split("\n"):
        if "**PDF**:" in line or "**Source**:" in line:
            # Extract link
            import re
            match = re.search(r'https?://[^\s\)]+', line)
            if match:
                return match.group(0)
    return None


def push_pdf_to_feishu(pdf_path: str, display_name: str) -> dict:
    """Push a single PDF to Feishu group"""
    token = get_tenant_access_token()
    file_key = upload_pdf(token, pdf_path, display_name)
    result = send_file_message(token, file_key)
    print(f"Sent: {display_name}")
    return result


def get_paper_folders(date_str: str) -> list:
    """Get all paper folders for a given date"""
    # date_str format: "2026/04/23"
    date_dir = Path(PAPER_OUTPUT_DIR) / date_str
    if not date_dir.exists():
        return []

    folders = []
    for folder in sorted(date_dir.iterdir()):
        if folder.is_dir():
            pdf_path = folder / "paper.pdf"
            summary_path = folder / "summary.md"
            if pdf_path.exists():
                # Extract title from folder name (remove index prefix)
                folder_name = folder.name
                # Format: 001-title-of-paper
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
    """Push all papers for a given date to Feishu group"""
    folders = get_paper_folders(date_str)
    if not folders:
        print(f"No papers found for {date_str}")
        return 0

    # Parse date for filename
    date_parts = date_str.split("/")
    date_prefix = f"{date_parts[0][-2:]}{date_parts[1]}{date_parts[2]}"  # 260423

    # Feishu file upload limit (30MB)
    MAX_FILE_SIZE = 30 * 1024 * 1024

    token = get_tenant_access_token()
    count = 0
    for folder in folders:
        pdf_path = folder["pdf_path"]

        # Filename format: 260423-title-of-paper.pdf
        display_name = f"{date_prefix}-{folder['title_part']}.pdf"

        # Check file size
        file_size = os.path.getsize(pdf_path)
        if file_size > MAX_FILE_SIZE:
            # File too large, send link instead
            pdf_link = extract_pdf_link_from_summary(folder["summary_path"])
            if pdf_link:
                message = f"📄 {display_name} (File too large {file_size / 1024 / 1024:.1f}MB)\nDownload link: {pdf_link}"
                try:
                    send_text_message(token, message)
                    print(f"Sent link: {display_name}")
                    count += 1
                except Exception as e:
                    print(f"Failed to send link for {folder['folder_name']}: {e}")
            else:
                print(f"Skipping {folder['folder_name']}: File too large and no link found")
            continue

        try:
            file_key = upload_pdf(token, pdf_path, display_name)
            send_file_message(token, file_key)
            print(f"Sent: {display_name}")
            count += 1
        except Exception as e:
            print(f"Send failed for {folder['folder_name']}: {e}")

    return count


def push_yesterday_papers() -> int:
    """Push yesterday's papers"""
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%Y/%m/%d")
    print(f"Pushing papers for {date_str}...")
    return push_papers_for_date(date_str)


def push_all_past_papers(end_date_str: str = "2026/04/23") -> int:
    """Push all historical papers up to a given date"""
    output_dir = Path(PAPER_OUTPUT_DIR)
    count = 0

    # Iterate year directories
    for year_dir in sorted(output_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        year = year_dir.name

        # Iterate month directories
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            month = month_dir.name

            # Iterate day directories
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                day = day_dir.name

                date_str = f"{year}/{month}/{day}"

                # Only push papers up to end_date_str
                if date_str <= end_date_str:
                    print(f"\n--- Pushing {date_str} ---")
                    count += push_papers_for_date(date_str)

    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push paper PDFs to Feishu group")
    parser.add_argument("--date", type=str, help="Specific date, format: 2026/04/23")
    parser.add_argument("--yesterday", action="store_true", help="Push yesterday's papers")
    parser.add_argument("--all-past", action="store_true", help="Push all historical papers (up to 2026/04/23)")
    parser.add_argument("--end-date", type=str, default="2026/04/23", help="Cut-off date for historical papers")

    args = parser.parse_args()

    if args.date:
        push_papers_for_date(args.date)
    elif args.yesterday:
        push_yesterday_papers()
    elif args.all_past:
        push_all_past_papers(args.end_date)
    else:
        # Default: push yesterday's papers
        push_yesterday_papers()