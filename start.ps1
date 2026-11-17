param([switch]$NoScheduler)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonPath = $null

# 优先使用已装好依赖的虚拟环境；空 venv 或缺少 Flask 时自动回退到全局 Python。
foreach ($candidate in @($venvPython, (Get-Command python -ErrorAction SilentlyContinue).Source)) {
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) { continue }
    & $candidate -c "import flask, pyodbc" *> $null
    if ($LASTEXITCODE -eq 0) { $pythonPath = $candidate; break }
}
if (-not $pythonPath) {
    throw '找不到可用的 Python 环境：请先按 README 安装 requirements.txt 中的依赖，或把 python 加入 PATH。'
}
Write-Host "使用 Python：$pythonPath"

$schedulerProcess = $null
try {
    if (-not $NoScheduler) {
        $schedulerProcess = Start-Process -FilePath $pythonPath -ArgumentList 'scripts/maintenance.py','--loop' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    }
    Write-Host '打开 http://127.0.0.1:5000，按 Ctrl+C 停止服务。'
    & $pythonPath run.py
}
finally {
    if ($schedulerProcess -and -not $schedulerProcess.HasExited) {
        Stop-Process -Id $schedulerProcess.Id
    }
}
