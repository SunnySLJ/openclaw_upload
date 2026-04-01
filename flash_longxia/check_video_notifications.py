#!/usr/bin/env python3
"""
视频完成通知检查脚本
由心跳调用，读取 completed_notification.json 并发送微信通知
"""
import json
import os
import sys
import subprocess
from pathlib import Path

from zhenlongxia_workflow import load_config

NOTIFY_FILE = Path(__file__).parent / "completed_notification.json"
PROCESSED_FILE = Path(__file__).parent / ".processed_notifications.json"

def load_processed():
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()

def save_processed(processed):
    PROCESSED_FILE.write_text(json.dumps(list(processed)))


def resolve_notify_settings():
    env_target = (os.getenv("FLASH_LONGXIA_WECHAT_TARGET") or os.getenv("OPENCLAW_WECHAT_TARGET") or "").strip()
    env_channel = (os.getenv("FLASH_LONGXIA_NOTIFY_CHANNEL") or "").strip()
    if env_target:
        return env_target, env_channel or None

    config = load_config()
    notify_cfg = config.get("notify", {}) or {}
    target = str(notify_cfg.get("wechat_target") or "").strip()
    channel = str(notify_cfg.get("channel") or "").strip()
    return (target or None, channel or None)


def send_wechat_notification(task_id, video_path, message):
    """发送通知到当前会话"""
    wechat_target, notify_channel = resolve_notify_settings()
    if not wechat_target:
        print("[通知] 未配置微信目标，跳过发送")
        return False

    notify_text = f"""🦐 **视频生成完成通知**

✅ 任务 {task_id} 已完成

{message}

---
请说"**可以发布**"或"**确认发布**"，我会上传到四个平台！"""
    
    # 发送文本通知
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
        result = subprocess.run(cmd_media, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"[✅] 视频文件已发送")
            return True
        else:
            print(f"[⚠️] 视频文件发送失败：{result.stderr}")
            return False
    except Exception as e:
        print(f"[⚠️] 视频文件发送异常：{e}")
        return False

def main():
    if not NOTIFY_FILE.exists():
        print("[INFO] 没有待处理的通知")
        return 0
    
    try:
        data = json.loads(NOTIFY_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        print("[错误] 通知文件格式错误")
        return 1
    
    # 兼容两种格式：单个对象或数组队列
    if isinstance(data, dict):
        notifications = [data]
    elif isinstance(data, list):
        notifications = data
    else:
        print(f"[错误] 通知格式错误：{type(data)}")
        return 1
    
    if not notifications:
        print("[INFO] 通知队列为空")
        return 0
    
    processed = load_processed()
    remaining = []
    sent_count = 0
    
    for notification in notifications:
        task_id = notification.get("task_id")
        video_path = notification.get("video_path")
        
        if not task_id or not video_path:
            print(f"[错误] 通知信息不完整，跳过：{notification}")
            continue
        
        # 检查是否已处理
        if task_id in processed:
            print(f"[INFO] 任务 {task_id} 已通知过，跳过")
            continue
        
        print(f"[通知] 发现待通知任务：{task_id}")
        print(f"[通知] 视频路径：{video_path}")
        
        # 发送微信通知
        success = send_wechat_notification(
            task_id,
            video_path,
            notification.get('message', '视频生成完成！')
        )
        
        if success:
            processed.add(task_id)
            sent_count += 1
        else:
            remaining.append(notification)
    
    # 保存已处理记录
    save_processed(processed)
    
    # 更新通知文件（保留未发送的）
    if remaining:
        NOTIFY_FILE.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"[INFO] 剩余 {len(remaining)} 个待发送通知")
    else:
        NOTIFY_FILE.unlink()
        print(f"[完成] 所有通知已处理，文件已清理")
    
    print(f"[汇总] 本次发送 {sent_count} 个通知")
    return 0

if __name__ == "__main__":
    sys.exit(main())
