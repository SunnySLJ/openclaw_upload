# =============================================================================
# PowerShell 启动主流程（优先使用项目 venv，其次 py 启动器）
# 用法: .\run_no_conda.ps1 <图片路径>
# =============================================================================
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$venvPython = Join-Path $rootDir "venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    & $venvPython "$scriptDir\zhenlongxia_workflow.py" $args
} else {
    py "$scriptDir\zhenlongxia_workflow.py" $args
}
