"""自适应关键词策略模块，根据城市首次试探结果动态调整后续搜索关键词。"""

from shared.config import get_config


def get_keywords_for_city(_city: str, l1_result_count: int) -> list[str]:
    """
    根据城市首次试探结果（L1关键词搜到的结果数），自适应决定后续关键词。
    返回该城市最终要搜索的关键词列表。
    """
    cfg = get_config()
    keywords = cfg.get("search", {}).get("keywords", {})
    l1 = keywords.get("L1", [])
    l2 = keywords.get("L2", [])
    l3 = keywords.get("L3", [])

    if not l1:
        return l2 + l3

    if l1_result_count > 80:
        # 制造业发达城市：L1全部 + L2制造业相关
        mfg_l2 = [k for k in l2 if k in ("质检", "仓管", "叉车工", "电工")]
        return l1 + (mfg_l2 if mfg_l2 else l2[:3])
    if l1_result_count >= 20:
        # 中等：L1全部 + L2服务业相关
        svc_l2 = [k for k in l2 if k in ("服务员", "厨师")]
        return l1 + (svc_l2 if svc_l2 else l2[:2])
    # 结果少：L1全部 + L3中的多样化岗位 + 可能追加更多L3
    diverse_kw = [k for k in l3 if k in ("文员", "客服", "司机")]
    result = l1 + (diverse_kw if diverse_kw else l3[:3])
    if l1_result_count < 10:
        result += [k for k in l3 if k not in result][:2]
    return result


def get_initial_keyword() -> str:
    """返回用于试探城市的第一轮关键词"""
    cfg = get_config()
    l1 = cfg.get("search", {}).get("keywords", {}).get("L1", [])
    return l1[0] if l1 else "普工"
