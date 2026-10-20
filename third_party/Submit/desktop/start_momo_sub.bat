@echo off
REM 启动 Momo 字幕 Electron 浮窗（conda 环境 momo_sub 提供 Node 运行时）
REM 快捷键：Ctrl+Alt+S 切换点击穿透（关掉后可拖动 #debug 区域移动窗口）；Ctrl+Alt+Q 退出

cd /d %~dp0

where conda >nul 2>nul
if errorlevel 1 (
    echo [momo_sub] 未找到 conda，请先安装 Anaconda/Miniconda
    pause
    exit /b 1
)

conda env list | findstr /c:"momo_sub" >nul
if errorlevel 1 (
    echo [momo_sub] conda 环境不存在，正在创建（首次需要几分钟）...
    call conda create -y -n momo_sub -c conda-forge nodejs=22
)

if not exist node_modules (
    echo [momo_sub] 首次运行，安装依赖...
    call conda run -n momo_sub --no-capture-output npm install
)

echo [momo_sub] 启动字幕浮窗...
call conda run -n momo_sub --no-capture-output npm start

pause
