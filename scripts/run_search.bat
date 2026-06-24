@echo off
chcp 65001 >nul
cd /d D:\G\github\游览器agent
set PYTHONPATH=D:\G\github\游览器agent\src
set PYTHONIOENCODING=utf-8
echo ========================================
echo  求职搜索工具箱
echo ========================================
echo.
echo  1 = BOSS 直聘搜索岗位 (12城 x 22关键词)
echo  2 = 企查查验证公司 (商业平台)
echo  3 = 国家企业信用信息公示系统验证 (官方, 合规)
echo  4 = 完整流水线 (搜索 + 官方验证)
echo.
set /p choice="请选择 (1/2/3/4): "

if "%choice%"=="1" (
    python -X utf8 -m modes.zhipin.pipeline
) else if "%choice%"=="2" (
    python -X utf8 -m modes.zhipin.pipeline
    echo 运行时选择选项 2
) else if "%choice%"=="3" (
    python -X utf8 -m modes.zhipin.gov_verify
) else if "%choice%"=="4" (
    echo --- 先搜索 ---
    python -X utf8 -m modes.zhipin.search_flow
    echo --- 再官方验证 ---
    python -X utf8 -m modes.zhipin.gov_verify
) else (
    echo 无效选择
)

pause
