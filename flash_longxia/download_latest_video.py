#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按任务 id 下载已生成的视频
==========================

场景：主流程中断或仅需补下载时，用 generateVideo 返回的 id 调 getById，
从返回中取 mediaUrl / videoUrl 等字段，流式保存为 MP4。
"""

import sys
import time
from pathlib import Path

import requests

BASE = "http://123.56.58.223:8081"
TOKEN_FILE = Path(__file__).parent / "token.txt"
OUTPUT_DIR = Path(__file__).parent / "output"


def main():
    if len(sys.argv) < 2:
        print("用法: python download_latest_video.py <视频id>")
        return

    video_id = sys.argv[1]
    if not TOKEN_FILE.exists():
        print("请将 Token 放入 token.txt")
        return

    tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    session = requests.Session()
    session.headers.update({"token": tok, "Accept": "application/json"})

    r = session.get(f"{BASE}/api/v1/aiMediaGenerations/getById", params={"id": video_id}, timeout=15)
    d = r.json()
    if d.get("code") not in (200, 0):
        print(f"接口返回 {d.get('code')}: {d.get('msg')}")
        return

    data = d.get("data")
    if not data or not isinstance(data, dict):
        print("无视频数据")
        return

    url = data.get("videoUrl") or data.get("mediaUrl") or data.get("url") or data.get("videoPath") or data.get("path")
    if not url:
        print("无法解析视频 URL:", data)
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"video_{video_id}_{int(time.time())}.mp4"
    resp = session.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    print(f"已保存: {path.resolve()}")


if __name__ == "__main__":
    main()
