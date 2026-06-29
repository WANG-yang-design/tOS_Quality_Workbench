import json
from collections import Counter
from typing import Dict, Any, List
from ..database import get_conn
from ..config import CLOSED_STATUS, HIGH_PRIORITY
from ..utils import now_iso

def build_analysis(version_id: int, stage: str):
    """
    构建分析报告（增强版，使用数据库中已计算的字段）
    """
    from ..routers.versions import get_version
    from ..routers.jira import load_issues
    
    version = get_version(version_id)
    issues = load_issues(version_id, stage)

    total = len(issues)

    if total == 0:
        return {
            "metrics": {"version_name": version["version_name"], "stage": stage, "cache_count": 0},
            "risks": {},
        }

    # 使用数据库中已存储的字段
    closed = [i for i in issues if i["status"] in CLOSED_STATUS or i.get("resolved_time")]
    unresolved = [i for i in issues if i["status"] not in CLOSED_STATUS and not i.get("resolved_time")]
    high_unresolved = [i for i in unresolved if i["priority"] in HIGH_PRIORITY]

    # 使用数据库中的 aging_days 和 stale_days
    issue_14 = [i for i in unresolved if (i.get("aging_days") or 0) >= 14]
    issue_30 = [i for i in unresolved if (i.get("aging_days") or 0) >= 30]
    long_unupdated = [i for i in unresolved if (i.get("stale_days") or 0) >= 7]

    net = total - len(closed)
    close_new_ratio = round(len(closed) / total * 100, 1) if total else 0
    unresolved_ratio = round(len(unresolved) / total * 100, 1) if total else 0
    high_unresolved_ratio = round(len(high_unresolved) / len(unresolved) * 100, 1) if unresolved else 0

    # 状态分布统计
    status_distribution = dict(Counter(i.get("status") or "未知" for i in issues))

    # Open/Reopen 统计
    open_reopen_status = {"Open", "Reopen", "Reopened", "打开", "重新打开"}
    open_reopen_issues = [i for i in issues if i.get("status") in open_reopen_status]
    open_reopen_count = len(open_reopen_issues)

    # Open/Reopen 高风险问题列表（使用数据库中的 risk_score）
    open_reopen_high_risk = sorted(
        [i for i in open_reopen_issues if i.get("priority") in HIGH_PRIORITY],
        key=lambda x: x.get("risk_score") or 0,
        reverse=True
    )

    # Submitted / Modifying 时效分布 + 问题列表
    submitted_issues = [i for i in issues if i.get("status") == "Submitted"]
    modifying_issues = [i for i in issues if i.get("status") == "Modifying"]
    submitted_modifying_issues = sorted(
        submitted_issues + modifying_issues,
        key=lambda x: x.get("risk_score") or 0, reverse=True
    )
    submitted_modifying_aging = {
        "lt3": {"Submitted": 0, "Modifying": 0},
        "d3_7": {"Submitted": 0, "Modifying": 0},
        "gt7": {"Submitted": 0, "Modifying": 0},
    }

    for i in submitted_modifying_issues:
        status = i.get("status")
        aging = i.get("aging_days")
        if aging is None:
            continue
        if aging < 3:
            submitted_modifying_aging["lt3"][status] += 1
        elif aging <= 7:
            submitted_modifying_aging["d3_7"][status] += 1
        else:
            submitted_modifying_aging["gt7"][status] += 1

    # Open/Reopened 详细列表（全部，按 risk_score 排序）
    open_reopen_all = sorted(
        open_reopen_issues,
        key=lambda x: x.get("risk_score") or 0, reverse=True
    )
    open_reopen_high_count = len([i for i in open_reopen_issues if i.get("priority") in HIGH_PRIORITY])
    open_reopen_avg_aging = round(sum(i.get("aging_days") or 0 for i in open_reopen_issues) / max(len(open_reopen_issues), 1), 1)

    # 必解问题（使用数据库中的 must_fix_flag）
    must_fix_issues = [i for i in issues if i.get("must_fix_flag") == 1]
    must_fix_unresolved = [i for i in must_fix_issues if i["status"] not in CLOSED_STATUS]

    must_fix_total_count = len(must_fix_issues)
    must_fix_pending_count = len(must_fix_unresolved)
    must_fix_timeout_count = len([i for i in must_fix_unresolved if (i.get("aging_days") or 0) > 3])
    must_fix_pass_count = len([i for i in must_fix_issues if i["status"] in {"Verified", "Closed", "Done", "Resolved"}])

    # A/B/C 等级分布
    grade_distribution = dict(Counter(i.get("grade") or "未分级" for i in issues))

    # 机型分布
    model_distribution = dict(Counter(i.get("model") or "未填写" for i in issues if i.get("model")))

    # 问题类别分布
    issue_category_distribution = dict(Counter(i.get("issue_category") or "未填写" for i in issues if i.get("issue_category")))

    # 模块分类分布
    module_category_distribution = dict(Counter(i.get("module_category") or "未填写" for i in issues if i.get("module_category")))

    # 遗留天数分布
    aging_bucket = {"0-3天": 0, "4-7天": 0, "8-14天": 0, "15-30天": 0, "31-60天": 0, ">60天": 0}
    for i in issues:
        aging = i.get("aging_days")
        if aging is None:
            continue
        if aging <= 3:
            aging_bucket["0-3天"] += 1
        elif aging <= 7:
            aging_bucket["4-7天"] += 1
        elif aging <= 14:
            aging_bucket["8-14天"] += 1
        elif aging <= 30:
            aging_bucket["15-30天"] += 1
        elif aging <= 60:
            aging_bucket["31-60天"] += 1
        else:
            aging_bucket[">60天"] += 1

    # 模块/负责人统计
    module_map = {}
    owner_map = {}

    for i in issues:
        m = i.get("module_name") or "未归类"
        a = i.get("assignee") or "未分配"

        module_map.setdefault(m, {"name": m, "total": 0, "unresolved": 0, "high": 0, "must_fix": 0})
        owner_map.setdefault(a, {"name": a, "total": 0, "unresolved": 0, "high": 0, "long_unupdated": 0, "must_fix": 0})

        module_map[m]["total"] += 1
        owner_map[a]["total"] += 1

        if i in unresolved:
            module_map[m]["unresolved"] += 1
            owner_map[a]["unresolved"] += 1

        if i.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
            owner_map[a]["high"] += 1

        if i in long_unupdated:
            owner_map[a]["long_unupdated"] += 1

        if i.get("must_fix_flag") == 1:
            module_map[m]["must_fix"] += 1
            owner_map[a]["must_fix"] += 1

    top_modules = sorted(
        module_map.values(),
        key=lambda x: (x["high"], x["must_fix"], x["unresolved"], x["total"]),
        reverse=True
    )[:10]

    top_owners = sorted(
        owner_map.values(),
        key=lambda x: (x["high"], x["must_fix"], x["long_unupdated"], x["unresolved"]),
        reverse=True
    )[:10]

    # Top 风险问题（使用 risk_score）
    typical_issues = sorted(
        unresolved,
        key=lambda x: x.get("risk_score") or 0,
        reverse=True
    )[:10]

    # 风险等级判断
    risk_level = "低"
    if len(high_unresolved) > 30 or unresolved_ratio > 60 or len(issue_30) > 20 or must_fix_pending_count > 10:
        risk_level = "高"
    elif len(high_unresolved) > 10 or unresolved_ratio > 35 or must_fix_pending_count > 5:
        risk_level = "中"

    metrics = {
        "version_name": version["version_name"],
        "stage": stage,
        "total_issue_count": total,
        "new_issue_count": total,
        "closed_issue_count": len(closed),
        "net_issue_count": net,
        "unresolved_issue_count": len(unresolved),
        "high_unresolved_count": len(high_unresolved),
        "close_new_ratio": close_new_ratio,
        "unresolved_ratio": unresolved_ratio,
        "high_unresolved_ratio": high_unresolved_ratio,
        "issue_14_count": len(issue_14),
        "issue_30_count": len(issue_30),
        "long_unupdated_count": len(long_unupdated),
        "risk_level": risk_level,
        "last_sync": max([i["synced_at"] for i in issues], default=None),
        "cache_count": total,
        # 状态分布
        "status_distribution": status_distribution,
        "open_reopen_count": open_reopen_count,
        # 时效分布
        "submitted_modifying_aging": submitted_modifying_aging,
        "aging_bucket": aging_bucket,
        # 必解统计
        "must_fix_total_count": must_fix_total_count,
        "must_fix_pending_count": must_fix_pending_count,
        "must_fix_timeout_count": must_fix_timeout_count,
        "must_fix_pass_count": must_fix_pass_count,
        # A/B/C 等级
        "grade_distribution": grade_distribution,
        # 机型/模块分布
        "model_distribution": model_distribution,
        "issue_category_distribution": issue_category_distribution,
        "module_category_distribution": module_category_distribution,
    }

    # 剥离大字段，减少 API 响应体积
    HEAVY_FIELDS = {"raw_payload", "description"}  # 前端不需要的大字段

    def slim_issues(issue_list):
        """剥离大字段，只保留前端展示需要的字段"""
        return [{k: v for k, v in i.items() if k not in HEAVY_FIELDS} for i in issue_list]
    risks = {
        "top_modules": top_modules,
        "top_owners": top_owners,
        "typical_issues": slim_issues(typical_issues),
        "open_reopen_high_risk": slim_issues(open_reopen_high_risk),
        "open_reopen_high_risk_total": len(open_reopen_high_risk),
        "open_reopen_issues": slim_issues(open_reopen_all),
        "open_reopen_issues_total": len(open_reopen_all),
        "open_reopen_high_count": open_reopen_high_count,
        "open_reopen_avg_aging": open_reopen_avg_aging,
        "submitted_issues": slim_issues([i for i in submitted_modifying_issues if i.get("status") == "Submitted"]),
        "submitted_count": len(submitted_issues),
        "modifying_issues": slim_issues([i for i in submitted_modifying_issues if i.get("status") == "Modifying"]),
        "modifying_count": len(modifying_issues),
        "submitted_modifying_issues": slim_issues(submitted_modifying_issues),
        "submitted_modifying_total": len(submitted_modifying_issues),
        "must_fix_issues": slim_issues(sorted([i for i in must_fix_unresolved if (i.get("risk_score") or 0) > 50], key=lambda x: x.get("risk_score") or 0, reverse=True)),
        "must_fix_issues_total": len([i for i in must_fix_unresolved if (i.get("risk_score") or 0) > 50]),
    }

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO analysis_snapshot (
        version_id, version_name, str_stage,
        period_start, period_end,
        metrics_json, risks_json, suggestions_json,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        version_id,
        version["version_name"],
        stage,
        None,
        None,
        json.dumps(metrics, ensure_ascii=False),
        json.dumps(risks, ensure_ascii=False),
        "[]",
        now_iso()
    ))
    conn.commit()
    conn.close()

    return {
        "metrics": metrics,
        "risks": risks,
    }

def get_analysis(version_id: int, stage: str = "STR1"):
    """获取分析报告"""
    from ..routers.jira import load_issues
    
    issues = load_issues(version_id, stage)
    if not issues:
        return build_analysis(version_id, stage)
    return build_analysis(version_id, stage)