# Flow Radar 72小时验证 - 后台运行版本
# 用法: powershell -ExecutionPolicy Bypass -File start_72h_background.ps1

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "========================================"
Write-Host "Flow Radar 72小时验证 (后台模式)"
Write-Host "========================================"
Write-Host ""

# 运行验收测试
Write-Host "[1/2] 运行验收测试..."
python tests/test_acceptance.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "验收测试失败，请修复后重试" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[2/2] 启动72小时验证 (后台)..."

$LogFile = "logs\72h_run_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
Write-Host "日志文件: $LogFile"
Write-Host ""

# 启动后台进程
$process = Start-Process -FilePath "python" `
    -ArgumentList "alert_monitor.py", "-s", "DOGE/USDT" `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "logs\72h_error.log" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "进程已启动: PID = $($process.Id)" -ForegroundColor Green
Write-Host ""
Write-Host "查看日志: Get-Content $LogFile -Wait"
Write-Host "停止进程: Stop-Process -Id $($process.Id)"
Write-Host ""

# 保存 PID 到文件
$process.Id | Out-File -FilePath "logs\72h_pid.txt"
Write-Host "PID 已保存到 logs\72h_pid.txt"
