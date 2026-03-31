#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频生成轮询监控脚本
每 30 秒检查一次，最多 30 分钟
"""

import os
import sys
import time

from zhenlongxia_workflow import (
    _extract_video_url_from_rep_msg,
    fetch_video_by_id,
    get_video_url,
    load_config,
    load_saved_token,
    requests,
)

TASK_ID = "1719"
BASE_URL = "http://123.56.58.223:8081"
TOKEN = "4ff2c1aa-384a-4c48-8fc1-e674c5f65219"
OUTPUT_DIR = "/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/output"
MAX_ATTEMPTS = 60  # 30 分钟，每 30 秒一次

def poll_task():
    """轮询任务状态"""
    config = load_config()
    token = load_saved_token()
    if not token:
        print("缺少 token.txt，无法查询任务状态")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "token": token,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })

    for attempt in range(1, MAX_ATTEMPTS + 1):
        time.sleep(30)

        try:
            record = fetch_video_by_id(config["base_url"].rstrip("/"), session, TASK_ID)
            if not record:
                print(f"任务 {TASK_ID} 暂无数据 (第{attempt}次查询)")
                continue

            status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
            video_url = get_video_url(record) or _extract_video_url_from_rep_msg(record)

            if video_url:
                download_video(video_url)
                print(f"视频下载完成：{OUTPUT_DIR}/{TASK_ID}.mp4")
                sys.exit(0)

            if str(status) in {"3", "failed", "FAILED", "error", "ERROR"}:
                print(f"任务 {TASK_ID} 生成失败")
                sys.exit(1)

            print(f"任务 {TASK_ID} 状态：{status} (第{attempt}次查询)")
        except Exception as e:
            print(f"查询异常：{e}")
    
    print(f"任务 {TASK_ID} 轮询超时")
    sys.exit(1)

def download_video(video_url):
    """下载视频"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{TASK_ID}.mp4")
    
    response = requests.get(video_url, stream=True)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path
    return None

if __name__ == "__main__":
    print(f"开始轮询任务 {TASK_ID}...")
    poll_task()
