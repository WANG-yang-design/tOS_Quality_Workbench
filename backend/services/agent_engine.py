# -*- coding: utf-8 -*-
"""Agent engine: core loop with LLM function calling."""
import json
from typing import Any, Dict, List
from ..services.ai_service import get_ai_config_decrypted
from ..services.agent_tools import AGENT_TOOLS, execute_tool
from ..services.agent_memory import (
    load_messages, save_messages, save_task, update_title, create_conversation,
)
from ..utils import now_iso

import requests
from urllib.parse import quote

MAX_STEPS = 6


def _build_system_prompt(version_name: str, stage: str, jira_project: str) -> str:
    return (
        "你是 tOS 测试项目管理工作台的 AI 助手，具备数据查询、刷新、导出等多种能力。\n\n"
        "## 你的能力\n\n"
        "### 数据查询\n"
        "1. 查询 Jira 问题（按状态/优先级/模块筛选）\n"
        "2. 查询 SR 需求详情（ALM）和 AI 风险等级\n"
        "3. 查询 ALM 加锁 SR 列表（按生命周期阶段筛选）\n"
        "4. 查询 SR 测试进度（UTP）\n"
        "5. 查询 UTP 测试计划进度\n"
        "6. 查询 UTP Weekly 测试报告\n"
        "7. 查询重点测试活动状态（各阶段 Pass/Fail/未确认）\n"
        "8. 查询工时数据\n"
        "9. 查询稳定性/性能/续航数据\n"
        "10. 查询 Jira 趋势分析（新老项目同期对比）\n"
        "11. 查询价值点验收情况\n"
        "12. 查询阶段时间表\n"
        "13. 查询版本配置信息\n"
        "14. 查询每日报告\n\n"
        "### 数据刷新\n"
        "15. 刷新 Jira 数据（从 Jira 服务器同步）\n"
        "16. 刷新 SR 数据（从 ALM 平台同步）\n"
        "17. 刷新 UTP 数据（从 UTP 平台同步）\n"
        "18. 一键刷新全部数据\n\n"
        "### 数据导出\n"
        "19. 导出 Jira 问题到 CSV（全量或按条件筛选）\n"
        "20. 导出 SR 列表到 CSV（全量）\n"
        "21. 生成并导出周报（Markdown 格式）\n"
        "22. **自定义导出**：导出自定义筛选后的数据到 CSV\n"
        "    - 可以导出任意筛选后的数据，如：高风险SR、特定模块的问题、超龄问题等\n"
        "    - 使用 export_custom_data 工具，传入 columns（列定义）和 rows（数据行）\n"
        "    - 工作流程：先查询数据 → 筛选/处理 → 调用 export_custom_data 导出\n\n"
        "### 数据操作\n"
        "23. 添加自定义风险项\n"
        "24. 删除自定义风险项\n"
        "25. 更新测试活动状态\n\n"
        f"## 当前上下文\n"
        f"- 版本：{version_name}\n"
        f"- 阶段：{stage}\n"
        f"- Jira 项目：{jira_project}\n\n"
        "## 导出规则（重要！）\n"
        "当用户要求导出特定/筛选后的数据时（如'导出中风险SR'、'导出超龄问题'），必须按以下流程操作：\n\n"
        "**正确流程：**\n"
        "1. 调用查询工具获取完整数据（如 get_sr_details、query_jira_issues）\n"
        "2. 从返回结果中筛选符合条件的数据\n"
        "3. 将筛选后的**完整数据**传给 export_custom_data 工具的 rows 参数\n"
        "4. **不要**在回复中展示所有数据后再导出，而是直接调用工具导出\n\n"
        "**错误做法：** ❌ 先在回复中列出部分数据，然后说'已导出'\n"
        "**正确做法：** ✅ 直接调用 export_custom_data 工具，把所有符合条件的数据作为 rows 传入\n\n"
        "**示例：导出中风险SR**\n"
        "```\n"
        "步骤1: 调用 get_sr_details(risk_level='medium') 获取中风险SR\n"
        "步骤2: 把返回的 sr_list 直接作为 rows 传给 export_custom_data\n"
        "步骤3: 调用 export_custom_data({\n"
        "  filename: 'medium_risk_srs',\n"
        "  title: '中风险SR列表',\n"
        "  columns: [...],\n"
        "  rows: [从步骤1结果中提取的完整数据]\n"
        "})\n"
        "```\n\n"
        "**注意：**\n"
        "- rows 必须包含所有符合条件的数据，不能只导出部分\n"
        "- 如果数据量很大（超过100条），先告诉用户'正在导出XX条数据'，然后调用工具\n"
        "- 不要在回复中逐条列出所有数据，直接导出即可\n\n"
        "## 其他规则\n"
        "- 回答前先用工具查询真实数据，不要猜测。\n"
        "- 用中文回答，简洁、数据驱动、可执行。\n"
        "- 引用具体问题时带上 Jira Issue 编号（如 TOS170-2954）。\n"
        "- 阶段名称：概念启动/STR1/STR2/STR3/STR4/STR4A/STR5/1+N版本火车\n"
    )


