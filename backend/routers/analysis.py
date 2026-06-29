from fastapi import APIRouter, HTTPException, Query
from ..database import get_conn
from ..config import CLOSED_STATUS, HIGH_PRIORITY
from ..utils import now_iso
from ..services.analysis_engine import get_analysis

router = APIRouter()

@router.get("/api/versions/{version_id}/analysis")
def api_get_analysis(version_id: int, stage: str = Query("STR1")):
    """获取分析报告（带 30 分钟缓存，避免切换阶段时重复查询数据库）"""
    import json as _json
    from datetime import datetime, timedelta

    import time as _time
    cache_key = f"analysis:{stage}"
    CACHE_TTL_SECONDS = 30 * 60

    # 检查缓存
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jira_issue_api_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                cache_key TEXT NOT NULL DEFAULT '',
                data_json TEXT DEFAULT '',
                synced_at TEXT,
                UNIQUE(version_id, cache_key)
            )
        """)
        try:
            cur.execute("ALTER TABLE jira_issue_api_cache ADD COLUMN cache_key TEXT NOT NULL DEFAULT ''")
            conn.commit()
        except Exception:
            pass
        cur.execute(
            "SELECT data_json, synced_at FROM jira_issue_api_cache WHERE version_id = ? AND cache_key = ?",
            (version_id, cache_key),
        )
        cached = cur.fetchone()
        conn.close()

        if cached and cached["data_json"] and cached["synced_at"]:
            try:
                cached_ts = float(cached["synced_at"])
                if _time.time() - cached_ts < CACHE_TTL_SECONDS:
                    result = _json.loads(cached["data_json"])
                    result["from_cache"] = True
                    return result
            except (ValueError, TypeError):
                pass
    except Exception:
        pass

    result = get_analysis(version_id, stage)

    # 保存到缓存
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jira_issue_api_cache (version_id, cache_key, data_json, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(version_id, cache_key) DO UPDATE SET
                data_json = excluded.data_json, synced_at = excluded.synced_at
        """, (version_id, cache_key, _json.dumps(result, ensure_ascii=False, default=str), str(_time.time())))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return result


def _compute_cycle_time_from_issues(issues: list):
    """从 Issue 列表计算 CycleTime 数据（通用，支持本地缓存和 Jira 实时数据）"""
    from dateutil import parser as dateparser

    if not issues:
        return None

    module_data = {}
    for r in issues:
        module = r.get("module_name") or "未归类"
        created = r.get("created_time", "")
        resolved = r.get("resolved_time", "")
        if not created or not resolved:
            continue
        try:
            ct = (dateparser.parse(resolved) - dateparser.parse(created)).days
            if ct < 0:
                continue
        except Exception:
            continue
        if module not in module_data:
            module_data[module] = {"total": 0, "cycle_times": [], "high": 0, "must_fix": 0}
        module_data[module]["total"] += 1
        module_data[module]["cycle_times"].append(ct)
        if r.get("priority") in HIGH_PRIORITY:
            module_data[module]["high"] += 1
        if r.get("must_fix_flag") == 1:
            module_data[module]["must_fix"] += 1

    all_cts = []
    for d in module_data.values():
        all_cts.extend(d["cycle_times"])
    overall_avg = round(sum(all_cts) / len(all_cts), 1) if all_cts else 0

    modules = []
    for name, d in module_data.items():
        avg_ct = round(sum(d["cycle_times"]) / len(d["cycle_times"]), 1) if d["cycle_times"] else 0
        modules.append({
            "module": name,
            "count": d["total"],
            "avg_cycle_time": avg_ct,
            "high_count": d["high"],
            "must_fix_count": d["must_fix"],
        })

    return {"modules": modules, "overall_avg": overall_avg, "total_resolved": len(issues)}


def _compute_cycle_time(version_id: int, stage: str):
    """计算单个版本的 CycleTime 数据（从本地缓存）"""
    conn = get_conn()
    cur = conn.cursor()
    if stage == "ALL":
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ? AND resolved_time IS NOT NULL AND resolved_time != ''", (version_id,))
    else:
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ? AND str_stage = ? AND resolved_time IS NOT NULL AND resolved_time != ''", (version_id, stage))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return _compute_cycle_time_from_issues(rows)


