#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轮询视频生成状态，完成后自动通知用户
"""
import json
import os
import sys
import time
import requests
from pathlib import Path

TASK_FILE = Path(__file__).parent / "pending_tasks.json"
OUTPUT_DIR = Path(__file__).parent / "output"

_STATUS_SUCCESS = ("2", 2, "completed", "success", "SUCCESS")
_STATUS_FAILED = ("3", 3, "failed", "FAILED", "error", "ERROR")

def fetch_video_by_id(base_url, session, video_id):
    """GET getById?id=，成功时返回 data 字典"""
    url = f"{base_url}/api/v1/aiMediaGenerations/getById"
    try:
        resp = session.get(url, params={"id": video_id}, timeout=15)
        data = resp.json()
        if data.get("code") in (200, 0):
            return data.get("data")
        return None
    except Exception:
        return None

def get_video_url(record):
    """从记录中提取视频 URL"""
    return (
        record.get("videoUrl")
        or record.get("mediaUrl")
        or record.get("url")
        or record.get("videoPath")
        or record.get("path")
    )

def download_video(video_url, output_dir, filename, session):
    """下载视频到本地"""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    resp = session.get(video_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return os.path.abspath(path)

def notify_user(video_path, task_info):
    """通知用户视频已生成完成"""
    # 写入通知文件，主会话会检查这个文件
    notify_file = Path(__file__).parent / "completed_notification.json"
    notification = {
        "type": "video_completed",
        "video_path": video_path,
        "task_id": task_info.get("task_id"),
        "image_path": task_info.get("image_path"),
        "message": "视频生成完成！请确认是否发布～"
    }
    with open(notify_file, "w", encoding="utf-8") as f:
        json.dump(notification, f, indent=2, ensure_ascii=False)
    print(f"[通知] 视频已完成：{video_path}")
    print(f"[通知] 通知文件已写入：{notify_file}")

def poll_task(task_info, session):
    """轮询单个任务"""
    task_id = task_info.get("task_id")
    base_url = task_info.get("base_url")
    poll_interval = 30  # 30 秒轮询一次
    max_wait_minutes = 30
    max_elapsed = max_wait_minutes * 60
    elapsed = 0
    attempt = 0
    
    print(f"[轮询] 开始检查任务 {task_id}...")
    
    while elapsed < max_elapsed:
        attempt += 1
        record = fetch_video_by_id(base_url, session, task_id)
        
        if record:
            status = record.get("status") or record.get("videoStatus")
            print(f"[轮询] 第{attempt}次：status={status}")
            
            if status in _STATUS_SUCCESS:
                print(f"[完成] 任务 {task_id} 已完成！")
                video_url = get_video_url(record)
                if video_url:
                    filename = f"video_{task_id}_{int(time.time())}.mp4"
                    video_path = download_video(video_url, str(OUTPUT_DIR), filename, session)
                    notify_user(video_path, task_info)
                    return True
            elif status in _STATUS_FAILED:
                print(f"[失败] 任务 {task_id} 失败")
                return False
        
        elapsed += poll_interval
        time.sleep(poll_interval)
    
    print(f"[超时] 任务 {task_id} 轮询超时")
    return False

def main():
    if not TASK_FILE.exists():
        print("[INFO] 没有待处理的任务")
        return
    
    # 读取任务列表
    with open(TASK_FILE, "r", encoding="utf-8") as f:
        pending_tasks = json.load(f)
    
    if not pending_tasks:
        print("[INFO] 任务列表为空")
        return
    
    print(f"[INFO] 发现 {len(pending_tasks)} 个待处理任务")
    
    # 处理每个任务
    completed_indices = []
    for i, task_info in enumerate(pending_tasks):
        session = requests.Session()
        session.headers.update({
            "token": task_info.get("token"),
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        
        success = poll_task(task_info, session)
        if success or task_info.get("status") in _STATUS_FAILED:
            completed_indices.append(i)
    
    # 移除已完成的任务
    if completed_indices:
        remaining_tasks = [t for i, t in enumerate(pending_tasks) if i not in completed_indices]
        with open(TASK_FILE, "w", encoding="utf-8") as f:
            json.dump(remaining_tasks, f, indent=2, ensure_ascii=False)
        print(f"[INFO] 已移除 {len(completed_indices)} 个已完成任务")

if __name__ == "__main__":
    main()
