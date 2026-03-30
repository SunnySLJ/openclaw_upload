@echo off
REM =============================================================================
REM 帧龙虾主流程启动器（Windows）
REM 强制使用 Python 3.12，并使用项目根目录 venv，避免系统 conda 与依赖冲突
REM 用法: run.bat <图片路径> [其它传给 zhenlongxia_workflow.py 的参数]
REM =============================================================================
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo 正在创建虚拟环境...
    py -3.12 -m venv venv
    venv\Scripts\pip install -r requirements.txt -q
)
venv\Scripts\python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
    echo 当前 venv 不是 Python 3.12，正在重建...
    rmdir /s /q venv
    py -3.12 -m venv venv
    venv\Scripts\pip install -r requirements.txt -q
)
venv\Scripts\python flash_longxia\zhenlongxia_workflow.py %*
