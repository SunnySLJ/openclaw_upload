# 帧龙虾（zhenlongxia）图生视频工具

核心流程：上传图片 -> 图生文 -> 按模型配置生成视频 -> 轮询 getById -> 下载视频。

## 关键文件
- `flash_longxia/zhenlongxia_workflow.py`：主流程（生产用）
- `flash_longxia/debug_apis.py`：分步调试接口
- `flash_longxia/download_latest_video.py`：按任务 ID 补下载
- `flash_longxia/device_verify.py`：设备 MAC 鉴权预留
- `config.example.yaml`：配置模板

## 使用
1) 准备 token：放到 `flash_longxia/token.txt`
2) 运行主流程：
   `python3.12 flash_longxia/zhenlongxia_workflow.py <图片路径>`
   如需查看可用模型：
   `python3.12 flash_longxia/zhenlongxia_workflow.py --list-models`
3) 若外部已拿到生成任务 ID，可直接补下载：
   `python3.12 flash_longxia/zhenlongxia_workflow.py --id=<任务ID>`
   `python3.12 flash_longxia/download_latest_video.py <任务ID>`

## 说明
- 本项目强制使用 Python 3.12；若版本不符，入口脚本会直接退出。
- 若仓库根目录存在 `.venv/bin/python3.12`，入口脚本会优先自动切换到该解释器运行。
- 模型、时长、比例来自 `GET /api/v1/globalConfig/getModel?modelType=1`，生成前会按接口返回值校验。
- 轮询间隔、超时、下载重试可在 `config.yaml` 配置。
- 当后端状态字段滞后时，主流程会尝试解析 `repMsg` 中的 `result` 链接并直接下载。

## 迁移
- 不要直接复制旧机器的 `.venv`；在新机器重新创建并安装依赖。
- 仓库内脚本现在默认按“脚本所在目录”定位 `flash_longxia/output` 等路径，不再依赖固定绝对路径。
- 若你的 OpenClaw 工作区不在默认位置，设置 `OPENCLAW_UPLOAD_ROOT` 指向仓库根目录，设置 `OPENCLAW_WORKSPACE_ROOT` 指向工作区根目录。
- 需要微信通知时，设置 `OPENCLAW_WECHAT_TARGET` 或 `FLASH_LONGXIA_WECHAT_TARGET`。
