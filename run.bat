@echo off
title 股市宏观分析系统
echo ============================================================
echo   股市宏观分析系统 - 一键运行
echo ============================================================
echo(

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 进入脚本所在目录
cd /d "%~dp0"

echo [1/3] 正在运行分析程序...
echo(

:: 运行 Python，捕获退出码（stderr 不干扰 errorlevel）
python run.py --no-fetch 2>&1
set PY_EXIT=%errorlevel%

echo(
echo ============================================================

if %PY_EXIT% equ 0 (
    echo [2/3] 分析完成，正在打开报告...
    echo(

    :: 用独立子程序打开最新报告，避免标签跳转污染 errorlevel
    call :open_report

    echo(
    echo [3/3] 打开图表目录...
    start "" "%~dp0output"
    echo(
    echo ============================================================
    echo   运行完成!
    echo   - 报告已在默认编辑器中打开
    echo   - 图表目录已打开，请查看 PNG 图片
    echo ============================================================
) else (
    echo(
    echo [失败] 分析程序运行出错（退出码=%PY_EXIT%），请查看 logs/ 目录下的日志文件
)

echo(
pause
exit /b %PY_EXIT%

:: ============================================================
:: 子程序：打开最新报告文件
:: ============================================================
:open_report
    set "REPORT="
    for /f "delims=" %%f in ('dir /b /o-d "%~dp0reports\*_report.md"') do (
        if not defined REPORT set "REPORT=%%f"
    )
    if defined REPORT (
        start "" "%~dp0reports\%REPORT%"
        echo   报告文件: %~dp0reports\%REPORT%
    ) else (
        echo   未找到报告文件，请检查 reports/ 目录
    )
    exit /b 0
