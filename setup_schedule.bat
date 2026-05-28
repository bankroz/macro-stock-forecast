@echo off
title 股市宏观分析系统 - 定时任务安装
echo ============================================================
echo   股市宏观分析系统 - 定时任务安装
echo ============================================================
echo(

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 获取当前脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%run.py"

:: 创建定时任务：每周一 09:00 运行
schtasks /create /tn "StockDepositAnalysis" /tr "python \"%PYTHON_SCRIPT%\" --no-fetch" /sc weekly /d MON /st 09:00 /f

if %errorlevel% equ 0 (
    echo(
    echo [成功] 定时任务已创建!
    echo   任务名称: StockDepositAnalysis
    echo   运行频率: 每周一 09:00
    echo   执行脚本: %PYTHON_SCRIPT%
    echo(
    echo 如需手动运行，请执行: python run.py
    echo 如需删除任务，请执行:
    echo   schtasks /delete /tn "StockDepositAnalysis" /f
) else (
    echo(
    echo [失败] 定时任务创建失败，请以管理员身份运行此脚本
)

echo(
pause
