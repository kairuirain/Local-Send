@echo off
chcp 65001 >nul
echo ============================================
echo     局域网文件分享中心 - 依赖安装工具
echo ============================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.7或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] Python版本检测通过
python --version
echo.

:: 安装依赖
echo [2/2] 正在安装依赖库 flask...
pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple

if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络连接或手动运行:
    echo   pip install flask
    pause
    exit /b 1
)

echo.
echo ============================================
echo     安装完成！
echo ============================================
echo.
echo 现在可以运行程序了:
echo   python main.py
echo.
pause
