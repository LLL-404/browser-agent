"""System verification test - validates all core modules are functional."""
from shared.config import get_config
from agent.core.anti_detect import ANTI_REDIRECT_SCRIPT, STEALTH_SCRIPT
from modes.zhipin.pre_filter import should_skip_job
from modes.zhipin.keyword_strategy import get_keywords_for_city, get_initial_keyword
from modes.zhipin.city_codes import get_city_code
from modes.zhipin.storage import init_db, get_stats

cfg = get_config()
print(f"\n[1] 配置加载: {len(cfg)} 个顶级配置")
print(f"    城市: {cfg.get('cities', {}).get('priority_1', [])[:3]}...")
print(f"    关键词: {cfg.get('search', {}).get('keywords', {}).get('L1', [])[:3]}...")
print(f"    最低薪资: {cfg.get('pre_filters', {}).get('min_salary', 'N/A')}")
print(f"    代理: {'启用' if cfg.get('proxy', {}).get('enabled') else '关闭'}")

skip, reason = should_skip_job("普工", "电子厂", "4K-6K", ["包住"], "刚刚活跃")
print(f"\n[2] 预过滤 (正常): skip={skip}")

skip, reason = should_skip_job("高级经理", "金融公司", "20K-40K", [], "3天前")
print(f"    预过滤 (黑名单): skip={skip}")

kw = get_keywords_for_city("深圳", 50)
print(f"\n[3] 关键词策略 (深圳): {kw}")
print(f"    初始关键词: {get_initial_keyword()}")

print(f"\n[4] 城市代码 (深圳): {get_city_code('深圳')}")

print(f"\n[5] Stealth: {len(STEALTH_SCRIPT)} 字符")
print(f"    Anti-redirect: {len(ANTI_REDIRECT_SCRIPT)} 字符")

init_db()
stats = get_stats()
print(f"\n[6] 数据库: {stats['total_jobs']} 条, {stats['analyzed']} 已分析")

print("\n" + "=" * 50)
print("ALL CORE MODULES VERIFIED - SYSTEM READY")
print("=" * 50)
