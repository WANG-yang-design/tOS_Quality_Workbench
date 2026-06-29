"""
Jira 趋势分析服务 — 新老项目同期对比 + AI 趋势预测
基于上一代项目同阶段 Jira 历史数据，AI 从 top 模块、严重等级、问题原因、发现时机、
修复效率、历史复现等维度识别项目质量规律，将历史风险映射到新一代项目。

展示内容：
- 整体趋势板块：新老项目同期对比，判断项目大盘风险和历史基线对比
- 提交板块：重点模块模型、当下模块提交问题数量，趋势预测与收敛性评估
- 解决板块：AI 趋势分析并给出建议
"""

import json
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional, Dict, Any, List, Tuple

from ..database import get_conn
from ..config import CLOSED_STATUS, HIGH_PRIORITY
from ..utils import now_iso


def _extract_version_tuple(version_name: str) -> Tuple[int, int]:
    m = re.search(r"(\d+)\.(\d+)", version_name or "")
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d+)", version_name or "")
    if m:
        return (int(m.group(1)), 0)
    return (0, 0)


def _sort_versions_by_number(versions: List[Dict]) -> List[Dict]:
    return sorted(versions, key=lambda v: _extract_version_tuple(v.get("version_name", "")))


def _find_predecessor(current_version: Dict, all_versions: List[Dict]) -> Optional[Dict]:
    """找到上一代版本，排除 PAD 版本（is_pad=1）"""
    # 排除 PAD 版本：is_pad 显式等于 1 或 "1" 的跳过
    non_pad_versions = [v for v in all_versions if int(v.get("is_pad") or 0) != 1]
    sorted_versions = _sort_versions_by_number(non_pad_versions)
    current_tuple = _extract_version_tuple(current_version.get("version_name", ""))
    # 跳过当前版本自身（如果它也是 PAD，已在上面被排除）
    for i, v in enumerate(sorted_versions):
        v_tuple = _extract_version_tuple(v.get("version_name", ""))
        if v_tuple == current_tuple and i > 0:
            return sorted_versions[i - 1]
    return None


def _load_issues(version_id: int, stage: str = "ALL") -> List[Dict]:
    """从本地缓存加载 Issue"""
    conn = get_conn()
    cur = conn.cursor()
    if stage == "ALL":
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    else:
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _fetch_predecessor_issues_from_jira(predecessor: Dict, cutoff_date: str) -> List[Dict]:
    """直接从 Jira 查询上一代版本在截止日期之前的所有 Bug Issue。
    JQL: project in ({jira_project}) AND issuetype in (Bug) AND created <= "{cutoff_date}"
    """
    from ..services.jira_service import get_valid_credential, jira_fetch_issues
    from ..utils import parse_dt, stringify_field_value
    from ..config import JIRA_CUSTOM_FIELDS

    jira_project = predecessor.get("jira_project", "")
    if not jira_project:
        print(f"[TrendAnalysis] 上一代 {predecessor['version_name']} 未配置 jira_project")
        return []

    # 构建 project 条件
    projects = [p.strip() for p in jira_project.split(",") if p.strip()]
    if len(projects) > 1:
        project_cond = f"project in ({','.join(projects)})"
    else:
        project_cond = f"project = {projects[0]}"

    jql = f'{project_cond} AND issuetype in (Bug) AND created <= "{cutoff_date}" ORDER BY created DESC'
    print(f"[TrendAnalysis] 查询上一代 Jira: {jql}")
    # 保存 JQL 用于前端展示
    _last_pred_jql = jql

    try:
        credential = get_valid_credential()
    except Exception as e:
        print(f"[TrendAnalysis] 获取 Jira 凭据失败: {e}")
        return []

    try:
        raw_issues, total = jira_fetch_issues(credential, jql)
    except Exception as e:
        print(f"[TrendAnalysis] Jira 查询失败: {e}")
        return []

    # 标准化 issue 格式（与 sync_jira_data 的 normalize_issue 一致）
    issues = []
    for issue in raw_issues:
        f = issue.get("fields", {})
        assignee = f.get("assignee") or {}
        reporter = f.get("reporter") or {}
        components = f.get("components") or []
        created_time = parse_dt(f.get("created"))
        updated_time = parse_dt(f.get("updated"))
        resolved_time = parse_dt(f.get("resolutiondate"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - datetime.fromisoformat(created_time)).days
            except Exception:
                pass
        issues.append({
            "issue_key": issue.get("key", ""),
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "assignee": assignee.get("displayName", "") or assignee.get("name", ""),
            "reporter": reporter.get("displayName", "") or reporter.get("name", ""),
            "module_name": components[0].get("name") if components else "未归类",
            "created_time": created_time,
            "updated_time": updated_time,
            "resolved_time": resolved_time,
            "aging_days": aging_days,
            "severity": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["severity"])),
            "must_fix": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["must_fix"])),
            "model": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["model"])),
            "issue_category": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["issue_category"])),
            "module_category": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["module_category"])),
        })

    print(f"[TrendAnalysis] 上一代 {predecessor['version_name']} 从 Jira 获取 {len(issues)} 条 (total={total})")
    return issues


