#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮询视频生成状态，完成后自动下载并写入完成通知。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

from zhenlongxia_workflow import (
    _STATUS_FAILED,
    _STATUS_SUCCESS,
    _build_status_text,
    _extract_rep_status,
    _extract_video_url_from_rep_msg,
    download_video,
    fetch_video_by_id,
    get_video_url,
    load_config,
    load_saved_token,
)

TASK_FILE = Path(__file__).parent / "pending_tasks.json"
OUTPUT_DIR = Path(__file__).parent / "output"
NOTIFY_FILE = Path(__file__).parent / "completed_notification.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="轮询视频生成任务，完成后自动下载")
    parser.add_argument("task_id", nargs="?", help="任务 ID；未传时处理 pending_tasks.json")
    parser.add_argument("--token", dest="token", help="接口 Token；默认读取 token.txt")
    return parser.parse_args()


def build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "token": token,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    return session


def resolve_notify_settings() -> tuple[str | None, str | None]:
    """从环境变量或 config.yaml 读取通知配置。"""
    env_target = (os.getenv("FLASH_LONGXIA_WECHAT_TARGET") or os.getenv("OPENCLAW_WECHAT_TARGET") or "").strip()
    env_channel = (os.getenv("FLASH_LONGXIA_NOTIFY_CHANNEL") or "").strip()
    if env_target:
        return env_target, env_channel or None

    config = load_config()
    notify_cfg = config.get("notify", {}) or {}
    target = str(notify_cfg.get("wechat_target") or "").strip()
    channel = str(notify_cfg.get("channel") or "").strip()
    return (target or None, channel or None)


