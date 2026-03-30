#!/bin/bash

OUTPUT_DIR="/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/output"
STATE_FILE="/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/.monitor_state.json"
TIMEOUT_SECONDS=1800  # 30 分钟
CHECK_INTERVAL=60     # 60 秒

# 获取当前已知的最新文件
KNOWN_FILE=$(cat "$STATE_FILE" 2>/dev/null | grep -o '"latest_file": *"[^"]*"' | cut -d'"' -f4)
echo "初始已知文件：$KNOWN_FILE"

START_TIME=$(date +%s)

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    # 检查是否超时
    if [ $ELAPSED -ge $TIMEOUT_SECONDS ]; then
        echo "超时，发送通知"
        # 发送超时通知
        openclaw message send --target="webchat" --message="视频生成超时，已放弃"
        exit 0
    fi
    
    # 查找最新的 mp4 文件
    LATEST_FILE=$(ls -t "$OUTPUT_DIR"/*.mp4 2>/dev/null | head -1 | xargs basename 2>/dev/null)
    
    if [ -n "$LATEST_FILE" ] && [ "$LATEST_FILE" != "$KNOWN_FILE" ]; then
        echo "发现新视频：$LATEST_FILE"
        VIDEO_PATH="$OUTPUT_DIR/$LATEST_FILE"
        
        # 发送通知
        openclaw message send --target="webchat" --message="🎬 视频生成完成"
        openclaw message send --target="webchat" --media="$VIDEO_PATH"
        
        # 更新状态文件
        echo "{\"latest_file\": \"$LATEST_FILE\", \"notified\": true}" > "$STATE_FILE"
        KNOWN_FILE="$LATEST_FILE"
        
        # 重置超时计时器（发现新视频后重新开始计时）
        START_TIME=$(date +%s)
    fi
    
    echo "检查完成，等待 ${CHECK_INTERVAL} 秒..."
    sleep $CHECK_INTERVAL
done