def _get_version_stages(version_id: int) -> List[Dict]:
    """获取版本的阶段配置"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM str_stage_config WHERE version_id = ? ORDER BY stage_name", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _is_default_schedule(stages: List[Dict]) -> bool:
    """检测阶段时间表是否为系统自动生成的默认值。
    默认模式：各阶段 end_date 间隔恰好 7 天（init_db/create_version 的生成规则）。
    """
    from datetime import datetime as dt
    stage_order = ["STR1", "STR2", "STR3", "STR4", "STR5"]
    dates = []
    for name in stage_order:
        for s in stages:
            if s.get("stage_name") == name and s.get("end_date"):
                dates.append(s["end_date"])
                break
    if len(dates) < 3:
        return True
    try:
        parsed = [dt.strptime(d, "%Y-%m-%d") for d in dates]
        gaps = [(parsed[i+1] - parsed[i]).days for i in range(len(parsed)-1)]
        # 默认模式下所有间隔恰好为 7 天（create_version 生成规则）
        return all(g == 7 for g in gaps)
    except Exception:
        return True


def _load_all_versions() -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _save_predecessor_stats(version_id: int, stage: str, cutoff_date: str, issues: List[Dict]):
    """保存上一代版本的统计数据到数据库（只存数量，不存完整 issue）"""
    if not issues:
        return

    metrics = _compute_stage_metrics(issues)
    top_modules = _compute_top_modules(issues, limit=20)
    severity_dist = _compute_severity_distribution(issues)
    category_dist = _compute_issue_category_distribution(issues)
    weekly_trends = _compute_weekly_trends(issues)

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jira_trend_predecessor_stats
                (version_id, stage_name, cutoff_date, total_count, closed_count, open_count,
                 unresolved_count, high_priority_count, high_unresolved_count, blocker_count,
                 must_fix_count, must_fix_open_count, avg_aging_days, over14_count, over30_count,
                 reopen_count, close_rate, module_stats_json, severity_stats_json,
                 category_stats_json, weekly_trends_json, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, stage_name) DO UPDATE SET
                cutoff_date = excluded.cutoff_date,
                total_count = excluded.total_count,
                closed_count = excluded.closed_count,
                open_count = excluded.open_count,
                unresolved_count = excluded.unresolved_count,
                high_priority_count = excluded.high_priority_count,
                high_unresolved_count = excluded.high_unresolved_count,
                blocker_count = excluded.blocker_count,
                must_fix_count = excluded.must_fix_count,
                must_fix_open_count = excluded.must_fix_open_count,
                avg_aging_days = excluded.avg_aging_days,
                over14_count = excluded.over14_count,
                over30_count = excluded.over30_count,
                reopen_count = excluded.reopen_count,
                close_rate = excluded.close_rate,
                module_stats_json = excluded.module_stats_json,
                severity_stats_json = excluded.severity_stats_json,
                category_stats_json = excluded.category_stats_json,
                weekly_trends_json = excluded.weekly_trends_json,
                synced_at = excluded.synced_at
        """, (
            version_id, stage, cutoff_date,
            metrics["total"], metrics["closed"], metrics["open"], metrics["unresolved"],
            metrics["high_priority"], metrics["high_unresolved"], metrics["blocker"],
            metrics["must_fix"], metrics["must_fix_open"], metrics["avg_aging"],
            metrics["over14"], metrics["over30"], metrics["reopen"], metrics["close_rate"],
            json.dumps(top_modules, ensure_ascii=False),
            json.dumps(severity_dist, ensure_ascii=False),
            json.dumps(category_dist, ensure_ascii=False),
            json.dumps(weekly_trends, ensure_ascii=False),
            now_iso()
        ))
        conn.commit()
        conn.close()
        print(f"[TrendAnalysis] 已保存上一代统计数据到数据库: version_id={version_id}, stage={stage}, count={len(issues)}")
    except Exception as e:
        print(f"[TrendAnalysis] 保存上一代统计数据失败: {e}")


