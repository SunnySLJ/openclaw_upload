# 🦐 龙虾上传 - 配置文件汇总

所有配置文件的详细说明和使用指南。

---

## 📁 配置文件列表

| 配置文件 | 路径 | 用途 |
|----------|------|------|
| **video_config.json** | `openclaw_upload/skills/flash-longxia/` | 视频生成参数、Token 校验 |
| **publish_config.json** | `openclaw_upload/skills/flash-longxia/` | 多平台发布行为 |
| **notification_config.json** | `openclaw_upload/skills/flash-longxia/` | 通知开关和模板 |
| **cleanup_config.json** | `openclaw_upload/skills/flash-longxia/` | 文件自动清理 |
| **paths_config.json** | `openclaw_upload/skills/flash-longxia/` | 文件路径和端口配置 |
| **login_check_config.json** | `skills/auth/` | 登录状态定时检查 |

---

## 🔧 快速修改指南

### 修改视频生成默认参数

编辑 `video_config.json`：
```json
{
  "defaults": {
    "model": "auto",           // 改成 sora2-new 使用 HT2.0
    "duration": 10,            // 改成 15 使用 15 秒
    "aspectRatio": "9:16"      // 改成 16:9 使用横屏
  }
}
```

### 修改登录检查时间

编辑 `login_check_config.json`：
```json
{
  "daily_check_time": "10:10"  // 改成 "09:00" 或其他时间
}
```
然后告诉我，我帮你更新 cron 任务～

### 修改默认发布平台

编辑 `publish_config.json`：
```json
{
  "default_platforms": ["douyin", "xiaohongshu"]
  // 改成 ["douyin"] 只发抖音
  // 或 ["douyin", "xiaohongshu", "kuaishou", "shipinhao"] 全平台
}
```

### 关闭某些通知

编辑 `notification_config.json`：
```json
{
  "wechat": {
    "notify_on_publish_success": false  // 关闭发布成功通知
  }
}
```

---

## 📋 配置项详解

### video_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `defaults.model` | 默认模型 | `auto` |
| `defaults.duration` | 默认时长（秒） | `10` |
| `defaults.aspectRatio` | 默认比例 | `9:16` |
| `max_wait_minutes` | 最大等待时间（分钟） | `30` |
| `poll_interval_seconds` | 轮询间隔（秒） | `30` |
| `auto_confirm` | 跳过用户确认 | `false` |
| `token.auto_check` | 自动检查 Token | `true` |

### publish_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `default_platforms` | 默认发布平台 | 抖音 + 小红书 |
| `publish_order` | 发布优先级 | 抖音→小红书→快手→视频号 |
| `skip_on_login_expired` | 登录失效时跳过 | `true` |
| `auto_retry_failed` | 失败自动重试 | `false` |
| `close_browser_after_upload` | 上传后关闭浏览器 | `true` |

### notification_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `wechat.notify_on_task_complete` | 视频完成通知 | `true` |
| `wechat.notify_on_publish_success` | 发布成功通知 | `true` |
| `wechat.notify_on_login_expired` | 登录失效通知 | `true` |
| `feishu.enabled` | 飞书通知开关 | `false` |

### cleanup_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `output_cleanup.enabled` | 启用输出目录清理 | `true` |
| `output_cleanup.schedule` | 清理时间（Cron） | `0 1 * * 2`（每周二 1AM） |
| `output_cleanup.keep_days` | 保留天数 | `7` |
| `screenshot_cleanup.delete_after_scan` | 扫码后自动删除 | `true` |

### paths_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `workspace_root` | OpenClaw 工作区根目录 | `${OPENCLAW_WORKSPACE_ROOT}` |
| `openclaw_upload_root` | 当前仓库根目录 | `${OPENCLAW_UPLOAD_ROOT}` |
| `paths.inbound_images` | 图片保存目录 | `${OPENCLAW_WORKSPACE_ROOT}/inbound_images/` |
| `paths.video_output` | 视频输出目录 | `flash_longxia/output/` |
| `chrome_profiles.douyin.port` | 抖音 Chrome 端口 | `9224` |
| `chrome_profiles.xiaohongshu.port` | 小红书 Chrome 端口 | `9223` |
| `chrome_profiles.kuaishou.port` | 快手 Chrome 端口 | `9225` |
| `chrome_profiles.shipinhao.port` | 视频号 Chrome 端口 | `9226` |

迁移建议：
- 新机器优先设置 `OPENCLAW_UPLOAD_ROOT` 和 `OPENCLAW_WORKSPACE_ROOT`，不要把旧机器绝对路径直接写回配置。
- `flash_longxia/output`、`flash_longxia/temp`、`cookies/` 建议保持仓库内相对路径，方便整体迁移。

### login_check_config.json

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `daily_check_time` | 检查时间 | `10:10` |
| `platforms` | 检查平台 | 当前仅视频号 |
| `auto_retry_login` | 自动恢复登录 | `true` |
| `qr_code_notify` | 发送二维码 | `true` |

---

## 💡 常用修改场景

### 场景 1：只想发抖音
```json
// publish_config.json
{
  "default_platforms": ["douyin"]
}
```

### 场景 2：视频默认横屏
```json
// video_config.json
{
  "defaults": {
    "aspectRatio": "16:9"
  }
}
```

### 场景 3：改成每天早上 9 点检查视频号登录
```json
// login_check_config.json
{
  "daily_check_time": "09:00"
}
```
然后告诉我更新 cron～

### 场景 4：关闭所有通知
```json
// notification_config.json
{
  "wechat": {
    "enabled": false
  }
}
```

### 场景 5：视频保留 3 天就清理
```json
// cleanup_config.json
{
  "output_cleanup": {
    "keep_days": 3
  }
}
```

---

## 🦐 有问题随时找我！

千千如果想改什么配置但找不到地方，直接告诉我就好啦～
比如：
- "把视频默认时长改成 15 秒"
- "以后只发抖音和小红书"
- "改成每天晚上 8 点检查登录"
- "关闭发布成功的通知"

我都会帮你改好配置文件 + 更新相关设置！💕

---

_最后更新：2026-03-31_
