import json
import requests
from urllib.parse import quote
from typing import Optional, Dict, Any
from fastapi import HTTPException
from ..database import get_conn
from ..encryption import encrypt_text, decrypt_text
from ..utils import now_iso
from ..config import CLOSED_STATUS, HIGH_PRIORITY

def get_ai_config():
    """获取AI配置（脱敏显示）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"api_base": "https://hk-intra-paas.transsion.com/tranai-proxy/v1", "api_key": "", "model": "gpt-5.2-chat",
                "user_no": "", "user_name": "", "user_dept": "", "sr_ai_prompt": ""}
    row_dict = dict(row)
    key = row_dict.get("api_key", "")
    masked = (key[:8] + "***") if len(key) > 8 else ("***" if key else "")
    return {"api_base": row_dict["api_base"], "api_key_masked": masked, "model": row_dict["model"],
            "user_no": row_dict.get("user_no", ""), "user_name": row_dict.get("user_name", ""),
            "user_dept": row_dict.get("user_dept", "AI创新部"),
            "sr_ai_prompt": row_dict.get("sr_ai_prompt", "")}

def save_ai_config(req):
    """保存AI配置"""
    conn = get_conn()
    cur = conn.cursor()
    encrypted_key = encrypt_text(req.api_key) if req.api_key else ""
    updates = ["api_base = ?", "model = ?", "user_no = ?", "user_name = ?", "user_dept = ?", "updated_at = ?"]
    vals = [req.api_base.rstrip("/"), req.model, req.user_no or "", req.user_name or "", req.user_dept or "", now_iso()]
    if req.api_key:
        updates.insert(1, "api_key = ?")
        vals.insert(1, encrypted_key)
    if req.sr_ai_prompt is not None:
        updates.append("sr_ai_prompt = ?")
        vals.append(req.sr_ai_prompt)
    vals.append(1)  # WHERE id = 1
    cur.execute(f"UPDATE ai_config SET {', '.join(updates)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    return {"message": "AI 配置已保存"}

def get_ai_config_decrypted():
    """获取解密后的 AI 配置"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=400, detail="请先配置 AI API Key")
    row_dict = dict(row)
    if not row_dict.get("api_key"):
        raise HTTPException(status_code=400, detail="请先配置 AI API Key")
    return {
        "api_base": row_dict["api_base"],
        "api_key": decrypt_text(row_dict["api_key"]),
        "model": row_dict["model"],
        "user_no": row_dict.get("user_no", ""),
        "user_name": row_dict.get("user_name", ""),
        "user_dept": row_dict.get("user_dept", "AI创新部"),
    }

def build_ai_context(version_id: int, stage: str) -> dict:
    """构建压缩的 AI 上下文数据"""
    from ..routers.versions import get_version
    from ..routers.jira import load_issues
    
    version = get_version(version_id)
    issues = load_issues(version_id, stage)

    total = len(issues)
    closed = [i for i in issues if i["status"] in CLOSED_STATUS or i.get("resolved_time")]
    unresolved = [i for i in issues if i["status"] not in CLOSED_STATUS and not i.get("resolved_time")]
    high = [i for i in unresolved if i["priority"] in HIGH_PRIORITY]
    must_fix = [i for i in issues if i.get("must_fix_flag") == 1]
    must_fix_open = [i for i in must_fix if i["status"] not in CLOSED_STATUS]
    over14 = [i for i in unresolved if (i.get("aging_days") or 0) >= 14]
    over30 = [i for i in unresolved if (i.get("aging_days") or 0) >= 30]
    reopen = [i for i in issues if i["status"] in {"Reopened", "Reopen", "重新打开"}]

    # 模块风险
    module_map = {}
    for i in issues:
        m = i.get("module_name") or "未归类"
        module_map.setdefault(m, {"open": 0, "high": 0, "risk": 0})
        if i["status"] not in CLOSED_STATUS:
            module_map[m]["open"] += 1
        if i.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
        module_map[m]["risk"] = module_map[m]["high"] * 3 + module_map[m]["open"]
    top_modules = sorted(module_map.items(), key=lambda x: x[1]["risk"], reverse=True)[:5]

    # 负责人风险
    owner_map = {}
    for i in unresolved:
        a = i.get("assignee") or "未分配"
        owner_map.setdefault(a, {"open": 0, "a_grade": 0, "avg_aging": []})
        owner_map[a]["open"] += 1
        if i.get("grade") == "A":
            owner_map[a]["a_grade"] += 1
        if i.get("aging_days"):
            owner_map[a]["avg_aging"].append(i["aging_days"])
    top_owners = sorted(owner_map.items(), key=lambda x: x[1]["a_grade"] * 10 + x[1]["open"], reverse=True)[:5]

    # 高风险 issue（前10）
    high_risk = sorted(unresolved, key=lambda x: x.get("risk_score") or 0, reverse=True)[:10]

    return {
        "version": version["version_name"],
        "stage": stage,
        "metrics": {
            "total": total,
            "open": len(unresolved),
            "closed": len(closed),
            "a_grade": sum(1 for i in issues if i.get("grade") == "A"),
            "b_grade": sum(1 for i in issues if i.get("grade") == "B"),
            "must_fix_open": len(must_fix_open),
            "reopen": len(reopen),
            "over_14_days": len(over14),
            "over_30_days": len(over30),
            "close_ratio": round(len(closed) / total * 100, 1) if total else 0,
        },
        "top_modules": [{"module": m, **d} for m, d in top_modules],
        "top_owners": [{"owner": o, "open": d["open"], "a_grade": d["a_grade"],
                        "avg_aging": round(sum(d["avg_aging"]) / len(d["avg_aging"])) if d["avg_aging"] else 0}
                       for o, d in top_owners],
        "high_risk_issues": [
            {"key": i["issue_key"], "summary": i["summary"][:80], "status": i["status"],
             "priority": i["priority"], "grade": i.get("grade", ""), "aging_days": i.get("aging_days", 0),
             "risk_score": i.get("risk_score", 0)}
            for i in high_risk
        ],
    }

