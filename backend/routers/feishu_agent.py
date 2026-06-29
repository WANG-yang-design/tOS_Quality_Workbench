# -*- coding: utf-8 -*-
"""飞书智能体 API 路由"""
import traceback
from fastapi import APIRouter, HTTPException, Body, Query
from ..services.feishu_agent_service import ask_stability_agent, get_conversation_history, get_stability_data_for_analysis, delete_conversation, clean_old_conversations
from ..utils import now_iso

router = APIRouter()

@router.post("/api/feishu-agent/ask")
def api_ask_feishu_agent(req: dict = Body(...)):
    """向稳定性测试专家智能体提问"""
    try:
        question = (req.get("question") or "").strip()
        version_id = req.get("version_id")
        force_login = req.get("force_login", False)
        if not question:
            raise HTTPException(400, "question is required")
        result = ask_stability_agent(question, version_id=version_id, force_login=force_login)
        if not result.get("success"):
            error_msg = result.get("error", "智能体调用失败")
            print(f"[FeishuAgent] 调用失败: {error_msg}")
            raise HTTPException(500, error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FeishuAgent] 未预期错误: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"服务器内部错误: {str(e)}")

@router.get("/api/feishu-agent/history")
def api_get_agent_history(version_id: int = Query(None), limit: int = Query(50)):
    """获取智能体对话历史"""
    # 自动清理2周前的数据
    clean_old_conversations()
    history = get_conversation_history(version_id=version_id, limit=limit)
    return {"history": history, "total": len(history)}

@router.get("/api/feishu-agent/stability-data")
def api_get_stability_data(version_id: int = Query(None)):
    """获取稳定性数据用于AI分析"""
    data = get_stability_data_for_analysis(version_id=version_id)
    return {"data": data}

@router.delete("/api/feishu-agent/history/{history_id}")
def api_delete_history_item(history_id: int):
    """删除单条历史记录"""
    delete_conversation(history_id)
    return {"message": "已删除"}

@router.delete("/api/feishu-agent/history")
def api_clear_agent_history(version_id: int = Query(None)):
    """清空智能体对话历史"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    if version_id:
        cur.execute("DELETE FROM feishu_agent_conversations WHERE version_id = ?", (version_id,))
    else:
        cur.execute("DELETE FROM feishu_agent_conversations")
    conn.commit()
    conn.close()
    return {"message": "对话历史已清空"}