def send_wechat_notification_direct(video_path: str, task_id: str) -> bool:
    """直接发送微信通知，不依赖 cron。"""
    import subprocess

    wechat_target, notify_channel = resolve_notify_settings()
    if not wechat_target:
        print("[通知] 未配置微信目标，跳过直接发送")
        return False

    notify_text = f"""🦐 **视频生成完成通知**

✅ 任务 {task_id} 已完成

视频已下载完成，正在发送给您～

---
请说"**可以发布**"或"**确认发布**"，我会上传到视频号！"""
    
    # 先发送文本通知
    cmd_text = ["openclaw", "message", "send"]
    if notify_channel:
        cmd_text.extend(["--channel", notify_channel])
    cmd_text.extend([
        "--target", wechat_target,
        "--message", notify_text,
    ])

    try:
        result = subprocess.run(cmd_text, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"[✅] 文本通知已发送")
        else:
            print(f"[⚠️] 文本通知发送失败：{result.stderr}")
    except Exception as e:
        print(f"[⚠️] 文本通知发送异常：{e}")
    
    # 发送视频文件
    cmd_media = ["openclaw", "message", "send"]
    if notify_channel:
        cmd_media.extend(["--channel", notify_channel])
    cmd_media.extend([
        "--target", wechat_target,
        "--media", video_path,
        "--message", f"📹 视频文件：任务 {task_id}",
    ])

    try:
        result = subprocess.run(cmd_media, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(f"[✅] 视频文件已直接发送")
            return True
        else:
            print(f"[⚠️] 视频文件发送失败：{result.stderr}")
            return False
    except Exception as e:
        print(f"[⚠️] 视频文件发送异常：{e}")
        return False


def write_notification(video_path: str, task_info: dict) -> None:
    """写入完成通知并立即发送微信。"""
    task_id = task_info.get("task_id", "unknown")
    
    # 先尝试直接发送微信通知
    print(f"[通知] 尝试直接发送微信通知...")
    sent = send_wechat_notification_direct(video_path, task_id)
    
    if sent:
        print(f"[通知] 视频已完成并发送：{video_path}")
        # 写入已处理记录，避免 cron 重复发送
        PROCESSED_FILE = Path(__file__).parent / ".processed_notifications.json"
        processed = set()
        if PROCESSED_FILE.exists():
            try:
                processed = set(json.loads(PROCESSED_FILE.read_text(encoding='utf-8')))
            except:
                processed = set()
        processed.add(str(task_id))
        PROCESSED_FILE.write_text(
            json.dumps(list(processed), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        # 如果直接发送失败，写入文件等待 cron 处理
        notification = {
            "type": "video_completed",
            "video_path": video_path,
            "task_id": task_id,
            "image_path": task_info.get("image_path"),
            "message": "视频生成完成！请确认是否发布～",
        }
        
        # 读取现有通知队列（如果存在）
        notifications = []
        if NOTIFY_FILE.exists():
            try:
                data = json.loads(NOTIFY_FILE.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    notifications = data
                elif isinstance(data, dict):
                    notifications = [data]
            except json.JSONDecodeError:
                notifications = []
        
        # 追加新通知
        notifications.append(notification)
        
        # 写入队列
        NOTIFY_FILE.write_text(
            json.dumps(notifications, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[通知] 直接发送失败，已写入通知文件：{NOTIFY_FILE}（队列长度：{len(notifications)}）")


def poll_task(task_info: dict, session: requests.Session) -> bool:
    task_id = str(task_info.get("task_id") or "").strip()
    base_url = str(task_info.get("base_url") or "").rstrip("/")
    poll_interval = int(task_info.get("poll_interval") or 30)
    max_wait_minutes = int(task_info.get("max_wait_minutes") or 30)
    max_elapsed = max_wait_minutes * 60
    elapsed = 0
    attempt = 0

    if not task_id or not base_url:
        print(f"[错误] 任务信息不完整：{task_info}")
        return False

    print(f"[轮询] 开始检查任务 {task_id}...")

    while elapsed < max_elapsed:
        attempt += 1
        record = fetch_video_by_id(base_url, session, task_id)

        if record:
            status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
            rep_status = _extract_rep_status(record)
            print(f"[轮询] 第{attempt}次：{_build_status_text(record)}")

            # 红线 8：判断视频完成的唯一标准是 mediaUrl 有值！
            video_url = get_video_url(record)
            if not video_url:
                video_url = _extract_video_url_from_rep_msg(record)
                if video_url:
                    record["mediaUrl"] = record.get("mediaUrl") or video_url

            # 优先检查 mediaUrl，不管 status 是什么值
            if video_url:
                print(f"[完成] 任务 {task_id} 已完成 (mediaUrl 有值)")
                filename = f"{task_id}.mp4"
                video_path = download_video(video_url, str(OUTPUT_DIR), filename, session=session)
                write_notification(video_path, task_info)
                return True

            if status in _STATUS_SUCCESS or rep_status in _STATUS_SUCCESS:
                print(f"[完成] 任务 {task_id} 已完成 (status 判断)")
                if not video_url:
                    print(f"[错误] 任务 {task_id} 已完成但未找到视频地址")
                    return False
                filename = f"{task_id}.mp4"
                video_path = download_video(video_url, str(OUTPUT_DIR), filename, session=session)
                write_notification(video_path, task_info)
                return True

            if status in _STATUS_FAILED or rep_status in _STATUS_FAILED:
                print(f"[失败] 任务 {task_id} 失败")
                return False
        else:
            print(f"[轮询] 第{attempt}次：接口未返回任务数据")

        sleep_sec = min(poll_interval, max_elapsed - elapsed)
        if sleep_sec <= 0:
            break
        elapsed += sleep_sec
        time.sleep(sleep_sec)

    print(f"[超时] 任务 {task_id} 轮询超时")
    return False


def process_single_task(task_id: str, token: str | None) -> int:
    config = load_config()
    video_cfg = config.get("video", {}) or {}
    token_val = token or load_saved_token()
    if not token_val:
        print("[错误] 缺少 Token，请传 --token 或写入 token.txt")
        return 1

    task_info = {
        "task_id": task_id,
        "base_url": config["base_url"].rstrip("/"),
        "token": token_val,
        "poll_interval": video_cfg.get("poll_interval", 30),
        "max_wait_minutes": video_cfg.get("max_wait_minutes", 30),
    }
    session = build_session(token_val)
    success = poll_task(task_info, session)
    return 0 if success else 1


def process_pending_tasks() -> int:
    if not TASK_FILE.exists():
        print("[INFO] 没有待处理的任务")
        return 0

    data = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    if not data:
        print("[INFO] 任务列表为空")
        return 0

    # 兼容两种格式：对象（单个任务）或数组（多个任务）
    if isinstance(data, dict):
        pending_tasks = [data]
        print("[INFO] 检测到单个任务格式（对象）")
    elif isinstance(data, list):
        pending_tasks = data
        print(f"[INFO] 检测到任务列表格式（数组），共 {len(pending_tasks)} 个任务")
    else:
        print(f"[错误] 任务文件格式错误：{type(data)}")
        return 1

    if not pending_tasks:
        print("[INFO] 任务列表为空")
        return 0

    print(f"[INFO] 开始处理 {len(pending_tasks)} 个待处理任务")
    completed_indices: list[int] = []

    for idx, task_info in enumerate(pending_tasks):
        token = task_info.get("token")
        if not token:
            print(f"[错误] 任务缺少 token，跳过：{task_info}")
            continue
        session = build_session(token)
        success = poll_task(task_info, session)
        if success:
            completed_indices.append(idx)

    if completed_indices:
        remaining = [task for idx, task in enumerate(pending_tasks) if idx not in completed_indices]
        # 如果只剩一个任务，保存为对象格式；否则保存为数组
        if len(remaining) == 1:
            TASK_FILE.write_text(json.dumps(remaining[0], indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            TASK_FILE.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[INFO] 已移除 {len(completed_indices)} 个已完成任务")

    return 0


def main() -> int:
    args = parse_args()

    if args.task_id:
        return process_single_task(args.task_id, args.token)

    return process_pending_tasks()


if __name__ == "__main__":
    sys.exit(main())
