@echo off
chcp 65001 >nul
cd /d D:\G\github\游览器agent
set PYTHONPATH=D:\G\github\游览器agent\src
set PYTHONIOENCODING=utf-8

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     智能求职流水线 (优化版)              ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  优化点:
echo    - URL直接加学历/经验筛选参数
echo    - 本地AI自动打分排序
echo    - 仅验证高分公司(>=6分)
echo    - 支持断点续传
echo.
echo  流程:
echo    1. BOSS搜索 (12城 x 12关键词, 带筛选)
echo    2. 本地AI打分
echo    3. 官方验证高分公司
echo    4. 生成推荐报告
echo.
echo  搜索量: 144次 (比旧版264次减少45%%)
echo  筛选: 大专/本科 | 应届/1-3年经验
echo.
pause

python -X utf8 -m modes.zhipin.smart_hunt

echo.
echo  报告: docs\运行结果\搜索报告.md
pause
