#!/usr/bin/env python3
# -*- utf-8 -*-
"""
帧龙虾 图片生成视频 完整工作流
============================

流程概览（与控制台 [x/7] 步骤一致）：
  1. 读取 Token
  2. 设备验证（可选，默认关闭，见 config.yaml device_verify）
  3. 上传本地图片 → 得到 OSS URL
  4. 图生文 imageToText → 得到系统提示词
  5. 发起 generateVideo → 得到任务 id
  6. 轮询 getById(id) → 成功拿到视频地址 / 失败或超时退出
  7. 下载 MP4 到 output 目录

前置条件：将站点返回的 Token 写入与本脚本同目录的 token.txt，
或通过命令行 --token=xxx 传入。

新增功能（v2.0）：
  - 支持命令行参数选择模型、风格、时长、画质、画面比例
  - 支持 config.yaml 配置默认参数
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _ensure_project_venv() -> None:
    """优先切换到仓库内的 .venv Python，避免依赖缺失。"""
    repo_root = Path(__file__).resolve().parent.parent
    venv_root = repo_root / ".venv"
    venv_python = venv_root / "bin" / "python3.12"
    if not venv_python.exists():
        return

    if Path(sys.prefix).resolve() == venv_root.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


_ensure_project_venv()

import requests
import yaml

if sys.version_info[:2] != (3, 12):
    print(
        f"[错误] 当前 Python 版本是 {sys.version.split()[0]}，本项目强制使用 Python 3.12，请改用 python3.12 运行。",
        flush=True,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 默认配置（可被同目录 config.yaml 覆盖，键合并规则见 load_config）
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "base_url": "http://123.56.58.223:8081",
    "upload_url": "http://123.56.58.223:8081/api/v1/file/upload",
    "model_config_url": "http://123.56.58.223:8081/api/v1/globalConfig/getModel",
    "device_verify": {
        "enabled": False,
        "api_path": "/api/v1/device/verify",
    },
    "video": {
        "poll_interval": 30,
        "max_wait_minutes": 30,
        "download_retries": 3,
        "download_retry_interval": 5,
        "output_dir": "./output",
        "confirm_before_generate": True,
        # 视频生成参数（可通过命令行或 config.yaml 覆盖）
        "model": "auto",          # 默认模型，可通过模型接口查询可选值
        "duration": 10,
        "aspectRatio": "16:9",
        "variants": 1,
    },
}


def load_config():
    """
    加载配置：先 DEFAULT_CONFIG，若存在 config.yaml 则合并。
    嵌套字典做浅合并（同名字典键会更新）。
    """
    config_path = Path(__file__).parent / "config.yaml"
    result = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for k, v in loaded.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = {**result[k], **v}
            else:
                result[k] = v
    return result


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
TOKEN_FILE = Path(__file__).parent / "token.txt"


def load_saved_token() -> str | None:
    """从 token.txt 读取一行 Token；文件不存在或为空则返回 None。"""
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return t if t else None
    return None


# ---------------------------------------------------------------------------
# API 封装
# ---------------------------------------------------------------------------

def upload_image(upload_url: str, image_path: str, session: requests.Session) -> str | None:
    """POST 上传接口，返回图片可访问 URL。"""
    url = upload_url.rstrip("/")
    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f)}
        resp = session.post(url, files=files, timeout=30)
    data = resp.json()
    if data.get("code") in (200, 0):
        d = data.get("data")
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            return d.get("url") or d.get("fileUrl") or d.get("path")
    print(f"[错误] 上传失败：{data}")
    return None


def image_to_text(
    base_url: str,
    image_url: str,
    session: requests.Session,
    image_type: int = 1,
) -> str | None:
    """
    POST /api/v1/aiMediaGenerations/imageToText
    image_type: 0 口播提示词，1 视频提示文案（本项目默认 1）
    """
    url = f"{base_url}/api/v1/aiMediaGenerations/imageToText"
    payload = {"imageType": image_type, "urlList": [image_url]}
    resp = session.post(url, json=payload, timeout=60)
    data = resp.json()
    if data.get("code") in (200, 0):
        d = data.get("data")
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            return d.get("systemPrompt") or d.get("prompt") or d.get("text") or str(d)
    print(f"[错误] 图生文失败：{data}")
    return None


def fetch_model_options(
    base_url: str,
    session: requests.Session,
    model_type: int = 1,
    model_config_url: str | None = None,
) -> list[dict]:
    """获取视频模型配置列表。"""
    url = (model_config_url or f"{base_url}/api/v1/globalConfig/getModel").rstrip("/")
    resp = session.get(url, params={"modelType": model_type}, timeout=15)
    data = resp.json()
    if data.get("code") not in (200, 0):
        raise RuntimeError(f"获取模型配置失败：{data}")
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError(f"模型配置返回格式异常：{data}")
    return items


def print_model_options(model_items: list[dict]) -> None:
    """打印模型及其支持的时长、比例。"""
    print("可用模型:", flush=True)
    for item in model_items:
        model_info = item.get("model") or {}
        model_value = str(model_info.get("value") or "").strip()
        model_label = str(model_info.get("label") or model_value).strip()
        if not model_value:
            continue

        durations = [
            str(opt.get("value"))
            for opt in item.get("time") or []
            if opt.get("value") is not None
        ]
        resolutions = [
            str(opt.get("value"))
            for opt in item.get("resolution") or []
            if opt.get("value")
        ]
        print(
            f"  - {model_value} ({model_label})"
            f" | durations={', '.join(durations) or '-'}"
            f" | aspectRatios={', '.join(resolutions) or '-'}",
            flush=True,
        )


def resolve_video_options(
    *,
    model: str,
    duration: int,
    aspect_ratio: str,
    model_items: list[dict],
) -> tuple[str, int, str]:
    """校验并规范化模型、时长、比例。"""
    normalized_model = str(model).strip()
    if not normalized_model:
        raise ValueError("model 不能为空")

    target = None
    for item in model_items:
        model_info = item.get("model") or {}
        if str(model_info.get("value") or "").strip() == normalized_model:
            target = item
            break

    if target is None:
        supported = ", ".join(
            str((item.get("model") or {}).get("value"))
            for item in model_items
            if (item.get("model") or {}).get("value")
        )
        raise ValueError(f"不支持的 model: {normalized_model}。可选值: {supported}")

    supported_durations = {
        int(opt["value"])
        for opt in target.get("time") or []
        if opt.get("value") is not None
    }
    supported_ratios = {
        str(opt["value"]).strip()
        for opt in target.get("resolution") or []
        if opt.get("value")
    }

    if supported_durations and duration not in supported_durations:
        allowed = ", ".join(str(v) for v in sorted(supported_durations))
        raise ValueError(f"model={normalized_model} 不支持 duration={duration}。可选值: {allowed}")
    if supported_ratios and aspect_ratio not in supported_ratios:
        allowed = ", ".join(sorted(supported_ratios))
        raise ValueError(f"model={normalized_model} 不支持 aspectRatio={aspect_ratio}。可选值: {allowed}")

    return normalized_model, duration, aspect_ratio


def validate_system_prompt(system_prompt: str | None) -> tuple[bool, str]:
    """判断图生文结果是否可用于后续视频生成。"""
    if system_prompt is None:
        return False, "图生文接口未返回提示词"

    prompt = system_prompt.strip()
    if not prompt:
        return False, "图生文接口返回了空提示词"

    lowered = prompt.lower()
    invalid_markers = (
        "图生文失败",
        "image_to_text failed",
        "generate failed",
        "error",
        "failed",
        "exception",
        "traceback",
        '"code":',
        "'code':",
        '"msg":',
        "'msg':",
        '"error":',
        "'error':",
    )
    if any(marker in lowered for marker in invalid_markers):
        return False, f"图生文返回内容疑似错误信息：{prompt[:120]}"

    if prompt.startswith("{") and prompt.endswith("}"):
        return False, f"图生文返回了未解析对象：{prompt[:120]}"

    if len(prompt) < 10:
        return False, f"图生文返回内容过短：{prompt}"

    return True, prompt


def confirm_video_generation(
    prompt: str,
    *,
    model: str,
    duration: int,
    aspectRatio: str,
    variants: int,
) -> bool:
    """在发起 generateVideo 前请求用户确认。"""
    preview = prompt.replace("\n", " ").strip()
    if len(preview) > 160:
        preview = f"{preview[:160]}..."

    print("[确认] 即将调用 generateVideo", flush=True)
    print(f"[确认] 参数: model={model}, duration={duration}, aspectRatio={aspectRatio}, variants={variants}", flush=True)
    print(f"[确认] 提示词预览: {preview}", flush=True)
    answer = input("[确认] 是否继续生成视频？输入 y 继续，其他任意键取消: ").strip().lower()
    return answer in {"y", "yes"}


def generate_video(
    base_url: str,
    image_url: str,
    system_prompt: str,
    session: requests.Session,
    aspectRatio: str = "16:9",
    duration: int = 10,
    model: str = "auto",
    variants: int = 1,
    **kwargs,
) -> str | None:
    """
    POST generateVideo，返回任务 id。
    
    参数:
        model: 模型值，来源于 /api/v1/globalConfig/getModel?modelType=1
        duration: 视频时长，需匹配所选模型支持的时长
        aspectRatio: 画面比例，需匹配所选模型支持的比例
        variants: 生成变体数量
    """
    url = f"{base_url}/api/v1/aiMediaGenerations/generateVideo"
    payload = {
        "urls": [image_url],
        "prompt": system_prompt,
        "aspectRatio": aspectRatio,
        "duration": duration,
        "variants": variants,
    }
    # model 参数按接口配置传递，也兼容调用方显式传空时跳过
    if model:
        payload["model"] = model
    payload.update({k: v for k, v in kwargs.items() if v is not None})
    resp = session.post(url, json=payload, timeout=30)
    data = resp.json()
    if data.get("code") in (200, 0):
        d = data.get("data")
        if isinstance(d, list) and d:
            d = d[0]
        if isinstance(d, dict):
            return str(d.get("id") or d.get("groupNo") or d.get("taskId") or d)
        return str(d) if d else None
    print(f"[错误] 生成视频失败：{data}")
    return None


def fetch_video_by_id(base_url: str, session: requests.Session, video_id: str) -> dict | None:
    """GET getById?id=，成功时返回 data 字典。"""
    url = f"{base_url}/api/v1/aiMediaGenerations/getById"
    try:
        resp = session.get(url, params={"id": video_id}, timeout=15)
        data = resp.json()
        if data.get("code") in (200, 0):
            return data.get("data")
        return None
    except Exception:
        return None


_STATUS_SUCCESS = ("2", 2, "completed", "success", "SUCCESS")
_STATUS_FAILED = ("3", 3, "failed", "FAILED", "error", "ERROR")
_STATUS_LABELS = {
    "0": "排队中", 0: "排队中",
    "1": "生成中", 1: "生成中",
    "2": "已完成", 2: "已完成",
    "3": "已失败", 3: "已失败",
    "completed": "已完成", "success": "已完成", "SUCCESS": "已完成",
    "failed": "已失败", "FAILED": "已失败", "error": "已失败", "ERROR": "已失败",
}


def _build_status_text(record: dict) -> str:
    """构建轮询日志里的状态文本。"""
    status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
    status_label = _STATUS_LABELS.get(status, "处理中")
    req_msg = record.get("reqMsg") or ""
    rep_msg = record.get("repMsg") or record.get("message") or record.get("msg") or record.get("errorMsg") or ""
    return f"status={status}({status_label}), reqMsg={req_msg}, repMsg={rep_msg}"


def _extract_video_url_from_rep_msg(record: dict) -> str | None:
    """兼容 repMsg 中包含 result 视频链接的场景。"""
    rep_msg = record.get("repMsg")
    if not rep_msg or not isinstance(rep_msg, str):
        return None
    try:
        parsed = json.loads(rep_msg)
    except Exception:
        return None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
    return None


def poll_video_status(
    base_url: str,
    session: requests.Session,
    task_id: str,
    poll_interval: int = 30,
    max_wait_minutes: int = 30,
) -> tuple[dict | None, str]:
    """轮询直到成功/失败/超时。"""
    max_elapsed = max_wait_minutes * 60
    elapsed = 0
    attempt = 0
    print(f"[轮询] 按 id={task_id} 查询 getById，每 {poll_interval}s 查一次，最多等 {max_wait_minutes} 分钟", flush=True)

    while elapsed < max_elapsed:
        attempt += 1
        try:
            record = fetch_video_by_id(base_url, session, task_id)
            if record:
                status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
                print(f"[轮询] 第{attempt}次：{_build_status_text(record)}", flush=True)
                rep_video_url = _extract_video_url_from_rep_msg(record)
                if rep_video_url:
                    record["mediaUrl"] = record.get("mediaUrl") or rep_video_url
                    print(f"[轮询] 第{attempt}次：repMsg 已包含成片链接，直接进入下载", flush=True)
                    return record, "success"
                if status in _STATUS_SUCCESS:
                    print(f"[轮询] 视频已完成 id={task_id}", flush=True)
                    return record, "success"
                if status in _STATUS_FAILED:
                    msg = record.get("msg") or record.get("message") or record.get("errorMsg", "")
                    print(f"[错误] 视频生成失败 status={status}, msg={msg}, record={record}", flush=True)
                    return None, "failed"
            else:
                print(f"[轮询] 第{attempt}次：暂无数据（接口返回空 data）", flush=True)
        except Exception as e:
            print(f"[轮询] 第 {attempt} 次异常：{e}", flush=True)

        remaining = max_elapsed - elapsed
        sleep_sec = min(poll_interval, remaining)
        if sleep_sec <= 0:
            break
        print(f"[轮询] 等待中... ({int(elapsed)}s/{max_elapsed}s, 下次 {sleep_sec}s 后)", flush=True)
        time.sleep(sleep_sec)
        elapsed += sleep_sec

    print(f"[轮询] 已等待 {max_wait_minutes} 分钟，未获取到视频，停止轮询", flush=True)
    return None, "timeout"


def get_video_url(record: dict) -> str | None:
    """从 getById 的 data 里取可下载的视频地址。"""
    return (
        record.get("videoUrl")
        or record.get("mediaUrl")
        or record.get("url")
        or record.get("videoPath")
        or record.get("path")
    )


def resolve_task_id(task_id: str | None = None, **kwargs) -> str | None:
    """统一解析任务 ID，兼容旧的别名入参。"""
    candidate = task_id or kwargs.get("id") or kwargs.get("traceid") or kwargs.get("traeid")
    if candidate is None:
        return None
    normalized = str(candidate).strip()
    return normalized or None


def download_video(
    video_url: str,
    output_dir: str,
    filename: str | None = None,
    session: requests.Session | None = None,
    retries: int = 3,
    retry_interval: int = 5,
) -> str:
    """流式下载 MP4 到本地，返回绝对路径。"""
    os.makedirs(output_dir, exist_ok=True)
    if not filename:
        filename = "video.mp4"
    path = os.path.join(output_dir, filename)
    req = session.get if session else requests.get
    attempts = max(1, retries)
    last_err: Exception | None = None

    for i in range(1, attempts + 1):
        try:
            resp = req(video_url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return os.path.abspath(path)
        except Exception as e:
            last_err = e
            if i < attempts:
                print(f"[下载] 第{i}次失败，{retry_interval}s 后重试：{e}", flush=True)
                time.sleep(max(1, retry_interval))

    raise RuntimeError(f"下载失败，已重试 {attempts} 次：{last_err}")


def fetch_generated_video(
    *,
    task_id: str | None = None,
    token: str | None = None,
    base_url: str | None = None,
    output_dir: str | None = None,
    filename: str | None = None,
    **kwargs,
) -> str:
    """按任务 ID 查询并下载已生成视频。"""
    config = load_config()
    video_cfg = config.get("video", {})
    resolved_task_id = resolve_task_id(task_id, **kwargs)
    if not resolved_task_id:
        raise ValueError("缺少任务 ID，请传 task_id 或 id")

    token_val = token or load_saved_token()
    if not token_val:
        raise ValueError("请将 Token 写入 flash_longxia/token.txt 或显式传入 token")

    resolved_base_url = (base_url or config["base_url"]).rstrip("/")
    resolved_output_dir = output_dir or video_cfg.get("output_dir", "./output")
    resolved_filename = filename or f"{resolved_task_id}.mp4"

    session = requests.Session()
    session.headers.update({
        "token": token_val,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })

    record = fetch_video_by_id(resolved_base_url, session, resolved_task_id)
    if not record:
        raise RuntimeError(f"未查询到任务 {resolved_task_id} 的视频信息")

    video_url = get_video_url(record)
    if not video_url:
        rep_video_url = _extract_video_url_from_rep_msg(record)
        if rep_video_url:
            video_url = rep_video_url
    if not video_url:
        raise RuntimeError(f"任务 {resolved_task_id} 暂无可下载视频地址: {record}")

    return download_video(
        video_url,
        resolved_output_dir,
        filename=resolved_filename,
        session=session,
        retries=video_cfg.get("download_retries", 3),
        retry_interval=video_cfg.get("download_retry_interval", 5),
    )


# ---------------------------------------------------------------------------
# 主流程入口
# ---------------------------------------------------------------------------

def run_workflow(
    image_path: str,
    *,
    token: str | None = None,
    model: str | None = None,
    duration: int | None = None,
    aspectRatio: str | None = None,
    variants: int | None = None,
    auto_confirm: bool = False,
    prompt: str | None = None,
):
    """
    串联上述步骤；任一步失败则 sys.exit(1)。
    
    参数:
        model: 模型值，来源于模型配置接口；未传时使用配置默认值
        duration: 视频时长，需匹配所选模型支持的时长
        aspectRatio: 画面比例，需匹配所选模型支持的比例
        variants: 生成变体数量
        auto_confirm: 为 True 时跳过发起视频前的人工确认
        prompt: 自定义提示词（传入后跳过图生文）
    """
    config = load_config()
    base_url = config["base_url"].rstrip("/")
    upload_url = config.get("upload_url", f"{base_url}/api/v1/file/upload").rstrip("/")
    model_config_url = config.get("model_config_url", f"{base_url}/api/v1/globalConfig/getModel")
    video_cfg = config.get("video", {})

    # 合并配置：命令行参数 > config.yaml > 默认值
    model = model if model is not None else video_cfg.get("model", "")
    duration = duration if duration is not None else video_cfg.get("duration", 10)
    aspectRatio = aspectRatio or video_cfg.get("aspectRatio", "16:9")
    variants = variants if variants is not None else video_cfg.get("variants", 1)
    confirm_before_generate = video_cfg.get("confirm_before_generate", True)

    token_val = token or load_saved_token()
    if not token_val:
        print("[错误] 请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx", flush=True)
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "token": token_val,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    print("[1/7] 使用 Token", flush=True)

    try:
        model_items = fetch_model_options(base_url, session, model_config_url=model_config_url)
        model, duration, aspectRatio = resolve_video_options(
            model=model,
            duration=duration,
            aspect_ratio=aspectRatio,
            model_items=model_items,
        )
        print(f"[OK] 模型配置已确认: model={model}, duration={duration}, aspectRatio={aspectRatio}", flush=True)
    except Exception as e:
        print(f"[错误] 模型参数校验失败：{e}", flush=True)
        sys.exit(1)

    dev_cfg = config.get("device_verify", {}) or {}
    if dev_cfg.get("enabled"):
        import device_verify
        if not device_verify.run_device_verify(base_url, session, api_path=dev_cfg.get("api_path")):
            print("[错误] 设备未授权，无法继续", flush=True)
            sys.exit(1)
        print("[2/7] 设备验证通过", flush=True)
    else:
        print("[2/7] 跳过设备验证（未启用）", flush=True)

    print("[3/7] 上传图片...", flush=True)
    image_url = upload_image(upload_url, image_path, session)
    if not image_url:
        sys.exit(1)
    print(f"[OK] 图片已上传：{image_url}")

    # [4/7] 图生文获取提示词（如果传入了自定义 prompt 则跳过）
    if prompt:
        print(f"[4/7] 使用自定义提示词...", flush=True)
        system_prompt = prompt
    else:
        print("[4/7] 图生文获取提示词...", flush=True)
        system_prompt = image_to_text(base_url, image_url, session)
        prompt_ok, prompt_msg = validate_system_prompt(system_prompt)
        if not prompt_ok:
            print(f"[错误] 提示词生成未成功，停止视频生成：{prompt_msg}", flush=True)
            sys.exit(1)
        system_prompt = prompt_msg
    print(f"[OK] 系统提示词：{system_prompt[:80]}...")

    if confirm_before_generate and not auto_confirm:
        if not confirm_video_generation(
            system_prompt,
            model=model,
            duration=duration,
            aspectRatio=aspectRatio,
            variants=variants,
        ):
            print("[已取消] 用户未确认，停止发起视频生成", flush=True)
            sys.exit(0)

    print(f"[5/7] 发起视频生成... (model={model}, duration={duration}s, aspectRatio={aspectRatio}, variants={variants})", flush=True)
    task_id = generate_video(
        base_url, image_url, system_prompt, session,
        aspectRatio=aspectRatio,
        duration=duration,
        model=model,
        variants=variants,
    )
    if not task_id:
        sys.exit(1)
    print(f"[OK] 任务 ID: {task_id}")
    print("[完成] 已提交视频生成任务，后续轮询与下载交由其他人处理", flush=True)
    return task_id

    # poll_int = video_cfg.get("poll_interval", 30)
    # max_wait = video_cfg.get("max_wait_minutes", 30)
    # print(f"[6/7] 轮询 getById(id={task_id}): 每{poll_int}s 查一次，最多等 {max_wait} 分钟", flush=True)
    # record, reason = poll_video_status(
    #     base_url, session, task_id,
    #     poll_interval=poll_int,
    #     max_wait_minutes=max_wait,
    # )
    # if not record:
    #     if reason == "failed":
    #         print("[错误] 任务状态已失败，停止后续下载")
    #     else:
    #         print("[错误] 轮询超时，未获取到可下载视频")
    #     sys.exit(1)
    #
    # video_url = get_video_url(record)
    # if not video_url:
    #     print("[错误] 无法解析视频 URL:", record)
    #     sys.exit(1)
    #
    # print("[7/7] 下载视频...", flush=True)
    # output_dir = video_cfg.get("output_dir", "./output")
    # local_path = download_video(
    #     video_url,
    #     output_dir,
    #     session=session,
    #     retries=video_cfg.get("download_retries", 3),
    #     retry_interval=video_cfg.get("download_retry_interval", 5),
    # )
    # print(f"[完成] 视频已保存：{local_path}")
    # return local_path


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python zhenlongxia_workflow.py <图片路径> [选项]")
        print("  python zhenlongxia_workflow.py --list-models [--token=xxx]")
        print()
        print("选项:")
        print("  --token=xxx          Token（也可写入 token.txt）")
        print("  --list-models        查询可用模型、时长与比例")
        print("  --model=MODEL        模型值，来自模型配置接口")
        print("  --duration=N         视频时长，需匹配所选模型")
        print("  --aspectRatio=XXX    画面比例，需匹配所选模型")
        print("  --variants=N         生成变体数量")
        print("  --yes                跳过发起视频前的人工确认")
        print("  --id=ID              按任务 ID 直接下载已生成视频")
        print("  --fetch-by-id=ID     按任务 ID 直接下载已生成视频（兼容旧参数）")
        print()
        print("示例:")
        print("  python zhenlongxia_workflow.py ./my_image.jpg")
        print("  python zhenlongxia_workflow.py --list-models")
        print("  python zhenlongxia_workflow.py ./my_image.jpg --model=sora2-new --duration=10")
        print("  python zhenlongxia_workflow.py ./my_image.jpg --model=grok_imagine --duration=10 --aspectRatio=9:16 --variants=1 --yes")
        print("  python zhenlongxia_workflow.py --id=123456")
        print("  python zhenlongxia_workflow.py --fetch-by-id=123456")
        sys.exit(1)

    image_path = None
    fetch_task_id = None
    list_models = False
    token = None
    model = None
    duration = None
    aspectRatio = None
    variants = None
    auto_confirm = False

    for arg in sys.argv[1:]:
        if arg == "--list-models":
            list_models = True
        elif arg.startswith("--id="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--fetch-by-id="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--traeid="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--token="):
            token = arg.split("=", 1)[1]
        elif arg.startswith("--model="):
            model = arg.split("=", 1)[1]
        elif arg.startswith("--duration="):
            duration = int(arg.split("=", 1)[1])
        elif arg.startswith("--aspectRatio="):
            aspectRatio = arg.split("=", 1)[1]
        elif arg.startswith("--variants="):
            variants = int(arg.split("=", 1)[1])
        elif arg == "--yes":
            auto_confirm = True
        elif not arg.startswith("--") and image_path is None:
            image_path = arg

    if list_models:
        config = load_config()
        base_url = config["base_url"].rstrip("/")
        model_config_url = config.get("model_config_url", f"{base_url}/api/v1/globalConfig/getModel")
        token_val = token or load_saved_token()
        if not token_val:
            print("错误：请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx")
            sys.exit(1)

        session = requests.Session()
        session.headers.update({
            "token": token_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        model_items = fetch_model_options(base_url, session, model_config_url=model_config_url)
        print_model_options(model_items)
        return

    if fetch_task_id:
        local_path = fetch_generated_video(task_id=fetch_task_id, token=token)
        print(f"[完成] 视频已保存：{local_path}")
        return

    if not image_path:
        print("错误：缺少图片路径，或请使用 --id=ID")
        sys.exit(1)

    if not os.path.isfile(image_path):
        alt = Path(__file__).parent / os.path.basename(image_path)
        if alt.exists():
            image_path = str(alt)
        else:
            print(f"错误：文件不存在 {image_path}")
            sys.exit(1)

    run_workflow(
        image_path,
        token=token,
        model=model,
        duration=duration,
        aspectRatio=aspectRatio,
        variants=variants,
        auto_confirm=auto_confirm,
    )


if __name__ == "__main__":
    main()
