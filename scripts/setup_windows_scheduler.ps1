<#
.SYNOPSIS
    Windows 작업 스케줄러에 quant_ko 자동매매 및 일일 모니터링 작업을 등록하는 스크립트.

.DESCRIPTION
    1. QuantKo-Rebalance: 매월 말일 15:20에 월별 리밸런싱 자동 실행
    2. QuantKo-DailyMonitor: 매주 월~금 08:30에 관리종목/거래정지 비상 감시 자동 실행
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment Python executable not found at: $PythonExe"
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [quant_ko] Windows 작업 스케줄러 자동 등록 마법사" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "프로젝트 경로 : $ProjectRoot"
Write-Host "파이썬 실행기 : $PythonExe"
Write-Host ""

# 1. 일일 모니터링 작업 (매주 월~금 08:30)
$MonitorTaskName = "QuantKo-DailyMonitor"
$MonitorAction = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m quant_ko.main --mode monitor" -WorkingDirectory $ProjectRoot
$MonitorTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 08:30AM
$MonitorSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Write-Host "1. 일일 비상 모니터링 작업 등록 중 ($MonitorTaskName, 평일 08:30)..." -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName $MonitorTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $MonitorTaskName -Action $MonitorAction -Trigger $MonitorTrigger -Settings $MonitorSettings -Description "quant_ko 소형주 퀀트 일일 관리종목 비상 모니터링" | Out-Null
    Write-Host "  -> [성공] $MonitorTaskName 등록 완료!" -ForegroundColor Green
} catch {
    Write-Warning "  -> 등록 실패: $_"
}

# 2. 월별 리밸런싱 작업 (매월 28~31일 15:20에 실행되어 거래일 여부 판별)
$RebalanceTaskName = "QuantKo-MonthlyRebalance"
$RebalanceAction = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m quant_ko.main --mode rebalance" -WorkingDirectory $ProjectRoot
$RebalanceTrigger = New-ScheduledTaskTrigger -Daily -At 03:20PM
$RebalanceSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Write-Host "2. 월별 리밸런싱 자동 작업 등록 중 ($RebalanceTaskName, 매일 15:20 확인)..." -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName $RebalanceTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $RebalanceTaskName -Action $RebalanceAction -Trigger $RebalanceTrigger -Settings $RebalanceSettings -Description "quant_ko 소형주 퀀트 월말 15:20 리밸런싱 실행" | Out-Null
    Write-Host "  -> [성공] $RebalanceTaskName 등록 완료!" -ForegroundColor Green
} catch {
    Write-Warning "  -> 등록 실패: $_"
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 모든 자동 스케줄러 등록이 완료되었습니다!" -ForegroundColor Cyan
Write-Host " - 작업 스케줄러(taskschd.msc)에서 언제든 확인 및 수동 실행이 가능합니다."
Write-Host "==========================================================" -ForegroundColor Cyan
