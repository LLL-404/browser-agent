@echo off
REM ====== BOSS Job Hunter - 开发工具集 ======
REM 用法: dev.bat [command]

setlocal enabledelayedexpansion

if "%1"=="" goto :help
if "%1"=="lint" goto :lint
if "%1"=="format" goto :format
if "%1"=="test" goto :test
if "%1"=="typecheck" goto :typecheck
if "%1"=="security" goto :security
if "%1"=="install-hooks" goto :install_hooks
if "%1"=="all" goto :all
goto :help

:help
echo.
echo  🚀 BOSS Job Hunter - 开发工具集
echo.
echo  命令:
echo    lint          运行 Ruff Linting（代码风格检查）
echo    format        自动格式化代码（Ruff Formatter）
echo    test          运行单元测试（pytest）
echo    typecheck     类型检查（MyPy）
echo    security      安全扫描（Bandit）
echo    install-hooks 安装 Pre-commit Hooks
echo    all           执行所有检查
echo.
exit /b

:lint
echo.
echo 🔍 Running Ruff Linting...
ruff check . --fix
exit /b %ERRORLEVEL%

:format
echo.
echo ✨ Formatting code...
ruff format .
exit /b %ERRORLEVEL%

:test
echo.
echo 🧪 Running tests...
pytest tests/ -v --cov=core --cov-report=term-missing
exit /b %ERRORLEVEL%

:typecheck
echo.
echo 🔎 Type checking with MyPy...
mypy core/ mcp_server/ cli/ --ignore-missing-imports
exit /b %ERRORLEVEL%

:security
echo.
echo 🔒 Security scanning with Bandit...
bandit -r core/ -ll
exit /b %ERRORLEVEL%

:install_hooks
echo.
echo 📦 Installing pre-commit hooks...
pip install pre-commit
pre-commit install
exit /b %ERRORLEVEL%

:all
echo.
echo ====== 🚀 Running All Checks ======
call :lint
if %ERRORLEVEL% neq 0 echo ❌ Lint failed & exit /b 1
call :format
call :test
if %ERRORLEVEL% neq 0 echo ❌ Tests failed & exit /b 1
call :typecheck
call :security
echo.
echo ✅ All checks passed!
exit /b 0

endlocal
