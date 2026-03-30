#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧龙虾视频生成 - 技能封装脚本

用法:
    python generate_video.py <图片路径> [选项]
    
示例:
    python generate_video.py image.jpg --model=auto --duration=10 --variants=1
"""

import sys
import os
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    print(f"错误：当前 Python 版本是 {sys.version.split()[0]}，请改用 python3.12 运行")
    sys.exit(1)

# 解析仓库根目录下的主工作流脚本
script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent.parent
workflow_path = repo_root / "flash_longxia" / "zhenlongxia_workflow.py"

if not workflow_path.exists():
    print(f"错误：找不到工作流脚本 {workflow_path}")
    sys.exit(1)

# 导入工作流模块
sys.path.insert(0, str(workflow_path.parent))
from zhenlongxia_workflow import run_workflow

def main():
    if len(sys.argv) < 2:
        print("用法：python generate_video.py <图片路径> [选项]")
        print()
        print("选项:")
        print("  --model=auto      模型固定为 auto")
        print("  --duration=N      时长：10, 15, 20 (秒)")
        print("  --aspectRatio=X   比例：16:9, 9:16, 1:1")
        print("  --variants=N      变体数量")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    # 解析参数
    kwargs = {}
    for arg in sys.argv[2:]:
        if arg.startswith("--model="):
            kwargs["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--duration="):
            kwargs["duration"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--aspectRatio="):
            kwargs["aspectRatio"] = arg.split("=", 1)[1]
        elif arg.startswith("--variants="):
            kwargs["variants"] = int(arg.split("=", 1)[1])
    
    # 运行工作流
    try:
        task_id = run_workflow(image_path, **kwargs)
        print(f"\n已提交视频生成任务，任务 ID：{task_id}")
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
