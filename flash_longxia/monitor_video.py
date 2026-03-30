#!/usr/bin/env python3
"""
视频生成监控脚本
每分钟检查 output 目录，发现新视频后写入通知队列
由 heartbeat 读取队列并发送微信通知
"""
import os
import json
from pathlib import Path

# 配置
OUTPUT_DIR = Path(__file__).parent / "output"
STATE_FILE = Path(__file__).parent / ".monitor_state.json"
QUEUE_FILE = Path(__file__).parent / ".video_notify_queue.json"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"latest_file": None, "notified": False}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

def get_latest_video():
    videos = list(OUTPUT_DIR.glob("*.mp4"))
    if not videos:
        return None
    return max(videos, key=lambda p: p.stat().st_mtime)

def main():
    state = load_state()
    latest_video = get_latest_video()
    
    if latest_video is None:
        return
    
    latest_name = latest_video.name
    video_path = str(latest_video.absolute())
    
    # 发现新视频
    if state.get("latest_file") != latest_name:
        print(f"发现新视频: {latest_name}")
        state["latest_file"] = latest_name
        state["notified"] = False
        save_state(state)
        
        # 写入通知队列
        queue = []
        if QUEUE_FILE.exists():
            queue = json.loads(QUEUE_FILE.read_text())
        
        # 检查是否已在队列中
        if not any(q.get("file") == latest_name for q in queue):
            queue.append({
                "file": latest_name,
                "path": video_path,
                "mtime": latest_video.stat().st_mtime
            })
            QUEUE_FILE.write_text(json.dumps(queue, indent=2))
            print(f"已加入通知队列: {latest_name}")
    
    # 标记已处理
    if not state.get("notified"):
        state["notified"] = True
        save_state(state)

if __name__ == "__main__":
    main()