def _call_llm(messages: List[dict], tools: list, cfg: dict) -> dict:
    """Call LLM with function calling support."""
    url = f"{cfg['api_base']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
        "x-user-no": cfg.get("user_no", ""),
        "x-user-name": quote(cfg.get("user_name", "")),
        "x-user-dept-name": quote(cfg.get("user_dept", "")),
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120, verify=False)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices")
    return choices[0].get("message", {})


def agent_chat(user_message: str, version_id: int, version_name: str,
               stage: str, jira_project: str, conversation_id: str = None) -> dict:
    """
    Agent chat entry point.

    Returns:
        {
            "reply": "...",
            "conversation_id": "conv_xxx",
            "tool_calls": [{"tool": "...", "args": {...}, "result_summary": "..."}],
            "steps": 3
        }
    """
    from ..routers.versions import get_version

    cfg = get_ai_config_decrypted()

    # Create or load conversation
    if not conversation_id:
        conversation_id = create_conversation(version_id, user_message[:40])

    messages = load_messages(conversation_id)
    if not messages:
        system_prompt = _build_system_prompt(version_name, stage, jira_project)
        messages = [{"role": "system", "content": system_prompt}]

    messages.append({"role": "user", "content": user_message})

    # Agent loop
    all_tool_calls = []
    for step in range(MAX_STEPS):
        try:
            response = _call_llm(messages, AGENT_TOOLS, cfg)
        except Exception as e:
            error_reply = f"AI 服务调用失败: {str(e)[:200]}"
            messages.append({"role": "assistant", "content": error_reply})
            save_messages(conversation_id, messages)
            save_task(conversation_id, version_id, user_message, error_reply, all_tool_calls, step + 1, "failed")
            return {"reply": error_reply, "conversation_id": conversation_id, "tool_calls": all_tool_calls, "steps": step + 1, "error": True}

        # Check if LLM wants to call tools
        tool_calls = response.get("tool_calls")
        if not tool_calls:
            # Final answer
            reply = response.get("content", "")
            messages.append({"role": "assistant", "content": reply})
            save_messages(conversation_id, messages)
            save_task(conversation_id, version_id, user_message, reply, all_tool_calls, step + 1)
            # Auto-generate title from first message
            if step == 0 and len(messages) <= 4:
                _auto_title(conversation_id, user_message, cfg)
            return {"reply": reply, "conversation_id": conversation_id, "tool_calls": all_tool_calls, "steps": step + 1}

        # Execute tool calls
        messages.append(response)  # assistant message with tool_calls
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            try:
                tool_args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                tool_args = {}

            result = execute_tool(tool_name, tool_args, version_id, stage)
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            # 根据工具类型设置不同的截断限制
            # 查询类工具允许更大的返回值，以便后续导出
            query_tools = ["query_jira_issues", "get_sr_details", "get_locked_sr_list",
                          "get_utp_plan_progress", "get_sr_test_progress", "get_value_points",
                          "get_performance_data", "get_battery_data", "get_stability_data"]
            max_len = 15000 if tool_name in query_tools else 4000
            if len(result_str) > max_len:
                result_str = result_str[:max_len] + "... (truncated)"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result_str,
            })
            # 保留完整的 result 中的关键字段（如 download_url）
            tool_call_info = {
                "tool": tool_name,
                "args": tool_args,
                "result_summary": _summarize_result(result),
            }
            # 如果 result 中有 download_url，传递给前端
            if isinstance(result, dict) and result.get("download_url"):
                tool_call_info["result"] = {"download_url": result["download_url"]}
            all_tool_calls.append(tool_call_info)

    # Max steps reached
    fallback = "抱歉，分析步骤过多，请尝试更具体的问题。"
    messages.append({"role": "assistant", "content": fallback})
    save_messages(conversation_id, messages)
    save_task(conversation_id, version_id, user_message, fallback, all_tool_calls, MAX_STEPS)
    return {"reply": fallback, "conversation_id": conversation_id, "tool_calls": all_tool_calls, "steps": MAX_STEPS}


def _auto_title(conversation_id: str, first_message: str, cfg: dict):
    """Auto-generate conversation title from first user message."""
    try:
        title = first_message[:30]
        if len(first_message) > 30:
            title += "..."
        update_title(conversation_id, title)
    except Exception:
        pass


def _summarize_result(result: Any) -> str:
    """Create a short summary of tool result for display."""
    if isinstance(result, dict):
        if "error" in result:
            return f"Error: {result['error'][:80]}"
        if "total" in result:
            return f"Total: {result['total']}"
        if "success" in result:
            return "Success"
        return f"Keys: {', '.join(list(result.keys())[:5])}"
    return str(result)[:100]