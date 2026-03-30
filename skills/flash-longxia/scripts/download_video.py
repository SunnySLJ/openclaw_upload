#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按任务 ID 下载帧龙虾已生成的视频

用法:
    python download_video.py <任务ID>
"""

import sys
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    print(f"错误：当前 Python 版本是 {sys.version.split()[0]}，请改用 python3.12 运行")
    sys.exit(1)

script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent.parent
workflow_path = repo_root / "flash_longxia" / "zhenlongxia_workflow.py"

if not workflow_path.exists():
    print(f"错误：找不到工作流脚本 {workflow_path}")
    sys.exit(1)

sys.path.insert(0, str(workflow_path.parent))
from zhenlongxia_workflow import fetch_generated_video


def main():
    if len(sys.argv) < 2:
        print("用法：python download_video.py <任务ID>")
        sys.exit(1)

    task_id = sys.argv[1].strip()
    if not task_id:
        print("错误：任务 ID 不能为空")
        sys.exit(1)

    try:
        local_path = fetch_generated_video(id=task_id)
        print(f"已下载视频：{local_path}")
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
