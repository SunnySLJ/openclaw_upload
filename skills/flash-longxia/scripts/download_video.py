#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按任务 ID 下载帧龙虾已生成的视频

用法:
    python download_video.py <任务ID>
"""

import sys
import os
from pathlib import Path

def resolve_repo_root() -> Path | None:
    """优先从 cwd 定位仓库，其次尝试脚本目录及环境变量。"""
    candidates = []

    env_root = os.environ.get("OPENCLAW_UPLOAD_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])

    for candidate in candidates:
        workflow = candidate / "flash_longxia" / "zhenlongxia_workflow.py"
        if workflow.exists():
            return candidate
    return None


repo_root = resolve_repo_root()
if repo_root is None:
    print("错误：找不到 openclaw_upload 仓库根目录，请在项目目录运行或设置 OPENCLAW_UPLOAD_ROOT")
    sys.exit(1)


def ensure_project_venv() -> None:
    """优先切换到仓库内的 .venv Python，避免依赖缺失。"""
    venv_root = repo_root / ".venv"
    venv_python = venv_root / "bin" / "python3.12"
    if not venv_python.exists():
        return

    if Path(sys.prefix).resolve() == venv_root.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


ensure_project_venv()

if sys.version_info[:2] != (3, 12):
    print(f"错误：当前 Python 版本是 {sys.version.split()[0]}，请改用 python3.12 运行")
    sys.exit(1)

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
