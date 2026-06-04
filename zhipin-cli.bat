@echo off
chcp 65001 >nul
setlocal

set "PYTHONPATH=d:\G\github\游览器agent\src"
set "VENV_PATH=d:\G\github\游览器agent\.venv"

:: 激活虚拟环境
if exist "%VENV_PATH%\Scripts\activate.bat" (
    call "%VENV_PATH%\Scripts\activate.bat"
)

:: 执行 CLI 命令
python "%~dp0src\cli\main.py" %*

endlocal