def _get_predecessor_version_id(version_id: int):
    """获取上一个版本的 ID（按 ID 倒序取前一个）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM version_config WHERE id < ? ORDER BY id DESC LIMIT 1", (version_id,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


@router.get("/api/versions/{version_id}/ai/cycle-time")
def api_cycle_time_analysis(version_id: int, stage: str = Query("ALL"), refresh: bool = Query(False)):
    """
    Bug 修复效能分析：与上个版本的模块解决时间做对比来区分异常。
    异常判定：当前模块平均 CycleTime > 上版本同模块 × 1.5 倍（且 >= 3 个 Issue）。
    如果上版本无数据，退回使用当前版本整体平均值 × 1.5 倍。
    """
    import json as _json

    # 优先从缓存加载
    if not refresh:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ai_analysis_cache WHERE version_id = ? AND analysis_type = 'cycle_time'", (version_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            row = dict(row)
            data = _json.loads(row.get("data_json") or "{}")
            data["ai_suggestion"] = row.get("ai_suggestion", "")
            data["synced_at"] = row.get("synced_at", "")
            data["cached"] = True
            return data

    # 计算当前版本
    current = _compute_cycle_time(version_id, stage)
    if not current:
        result = {"modules": [], "overall_avg": 0, "total_resolved": 0, "ai_suggestion": "", "message": "暂无已解决的 Issue 数据（请先同步 Jira 数据）"}
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO ai_analysis_cache (version_id, analysis_type, data_json, ai_suggestion, synced_at)
        VALUES (?, 'cycle_time', ?, '', ?)
        ON CONFLICT(version_id, analysis_type) DO UPDATE SET
            data_json = excluded.data_json, ai_suggestion = excluded.ai_suggestion, synced_at = excluded.synced_at
        """, (version_id, _json.dumps(result, ensure_ascii=False), now_iso()))
        conn.commit()
        conn.close()
        return result

    # 获取上个版本的 CycleTime 数据（优先本地缓存 → DB缓存 → Jira实时查询）
    pred_id = _get_predecessor_version_id(version_id)
    pred_data = _compute_cycle_time(pred_id, stage) if pred_id else None

    # 尝试从 DB 缓存读取上版本数据
    if pred_id and (not pred_data or pred_data.get("total_resolved", 0) == 0):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT data_json FROM ai_analysis_cache WHERE version_id = ? AND analysis_type = 'cycle_time'", (pred_id,))
            cached_row = cur.fetchone()
            conn.close()
            if cached_row:
                pred_data = _json.loads(cached_row["data_json"])
                if pred_data.get("total_resolved", 0) > 0:
                    print(f"[CycleTime] 上版本从 DB 缓存读取: {pred_data['total_resolved']} 条")
        except Exception:
            pass

    # DB 也没有，从 Jira 实时查询并缓存
    if pred_id and (not pred_data or pred_data.get("total_resolved", 0) == 0):
        try:
            from ..services.jira_service import get_valid_credential, jira_fetch_issues
            from ..routers.versions import get_version as _get_ver
            pred_ver = _get_ver(pred_id)
            pred_project = (pred_ver.get("jira_project") or "").split(",")[0].strip()
            if pred_project:
                cred = get_valid_credential(pred_id)
                jql = f'project = {pred_project} AND issuetype in (Bug) AND resolution != Unresolved ORDER BY updated DESC'
                raw, _ = jira_fetch_issues(cred, jql)
                from ..utils import parse_dt as _parse_dt
                pred_issues_list = []
                for iss in raw:
                    f = iss.get("fields", {})
                    comps = f.get("components") or []
                    pred_issues_list.append({
                        "module_name": comps[0].get("name") if comps else "未归类",
                        "created_time": _parse_dt(f.get("created")),
                        "resolved_time": _parse_dt(f.get("resolutiondate")),
                        "priority": (f.get("priority") or {}).get("name", ""),
                        "must_fix_flag": 0,
                    })
                pred_data = _compute_cycle_time_from_issues(pred_issues_list)
                print(f"[CycleTime] 上版本 {pred_ver['version_name']} 从 Jira 获取 {len(pred_issues_list)} 条已解决 Issue")
                # 缓存到 DB，下次直接读取
                if pred_data and pred_data.get("total_resolved", 0) > 0:
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("""
                    INSERT INTO ai_analysis_cache (version_id, analysis_type, data_json, ai_suggestion, synced_at)
                    VALUES (?, 'cycle_time', ?, '', ?)
                    ON CONFLICT(version_id, analysis_type) DO UPDATE SET
                        data_json = excluded.data_json, synced_at = excluded.synced_at
                    """, (pred_id, _json.dumps(pred_data, ensure_ascii=False), now_iso()))
                    conn.commit()
                    conn.close()
                    print(f"[CycleTime] 上版本数据已缓存到 DB (version_id={pred_id})")
        except Exception as e:
            print(f"[CycleTime] 上版本 Jira 查询失败: {e}")

    # 构建上版本模块 avg 映射
    pred_avg_map = {}
    if pred_data:
        for m in pred_data["modules"]:
            pred_avg_map[m["module"]] = m["avg_cycle_time"]

    # 判断异常：与上版本同模块对比，> 1.5x 为异常；无上版本数据时退回用当前整体平均
    overall_avg = current["overall_avg"]
    for m in current["modules"]:
        pred_avg = pred_avg_map.get(m["module"])
        if pred_avg and pred_avg > 0:
            m["pred_avg"] = pred_avg
            m["ratio"] = round(m["avg_cycle_time"] / pred_avg, 2)
            m["is_slow"] = m["ratio"] > 1.5 and m["count"] >= 3
        else:
            m["pred_avg"] = None
            m["ratio"] = round(m["avg_cycle_time"] / overall_avg, 2) if overall_avg > 0 else 0
            m["is_slow"] = m["ratio"] > 1.5 and m["count"] >= 3

    current["modules"].sort(key=lambda x: x["avg_cycle_time"], reverse=True)

    result = {
        "modules": current["modules"],
        "overall_avg": overall_avg,
        "total_resolved": current["total_resolved"],
        "predecessor_overall_avg": pred_data["overall_avg"] if pred_data else None,
    }

    # 调用 AI 生成测试建议
    ai_suggestion = ""
    slow_modules = [m for m in current["modules"] if m.get("is_slow")]
    if slow_modules:
        try:
            from ..services.ai_service import call_ai
            pred_info = f"上版本整体平均: {pred_data['overall_avg']} 天\n" if pred_data else "上版本无数据，以当前整体平均为基线\n"
            context = f"整体平均修复周期: {overall_avg} 天\n{pred_info}已解决 Issue 总数: {current['total_resolved']}\n\n修复周期异常的模块:\n"
            for m in slow_modules[:10]:
                pred_str = f"（上版本 {m['pred_avg']} 天）" if m.get('pred_avg') else "（无上版本数据）"
                context += f"- {m['module']}: 平均 {m['avg_cycle_time']} 天 {pred_str}，{m['ratio']}x，{m['count']} 个 Issue，高优 {m['high_count']} 个\n"
            ai_suggestion = call_ai(
                "你是软件测试质量分析专家。根据 Bug 修复效能数据（含上版本对比），分析可能的原因并给出测试建议。用中文，300字以内。",
                context
            )
        except Exception as e:
            ai_suggestion = f"AI 分析失败: {str(e)[:80]}"

    result["ai_suggestion"] = ai_suggestion

    # 保存到缓存
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO ai_analysis_cache (version_id, analysis_type, data_json, ai_suggestion, synced_at)
    VALUES (?, 'cycle_time', ?, ?, ?)
    ON CONFLICT(version_id, analysis_type) DO UPDATE SET
        data_json = excluded.data_json, ai_suggestion = excluded.ai_suggestion, synced_at = excluded.synced_at
    """, (version_id, _json.dumps(result, ensure_ascii=False), ai_suggestion, now_iso()))
    conn.commit()
    conn.close()

    return result


@router.get("/api/versions/{version_id}/ai/health-map")
def api_health_map(version_id: int, stage: str = Query("ALL"), refresh: bool = Query(False)):
    """
    健康地图：优先从数据库缓存加载，refresh=true 时重新计算并调用 AI 生成建议。
    """
    import json as _json

    if not refresh:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ai_analysis_cache WHERE version_id = ? AND analysis_type = 'health_map'", (version_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            row = dict(row)
            data = _json.loads(row.get("data_json") or "{}")
            data["ai_suggestion"] = row.get("ai_suggestion", "")
            data["synced_at"] = row.get("synced_at", "")
            data["cached"] = True
            return data
        # 缓存为空，自动计算

    conn = get_conn()
    cur = conn.cursor()

    if stage == "ALL":
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    else:
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        result = {"modules": [], "total_issues": 0, "ai_suggestion": "", "message": "暂无 Issue 数据（请先同步 Jira 数据）"}
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO ai_analysis_cache (version_id, analysis_type, data_json, ai_suggestion, synced_at)
        VALUES (?, 'health_map', ?, '', ?)
        ON CONFLICT(version_id, analysis_type) DO UPDATE SET
            data_json = excluded.data_json, ai_suggestion = excluded.ai_suggestion, synced_at = excluded.synced_at
        """, (version_id, _json.dumps(result, ensure_ascii=False), now_iso()))
        conn.commit()
        conn.close()
        return result

    module_map = {}
    for r in rows:
        m = r.get("module_name") or "未归类"
        if m not in module_map:
            module_map[m] = {"name": m, "total": 0, "unresolved": 0, "high": 0, "blocker": 0, "must_fix": 0, "over14": 0}
        module_map[m]["total"] += 1
        if r.get("status") not in CLOSED_STATUS:
            module_map[m]["unresolved"] += 1
            if (r.get("aging_days") or 0) >= 14:
                module_map[m]["over14"] += 1
        if r.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
        if r.get("priority") == "Blocker":
            module_map[m]["blocker"] += 1
        if r.get("must_fix_flag") == 1:
            module_map[m]["must_fix"] += 1

    modules = sorted(module_map.values(), key=lambda x: (x["blocker"], x["high"], x["unresolved"], x["total"]), reverse=True)

    for m in modules:
        if m["blocker"] > 0 or m["must_fix"] > 3:
            m["risk"] = "high"
        elif m["high"] > 5 or m["unresolved"] > 15:
            m["risk"] = "medium"
        else:
            m["risk"] = "low"

    result = {"modules": modules, "total_issues": len(rows)}

    # 调用 AI 生成测试建议
    ai_suggestion = ""
    high_risk = [m for m in modules if m["risk"] == "high"]
    med_risk = [m for m in modules if m["risk"] == "medium"]
    if high_risk or med_risk:
        try:
            from ..services.ai_service import call_ai
            context = f"总 Issue 数: {len(rows)}\n\n高风险模块:\n"
            for m in high_risk[:8]:
                context += f"- {m['name']}: 总数 {m['total']}，未关闭 {m['unresolved']}，高优 {m['high']}，Blocker {m['blocker']}，必解 {m['must_fix']}，超14天 {m['over14']}\n"
            context += "\n中风险模块:\n"
            for m in med_risk[:5]:
                context += f"- {m['name']}: 总数 {m['total']}，未关闭 {m['unresolved']}，高优 {m['high']}\n"
            ai_suggestion = call_ai(
                "你是软件测试质量分析专家。根据模块健康地图数据，识别高频故障模块，分析根因并给出测试建议和回归策略。用中文，300字以内。",
                context
            )
        except Exception as e:
            ai_suggestion = f"AI 分析失败: {str(e)[:80]}"

    result["ai_suggestion"] = ai_suggestion

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO ai_analysis_cache (version_id, analysis_type, data_json, ai_suggestion, synced_at)
    VALUES (?, 'health_map', ?, ?, ?)
    ON CONFLICT(version_id, analysis_type) DO UPDATE SET
        data_json = excluded.data_json, ai_suggestion = excluded.ai_suggestion, synced_at = excluded.synced_at
    """, (version_id, _json.dumps(result, ensure_ascii=False), ai_suggestion, now_iso()))
    conn.commit()
    conn.close()

    return result