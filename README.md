# 帧龙虾（zhenlongxia）图生视频工具

核心流程：上传图片 -> 可选行业模板 -> 图生文 -> 按模型配置生成视频 -> 后台轮询 getById -> 下载视频。

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
   如需查看行业模板：
   `python3.12 flash_longxia/zhenlongxia_workflow.py --list-templates`
3) 若外部已拿到生成任务 ID，可直接补下载：
   `python3.12 flash_longxia/zhenlongxia_workflow.py --id=<任务ID>`
   `python3.12 flash_longxia/download_latest_video.py <任务ID>`

## 行业模板
- 交互式使用：直接运行主流程且不要带 `--yes`，上传完成后会提示是否选择行业模板。
- 查询模板：`python3.12 flash_longxia/zhenlongxia_workflow.py --list-templates --mediaType=1`
- 指定模板生成：`python3.12 flash_longxia/zhenlongxia_workflow.py <图片路径> --tmpplateId=<模板ID> --title=<模板标题或产品名> --yes`
- `--templateId` 是 `--tmpplateId` 的兼容别名，最终都会透传给 `generateVideo` 的 `tmpplateId` 字段。
- 模板分类默认使用 `mediaType=1`，并优先选择 `tabName=行业模板` 对应的 `tabType`。

## 说明
- 本项目强制使用 Python 3.12；若版本不符，入口脚本会直接退出。
- 若仓库根目录存在 `.venv/bin/python3.12`，入口脚本会优先自动切换到该解释器运行。
- 模型、时长、比例来自 `GET /api/v1/globalConfig/getModel?modelType=1`，生成前会按接口返回值校验。
- 行业模板通过 `api/v1/aiTemplateCategory/getList` 和 `api/v1/aiTemplate/pageList` 获取，生成时只传 `tmpplateId` 与 `title`，不额外传 `style` 或 `quality`。
- 轮询间隔、超时、下载重试可在 `config.yaml` 配置。
- 当后端状态字段滞后时，主流程会尝试解析 `repMsg` 中的 `result` 链接并直接下载。

## 迁移
- 不要直接复制旧机器的 `.venv`；在新机器重新创建并安装依赖。
- 仓库内脚本现在默认按“脚本所在目录”定位 `flash_longxia/output` 等路径，不再依赖固定绝对路径。
- 若你的 OpenClaw 工作区不在默认位置，设置 `OPENCLAW_UPLOAD_ROOT` 指向仓库根目录，设置 `OPENCLAW_WORKSPACE_ROOT` 指向工作区根目录。
- 需要微信通知时，设置 `OPENCLAW_WECHAT_TARGET` 或 `FLASH_LONGXIA_WECHAT_TARGET`。
