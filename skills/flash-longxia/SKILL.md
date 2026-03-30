---
name: flash-longxia
description: Use this skill when the user wants to generate a video from a static image through the zhenlongxia workflow in this repo, or download a generated video by task id.
---

# flash-longxia

将静态图片提交到真龙虾工作流发起视频生成任务，或按任务 ID 下载已生成视频。

## 何时使用

- 用户提到“生成视频”“图生视频”“图片转视频”“真龙虾”“flash-longxia”
- 用户提到“下载视频”“获取视频”“按 id 下载”“补下载”
- 需要调用本仓库的 `flash_longxia/zhenlongxia_workflow.py`

## 入口

- 主脚本: `/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/zhenlongxia_workflow.py`
- 封装脚本: `/Users/mima0000/.openclaw/workspace/openclaw_upload/skills/flash-longxia/scripts/generate_video.py`
- 下载脚本: `/Users/mima0000/.openclaw/workspace/openclaw_upload/skills/flash-longxia/scripts/download_video.py`
- 配置文件: `/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/config.yaml`

## 前置条件

- `flash_longxia/token.txt` 存在，或命令行传 `--token=...`
- 生成时输入是本地图片路径
- 下载时输入是 `generateVideo` 返回的任务 `id`

## 实际流程

1. 上传图片到 `/api/v1/file/upload`
2. 调用 `/api/v1/aiMediaGenerations/imageToText` 生成提示词
3. 先校验提示词是否生成成功
4. 默认先请求用户确认
5. 只有确认且提示词成功后才调用 `/api/v1/aiMediaGenerations/generateVideo`
6. 返回任务 ID
7. 需要补下载时，调用 `fetch_generated_video(id=任务ID)` 查询 `getById?id=` 并下载视频

## 视频生成参数

只使用这组参数，不要再引入风格模板或画质参数：

```python
{
  "poll_interval": 30,
  "max_wait_minutes": 30,
  "download_retries": 3,
  "download_retry_interval": 5,
  "output_dir": "./output",
  "confirm_before_generate": true,
  "model": "auto",
  "duration": 10,
  "aspectRatio": "16:9",
  "variants": 1,
}
```

`generateVideo` 请求体固定为：

```json
{
  "aspectRatio": "16:9",
  "duration": 10,
  "model": "auto",
  "prompt": "...",
  "urls": ["..."],
  "variants": 1
}
```

## 命令行用法

```bash
cd /Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia
python3 zhenlongxia_workflow.py <图片路径>
python3 zhenlongxia_workflow.py <图片路径> --model=auto --duration=10 --aspectRatio=9:16 --variants=1
python3 zhenlongxia_workflow.py <图片路径> --model=auto --duration=10 --aspectRatio=9:16 --variants=1 --yes
```

或：

```bash
cd /Users/mima0000/.openclaw/workspace/openclaw_upload/skills/flash-longxia/scripts
python3 generate_video.py <图片路径> --model=auto --duration=10 --aspectRatio=16:9 --variants=1
python3 download_video.py <任务ID>
```

## 约束

- `model` 只允许 `auto`
- `aspectRatio` 使用驼峰写法
- 不要使用 `style`
- 不要使用 `quality`
- 提示词校验失败时，不能继续生成视频
- 默认会在 `generateVideo` 前要求人工确认
- 传 `--yes` 可以跳过确认

## 排错

- 提示词失败：先看 `imageToText` 返回值，确认不是空串、错误文本或未解析对象
- 视频失败：检查 `generateVideo` 返回的任务信息
- 下载失败：确认传入的是 `generateVideo` 返回的任务 `id`，并检查 `getById?id=` 返回内容
