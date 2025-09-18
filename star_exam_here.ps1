# start_exam_here.ps1
$ErrorActionPreference = 'SilentlyContinue'
$root  = $PSScriptRoot
$logs  = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$logFile = Join-Path $logs 'log01.txt'
Start-Transcript -Path $logFile -Append
Write-Host "Transcript ON -> $logFile"
Start-Process python -WorkingDirectory $root -ArgumentList "`"$root\logger.py`""
