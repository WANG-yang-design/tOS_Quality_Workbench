# -*- coding: utf-8 -*-
"""UTP Weekly test report router."""
import json as _json
from fastapi import APIRouter, HTTPException, Body
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()


@router.get("/api/versions/{version_id}/utp/weekly-reports")
def get_utp_weekly_reports(version_id: int):
    """Read UTP weekly report data from DB cache."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM utp_weekly_cache WHERE version_id = ? ORDER BY platform", (version_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return {"platforms": [], "cached": False}
    platforms = []
    for row in rows:
        rd = dict(row)
        data = _json.loads(rd.get("data_json") or "{}")
        data["platform"] = rd["platform"]
        data["synced_at"] = rd.get("synced_at", "")
        data["cached"] = True
        platforms.append(data)
    return {"platforms": platforms, "cached": True}


@router.post("/api/versions/{version_id}/utp/weekly-reports/refresh")
def refresh_utp_weekly(version_id: int):
    """Fetch UTP weekly reports from UTP platform and cache to DB."""
    from ..routers.versions import get_version
    from ..services.utp_service import utp_fetch_weekly_reports
    import time as _time

    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    project_code = version.get("version_name", "")
    # PAD 版本使用基础版本名查询 UTP（如 "tOS16.3 PAD" → "tOS16.3"）
    import re
    project_code = re.sub(r'\s*PAD\s*$', '', project_code, flags=re.IGNORECASE).strip() or project_code
    owner_codes = (version.get("utp_owner_codes") or "").strip() or "18620222"
    # tOS17.0 only has MTK and Q; others may also have UNISOC
    if "17" in project_code:
        platform_keywords = ["[MTK]", "[Q]"]
    else:
        platform_keywords = ["[MTK]", "[Q]", "[展锐]"]

    result = utp_fetch_weekly_reports(
        project_code=project_code,
        owner_codes=owner_codes,
        platform_keywords=platform_keywords,
    )
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    conn = get_conn()
    cur = conn.cursor()
    synced = str(_time.time())

    # 保留已有的 AI 分析结果（刷新时不应丢失）
    cur.execute("SELECT platform, data_json FROM utp_weekly_cache WHERE version_id = ?", (version_id,))
    existing_ai: dict = {}
    for r in cur.fetchall():
        try:
            d = _json.loads(r["data_json"])
            if d.get("ai_analysis"):
                existing_ai[r["platform"]] = d["ai_analysis"]
        except Exception:
            pass

    cur.execute("DELETE FROM utp_weekly_cache WHERE version_id = ?", (version_id,))
    for p in result.get("platforms", []):
        platform = p.get("platform", "unknown")
        # 如果该平台之前有 AI 分析，保留到新数据中
        if platform in existing_ai:
            p["ai_analysis"] = existing_ai[platform]
        cur.execute(
            "INSERT INTO utp_weekly_cache (version_id,platform,data_json,synced_at) "
            "VALUES (?,?,?,?) ON CONFLICT(version_id,platform) DO UPDATE SET "
            "data_json=excluded.data_json,synced_at=excluded.synced_at",
            (version_id, platform, _json.dumps(p, ensure_ascii=False), synced),
        )
    conn.commit()
    conn.close()
    return {"platforms": result.get("platforms", []), "cached": False}


@router.post("/api/versions/{version_id}/utp/weekly-reports/jira-issues")
def get_utp_jira_issues(version_id: int, platform: str = Body(...), priority: str = Body(...), plan_id: int = Body(None)):
    """Fetch A/B class Jira issue details from UTP for a specific platform's weekly report.

    正确流程（注意 report_id ≠ plan_id）：
    1. 从缓存中获取 report_id（由 getPlanReport 返回的 report.id 字段）
    2. 如果缓存中没有 report_id（旧数据），则调用 GET /api/report/getPlanReport 获取
    3. 使用 report_id 调用 POST /api/report/getJiraNumIssue 获取 A/B 类缺陷列表
    """
    from ..services.utp_service import _get_alm_credentials, _utp_post, _utp_get
    import json as _json

    conn = get_conn()
    cur = conn.cursor()
    # 先查所有缓存的平台，用于 debug
    cur.execute(
        "SELECT platform, data_json FROM utp_weekly_cache WHERE version_id=?",
        (version_id,),
    )
    all_rows = cur.fetchall()
    conn.close()

    if not all_rows:
        raise HTTPException(status_code=404, detail=f"无 UTP 缓存数据（version_id={version_id}），请先点击「从 UTP 获取」")

    # 精确匹配 platform
    target_row = None
    cached_platforms = []
    for r in all_rows:
        d = _json.loads(r["data_json"])
        cached_platforms.append(f"{r['platform']}(plan_id={d.get('plan_id')}, report_id={d.get('report_id')})")
        if r["platform"] == platform:
            target_row = r

    if not target_row:
        avail = ", ".join(cached_platforms)
        raise HTTPException(status_code=404, detail=f"未找到 platform={platform} 的缓存，可用: [{avail}]")

    data = _json.loads(target_row["data_json"])
    cached_plan_id = data.get("plan_id")
    cached_report_id = data.get("report_id")
    plan_name = data.get("plan_name", "")

    # 优先使用前端传入的 plan_id，其次使用缓存中的
    if plan_id is not None:
        final_plan_id = plan_id
        print(f"[UTP-JIRA] 使用前端传入的 plan_id: {final_plan_id}")
    elif cached_plan_id is not None:
        final_plan_id = int(cached_plan_id)
        print(f"[UTP-JIRA] 使用缓存中的 plan_id: {final_plan_id}")
    else:
        raise HTTPException(status_code=400, detail=f"UTP 缓存中 plan_id 为空（platform={platform}），请重新从 UTP 获取")

    cred = _get_alm_credentials()
    if not cred:
        raise HTTPException(status_code=400, detail="请先配置 ALM/UTP 账号")

    # 获取 report_id（注意：report_id ≠ plan_id，getJiraNumIssue 需要的是 report_id）
    report_id = None
    if cached_report_id is not None:
        report_id = int(cached_report_id)
        print(f"[UTP-JIRA] 使用缓存中的 report_id: {report_id}")
    else:
        # 缓存中没有 report_id（旧数据），调用 getPlanReport 获取
        print(f"[UTP-JIRA] 缓存中无 report_id，调用 getPlanReport 获取: planId={final_plan_id}")
        try:
            report_resp = _utp_get(cred, "/api/report/getPlanReport", params={"planId": final_plan_id})
            report_data = report_resp.get("data") or {}
            report_obj = report_data.get("report") or {}
            report_id = report_obj.get("id")
            if report_id is None:
                raise RuntimeError(f"getPlanReport 返回的 report 中没有 id 字段: {report_resp}")
            report_id = int(report_id)
            print(f"[UTP-JIRA] 从 getPlanReport 获取到 report_id: {report_id}")

            # 回写缓存，下次无需再查
            data["report_id"] = report_id
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE utp_weekly_cache SET data_json=? WHERE version_id=? AND platform=?",
                (_json.dumps(data, ensure_ascii=False), version_id, platform),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[UTP-JIRA] 获取 report_id 失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取报告 ID 失败: {str(e)[:200]}")

    print(f"[UTP-JIRA] platform={platform}, priority={priority}, plan_id={final_plan_id}, report_id={report_id}, plan_name={plan_name}")

    # 使用 report_id（而非 plan_id）调用 getJiraNumIssue
    payload = {"id": report_id, "priority": priority}
    print(f"[UTP-JIRA] 调用 UTP: POST /api/report/getJiraNumIssue, payload={payload}")

    try:
        resp = _utp_post(cred, "/api/report/getJiraNumIssue", payload)
    except Exception as e:
        print(f"[UTP-JIRA] 请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"UTP 查询失败: {str(e)[:200]}")

    issues = resp.get("data") or []
    print(f"[UTP-JIRA] 返回 {len(issues)} 个 {priority} 类缺陷 (report_id={report_id})")
    if issues:
        print(f"[UTP-JIRA] 第1条: {issues[0].get('jiraKey', '')} - {issues[0].get('summary', '')[:60]}")
    return {
        "platform": platform, "priority": priority,
        "plan_id": final_plan_id, "report_id": report_id, "plan_name": plan_name,
        "issues": issues, "total": len(issues),
    }


@router.post("/api/versions/{version_id}/utp/weekly-reports/ai-analyze")
def ai_analyze(version_id: int, platform: str = Body(..., embed=True)):
    """AI analysis for a specific platform's UTP weekly report."""
    from ..services.ai_service import call_ai

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT data_json FROM utp_weekly_cache WHERE version_id=? AND platform=?",
        (version_id, platform),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No data for " + platform)

    data = _json.loads(row["data_json"])
    cc = data.get("case_count", {})
    jc = data.get("jira_count", {})
    tasks = data.get("group_tasks", [])

    lines = [
        "Platform: " + platform,
        "Plan: " + str(data.get("plan_name", "")),
        "Result: " + str(data.get("report_result", "")),
        "Cases: total=" + str(cc.get("total", 0))
        + ", pass=" + str(cc.get("pass", 0))
        + ", fail=" + str(cc.get("fail", 0))
        + ", blocked=" + str(cc.get("blocked", 0))
        + ", rate=" + str(cc.get("rate", "")),
        "Defects: leave=" + str(jc.get("leave", 0))
        + ", leaveAB=" + str(jc.get("leave_ab", 0))
        + ", DI=" + str(jc.get("di", 0))
        + ", A=" + str(jc.get("a", 0))
        + ", B=" + str(jc.get("b", 0)),
        "",
        "Domain Results:",
    ]
    for t in tasks:
        lines.append(
            "  [" + str(t.get("group_result", "")) + "] "
            + str(t.get("group_name", "")) + "/" + str(t.get("sub_group_name", ""))
            + ": result=" + str(t.get("sub_result", ""))
            + ", cases=" + str(t.get("case_count", 0))
            + ", rate=" + str(t.get("pass_rate", ""))
            + ", jira=" + str(t.get("jira_count", 0))
            + ", risk=" + str(t.get("risk_count", 0))
        )

    sys_prompt = (
        "You are a software testing quality expert. Analyze the UTP weekly test report. "
        "Respond in Chinese. Focus on: fail/NG domains and their impact, pass rate, "
        "defect distribution, risk areas. Give 3-5 actionable recommendations. "
        "Identify top 3 areas needing immediate attention. Keep within 500 chars."
    )
    try:
        analysis = call_ai(sys_prompt, chr(10).join(lines))
    except Exception as e:
        analysis = "AI analysis failed: " + str(e)[:100]

    data["ai_analysis"] = analysis
    data["ai_analyzed_at"] = now_iso()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE utp_weekly_cache SET data_json=? WHERE version_id=? AND platform=?",
        (_json.dumps(data, ensure_ascii=False), version_id, platform),
    )
    conn.commit()
    conn.close()
    return {"platform": platform, "analysis": analysis}