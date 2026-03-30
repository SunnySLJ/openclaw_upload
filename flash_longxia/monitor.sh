#!/bin/bash

OUTPUT_DIR="/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/output"
STATE_FILE="/Users/mima0000/.openclaw/workspace/openclaw_upload/flash_longxia/.monitor_state.json"

echo "🎬 视频监控启动..."

while true; do
    # 获取当前最新的视频文件
    LATEST_VIDEO=$(ls -t "$OUTPUT_DIR"/*.mp4 2>/dev/null | head -1)
    
    if [ -z "$LATEST_VIDEO" ]; then
        echo "⏳ 暂无视频文件..."
        sleep 60
        continue
    fi
    
    LATEST_FILENAME=$(basename "$LATEST_VIDEO")
    
    # 读取当前 state
    CURRENT_STATE=$(cat "$STATE_FILE" 2>/dev/null)
    NOTIFIED_FILE=$(echo "$CURRENT_STATE" | grep -o '"latest_file": *"[^"]*"' | cut -d'"' -f4)
    
    echo "📁 最新视频：$LATEST_FILENAME"
    echo "📋 已通知：$NOTIFIED_FILE"
    
    # 如果发现新视频
    if [ "$LATEST_FILENAME" != "$NOTIFIED_FILE" ]; then
        echo "✨ 发现新视频！发送通知..."
        
        # 使用 openclaw message 发送通知
        openclaw message send \
            --target "openclaw-weixin" \
            --message "🎬 视频生成完成：$LATEST_FILENAME" \
            --media "$LATEST_VIDEO"
        
        # 更新 state 文件
        echo "{\"latest_file\": \"$LATEST_FILENAME\", \"notified\": true}" > "$STATE_FILE"
        
        echo "✅ 通知已发送，state 已更新"
    else
        echo "⏸️  无新视频，继续监控..."
    fi
    
    sleep 60
done
