---
name: flash-longxia
description: Generate videos from a static image and download completed videos for the zhenlongxia or flash_longxia workflow in this project. Use when the user asks to run this repo's image-to-video pipeline, inspect available models, submit a generation task, download a finished video by task ID, or troubleshoot flash-longxia generation and download issues.
---

# flash-longxia

使用此 skill 时，优先复用 skill 自带脚本，不要重新实现上传、图生文、模型查询、生成和下载 API。

## 定位仓库

- 先定位包含 `flash_longxia/zhenlongxia_workflow.py` 的仓库根目录。
- 封装脚本会优先尝试当前目录、环境变量 `OPENCLAW_UPLOAD_ROOT`、`~/Desktop/openclaw_upload` 和 `~/.openclaw/workspace/openclaw_upload`。
- 若自动定位失败，显式设置 `OPENCLAW_UPLOAD_ROOT=/path/to/openclaw_upload` 再运行命令。

## 前置条件

- 使用 `python3.12`；如果仓库根目录有 `.venv/bin/python3.12`，脚本会自动切换过去。
- 确保 `flash_longxia/config.yaml` 已准备好。
- 确保 `flash_longxia/token.txt` 存在，或在命令中传 `--token=...`。
- 生成任务需要本地图片路径；下载任务需要 `generateVideo` 返回的任务 ID。

## 常用命令

```bash
python3 scripts/generate_video.py --list-models [--token=...]
python3 scripts/generate_video.py <image-path> [--model=...] [--duration=10] [--aspectRatio=16:9] [--variants=1] [--token=...]
python3 scripts/generate_video.py <image-path> --yes [--token=...]
python3 scripts/download_video.py <task-id> [--token=...]
```

## 执行规则

- 先用 `--list-models` 获取可用 `model`、`duration` 和 `aspectRatio`。
- 只传后端模型接口支持的 `model`、`duration`、`aspectRatio` 组合。
- 保持参数名 `aspectRatio` 为驼峰写法。
- 不要向请求体加入 `style` 或 `quality`。
- 图生文失败或提示词校验失败时，立即停止，不要继续发起生成。
- 默认保留人工确认；只有明确需要无人值守时才传 `--yes`。
- 生成成功后返回任务 ID；补下载时调用 `scripts/download_video.py`，不要重写查询逻辑。

## 排错

- 模型参数报错时，先重新执行 `--list-models`。
- 找不到仓库时，检查 `OPENCLAW_UPLOAD_ROOT` 是否指向包含 `flash_longxia/` 的目录。
- Token 报错时，检查 `flash_longxia/token.txt` 或显式传 `--token=...`。
- 下载失败时，确认传入的是生成接口返回的任务 ID，而不是其他业务字段。