def call_ai(system_prompt: str, user_prompt: str) -> str:
    """调用 TranAI / OpenAI 兼容 API"""
    cfg = get_ai_config_decrypted()
    url = f"{cfg['api_base']}/chat/completions"

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
                "x-user-no": cfg.get("user_no", ""),
                "x-user-name": quote(cfg.get("user_name", "")),
                "x-user-dept-name": quote(cfg.get("user_dept", "")),
            },
            timeout=120,
        )
        if resp.status_code != 200:
            # 尝试从返回体提取错误信息（兼容非 UTF-8 响应）
            try:
                err_body = resp.json()
                err_msg = err_body.get("error", {}).get("message", "") or err_body.get("detail", "") or str(err_body)[:300]
            except Exception:
                try:
                    err_msg = resp.content.decode("utf-8", errors="replace")[:300]
                except Exception:
                    err_msg = f"(无法读取响应体，状态码 {resp.status_code})"
            raise HTTPException(status_code=502, detail=f"AI API 错误 ({resp.status_code}): {err_msg}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="AI API 请求超时（120秒）")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="无法连接 AI API 服务器")
    except HTTPException:
        raise
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"AI API 返回格式异常: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用异常: {str(e)[:200]}")

def ai_quality_summary(version_id: int, stage: str = "ALL"):
    """AI 质量报告总结"""
    ctx = build_ai_context(version_id, stage)
    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = """你是一位资深的软件测试质量分析专家。根据提供的 Jira Issue 数据，生成一份简洁、专业的质量总结报告。
要求：
1. 用中文回答
2. 结构清晰，使用编号列表
3. 重点关注风险、趋势、闭环效率
4. 给出具体可执行的建议
5. 控制在 500 字以内"""

    user_prompt = f"以下是当前版本/阶段的 Jira 质量数据：\n```json\n{ctx_json}\n```\n\n请生成质量总结报告。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx}

def ai_risk_analysis(version_id: int, stage: str = "ALL"):
    """AI 风险解读与行动建议"""
    ctx = build_ai_context(version_id, stage)
    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = """你是一位资深的软件测试质量分析专家。根据提供的 Jira Issue 数据，进行深度风险解读并给出行动建议。
输出格式要求：
一、主要风险（列出 3-5 个核心风险点）
二、建议优先级（P0/P1/P2 分级，给出具体 issue 编号和动作）
三、准出判断（当前阶段是否建议进入下一阶段，需要满足什么条件）
要求：用中文回答，具体到 issue 编号、负责人、天数，不要泛泛而谈。"""

    user_prompt = f"以下是当前版本/阶段的 Jira 质量数据：\n```json\n{ctx_json}\n```\n\n请进行风险解读并给出行动建议。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx}

def ai_weekly_report(version_id: int, stage: str = "ALL"):
    """AI 周报生成"""
    from datetime import datetime
    
    ctx = build_ai_context(version_id, stage)
    week_info = {
        "year": datetime.now().isocalendar()[0],
        "week": datetime.now().isocalendar()[1],
    }

    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = "你是一位专业的测试项目经理，负责撰写每周测试质量周报。根据提供的数据生成结构化周报，包含：1.本周概况 2.关键数据 3.风险预警 4.下周计划。用中文，800字以内。"

    user_prompt = f"当前是{week_info['year']}年第{week_info['week']}周。\n\nJira质量数据：\n{ctx_json}\n\n请生成本周质量周报。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx, "week": week_info}