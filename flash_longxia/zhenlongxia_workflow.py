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
  - 支持命令行参数选择模型、时长、变体数、画面比例
  - 支持行业模板查询、交互选择和命令行透传
  - 支持 config.yaml 配置默认参数
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _resolve_venv_python(venv_root: Path) -> Path | None:
    """兼容 macOS/Linux 与 Windows 的虚拟环境 Python 路径。"""
    candidates = [
        venv_root / "bin" / "python3.12",
        venv_root / "bin" / "python3",
        venv_root / "bin" / "python",
        venv_root / "Scripts" / "python.exe",
        venv_root / "Scripts" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _ensure_project_venv() -> None:
    """优先切换到仓库内的 .venv Python，避免依赖缺失。"""
    repo_root = Path(__file__).resolve().parent.parent
    venv_root = repo_root / ".venv"
    venv_python = _resolve_venv_python(venv_root)
    if venv_python is None:
        return

    if Path(sys.prefix).resolve() == venv_root.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


_ensure_project_venv()

import requests
import yaml

if sys.version_info[:2] != (3, 12):
    print(
        f"[错误] 当前 Python 版本是 {sys.version.split()[0]}，本项目强制使用 Python 3.12，请改用 Python 3.12 运行。",
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
        "aspectRatio": "9:16",
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


def normalize_image_paths(image_paths: str | list[str] | tuple[str, ...]) -> list[str]:
    """统一图片入参，兼容单张和多张本地图片路径。"""
    if isinstance(image_paths, str):
        candidates = [image_paths]
    else:
        candidates = list(image_paths)
    normalized = [str(item).strip() for item in candidates if str(item).strip()]
    if not normalized:
        raise ValueError("至少需要传入一张图片路径")
    if len(normalized) > 4:
        raise ValueError(f"最多只支持 4 张图片，当前传入 {len(normalized)} 张")
    return normalized


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


def fetch_template_categories(
    base_url: str,
    session: requests.Session,
    *,
    media_type: int = 0,
) -> list[dict]:
    """获取行业模板分类列表。"""
    url = f"{base_url}/api/v1/aiTemplateCategory/getList"
    resp = session.post(url, json={"mediaType": media_type}, timeout=15)
    data = resp.json()
    if data.get("code") not in (200, 0):
        raise RuntimeError(f"获取模板分类失败：{data}")
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError(f"模板分类返回格式异常：{data}")
    return items


def fetch_template_options(
    base_url: str,
    session: requests.Session,
    *,
    page_num: int = 1,
    page_size: int = 10,
    tab_type: int = 0,
) -> list[dict]:
    """获取行业模板列表。"""
    url = f"{base_url}/api/v1/aiTemplate/pageList"
    payload = {
        "pageNum": page_num,
        "pageSize": page_size,
        "tabType": tab_type,
    }
    resp = session.post(url, json=payload, timeout=15)
    data = resp.json()
    if data.get("code") not in (200, 0):
        raise RuntimeError(f"获取模板列表失败：{data}")

    items = data.get("data")
    if isinstance(items, dict):
        for key in ("records", "list", "rows"):
            candidate = items.get(key)
            if isinstance(candidate, list):
                return candidate
    if isinstance(items, list):
        return items
    raise RuntimeError(f"模板列表返回格式异常：{data}")


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


def print_template_options(template_items: list[dict]) -> None:
    """打印行业模板列表。"""
    print("可用行业模板:", flush=True)
    for item in template_items:
        template_id = (
            item.get("id")
            or item.get("tmpplateId")
            or item.get("templateId")
            or item.get("aiTemplateId")
        )
        title = str(item.get("title") or "").strip() or "-"
        prompt = str(item.get("prompt") or "").strip().replace("\n", " ")
        if len(prompt) > 60:
            prompt = f"{prompt[:60]}..."
        print(
            f"  - id={template_id} | tabType={item.get('tabType')} | picType={item.get('picType')}"
            f" | mediaType={item.get('mediaType')} | title={title} | prompt={prompt or '-'}",
            flush=True,
        )


def print_template_categories(category_items: list[dict]) -> None:
    """打印模板分类列表。"""
    print("模板分类:", flush=True)
    for item in category_items:
        print(
            f"  - tabType={item.get('tabType')} | tabName={item.get('tabName') or '-'}"
            f" | mediaType={item.get('mediaType')}",
            flush=True,
        )


def find_template_category(
    category_items: list[dict],
    *,
    tab_type: int,
) -> dict | None:
    """按 tabType 查找模板分类。"""
    for item in category_items:
        if item.get("tabType") == tab_type:
            return item
    return None


def find_template_category_by_name(
    category_items: list[dict],
    *,
    tab_name: str,
) -> dict | None:
    """按 tabName 查找模板分类。"""
    target_name = str(tab_name).strip()
    for item in category_items:
        if str(item.get("tabName") or "").strip() == target_name:
            return item
    return None


def select_industry_template(
    base_url: str,
    session: requests.Session,
    *,
    page_num: int = 1,
    page_size: int = 10,
) -> tuple[int | None, str | None]:
    """交互式选择行业模板；用户跳过时返回 (None, None)。"""
    answer = input("[模板] 是否使用行业模板？输入 y 选择，其他任意键跳过: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("[模板] 已跳过行业模板", flush=True)
        return None, None

    category_items = fetch_template_categories(base_url, session, media_type=1)
    industry_category = find_template_category_by_name(category_items, tab_name="行业模板")
    if not industry_category or industry_category.get("tabType") is None:
        print("[模板] 未找到 tabName=行业模板 的分类，跳过模板生成", flush=True)
        return None, None

    tab_type = int(industry_category["tabType"])
    category_title = str(industry_category.get("tabName") or "").strip() or "行业模板"
    template_items = fetch_template_options(
        base_url,
        session,
        page_num=page_num,
        page_size=page_size,
        tab_type=tab_type,
    )
    if not template_items:
        print(f"[模板] tabType={tab_type} 当前没有可选模板，跳过模板生成", flush=True)
        return None, None

    print(f"[模板] 可选行业模板（tabType={tab_type}, title={category_title}）:", flush=True)
    for idx, item in enumerate(template_items, start=1):
        template_id = (
            item.get("id")
            or item.get("tmpplateId")
            or item.get("templateId")
            or item.get("aiTemplateId")
        )
        item_title = str(item.get("title") or "").strip() or category_title
        print(f"  {idx}. id={template_id} | title={item_title}", flush=True)

    choice = input("[模板] 请输入序号选择模板，直接回车或输入 0 跳过: ").strip()
    if not choice or choice == "0":
        print("[模板] 已跳过行业模板", flush=True)
        return None, None
    if not choice.isdigit():
        print(f"[模板] 无效序号：{choice}，跳过行业模板", flush=True)
        return None, None

    index = int(choice) - 1
    if index < 0 or index >= len(template_items):
        print(f"[模板] 序号超出范围：{choice}，跳过行业模板", flush=True)
        return None, None

    selected = template_items[index]
    template_id = (
        selected.get("id")
        or selected.get("tmpplateId")
        or selected.get("templateId")
        or selected.get("aiTemplateId")
    )
    if template_id is None:
        print("[模板] 选中的模板缺少 ID，跳过行业模板", flush=True)
        return None, None

    selected_title = str(selected.get("title") or "").strip() or category_title
    print(f"[模板] 已选择: id={template_id}, title={selected_title}, tabType={tab_type}", flush=True)
    return int(template_id), selected_title


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
    tmpplateId: int | None = None,
    title: str | None = None,
) -> bool:
    """在发起 generateVideo 前请求用户确认。"""
    preview = prompt.replace("\n", " ").strip()
    if len(preview) > 160:
        preview = f"{preview[:160]}..."

    print("[确认] 即将调用 generateVideo", flush=True)
    print(f"[确认] 参数: model={model}, duration={duration}, aspectRatio={aspectRatio}, variants={variants}", flush=True)
    if tmpplateId is not None:
        print(f"[确认] 模板: tmpplateId={tmpplateId}, title={title or '-'}", flush=True)
    print(f"[确认] 提示词预览: {preview}", flush=True)
    answer = input("[确认] 是否继续生成视频？输入 y 继续，其他任意键取消: ").strip().lower()
    return answer in {"y", "yes"}


def generate_video(
    base_url: str,
    image_urls: str | list[str] | tuple[str, ...],
    system_prompt: str,
    session: requests.Session,
    aspectRatio: str = "9:16",
    duration: int = 10,
    model: str = "auto",
    variants: int = 1,
    tmpplateId: int | None = None,
    title: str | None = None,
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
    normalized_urls = normalize_image_paths(image_urls)
    payload = {
        "urls": normalized_urls,
        "prompt": system_prompt,
        "aspectRatio": aspectRatio,
        "duration": duration,
        "variants": variants,
    }
    # model 参数按接口配置传递，也兼容调用方显式传空时跳过
    if model:
        payload["model"] = model
    if tmpplateId is not None:
        payload["tmpplateId"] = tmpplateId
        payload["title"] = title or ""
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
    rep_status = _extract_rep_status(record)
    rep_status_label = _STATUS_LABELS.get(rep_status, "未知") if rep_status is not None else "无"
    req_msg = record.get("reqMsg") or ""
    rep_msg = record.get("repMsg") or record.get("message") or record.get("msg") or record.get("errorMsg") or ""
    return (
        f"topStatus={status}({status_label}), "
        f"repStatus={rep_status}({rep_status_label}), "
        f"reqMsg={req_msg}, repMsg={rep_msg}"
    )


def _parse_rep_msg(record: dict) -> dict | None:
    """解析 getById 中的 repMsg JSON。"""
    rep_msg = record.get("repMsg")
    if not rep_msg or not isinstance(rep_msg, str):
        return None
    try:
        parsed = json.loads(rep_msg)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    data = parsed.get("data")
    return data if isinstance(data, dict) else None


def _extract_rep_status(record: dict) -> str | int | None:
    """提取 repMsg 中的下游任务状态。"""
    rep_data = _parse_rep_msg(record)
    if not rep_data:
        return None
    return rep_data.get("status")


def _extract_video_url_from_rep_msg(record: dict) -> str | None:
    """兼容 repMsg 中包含 result 视频链接的场景。"""
    rep_data = _parse_rep_msg(record)
    if not rep_data:
        return None
    result = rep_data.get("result")
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
                rep_status = _extract_rep_status(record)
                print(f"[轮询] 第{attempt}次：{_build_status_text(record)}", flush=True)
                direct_video_url = get_video_url(record)
                if direct_video_url:
                    print(f"[轮询] 第{attempt}次：已拿到视频地址，顶层状态未必同步，直接进入下载", flush=True)
                    return record, "success"
                rep_video_url = _extract_video_url_from_rep_msg(record)
                if rep_video_url:
                    record["mediaUrl"] = record.get("mediaUrl") or rep_video_url
                    print(f"[轮询] 第{attempt}次：repMsg 已包含成片链接，顶层状态未必同步，直接进入下载", flush=True)
                    return record, "success"
                if status in _STATUS_SUCCESS or rep_status in _STATUS_SUCCESS:
                    print(f"[轮询] 视频已完成 id={task_id}", flush=True)
                    return record, "success"
                if status in _STATUS_FAILED or rep_status in _STATUS_FAILED:
                    msg = record.get("msg") or record.get("message") or record.get("errorMsg", "")
                    print(
                        f"[错误] 视频生成失败 topStatus={status}, repStatus={rep_status}, msg={msg}, record={record}",
                        flush=True,
                    )
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

    top_status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
    rep_status = _extract_rep_status(record)
    video_url = get_video_url(record)
    if not video_url:
        rep_video_url = _extract_video_url_from_rep_msg(record)
        if rep_video_url:
            video_url = rep_video_url
    if not video_url and (top_status in _STATUS_FAILED or rep_status in _STATUS_FAILED):
        raise RuntimeError(
            f"任务 {resolved_task_id} 已失败: topStatus={top_status}, repStatus={rep_status}, record={record}"
        )
    if not video_url:
        raise RuntimeError(
            f"任务 {resolved_task_id} 暂无可下载视频地址: topStatus={top_status}, repStatus={rep_status}, record={record}"
        )

    return download_video(
        video_url,
        resolved_output_dir,
        filename=resolved_filename,
        session=session,
        retries=video_cfg.get("download_retries", 3),
        retry_interval=video_cfg.get("download_retry_interval", 5),
    )


def start_background_poll(task_id: str, token: str) -> None:
    """提交任务后拉起后台轮询脚本，优先使用 openclaw_upload/.venv 中的 Python。"""
    poll_script = Path(__file__).parent / "poll_and_notify.py"
    if not poll_script.exists():
        print(f"[警告] 未找到后台轮询脚本：{poll_script}", flush=True)
        return

    upload_root = Path(__file__).resolve().parent.parent
    venv_python = _resolve_venv_python(upload_root / ".venv")
    python_bin = venv_python or Path(sys.executable)

    poll_log = Path(__file__).parent / "poll_and_notify.log"
    cmd = [
        str(python_bin),
        str(poll_script),
        str(task_id),
        f"--token={token}",
    ]

    print(f"[后台轮询] 启动：{python_bin} poll_and_notify.py {task_id}", flush=True)

    with poll_log.open("a", encoding="utf-8") as log_fp:
        subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=log_fp,
            stderr=log_fp,
        )


# ---------------------------------------------------------------------------
# 主流程入口
# ---------------------------------------------------------------------------

def run_workflow(
    image_path: str | list[str] | tuple[str, ...],
    *,
    token: str | None = None,
    model: str | None = None,
    duration: int | None = None,
    aspectRatio: str | None = None,
    variants: int | None = None,
    tmpplateId: int | None = None,
    title: str | None = None,
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
    aspectRatio = aspectRatio or video_cfg.get("aspectRatio", "9:16")
    variants = variants if variants is not None else video_cfg.get("variants", 1)
    confirm_before_generate = video_cfg.get("confirm_before_generate", True)

    token_val = token or load_saved_token()
    if not token_val:
        print("[错误] 请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx", flush=True)
        sys.exit(1)
    if tmpplateId is not None and not (title or "").strip():
        print("[错误] 使用模板生成时必须同时传入 title", flush=True)
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

    try:
        local_image_paths = normalize_image_paths(image_path)
    except ValueError as e:
        print(f"[错误] {e}", flush=True)
        sys.exit(1)

    print(f"[3/7] 上传图片... 共 {len(local_image_paths)} 张", flush=True)
    image_urls: list[str] = []
    for idx, current_path in enumerate(local_image_paths, start=1):
        image_url = upload_image(upload_url, current_path, session)
        if not image_url:
            sys.exit(1)
        image_urls.append(image_url)
        print(f"[OK] 第{idx}/{len(local_image_paths)}张图片已上传：{image_url}", flush=True)

    if tmpplateId is None and not auto_confirm:
        selected_template_id, selected_template_title = select_industry_template(base_url, session)
        if selected_template_id is not None:
            tmpplateId = selected_template_id
            title = selected_template_title

    # [4/7] 图生文获取提示词（如果传入了自定义 prompt 则跳过）
    if prompt:
        print(f"[4/7] 使用自定义提示词...", flush=True)
        system_prompt = prompt
    else:
        print("[4/7] 图生文获取提示词... (默认使用第1张图片)", flush=True)
        system_prompt = image_to_text(base_url, image_urls[0], session)
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
            tmpplateId=tmpplateId,
            title=title,
        ):
            print("[已取消] 用户未确认，停止发起视频生成", flush=True)
            sys.exit(0)

    print(f"[5/7] 本次提交 {len(image_urls)} 个图片地址:", flush=True)
    for idx, image_url in enumerate(image_urls, start=1):
        print(f"[5/7]   {idx}. {image_url}", flush=True)
    print(
        f"[5/7] 发起视频生成... (images={len(image_urls)}, model={model}, duration={duration}s, aspectRatio={aspectRatio}, variants={variants})",
        flush=True,
    )
    if tmpplateId is not None:
        print(f"[5/7] 使用模板生成: tmpplateId={tmpplateId}, title={title}", flush=True)
    task_id = generate_video(
        base_url, image_urls, system_prompt, session,
        aspectRatio=aspectRatio,
        duration=duration,
        model=model,
        variants=variants,
        tmpplateId=tmpplateId,
        title=title,
    )
    if not task_id:
        sys.exit(1)
    print(f"[OK] 任务 ID: {task_id}")
    start_background_poll(task_id, token_val)
    print(f"[完成] 已提交任务 {task_id}，后台轮询已启动", flush=True)
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
        print("  python zhenlongxia_workflow.py <图片路径1> [图片路径2 ...] [选项]")
        print("  python zhenlongxia_workflow.py --list-models [--token=xxx]")
        print("  python zhenlongxia_workflow.py --list-templates [--mediaType=1] [--tabType=0] [--pageNum=1] [--pageSize=10] [--token=xxx]")
        print()
        print("选项:")
        print("  --token=xxx          Token（也可写入 token.txt）")
        print("  --list-models        查询可用模型、时长与比例")
        print("  --list-templates     先查模板分类，再按 tabType 查询行业模板")
        print("  --mediaType=N        模板分类 mediaType，默认 1")
        print("  --tabType=N          模板 tabType；不传则优先取 tabName=行业模板")
        print("  --pageNum=N          模板分页页码，默认 1")
        print("  --pageSize=N         模板分页大小，默认 10")
        print("  --model=MODEL        模型值，来自模型配置接口")
        print("  --duration=N         视频时长，需匹配所选模型")
        print("  --aspectRatio=XXX    画面比例，需匹配所选模型")
        print("  --variants=N         生成变体数量")
        print("  --tmpplateId=ID      模板 ID，透传给 generateVideo")
        print("  --templateId=ID      模板 ID，兼容别名，透传为 tmpplateId")
        print("  --title=TEXT         模板标题/产品名称；交互选模板时默认取模板标题")
        print("  --yes                跳过发起视频前的人工确认")
        print("  --id=ID              按任务 ID 直接下载已生成视频")
        print("  --fetch-by-id=ID     按任务 ID 直接下载已生成视频（兼容旧参数）")
        print()
        print("示例:")
        print("  python zhenlongxia_workflow.py ./my_image.jpg")
        print("  python zhenlongxia_workflow.py ./img1.jpg ./img2.jpg ./img3.jpg --model=grok_imagine --duration=10 --yes")
        print("  python zhenlongxia_workflow.py --list-models")
        print("  python zhenlongxia_workflow.py ./my_image.jpg --model=sora2-new --duration=10")
        print("  python zhenlongxia_workflow.py ./my_image.jpg --model=grok_imagine --duration=10 --aspectRatio=9:16 --variants=1 --yes")
        print("  python zhenlongxia_workflow.py --list-templates --mediaType=1")
        print("  python zhenlongxia_workflow.py --list-templates --mediaType=1 --tabType=0")
        print("  python zhenlongxia_workflow.py ./my_image.jpg --tmpplateId=1001 --title=产品名 --yes")
        print("  python zhenlongxia_workflow.py --id=123456")
        print("  python zhenlongxia_workflow.py --fetch-by-id=123456")
        sys.exit(1)

    image_paths: list[str] = []
    fetch_task_id = None
    list_models = False
    list_templates = False
    token = None
    model = None
    duration = None
    aspectRatio = None
    variants = None
    page_num = 1
    page_size = 20
    media_type = 1
    tab_type = None
    tmpplateId = None
    title = None
    auto_confirm = False

    for arg in sys.argv[1:]:
        if arg == "--list-models":
            list_models = True
        elif arg == "--list-templates":
            list_templates = True
        elif arg.startswith("--id="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--fetch-by-id="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--traeid="):
            fetch_task_id = arg.split("=", 1)[1]
        elif arg.startswith("--token="):
            token = arg.split("=", 1)[1]
        elif arg.startswith("--mediaType="):
            media_type = int(arg.split("=", 1)[1])
        elif arg.startswith("--tabType="):
            tab_type = int(arg.split("=", 1)[1])
        elif arg.startswith("--pageNum="):
            page_num = int(arg.split("=", 1)[1])
        elif arg.startswith("--pageSize="):
            page_size = int(arg.split("=", 1)[1])
        elif arg.startswith("--model="):
            model = arg.split("=", 1)[1]
        elif arg.startswith("--duration="):
            duration = int(arg.split("=", 1)[1])
        elif arg.startswith("--aspectRatio="):
            aspectRatio = arg.split("=", 1)[1]
        elif arg.startswith("--variants="):
            variants = int(arg.split("=", 1)[1])
        elif arg.startswith("--tmpplateId="):
            tmpplateId = int(arg.split("=", 1)[1])
        elif arg.startswith("--templateId="):
            tmpplateId = int(arg.split("=", 1)[1])
        elif arg.startswith("--title="):
            title = arg.split("=", 1)[1]
        elif arg == "--yes":
            auto_confirm = True
        elif not arg.startswith("--"):
            image_paths.append(arg)

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

    if list_templates:
        config = load_config()
        base_url = config["base_url"].rstrip("/")
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
        category_items = fetch_template_categories(base_url, session, media_type=media_type)
        print_template_categories(category_items)
        if tab_type is not None:
            tab_types = [tab_type]
        else:
            industry_category = find_template_category_by_name(
                category_items,
                tab_name="行业模板",
            )
            if industry_category and industry_category.get("tabType") is not None:
                tab_types = [industry_category.get("tabType")]
            else:
                tab_types = [
                    item.get("tabType")
                    for item in category_items
                    if item.get("tabType") is not None
                ]
        seen_tab_types: set[int] = set()
        for current_tab_type in tab_types:
            if current_tab_type in seen_tab_types:
                continue
            seen_tab_types.add(current_tab_type)
            category = find_template_category(category_items, tab_type=current_tab_type)
            mapped_title = (category or {}).get("tabName") or ""
            print(
                f"分类映射: title={mapped_title or '-'}, tabType={current_tab_type}",
                flush=True,
            )
            print(f"tabType={current_tab_type} 的行业模板:", flush=True)
            template_items = fetch_template_options(
                base_url,
                session,
                page_num=page_num,
                page_size=page_size,
                tab_type=current_tab_type,
            )
            print_template_options(template_items)
        return

    if fetch_task_id:
        local_path = fetch_generated_video(task_id=fetch_task_id, token=token)
        print(f"[完成] 视频已保存：{local_path}")
        return

    if not image_paths:
        print("错误：缺少图片路径，或请使用 --id=ID")
        sys.exit(1)

    resolved_image_paths: list[str] = []
    for image_path in image_paths:
        current_path = image_path
        if not os.path.isfile(current_path):
            alt = Path(__file__).parent / os.path.basename(current_path)
            if alt.exists():
                current_path = str(alt)
            else:
                print(f"错误：文件不存在 {current_path}")
                sys.exit(1)
        resolved_image_paths.append(current_path)

    run_workflow(
        resolved_image_paths,
        token=token,
        model=model,
        duration=duration,
        aspectRatio=aspectRatio,
        variants=variants,
        tmpplateId=tmpplateId,
        title=title,
        auto_confirm=auto_confirm,
    )


if __name__ == "__main__":
    main()
