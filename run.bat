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
python run.py --no-fetch
echo(
echo ============================================================

:: 检查是否运行成功
if %errorlevel% equ 0 (
    echo [2/3] 分析完成，正在打开报告...
    echo(
    for /f %%f in ('dir /b /o-d "%~dp0reports\*_report.md" 2^>nul') do (
        set "REPORT=%~dp0reports\%%f"
        goto :open_report
    )
    :open_report
    if defined REPORT (
        start "" "%REPORT%"
        echo   报告文件: %REPORT%
    ) else (
        echo   未找到报告文件，请检查 reports/ 目录
    )
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
    echo.
    echo [失败] 分析程序运行出错，请查看 logs/ 目录下的日志文件
)

echo(
pause
