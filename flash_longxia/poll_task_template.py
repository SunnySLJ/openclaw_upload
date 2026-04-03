#!/usr/bin/env python3
"""
视频生成任务轮询脚本模板
每 30 秒查询一次任务状态，最多等待 30 分钟
视频生成完成后自动下载并发送微信通知

使用方法：
    python3 poll_task_template.py <TASK_ID> <TOKEN> [WECHAT_TARGET]

参数：
    TASK_ID: 任务 ID
    TOKEN: API Token
    WECHAT_TARGET: 微信目标用户 ID（可选，默认使用当前会话）
"""

import requests
import time
import os
import sys
import subprocess
from pathlib import Path

# 配置
BASE_URL = os.getenv("FLASH_LONGXIA_BASE_URL", "http://123.56.58.223:8081")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
MAX_ATTEMPTS = 60  # 30 分钟
INTERVAL = 30  # 30 秒

def get_task_args():
    """从命令行参数获取任务信息"""
    if len(sys.argv) < 3:
        print("用法：python3 poll_task_template.py <TASK_ID> <TOKEN> [WECHAT_TARGET]")
        sys.exit(1)
    
    task_id = sys.argv[1]
    token = sys.argv[2]
    default_target = os.getenv("FLASH_LONGXIA_WECHAT_TARGET") or os.getenv("OPENCLAW_WECHAT_TARGET")
    wechat_target = sys.argv[3] if len(sys.argv) > 3 else default_target
    return task_id, token, wechat_target

def check_task_status(task_id, token):
    """查询任务状态"""
    url = f"{BASE_URL}/api/v1/aiMediaGenerations/getById"
    headers = {"token": token}
    params = {"id": task_id}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        return response.json()
    except Exception as e:
        print(f"[错误] 查询失败：{e}")
        return None

def download_video(video_url, task_id):
    """下载视频到本地"""
    output_file = OUTPUT_DIR / f"{task_id}.mp4"
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        response = requests.get(video_url, timeout=60)
        with open(output_file, 'wb') as f:
            f.write(response.content)
        print(f"[完成] 视频已保存：{output_file}")
        return str(output_file)
    except Exception as e:
        print(f"[错误] 下载失败：{e}")
        return None

def send_wechat_notification(video_file, task_id, wechat_target):
    """发送微信通知"""
    try:
        cmd = [
            "openclaw", "message", "send",
            "--channel", "openclaw-weixin",
            "--target", wechat_target,
            "--media", video_file,
            "--message", f'🎀 视频生成完成啦！任务 {task_id}，10 秒竖屏。千千看看效果怎么样？回复"可以发布"我就帮你上传～ ✨'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"[通知] 微信推送成功")
            return True
        else:
            print(f"[通知] 微信推送失败：{result.stderr}")
            return False
    except Exception as e:
        print(f"[通知] 发送异常：{e}")
        return False

def main():
    task_id, token, wechat_target = get_task_args()
    if not wechat_target:
        print("[错误] 缺少微信目标，请传第三个参数，或设置 FLASH_LONGXIA_WECHAT_TARGET / OPENCLAW_WECHAT_TARGET")
        sys.exit(1)
    print(f"[开始] 轮询任务 {task_id} 状态，最多等待 {MAX_ATTEMPTS * INTERVAL // 60} 分钟")
    
    for i in range(1, MAX_ATTEMPTS + 1):
        data = check_task_status(task_id, token)
        
        if not data or not data.get('data'):
            print(f"({i}/{MAX_ATTEMPTS}) 查询失败，等待 {INTERVAL} 秒...")
            time.sleep(INTERVAL)
            continue
        
        record = data.get('data', {})
        status = record.get('status')
        status_map = {0: "排队中", 1: "生成中", 2: "已完成", 3: "已失败"}
        status_text = status_map.get(status, f"未知 ({status})")
        print(f"({i}/{MAX_ATTEMPTS}) 任务 {task_id} 状态：{status_text}")
        
        if status == 2:  # 已完成
            video_url = record.get('mediaUrl')
            if not video_url:
                rep_msg = record.get('repMsg', '')
                if 'result' in rep_msg:
                    import json
                    try:
                        rep_data = json.loads(rep_msg)
                        video_url = rep_data.get('data', {}).get('result', [None])[0]
                    except:
                        pass
            
            if video_url:
                print(f"[下载] 视频 URL: {video_url}")
                video_file = download_video(video_url, task_id)
                if video_file:
                    print(f"[成功] 任务 {task_id} 完成！")
                    send_wechat_notification(video_file, task_id, wechat_target)
                    sys.exit(0)
            else:
                print(f"[错误] 未找到视频 URL")
            break
        
        elif status == 3:  # 已失败
            print(f"[失败] 任务 {task_id} 生成失败")
            sys.exit(1)
        
        if i < MAX_ATTEMPTS:
            time.sleep(INTERVAL)
    
    print(f"[超时] 任务 {task_id} 等待超时")
    sys.exit(1)

if __name__ == "__main__":
    main()
