param([switch]$NoScheduler)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = if (Test-Path -LiteralPath "$PSScriptRoot\.venv\Scripts\python.exe") { "$PSScriptRoot\.venv\Scripts\python.exe" } else { (Get-Command python).Source }
$schedulerProcess = $null
try {
    if (-not $NoScheduler) {
        $schedulerProcess = Start-Process -FilePath $pythonPath -ArgumentList 'scripts/maintenance.py','--loop' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    }
    Write-Host 'Open http://127.0.0.1:5000 - press Ctrl+C to stop.'
    & $pythonPath run.py
}
finally {
    if ($schedulerProcess -and -not $schedulerProcess.HasExited) {
        Stop-Process -Id $schedulerProcess.Id
    }
}
