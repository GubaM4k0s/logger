# stop_exam.ps1
$ErrorActionPreference = 'SilentlyContinue'
$root  = $PSScriptRoot
$logs  = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$trigger = Join-Path $logs 'STOP.TRIGGER'
Set-Content -Path $trigger -Value '' -Encoding ASCII