def _load_predecessor_stats(version_id: int, stage: str) -> Optional[Dict]:
    """从数据库加载上一代版本的统计数据"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM jira_trend_predecessor_stats WHERE version_id = ? AND stage_name = ?",
                    (version_id, stage))
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        # 构造 metrics 格式
        metrics = {
            "total": row["total_count"],
            "closed": row["closed_count"],
            "open": row["open_count"],
            "unresolved": row["unresolved_count"],
            "high_priority": row["high_priority_count"],
            "high_unresolved": row["high_unresolved_count"],
            "blocker": row["blocker_count"],
            "must_fix": row["must_fix_count"],
            "must_fix_open": row["must_fix_open_count"],
            "avg_aging": row["avg_aging_days"],
            "over14": row["over14_count"],
            "over30": row["over30_count"],
            "reopen": row["reopen_count"],
            "close_rate": row["close_rate"]
        }

        # 构造模块统计格式
        module_stats = json.loads(row["module_stats_json"]) if row["module_stats_json"] else []

        # 构造严重等级分布
        severity_stats = json.loads(row["severity_stats_json"]) if row["severity_stats_json"] else {}

        # 构造问题类型分布
        category_stats = json.loads(row["category_stats_json"]) if row["category_stats_json"] else {}

        # 构造周趋势数据
        weekly_trends = json.loads(row["weekly_trends_json"]) if row["weekly_trends_json"] else []

        return {
            "metrics": metrics,
            "top_modules": module_stats,
            "severity_dist": severity_stats,
            "category_dist": category_stats,
            "weekly_trends": weekly_trends,
            "cutoff_date": row["cutoff_date"],
            "synced_at": row["synced_at"]
        }
    except Exception as e:
        print(f"[TrendAnalysis] 加载上一代统计数据失败: {e}")
        return None


def _compute_stage_metrics(issues: List[Dict]) -> Dict:
    total = len(issues)
    if total == 0:
        return {"total": 0, "closed": 0, "open": 0, "unresolved": 0, "close_rate": 0,
                "high_priority": 0, "high_unresolved": 0, "blocker": 0, "must_fix": 0,
                "must_fix_open": 0, "avg_aging": 0, "over14": 0, "over30": 0, "reopen": 0}
    closed = [i for i in issues if i.get("status") in CLOSED_STATUS or i.get("resolved_time")]
    unresolved = [i for i in issues if i.get("status") not in CLOSED_STATUS and not i.get("resolved_time")]
    high = [i for i in issues if i.get("priority") in HIGH_PRIORITY]
    high_unresolved = [i for i in unresolved if i.get("priority") in HIGH_PRIORITY]
    blocker = [i for i in issues if i.get("priority") == "Blocker"]
    must_fix = [i for i in issues if i.get("must_fix_flag") == 1]
    must_fix_open = [i for i in must_fix if i.get("status") not in CLOSED_STATUS]
    reopen = [i for i in issues if i.get("status") in {"Reopened", "Reopen", "重新打开"}]
    agings = [i.get("aging_days", 0) or 0 for i in unresolved]
    avg_aging = round(sum(agings) / len(agings), 1) if agings else 0
    over14 = [i for i in unresolved if (i.get("aging_days") or 0) >= 14]
    over30 = [i for i in unresolved if (i.get("aging_days") or 0) >= 30]
    return {"total": total, "closed": len(closed), "open": len(unresolved), "unresolved": len(unresolved),
            "close_rate": round(len(closed) / total * 100, 1) if total else 0,
            "high_priority": len(high), "high_unresolved": len(high_unresolved), "blocker": len(blocker),
            "must_fix": len(must_fix), "must_fix_open": len(must_fix_open), "avg_aging": avg_aging,
            "over14": len(over14), "over30": len(over30), "reopen": len(reopen)}


def _compute_top_modules(issues: List[Dict], limit: int = 10) -> List[Dict]:
    module_map: Dict[str, Dict] = {}
    for i in issues:
        m = i.get("module_name") or "未归类"
        if m not in module_map:
            module_map[m] = {"module": m, "total": 0, "open": 0, "high": 0, "blocker": 0,
                             "must_fix": 0, "_agings": []}
        module_map[m]["total"] += 1
        if i.get("status") not in CLOSED_STATUS:
            module_map[m]["open"] += 1
            module_map[m]["_agings"].append((i.get("aging_days") or 0))
        if i.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
        if i.get("priority") == "Blocker":
            module_map[m]["blocker"] += 1
        if i.get("must_fix_flag") == 1:
            module_map[m]["must_fix"] += 1
    modules = sorted(module_map.values(), key=lambda x: (x["high"], x["blocker"], x["open"], x["total"]),
                     reverse=True)[:limit]
    for m in modules:
        agings = m.pop("_agings")
        m["avg_aging"] = round(sum(agings) / len(agings), 1) if agings else 0
    return modules


def _compute_severity_distribution(issues: List[Dict]) -> Dict[str, int]:
    sev_map = {}
    for i in issues:
        sev = i.get("severity") or "未填写"
        sev_map[sev] = sev_map.get(sev, 0) + 1
    return dict(sorted(sev_map.items(), key=lambda x: -x[1]))


def _compute_issue_category_distribution(issues: List[Dict]) -> Dict[str, int]:
    cat_map = {}
    for i in issues:
        cat = i.get("issue_category") or "未填写"
        cat_map[cat] = cat_map.get(cat, 0) + 1
    return dict(sorted(cat_map.items(), key=lambda x: -x[1]))


def _compute_weekly_trends(issues: List[Dict]) -> List[Dict]:
    from datetime import datetime as dt
    weeks_created: Dict[str, int] = defaultdict(int)
    weeks_closed: Dict[str, int] = defaultdict(int)
    weeks_high_created: Dict[str, int] = defaultdict(int)
    weeks_high_closed: Dict[str, int] = defaultdict(int)
    for i in issues:
        created = i.get("created_time", "")
        if created:
            try:
                d = dt.fromisoformat(created.replace("Z", "+00:00"))
                iso = d.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
                weeks_created[key] += 1
                if i.get("priority") in HIGH_PRIORITY:
                    weeks_high_created[key] += 1
            except Exception:
                pass
        resolved = i.get("resolved_time", "")
        if resolved:
            try:
                d = dt.fromisoformat(resolved.replace("Z", "+00:00"))
                iso = d.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
                weeks_closed[key] += 1
                if i.get("priority") in HIGH_PRIORITY:
                    weeks_high_closed[key] += 1
            except Exception:
                pass
    all_weeks = sorted(set(list(weeks_created.keys()) + list(weeks_closed.keys())))
    result = []
    cumulative_open = 0
    for wk in all_weeks:
        created = weeks_created.get(wk, 0)
        closed = weeks_closed.get(wk, 0)
        cumulative_open += (created - closed)
        result.append({"week": wk, "created": created, "closed": closed, "net": created - closed,
                        "cumulative_open": cumulative_open,
                        "high_created": weeks_high_created.get(wk, 0),
                        "high_closed": weeks_high_closed.get(wk, 0)})
    return result


def _align_weekly_by_stage_start(current_weekly: List[Dict], pred_weekly: List[Dict],
                                  cur_stage_start_week: Optional[str] = None,
                                  pred_stage_start_week: Optional[str] = None,
                                  pre_weeks: int = 4, max_forward: int = 12) -> List[Dict]:
    """以阶段开始周为锚点对齐两个版本的周数据。
    - week_idx=0 对齐两个版本的阶段开始周
    - 往前取 pre_weeks 周，往后默认取 max_forward 周
    - 如果当前时间已超出 max_forward 则自动延伸
    """
    cur_map = {w["week"]: i for i, w in enumerate(current_weekly)}
    pred_map = {w["week"]: i for i, w in enumerate(pred_weekly)}

    cur_anchor = cur_map.get(cur_stage_start_week, 0) if cur_stage_start_week else 0
    pred_anchor = pred_map.get(pred_stage_start_week, 0) if pred_stage_start_week else 0

    cur_data_max = len(current_weekly) - 1 - cur_anchor
    pred_data_max = len(pred_weekly) - 1 - pred_anchor

    # 后向默认 max_forward，仅当当前版本数据超出时才延伸
    global_max = max_forward
    if cur_data_max > max_forward:
        global_max = cur_data_max

    global_min = -pre_weeks

    result = []
    for week_idx in range(global_min, global_max + 1):
        # 当前版本
        cur_data_idx = cur_anchor + week_idx
        cur_w = current_weekly[cur_data_idx] if 0 <= cur_data_idx < len(current_weekly) else None
        # 前代版本
        pred_data_idx = pred_anchor + week_idx
        pred_w = pred_weekly[pred_data_idx] if 0 <= pred_data_idx < len(pred_weekly) else None

        # 标签
        if week_idx == 0:
            label = "阶段开始"
        elif week_idx < 0:
            label = f"W{week_idx}"
        else:
            label = f"W+{week_idx}"

        result.append({
            "label": label,
            "week_idx": week_idx,
            "cur_week": cur_w["week"] if cur_w else "",
            "cur_created": cur_w["created"] if cur_w else 0,
            "cur_closed": cur_w["closed"] if cur_w else 0,
            "cur_cumulative": cur_w["cumulative_open"] if cur_w else 0,
            "pred_week": pred_w["week"] if pred_w else "",
            "pred_created": pred_w["created"] if pred_w else 0,
            "pred_closed": pred_w["closed"] if pred_w else 0,
            "pred_cumulative": pred_w["cumulative_open"] if pred_w else 0,
        })

    return result


def _compute_convergence(weekly: List[Dict]) -> Dict:
    if len(weekly) < 3:
        return {"trend": "数据不足", "slope": 0, "close_ratio": 0,
                "deviation": 0, "converging": None,
                "detail": "周数据不足 3 周，无法判断收敛趋势"}
    last3 = weekly[-3:]
    created_values = [w["created"] for w in last3]
    closed_values = [w["closed"] for w in last3]
    slopes = [created_values[i+1] - created_values[i] for i in range(len(created_values)-1)]
    avg_slope = round(sum(slopes) / len(slopes), 2)
    total_created = sum(created_values)
    total_closed = sum(closed_values)
    close_ratio = round(total_closed / total_created * 100, 1) if total_created else 0
    cumulative = weekly[-1]["cumulative_open"]
    deviation = cumulative
    if avg_slope < 0 and close_ratio >= 80:
        converging, trend = True, "收敛"
        detail = f"最近 3 周新增趋势下降（斜率 {avg_slope}），关闭率 {close_ratio}%，问题正在收敛"
    elif avg_slope > 0 and close_ratio < 60:
        converging, trend = False, "发散"
        detail = f"最近 3 周新增趋势上升（斜率 +{avg_slope}），关闭率仅 {close_ratio}%，问题持续累积"
    elif avg_slope > 0:
        converging, trend = False, "发散（需关注）"
        detail = f"最近 3 周新增趋势上升（斜率 +{avg_slope}），关闭率 {close_ratio}%，需关注收敛能力"
    elif close_ratio >= 60:
        converging, trend = True, "趋于收敛"
        detail = f"最近 3 周新增趋势下降（斜率 {avg_slope}），关闭率 {close_ratio}%，整体趋向收敛"
    else:
        converging, trend = None, "波动"
        detail = f"最近 3 周趋势波动（斜率 {avg_slope}），关闭率 {close_ratio}%，尚无明显收敛/发散趋势"
    return {"trend": trend, "slope": avg_slope, "close_ratio": close_ratio, "deviation": deviation,
            "cumulative_open": cumulative, "converging": converging, "detail": detail}


def _compute_module_submit_trends(current_issues: List[Dict], pred_issues: Optional[List[Dict]]) -> List[Dict]:
    current_modules = _compute_top_modules(current_issues, limit=10)
    pred_module_map: Dict[str, Dict] = {}
    if pred_issues:
        for i in pred_issues:
            m = i.get("module_name") or "未归类"
            if m not in pred_module_map:
                pred_module_map[m] = {"total": 0, "open": 0, "high": 0}
            pred_module_map[m]["total"] += 1
            if i.get("status") not in CLOSED_STATUS:
                pred_module_map[m]["open"] += 1
            if i.get("priority") in HIGH_PRIORITY:
                pred_module_map[m]["high"] += 1
    result = []
    for cm in current_modules:
        name = cm["module"]
        pred = pred_module_map.get(name, {"total": 0, "open": 0, "high": 0})
        delta_total = cm["total"] - pred["total"]
        delta_pct = round((delta_total / pred["total"]) * 100, 1) if pred["total"] else (100.0 if cm["total"] > 0 else 0)
        risk_level = "低"
        if cm["high"] > pred["high"] * 1.5 and cm["high"] >= 3:
            risk_level = "高"
        elif cm["high"] > pred["high"] * 1.2 or cm["open"] > pred["open"] * 1.3:
            risk_level = "中"
        result.append({**cm, "pred_total": pred["total"], "pred_open": pred["open"],
                        "pred_high": pred["high"], "delta_total": delta_total,
                        "delta_pct": delta_pct, "risk_level": risk_level})
    return result


def _call_ai_trend(system_prompt: str, user_prompt: str) -> str:
    try:
        from .ai_service import call_ai
        return call_ai(system_prompt, user_prompt)
    except Exception as e:
        return f"AI 分析失败: {str(e)[:120]}"


def build_trend_analysis(version_id: int, stage: str = "ALL", use_cache: bool = True,
                          refresh_ai: bool = False, force: bool = False) -> Dict:
    """构建趋势分析。
    force=True: 重新从数据库计算数据（忽略数据缓存），但 AI 结果仍保留缓存。
    refresh_ai=True: 重新从数据库计算数据 + 重新调用 AI（忽略所有缓存）。
    """
    all_versions = _load_all_versions()
    current_version = None
    for v in all_versions:
        if v["id"] == version_id:
            current_version = v
            break
    if not current_version:
        return {"error": "版本不存在"}
    predecessor = _find_predecessor(current_version, all_versions)

    # cache check：只有 use_cache=True 且 force=False 且 refresh_ai=False 时才用缓存
    if use_cache and not force and not refresh_ai:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT data_json, generated_at FROM jira_trend_analysis_cache WHERE version_id = ? AND stage_name = ?", (version_id, stage))
            cached = cur.fetchone()
            conn.close()
            if cached and cached["data_json"]:
                result = json.loads(cached["data_json"])
                result["cached"] = True
                result["generated_at"] = cached["generated_at"]
                return result
        except Exception:
            pass

    # ── 加载数据 ──
    # 当前版本：从本地缓存加载
    current_issues = _load_issues(version_id, "ALL")

    # 上一代版本：优先从数据库缓存读取，如果没有则从 Jira 查询
    pred_issues = []
    pred_cutoff_date = None
    pred_schedule_warning = None
    pred_stats_from_db = None

    if predecessor:
        pred_stages = _get_version_stages(predecessor["id"])
        is_default = _is_default_schedule(pred_stages)
        pred_stage_map = {s["stage_name"]: s for s in pred_stages}
        matching_stage = pred_stage_map.get(stage)
        end_date = matching_stage.get("end_date") if matching_stage else None
        start_date = matching_stage.get("start_date") if matching_stage else None

        cutoff = end_date or start_date
        if cutoff:
            pred_cutoff_date = cutoff

            # 优先从数据库加载上一代统计数据（快速路径）
            # force=True 或 refresh_ai=True 时跳过缓存，强制从 Jira 查询
            if not force and not refresh_ai:
                pred_stats_from_db = _load_predecessor_stats(predecessor["id"], stage)
                if pred_stats_from_db:
                    print(f"[TrendAnalysis] 从数据库缓存加载上一代 {predecessor['version_name']} 统计数据"
                          f" (synced_at={pred_stats_from_db.get('synced_at', 'N/A')})")

            # 如果数据库没有缓存或强制刷新，则从 Jira 查询
            if not pred_stats_from_db:
                pred_issues = _fetch_predecessor_issues_from_jira(predecessor, cutoff)
                # 保存到数据库缓存
                if pred_issues:
                    _save_predecessor_stats(predecessor["id"], stage, cutoff, pred_issues)

            if is_default:
                pred_schedule_warning = (
                    f"{predecessor['version_name']} 使用系统默认时间表（{stage} 截止 {cutoff}），对比结果仅供参考。"
                    f"建议在 ⚙️ 设置 → 📅 时间表中完善 {predecessor['version_name']} 的阶段日期。"
                )
        else:
            pred_schedule_warning = f"{predecessor['version_name']} 的时间表中未找到 {stage} 阶段日期。"

        pred_count = pred_stats_from_db["metrics"]["total"] if pred_stats_from_db else len(pred_issues)
        print(f"[TrendAnalysis] 当前 {current_version['version_name']}: {len(current_issues)} 条"
              f" | 上一代 {predecessor['version_name']}: {pred_count} 条 (cutoff={pred_cutoff_date})")

    if not current_issues:
        return {"error": "当前版本暂无 Jira 数据，请先同步",
                "current_version": current_version["version_name"],
                "predecessor_version": predecessor["version_name"] if predecessor else None, "stage": stage}

    current_metrics = _compute_stage_metrics(current_issues)

    # 根据数据来源获取上一代数据
    if pred_stats_from_db:
        # 从数据库缓存读取
        pred_metrics = pred_stats_from_db["metrics"]
        pred_weekly = pred_stats_from_db["weekly_trends"]
        pred_modules = pred_stats_from_db["top_modules"]
        pred_severity = pred_stats_from_db["severity_dist"]
        pred_category = pred_stats_from_db["category_dist"]
    else:
        # 从 Jira 查询的数据计算
        pred_metrics = _compute_stage_metrics(pred_issues) if pred_issues else None
        pred_weekly = _compute_weekly_trends(pred_issues) if pred_issues else []
        pred_modules = _compute_top_modules(pred_issues, limit=10) if pred_issues else []
        pred_severity = _compute_severity_distribution(pred_issues) if pred_issues else {}
        pred_category = _compute_issue_category_distribution(pred_issues) if pred_issues else {}

    current_weekly = _compute_weekly_trends(current_issues)
    convergence = _compute_convergence(current_weekly)
    pred_convergence = _compute_convergence(pred_weekly) if pred_weekly else None
    current_modules = _compute_top_modules(current_issues, limit=10)
    module_trends = _compute_module_submit_trends(current_issues, pred_issues if pred_issues else None)
    current_severity = _compute_severity_distribution(current_issues)
    current_category = _compute_issue_category_distribution(current_issues)

    # 生成按阶段开始日期对齐的图表数据
    cur_stage_start_week = None
    pred_stage_start_week = None
    if stage and stage != "ALL":
        from datetime import datetime as _dt
        # 当前版本的阶段开始周
        cur_stages = _get_version_stages(version_id)
        cur_stage_map = {s["stage_name"]: s for s in cur_stages}
        cur_stage = cur_stage_map.get(stage)
        if cur_stage and cur_stage.get("start_date"):
            try:
                d = _dt.strptime(cur_stage["start_date"], "%Y-%m-%d")
                iso = d.isocalendar()
                cur_stage_start_week = f"{iso[0]}-W{iso[1]:02d}"
            except Exception:
                pass
        # 上版本的同阶段开始周
        if predecessor:
            pred_stage_map_local = {s["stage_name"]: s for s in _get_version_stages(predecessor["id"])}
            pred_stage = pred_stage_map_local.get(stage)
            if pred_stage and pred_stage.get("start_date"):
                try:
                    d = _dt.strptime(pred_stage["start_date"], "%Y-%m-%d")
                    iso = d.isocalendar()
                    pred_stage_start_week = f"{iso[0]}-W{iso[1]:02d}"
                except Exception:
                    pass

    submit_chart = _align_weekly_by_stage_start(current_weekly, pred_weekly,
                                                 cur_stage_start_week=cur_stage_start_week,
                                                 pred_stage_start_week=pred_stage_start_week,
                                                 pre_weeks=4, max_forward=12)
    resolve_chart = _align_weekly_by_stage_start(current_weekly, pred_weekly,
                                                  cur_stage_start_week=cur_stage_start_week,
                                                  pred_stage_start_week=pred_stage_start_week,
                                                  pre_weeks=4, max_forward=24)

    pred_issue_count = pred_stats_from_db["metrics"]["total"] if pred_stats_from_db else len(pred_issues)
    pred_data_source = f"数据库缓存 (version_id={predecessor['id']}, stage={stage})" if pred_stats_from_db else f"Jira 实时查询 (cutoff={pred_cutoff_date})"

    result = {
        "current_version": current_version["version_name"],
        "predecessor_version": predecessor["version_name"] if predecessor else None,
        "stage": stage,
        "pred_cutoff_date": pred_cutoff_date,
        "pred_schedule_warning": pred_schedule_warning,
        "pred_data_source": pred_data_source,
        "debug_jql": {
            "current_source": f"本地缓存 (version_id={version_id}, stage=ALL)",
            "pred_jql": f'project = {predecessor.get("jira_project", "").split(",")[0].strip()} AND issuetype in (Bug) AND created <= "{pred_cutoff_date}"' if pred_cutoff_date and predecessor else "无上版本",
            "pred_project": predecessor.get("jira_project", "") if predecessor else "",
            "current_issue_count": len(current_issues),
            "pred_issue_count": pred_issue_count,
        },
        "overall": {"current": current_metrics, "predecessor": pred_metrics,
                    "convergence": convergence, "pred_convergence": pred_convergence,
                    "severity_current": current_severity, "severity_pred": pred_severity,
                    "category_current": current_category, "category_pred": pred_category},
        "submit": {"modules": module_trends,
                    "chart_data": submit_chart,
                    "convergence": convergence,
                    "top_modules_current": current_modules,
                    "top_modules_pred": pred_modules},
        "resolve": {"current_metrics": current_metrics, "predecessor_metrics": pred_metrics,
                    "convergence": convergence,
                    "chart_data": resolve_chart},
    }

    # load cached AI
    if not refresh_ai:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT ai_overall, ai_submit, ai_resolve FROM jira_trend_analysis_cache WHERE version_id = ? AND stage_name = ?", (version_id, stage))
            ai_cached = cur.fetchone()
            conn.close()
            if ai_cached:
                result["ai_overall"] = ai_cached["ai_overall"] or ""
                result["ai_submit"] = ai_cached["ai_submit"] or ""
                result["ai_resolve"] = ai_cached["ai_resolve"] or ""
        except Exception:
            pass

    need_ai = refresh_ai or not result.get("ai_overall")
    if need_ai:
        pred_name = predecessor["version_name"] if predecessor else "无"
        overall_ctx = json.dumps({"current_version": current_version["version_name"],
                                   "predecessor_version": pred_name, "stage": stage,
                                   "current_metrics": current_metrics, "predecessor_metrics": pred_metrics,
                                   "top_modules": current_modules[:5], "convergence": convergence},
                                  ensure_ascii=False, indent=2)
        result["ai_overall"] = _call_ai_trend(
            "你是资深的软件测试质量分析专家，擅长跨项目质量趋势对比分析。\n"
            "根据提供的当前版本和上一代版本在同一阶段的 Jira 数据对比，分析：\n"
            "1. 整体大盘风险：当前项目对比历史基线是否健康\n"
            "2. 关键风险预警：基于历史数据识别当前阶段的高风险模块/问题类型\n"
            "3. 趋势判断：当前项目的收敛/发散状态对比历史同期\n"
            "4. 建议动作：具体的测试策略建议\n"
            "用中文回答，500 字以内，结构清晰。",
            f"以下是 {current_version['version_name']} 与历史版本在 {stage} 阶段的对比数据：\n```json\n{overall_ctx}\n```")

        submit_ctx = json.dumps({"current_version": current_version["version_name"],
                                  "predecessor_version": pred_name, "stage": stage,
                                  "module_trends": module_trends[:8]},
                                 ensure_ascii=False, indent=2)
        result["ai_submit"] = _call_ai_trend(
            "你是软件测试质量分析专家。\n"
            "根据提供的各模块提交趋势数据（当前版本 vs 上一代版本同期），分析：\n"
            "1. 重点模块风险：哪些模块提交量显著高于历史同期，可能原因\n"
            "2. 趋势预测：当前项目各模块的问题提交趋势\n"
            "3. 收敛性评估：哪些模块已收敛、哪些仍在发散\n"
            "4. 测试建议：需要重点关注的模块和测试策略\n"
            "用中文回答，400 字以内。",
            f"以下是模块提交趋势对比数据：\n```json\n{submit_ctx}\n```")

        resolve_ctx = json.dumps({"current_version": current_version["version_name"],
                                   "predecessor_version": pred_name, "stage": stage,
                                   "current_metrics": current_metrics, "predecessor_metrics": pred_metrics,
                                   "convergence": convergence},
                                  ensure_ascii=False, indent=2)
        result["ai_resolve"] = _call_ai_trend(
            "你是软件测试质量分析专家。\n"
            "根据提供的当前版本和上一代版本在同阶段的解决效率数据，分析：\n"
            "1. 解决效率对比：当前版本的关闭率、平均遗留天数对比历史\n"
            "2. 风险预测：基于历史数据，预测当前阶段剩余问题的解决节奏\n"
            "3. 瓶颈分析：可能导致解决效率低的原因\n"
            "4. 改进建议：提高解决效率的具体措施\n"
            "用中文回答，400 字以内。",
            f"以下是解决效率对比数据：\n```json\n{resolve_ctx}\n```")

    # save to cache
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jira_trend_analysis_cache
                (version_id, stage_name, data_json, ai_overall, ai_submit, ai_resolve, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, stage_name) DO UPDATE SET
                data_json = excluded.data_json,
                ai_overall = CASE WHEN excluded.ai_overall != '' THEN excluded.ai_overall ELSE jira_trend_analysis_cache.ai_overall END,
                ai_submit = CASE WHEN excluded.ai_submit != '' THEN excluded.ai_submit ELSE jira_trend_analysis_cache.ai_submit END,
                ai_resolve = CASE WHEN excluded.ai_resolve != '' THEN excluded.ai_resolve ELSE jira_trend_analysis_cache.ai_resolve END,
                generated_at = excluded.generated_at
        """, (version_id, stage, json.dumps(result, ensure_ascii=False, default=str),
              result.get("ai_overall", ""), result.get("ai_submit", ""), result.get("ai_resolve", ""), now_iso()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[TrendAnalysis] cache save error: {e}")
    result["cached"] = False
    return result