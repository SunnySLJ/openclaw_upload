#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧龙虾视频生成 - 技能封装脚本

用法:
    python generate_video.py <图片路径1> [图片路径2] [图片路径3] [图片路径4] [选项]
    python generate_video.py --list-models [--token=xxx]

示例:
    python generate_video.py --list-models
    python generate_video.py image.jpg --model=sora2-new --duration=10 --variants=1
    python generate_video.py img1.jpg img2.jpg img3.jpg img4.jpg --model=grok_imagine --duration=10 --yes
    python generate_video.py image.jpg --yes
"""

import sys
import os
from pathlib import Path

def resolve_repo_root() -> Path | None:
    """优先从 cwd、环境变量和 OpenClaw 常见目录定位仓库。"""
    candidates: list[Path] = []

    env_root = os.environ.get("OPENCLAW_UPLOAD_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])

    home = Path.home()
    candidates.extend([
        home / ".openclaw" / "workspace" / "openclaw_upload",
        home / "Desktop" / "openclaw_upload",
        home / "workspace" / "openclaw_upload",
        home / "openclaw_upload",
    ])

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except FileNotFoundError:
            continue

        workflow = candidate / "flash_longxia" / "zhenlongxia_workflow.py"
        if workflow.exists():
            return candidate
    return None


repo_root = resolve_repo_root()
if repo_root is None:
    print("错误：找不到 openclaw_upload 仓库根目录，请在项目目录运行，或设置 OPENCLAW_UPLOAD_ROOT 指向包含 flash_longxia 的目录")
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

# 导入工作流模块
sys.path.insert(0, str(workflow_path.parent))
from zhenlongxia_workflow import fetch_model_options, load_config, load_saved_token, print_model_options, run_workflow

def main():
    if len(sys.argv) < 2:
        print("用法：python generate_video.py <图片路径1> [图片路径2] [图片路径3] [图片路径4] [选项]")
        print("      python generate_video.py --list-models [--token=xxx]")
        print()
        print("选项:")
        print("  --list-models     查询可用模型、时长与比例")
        print("  --token=xxx       Token（也可写入 token.txt）")
        print("  --model=MODEL     模型值，来自模型配置接口")
        print("  --duration=N      时长，需匹配所选模型")
        print("  --aspectRatio=X   比例，需匹配所选模型")
        print("  --variants=N      变体数量")
        print("  --yes             跳过发起视频前的人工确认")
        print("  说明              最多传 4 张图片，最终生成 1 个视频")
        sys.exit(1)

    image_paths: list[str] = []
    list_models = False

    # 解析参数
    kwargs = {}
    for arg in sys.argv[1:]:
        if arg == "--list-models":
            list_models = True
        elif arg.startswith("--token="):
            kwargs["token"] = arg.split("=", 1)[1]
        elif arg.startswith("--model="):
            kwargs["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--duration="):
            kwargs["duration"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--aspectRatio="):
            kwargs["aspectRatio"] = arg.split("=", 1)[1]
        elif arg.startswith("--variants="):
            kwargs["variants"] = int(arg.split("=", 1)[1])
        elif arg == "--yes":
            kwargs["auto_confirm"] = True
        elif not arg.startswith("--"):
            image_paths.append(arg)

    if list_models:
        config = load_config()
        base_url = config["base_url"].rstrip("/")
        model_config_url = config.get("model_config_url", f"{base_url}/api/v1/globalConfig/getModel")
        token_val = kwargs.get("token") or load_saved_token()
        if not token_val:
            print("错误：请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx")
            sys.exit(1)

        import requests

        session = requests.Session()
        session.headers.update({
            "token": token_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        model_items = fetch_model_options(base_url, session, model_config_url=model_config_url)
        print_model_options(model_items)
        return

    if not image_paths:
        print("错误：缺少图片路径")
        sys.exit(1)
    if len(image_paths) > 4:
        print(f"错误：最多只支持 4 张图片，当前传入 {len(image_paths)} 张")
        sys.exit(1)

    # 运行工作流
    try:
        task_id = run_workflow(image_paths, **kwargs)
        print(f"\n已提交视频生成任务，任务 ID：{task_id}")
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
