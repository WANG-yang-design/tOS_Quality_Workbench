# -*- coding: utf-8 -*-
"""Custom risks router + Chapter 2 AI summary."""
import json as _json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Body
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()

@router.get("/api/versions/{version_id}/custom-risks")
def get_custom_risks(version_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM custom_risks WHERE version_id = ? ORDER BY "
        "CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
        "created_at DESC",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"risks": rows, "total": len(rows)}

@router.post("/api/versions/{version_id}/custom-risks")
def add_custom_risk(version_id: int, req: dict = Body(...)):
    conn = get_conn()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "INSERT INTO custom_risks (version_id,risk_level,title,description,impact_scope,owner,plan_close_date,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (version_id, req.get("risk_level","medium"), req.get("title",""), req.get("description",""), req.get("impact_scope",""), req.get("owner",""), req.get("plan_close_date",""), req.get("status","open"), ts, ts),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": rid, "message": "ok"}

@router.delete("/api/versions/{version_id}/custom-risks/{risk_id}")
def delete_custom_risk(version_id: int, risk_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_risks WHERE id=? AND version_id=?", (risk_id, version_id))
    if not cur.rowcount:
        conn.close()
        raise HTTPException(404, "Not found")
    conn.commit()
    conn.close()
    return {"message": "deleted"}

@router.get("/api/versions/{version_id}/chapter2-ai-summary")
def get_ch2_summary(version_id: int, stage: str = "ALL"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chapter2_ai_summary WHERE version_id=? AND stage_name=?", (version_id, stage))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"cached": False, "summary": "", "generated_at": ""}
    row = dict(row)
    return {"cached": True, "summary": row.get("summary_text",""), "generated_at": row.get("generated_at","")}

@router.post("/api/versions/{version_id}/chapter2-ai-summary")
def generate_ch2_summary(version_id: int, stage: str = "ALL"):
    from ..routers.versions import get_version
    from ..services.ai_service import call_ai
    version = get_version(version_id)
    if not version:
        raise HTTPException(404, "Version not found")
    conn = get_conn()
    cur = conn.cursor()
    # Collect data
    cur.execute("SELECT metrics_json,risks_json FROM analysis_snapshot WHERE version_id=? AND str_stage=? ORDER BY created_at DESC LIMIT 1", (version_id, stage))
    arow = cur.fetchone()
    metrics = _json.loads(arow["metrics_json"]) if arow and arow["metrics_json"] else {}
    risks_data = _json.loads(arow["risks_json"]) if arow and arow["risks_json"] else {}
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND status IN ('Open','Reopened')", (version_id, stage))
    open_cnt = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND status IN ('Submitted','Modifying')", (version_id, stage))
    sub_cnt = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND must_fix_flag=1 AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id, stage))
    mf_cnt = cur.fetchone()["c"]
    cur.execute("SELECT risk_level,title,description,owner,plan_close_date,status FROM custom_risks WHERE version_id=? ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END", (version_id,))
    crisks = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT total_count FROM alm_locked_sr_snapshot WHERE version_id=?", (version_id,))
    sr = cur.fetchone()
    sr_total = sr["total_count"] if sr else 0

    # 新增：待验证问题数据
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND status IN ('Resolved','Verified')", (version_id, stage))
    pending_cnt = cur.fetchone()["c"]

    # 新增：Blocker 问题
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND priority='Blocker' AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id, stage))
    blocker_cnt = cur.fetchone()["c"]

    # 新增：Critical 问题
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND priority='Critical' AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id, stage))
    critical_cnt = cur.fetchone()["c"]

    # 新增：超龄问题（>14天）
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed') AND aging_days > 14", (version_id, stage))
    over14_cnt = cur.fetchone()["c"]

    # 新增：超龄问题（>30天）
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND str_stage=? AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed') AND aging_days > 30", (version_id, stage))
    over30_cnt = cur.fetchone()["c"]

    # 新增：测试活动数据
    cur.execute("SELECT activity_name, status FROM test_activities WHERE version_id=? AND stage_name=?", (version_id, stage))
    test_activities = [dict(r) for r in cur.fetchall()]

    # 新增：稳定性测试专家对话数据
    cur.execute("""
        SELECT question, answer, created_at
        FROM feishu_agent_conversations
        ORDER BY created_at DESC
        LIMIT 10
    """)
    stability_conversations = [dict(r) for r in cur.fetchall()]

    conn.close()

    top_mods = (risks_data.get("top_modules") or [])[:5]
    top_owns = (risks_data.get("top_owners") or [])[:5]
    lines = [
        f"Version: {version.get('version_name','')}, Stage: {stage}",
        "",
        "=== 一、质量风险总结 ===",
        f"[Jira] total={metrics.get('total_issue_count',0)}, closed={metrics.get('closed_issue_count',0)}, rate={metrics.get('close_new_ratio',0)}%, open/reopen={open_cnt}, submitted/modifying={sub_cnt}, must_fix_open={mf_cnt}, high_unresolved={metrics.get('high_unresolved_count',0)}",
        f"[Blocker] {blocker_cnt}, [Critical] {critical_cnt}",
        f"[待验证] {pending_cnt}",
        f"[超龄] >14天={over14_cnt}, >30天={over30_cnt}",
        f"[SR] locked_total={sr_total}",
        "[Top Modules]",
    ]
    for m in top_mods:
        lines.append(f"  {m.get('module','?')}: open={m.get('open',0)}, high={m.get('high',0)}")
    lines.append("[Top Owners]")
    for o in top_owns:
        lines.append(f"  {o.get('owner','?')}: open={o.get('open',0)}, a_grade={o.get('a_grade',0)}, avg_aging={o.get('avg_aging',0)}d")
    lines.append("[Custom Risks]")
    if crisks:
        for cr in crisks:
            lv = {"high":"HIGH","medium":"MED","low":"LOW"}.get(cr["risk_level"],cr["risk_level"])
            lines.append(f"  [{lv}] {cr['title']} - {cr['description']} owner={cr['owner']} close={cr['plan_close_date']} status={cr['status']}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=== 二、测试活动 ===")
    if test_activities:
        for act in test_activities:
            lines.append(f"  {act['activity_name']}: {act['status']}")
    else:
        lines.append("  (暂无)")

    lines.append("")
    lines.append("=== 三、稳定性测试专家对话记录 ===")
    if stability_conversations:
        for conv in stability_conversations:
            lines.append(f"[{conv['created_at'][:16]}] 问: {conv['question'][:150]}")
            lines.append(f"答: {conv['answer'][:300]}")
            lines.append("")
    else:
        lines.append("  (暂无对话记录)")

    sys_p = (
        "你是软件测试质量分析专家。请综合分析以下第二章所有数据，输出全面的风险总结。\n\n"
        "分析维度：\n"
        "1. 整体质量态势（2-3句话）\n"
        "2. 前3个风险点（带数据支撑）\n"
        "3. 3-5条可执行的建议\n"
        "4. 发布就绪性判断\n\n"
        "特别注意：\n"
        "- 如果有稳定性测试专家的对话记录，请分析其中的稳定性风险\n"
        "- 综合考虑Jira问题、SR需求、测试活动、稳定性数据等多维度信息\n\n"
        "要求：\n"
        "- 用中文回答\n"
        "- 控制在1000字以内\n"
        "- 结构清晰，使用编号列表\n"
        "- 重点关注高风险、超龄、Blocker问题\n"
        "- 如果有稳定性相关风险，需要特别强调"
    )
    try:
        analysis = call_ai(sys_p, "\n".join(lines))
    except Exception as e:
        analysis = f"AI failed: {str(e)[:100]}"
    ts = now_iso()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO chapter2_ai_summary (version_id,stage_name,summary_text,generated_at) VALUES (?,?,?,?) ON CONFLICT(version_id,stage_name) DO UPDATE SET summary_text=excluded.summary_text,generated_at=excluded.generated_at", (version_id, stage, analysis, ts))
    conn.commit()
    conn.close()
    return {"summary": analysis, "generated_at": ts}