# -*- coding: utf-8 -*-
"""Agent API endpoints."""
import os
import tempfile
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse
from ..database import get_conn

router = APIRouter()

# 导出文件存储目录
EXPORT_DIR = os.path.join(tempfile.gettempdir(), "tos_workbench_exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

@router.get("/api/agent/export/{filename}")
def api_download_export(filename: str):
    """下载导出的文件"""
    filepath = os.path.join(EXPORT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "文件不存在或已过期")
    return FileResponse(filepath, filename=filename)


@router.post("/api/agent/chat")
def api_agent_chat(req: dict = Body(...)):
    """Agent chat endpoint.

    Request body:
        {
            "message": "What blockers are open?",
            "version_id": 3,
            "stage": "STR3",
            "conversation_id": "conv_xxx"  // optional
        }
    """
    from ..services.agent_engine import agent_chat
    from ..routers.versions import get_version

    message = (req.get("message") or "").strip()
    version_id = req.get("version_id")
    stage = req.get("stage", "ALL")
    conversation_id = req.get("conversation_id")

    if not message:
        raise HTTPException(400, "message is required")
    if not version_id:
        raise HTTPException(400, "version_id is required")

    version = get_version(version_id)
    if not version:
        raise HTTPException(404, "Version not found")

    result = agent_chat(
        user_message=message,
        version_id=version_id,
        version_name=version.get("version_name", ""),
        stage=stage,
        jira_project=version.get("jira_project", ""),
        conversation_id=conversation_id,
    )
    return result


@router.get("/api/agent/conversations")
def api_list_conversations(version_id: int):
    """List conversations for a version."""
    from ..services.agent_memory import list_conversations
    convs = list_conversations(version_id)
    return {"conversations": convs, "total": len(convs)}


@router.get("/api/agent/conversations/{conversation_id}")
def api_get_conversation(conversation_id: str):
    """Get conversation with full message history."""
    from ..services.agent_memory import get_conversation, load_messages
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    messages = load_messages(conversation_id)
    # Filter out system messages and tool messages for display
    display_messages = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            continue
        if role == "tool":
            continue
        if role == "assistant" and m.get("tool_calls"):
            # Show tool call info
            tools_info = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                tools_info.append({"name": fn.get("name", ""), "arguments": fn.get("arguments", "")})
            display_messages.append({"role": "assistant", "content": m.get("content", ""), "tool_calls_info": tools_info})
            continue
        display_messages.append({"role": role, "content": m.get("content", "")})
    return {
        "id": conv["id"],
        "title": conv.get("title", ""),
        "created_at": conv.get("created_at", ""),
        "messages": display_messages,
    }


@router.delete("/api/agent/conversations/{conversation_id}")
def api_delete_conversation(conversation_id: str):
    """Delete a conversation."""
    from ..services.agent_memory import delete_conversation
    delete_conversation(conversation_id)
    return {"message": "deleted"}


@router.post("/api/agent/weekly-report")
def api_generate_weekly_report(req: dict = Body(...)):
    """生成周报接口"""
    import json as _json
    from datetime import datetime
    from ..routers.versions import get_version
    from ..services.ai_service import call_ai
    from ..utils import now_iso

    version_id = req.get("version_id")
    stage = req.get("stage", "ALL")

    if not version_id:
        raise HTTPException(400, "version_id is required")

    version = get_version(version_id)
    if not version:
        raise HTTPException(404, "Version not found")

    version_name = version.get("version_name", "")
    conn = get_conn()
    cur = conn.cursor()

    # 收集 Jira 数据
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=?", (version_id,))
    total_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id,))
    closed_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status IN ('Open','Reopened')", (version_id,))
    open_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status IN ('Submitted','Modifying')", (version_id,))
    submitted_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND priority='Blocker' AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id,))
    blocker_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND priority='Critical' AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id,))
    critical_issues = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND must_fix_flag=1 AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed')", (version_id,))
    must_fix_open = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed') AND aging_days > 14", (version_id,))
    over14_days = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status NOT IN ('Closed','Resolved','Verified','Done','Fixed') AND aging_days > 30", (version_id,))
    over30_days = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id=? AND status IN ('Resolved','Verified')", (version_id,))
    pending_verification = cur.fetchone()["c"]

    # 收集 SR 数据
    cur.execute("SELECT total_count FROM alm_locked_sr_snapshot WHERE version_id=?", (version_id,))
    sr_row = cur.fetchone()
    sr_total = sr_row["total_count"] if sr_row else 0

    # 收集 Top 模块
    cur.execute("""
        SELECT module_name, COUNT(*) as cnt,
            SUM(CASE WHEN status NOT IN ('Closed','Resolved','Verified','Done','Fixed') THEN 1 ELSE 0 END) as open_cnt,
            SUM(CASE WHEN priority IN ('Blocker','Critical') THEN 1 ELSE 0 END) as high_cnt
        FROM jira_issue_cache WHERE version_id=?
        GROUP BY module_name ORDER BY open_cnt DESC, cnt DESC LIMIT 10
    """, (version_id,))
    top_modules = [dict(r) for r in cur.fetchall()]

    # 收集自定义风险
    cur.execute("SELECT risk_level, title, status FROM custom_risks WHERE version_id=?", (version_id,))
    custom_risks = [dict(r) for r in cur.fetchall()]

    # 收集测试活动
    cur.execute("SELECT activity_name, status FROM test_activities WHERE version_id=?", (version_id,))
    test_activities = [dict(r) for r in cur.fetchall()]

    # 收集趋势数据（最近4周）
    cur.execute("""
        SELECT
            strftime('%Y-W%W', created_time) as week,
            COUNT(*) as created,
            SUM(CASE WHEN status IN ('Closed','Resolved','Verified','Done','Fixed') THEN 1 ELSE 0 END) as closed
        FROM jira_issue_cache
        WHERE version_id=? AND created_time IS NOT NULL
        GROUP BY week ORDER BY week DESC LIMIT 4
    """, (version_id,))
    weekly_trends = [dict(r) for r in cur.fetchall()]

    conn.close()

    # 构建提示词
    close_rate = round(closed_issues / total_issues * 100, 1) if total_issues > 0 else 0
    lines = [
        f"版本: {version_name}",
        f"阶段: {stage}",
        f"报告日期: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "=== Jira 数据概览 ===",
        f"问题总数: {total_issues}",
        f"已关闭: {closed_issues} (关闭率: {close_rate}%)",
        f"遗留问题(Open/Reopened): {open_issues}",
        f"待处理(Submitted/Modifying): {submitted_issues}",
        f"待验证(Resolved/Verified): {pending_verification}",
        f"Blocker: {blocker_issues}",
        f"Critical: {critical_issues}",
        f"Must Fix未关闭: {must_fix_open}",
        f"超龄>14天: {over14_days}",
        f"超龄>30天: {over30_days}",
        "",
        "=== SR 需求 ===",
        f"加锁SR总数: {sr_total}",
        "",
        "=== Top 问题模块 ===",
    ]
    for m in top_modules:
        lines.append(f"  {m['module_name']}: 总{m['cnt']}, 未关{m['open_cnt']}, 高优{m['high_cnt']}")

    lines.append("")
    lines.append("=== 自定义风险 ===")
    for r in custom_risks:
        lv = {"high": "高", "medium": "中", "low": "低"}.get(r["risk_level"], r["risk_level"])
        lines.append(f"  [{lv}] {r['title']} ({r['status']})")

    if test_activities:
        lines.append("")
        lines.append("=== 测试活动 ===")
        for a in test_activities:
            lines.append(f"  {a['activity_name']}: {a['status']}")

    if weekly_trends:
        lines.append("")
        lines.append("=== 周趋势 ===")
        for w in weekly_trends:
            lines.append(f"  {w['week']}: 新增{w['created']}, 关闭{w['closed']}")

    sys_prompt = """你是软件测试质量分析专家。请根据以下数据生成一份专业的测试周报。

周报要求：
1. 使用 Markdown 格式
2. 包含以下章节：
   - 📊 本周概览（关键数据摘要）
   - 🔴 风险预警（高优先级问题）
   - 📈 质量趋势（与上周对比）
   - ✅ 已完成工作
   - 📋 待办事项
   - 💡 测试建议
3. 用中文撰写
4. 语言简洁专业
5. 重点关注风险和改进建议
6. 控制在1500字以内"""

    try:
        report = call_ai(sys_prompt, "\n".join(lines))
    except Exception as e:
        report = f"周报生成失败: {str(e)}"

    # 生成文件名
    week_num = datetime.now().isocalendar()[1]
    filename = f"{version_name}_周报_W{week_num}_{datetime.now().strftime('%Y%m%d')}.md"

    return {
        "report": report,
        "filename": filename,
        "generated_at": now_iso()
    }