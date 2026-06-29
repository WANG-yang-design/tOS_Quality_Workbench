# -*- coding: utf-8 -*-
"""飞书/传音智库智能体服务 - 稳定性测试专家集成"""
import json
import time
import ssl
import base64
import os
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import requests
from ..database import get_conn
from ..utils import now_iso
from ..config import APP_DIR

# WebSocket 支持
try:
    from websocket import create_connection
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False
    print("[FeishuAgent] websocket-client 未安装，请运行: pip install websocket-client")

# RSA 加密支持
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("[FeishuAgent] cryptography 未安装，请运行: pip install cryptography")

# 智能体固定配置（不需要用户配置）
AGENT_TICKET_URL = "https://pfgateway.transsion.com:9199/transsioner-intelligent-service/ticket/getWsTicket"
AGENT_WS_HOST = "wss://gpt-ws.transsion.com/"
AGENT_CHAT_TOPIC_ID = "1139032"
AGENT_ASSISTANT_ID = "9251"
AGENT_ASSISTANT_NAME = "稳定性测试专家"
AGENT_MODEL_CODE = "94"
AGENT_TENANT = "b4b38189e32f48fca1a29da4a7a56580"
AGENT_ORIGIN = "https://gpt.transsion.com"
AGENT_REFERER = "https://gpt.transsion.com/"
AGENT_LANGID = "zh"
AGENT_PLATFORM = "win"
AGENT_SYSCODE = "priority"
REQUESTS_VERIFY = False
AGENT_TIMEOUT = 120
TOKEN_CACHE_FILE = APP_DIR / "feishu_agent_token_cache.json"

def _get_uac_credentials() -> Dict:
    """从ALM配置获取UAC凭据"""
    try:
        from ..encryption import decrypt_text
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT uac_gateway, alm_app_id, uac_username, encrypted_password, uac_source FROM alm_config WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"error": "ALM配置未找到，请先在设置中配置ALM"}
        row_dict = dict(row)
        password = ""
        if row_dict.get("encrypted_password"):
            try:
                password = decrypt_text(row_dict["encrypted_password"])
            except Exception:
                pass
        if not row_dict.get("uac_username") or not password:
            return {"error": "ALM工号或密码未配置，请先在设置中配置ALM"}
        return {
            "uac_gateway": (row_dict.get("uac_gateway") or "https://pfgateway.transsion.com:9199").rstrip("/"),
            "uac_app_id": row_dict.get("alm_app_id") or "c_MjYwNjAxMDAxaA",
            "uac_username": row_dict.get("uac_username"),
            "uac_password": password,
            "uac_source": row_dict.get("uac_source") or "ALM",
        }
    except Exception as e:
        return {"error": f"获取ALM配置失败: {str(e)}"}

def _mask_value(value: str, left: int = 6, right: int = 4) -> str:
    if not value: return ""
    if len(value) <= left + right: return "***"
    return value[:left] + "***" + value[-right:]

def _load_token_cache() -> Optional[Dict]:
    if not TOKEN_CACHE_FILE.exists(): return None
    try:
        with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("p_auth") or not data.get("p_rtoken"): return None
        return data
    except Exception: return None

def _save_token_cache(token_info: Dict):
    try:
        with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(token_info, f, ensure_ascii=False, indent=2)
    except Exception as e: print(f"[FeishuAgent] 保存 token 缓存失败: {e}")

def _build_user_agent() -> str:
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

def _get_rsa_key_pair(session: requests.Session, uac_gateway: str) -> Dict:
    url = uac_gateway + "/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair"
    resp = session.get(url, headers={"accept": "application/json", "user-agent": _build_user_agent()}, timeout=30, verify=REQUESTS_VERIFY)
    if resp.status_code != 200: raise RuntimeError(f"获取 RSA 公钥失败: HTTP {resp.status_code}")
    data = resp.json()
    if str(data.get("code")) != "200" and not data.get("success"): raise RuntimeError(f"获取 RSA 公钥失败: {data}")
    rsa_data = data.get("data") or {}
    if not rsa_data.get("publicKey") or not rsa_data.get("verifyKey"): raise RuntimeError("RSA 接口未返回 publicKey 或 verifyKey")
    return rsa_data

def _encrypt_password(password: str, public_key_base64: str) -> str:
    if not HAS_CRYPTO: raise RuntimeError("cryptography 未安装")
    public_key_der = base64.b64decode(public_key_base64)
    public_key = serialization.load_der_public_key(public_key_der)
    encrypted_bytes = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted_bytes).decode("utf-8")

def _normalize_login_token(login_data: Dict, creds: Dict) -> Dict:
    token_data = login_data.get("data") or {}
    p_auth = token_data.get("token") or token_data.get("rtoken") or token_data.get("auth")
    p_rtoken = token_data.get("utoken") or token_data.get("rtoken") or token_data.get("refreshToken")
    employee_no = token_data.get("employeeNo") or token_data.get("empNo") or creds.get("uac_username", "")
    expires_in = int(float(token_data.get("expiresIn") or 900))
    if not p_auth: raise RuntimeError(f"登录成功但未找到 token")
    if not p_rtoken: raise RuntimeError(f"登录成功但未找到 utoken")
    expires_at = int(time.time()) + max(expires_in - 120, 60)
    return {"p_auth": p_auth, "p_rtoken": p_rtoken, "employee_no": str(employee_no), "expires_in": expires_in, "expires_at": expires_at, "app_id": creds.get("uac_app_id", ""), "source": creds.get("uac_source", "ALM"), "created_at": int(time.time())}

def _login_uac(session: requests.Session, creds: Dict) -> Dict:
    if not creds.get("uac_username") or not creds.get("uac_password"):
        raise RuntimeError("ALM工号或密码未配置")
    rsa_info = _get_rsa_key_pair(session, creds["uac_gateway"])
    encrypted_pwd = _encrypt_password(creds["uac_password"], rsa_info["publicKey"])
    url = creds["uac_gateway"] + "/uac-auth-service/v2/api/uac-auth/login/account"
    payload = {"appId": creds["uac_app_id"], "username": creds["uac_username"], "pwd": encrypted_pwd, "verifyKey": rsa_info["verifyKey"], "source": creds.get("uac_source", "ALM")}
    resp = session.post(url, headers={"accept": "application/json", "content-type": "application/json", "user-agent": _build_user_agent()}, json=payload, timeout=30, verify=REQUESTS_VERIFY)
    if resp.status_code != 200: raise RuntimeError(f"用户中心登录失败: HTTP {resp.status_code}")
    data = resp.json()
    if str(data.get("code")) != "200" and not data.get("success"): raise RuntimeError(f"登录失败: {data}")
    token_info = _normalize_login_token(data, creds)
    _save_token_cache(token_info)
    return token_info

def _refresh_uac_token(session: requests.Session, old_token: Dict, creds: Dict) -> Dict:
    url = creds["uac_gateway"] + "/uac-auth-service/v2/api/uac-auth/rtoken/get"
    payload = {"appId": creds["uac_app_id"], "utoken": old_token.get("p_rtoken")}
    resp = session.post(url, headers={"accept": "application/json", "content-type": "application/json", "user-agent": _build_user_agent()}, json=payload, timeout=30, verify=REQUESTS_VERIFY)
    if resp.status_code != 200: raise RuntimeError(f"刷新 token 失败: HTTP {resp.status_code}")
    data = resp.json()
    if str(data.get("code")) != "200" and not data.get("success"): raise RuntimeError(f"刷新失败: {data}")
    token_info = _normalize_login_token(data, creds)
    _save_token_cache(token_info)
    return token_info

def _get_valid_token(session: requests.Session, creds: Dict, force_login: bool = False) -> Dict:
    if force_login: return _login_uac(session, creds)
    cached = _load_token_cache()
    if cached:
        expires_at = int(cached.get("expires_at") or 0)
        if expires_at > int(time.time()) + 60: return cached
        try: return _refresh_uac_token(session, cached, creds)
        except Exception: pass
    return _login_uac(session, creds)

def _get_ws_ticket(session: requests.Session, token_info: Dict, creds: Dict) -> str:
    headers = {"accept": "application/json", "origin": AGENT_ORIGIN, "referer": AGENT_REFERER, "user-agent": _build_user_agent(), "x-header-tenant": AGENT_TENANT, "p-appid": creds.get("uac_app_id", ""), "p-auth": token_info["p_auth"], "p-empno": token_info.get("employee_no", ""), "p-langid": AGENT_LANGID, "p-platform": AGENT_PLATFORM, "p-rtoken": token_info["p_rtoken"], "p-syscode": AGENT_SYSCODE}
    resp = session.get(AGENT_TICKET_URL, headers=headers, timeout=30, verify=REQUESTS_VERIFY)
    if resp.status_code != 200: raise RuntimeError(f"获取 ticket 失败: HTTP {resp.status_code}")
    data = resp.json()
    ticket = (data.get("data") or {}).get("ticket")
    if not ticket: raise RuntimeError(f"未返回 ticket")
    return ticket

def _build_ws_url(ticket: str) -> str:
    query = {"type": "1", "chatTopicId": AGENT_CHAT_TOPIC_ID, "ticket": ticket, "lang": AGENT_LANGID, "x-header-tenant": AGENT_TENANT, "sc": "0"}
    return AGENT_WS_HOST + "?" + urlencode(query)

def _build_ws_headers(token_info: Dict, creds: Dict) -> list:
    return [f"User-Agent: {_build_user_agent()}", f"x-header-tenant: {AGENT_TENANT}", f"p-appid: {creds.get('uac_app_id', '')}", f"p-auth: {token_info['p_auth']}", f"p-empno: {token_info.get('employee_no', '')}", f"p-langid: {AGENT_LANGID}", f"p-platform: {AGENT_PLATFORM}", f"p-rtoken: {token_info['p_rtoken']}", f"p-syscode: {AGENT_SYSCODE}"]

def _build_question_payload(question: str) -> Dict:
    return {"type": 1, "content": question, "modelCode": str(AGENT_MODEL_CODE), "fileType": 0, "fileUrlList": [], "enterType": 1, "atAssistantId": None, "atAssistantSource": 2, "fileName": "", "isMemory": True, "isOnlineSearchPlugin": False, "isSpeech": False}

def ask_stability_agent(question: str, version_id: int = None, force_login: bool = False) -> Dict:
    """向稳定性测试专家智能体提问"""
    print(f"[FeishuAgent] 收到请求: question={question}, version_id={version_id}, force_login={force_login}")

    if not HAS_WEBSOCKET:
        return {"success": False, "error": "websocket-client 未安装，请运行: pip install websocket-client"}
    if not HAS_CRYPTO:
        return {"success": False, "error": "cryptography 未安装，请运行: pip install cryptography"}

    # 从ALM配置获取凭据
    print("[FeishuAgent] 获取ALM凭据...")
    creds = _get_uac_credentials()
    if creds.get("error"):
        print(f"[FeishuAgent] 凭据获取失败: {creds['error']}")
        return {"success": False, "error": creds["error"]}

    print(f"[FeishuAgent] 凭据获取成功: username={creds.get('uac_username')}")

    try:
        session = requests.Session()
        print("[FeishuAgent] 获取token...")
        token_info = _get_valid_token(session, creds, force_login=force_login)
        print(f"[FeishuAgent] token获取成功: employee_no={token_info.get('employee_no')}")

        try:
            print("[FeishuAgent] 获取WebSocket ticket...")
            ticket = _get_ws_ticket(session, token_info, creds)
        except Exception as e:
            print(f"[FeishuAgent] ticket获取失败，尝试重新登录: {e}")
            token_info = _get_valid_token(session, creds, force_login=True)
            ticket = _get_ws_ticket(session, token_info, creds)

        print(f"[FeishuAgent] ticket获取成功: {ticket[:10]}...")

        ws_url = _build_ws_url(ticket)
        ws_headers = _build_ws_headers(token_info, creds)
        sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False} if not REQUESTS_VERIFY else {}

        print("[FeishuAgent] 连接WebSocket...")
        ws = create_connection(ws_url, timeout=AGENT_TIMEOUT, header=ws_headers, sslopt=sslopt, origin=AGENT_ORIGIN)
        print("[FeishuAgent] WebSocket连接成功")

        payload = _build_question_payload(question)
        print(f"[FeishuAgent] 发送问题: {question}")
        ws.send(json.dumps(payload, ensure_ascii=False))

        final_answer = ""
        start_time = time.time()
        try:
            while True:
                if time.time() - start_time > AGENT_TIMEOUT:
                    raise TimeoutError("超时")
                msg = ws.recv()
                if not msg:
                    continue
                try:
                    parsed = json.loads(msg)
                except Exception:
                    continue
                msg_type = parsed.get("type")
                data_flag = parsed.get("data")
                print(f"[FeishuAgent] 收到消息: type={msg_type}, data={data_flag}")

                if data_flag == "end":
                    final_answer = (parsed.get("answerObj") or {}).get("content") or ""
                    print(f"[FeishuAgent] 收到最终回答，长度: {len(final_answer)}")
                    break
                if (parsed.get("answerObj") or {}).get("content"):
                    final_answer = parsed["answerObj"]["content"]
                if parsed.get("content"):
                    final_answer = parsed["content"]
        finally:
            try:
                ws.close()
            except Exception:
                pass

        print(f"[FeishuAgent] 保存对话到数据库...")
        _save_conversation_to_db(question, final_answer, version_id)
        print(f"[FeishuAgent] 调用完成")
        return {"success": True, "question": question, "answer": final_answer, "agent_name": AGENT_ASSISTANT_NAME, "timestamp": now_iso()}
    except Exception as e:
        import traceback
        print(f"[FeishuAgent] 调用异常: {e}")
        traceback.print_exc()
        return {"success": False, "error": f"智能体调用失败: {str(e)}", "question": question}

def _save_conversation_to_db(question: str, answer: str, version_id: int = None):
    """保存对话到数据库，如果相同问题已存在则更新回答"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        # 检查是否已存在相同问题（同一版本）
        if version_id:
            cur.execute("SELECT id FROM feishu_agent_conversations WHERE question = ? AND version_id = ?", (question, version_id))
        else:
            cur.execute("SELECT id FROM feishu_agent_conversations WHERE question = ? AND version_id IS NULL", (question,))
        existing = cur.fetchone()

        if existing:
            # 更新已有记录的回答
            cur.execute("UPDATE feishu_agent_conversations SET answer = ?, created_at = ? WHERE id = ?",
                       (answer, now_iso(), existing["id"]))
            print(f"[FeishuAgent] 更新已有对话 id={existing['id']}")
        else:
            # 插入新记录
            cur.execute("INSERT INTO feishu_agent_conversations (question, answer, agent_name, created_at, version_id) VALUES (?, ?, ?, ?, ?)",
                       (question, answer, AGENT_ASSISTANT_NAME, now_iso(), version_id))
        conn.commit()
        conn.close()
    except Exception as e: print(f"[FeishuAgent] 保存对话失败: {e}")

def delete_conversation(history_id: int):
    """删除单条历史记录"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM feishu_agent_conversations WHERE id = ?", (history_id,))
        conn.commit()
        conn.close()
    except Exception as e: print(f"[FeishuAgent] 删除对话失败: {e}")

def clean_old_conversations(keep_days: int = 14):
    """清理超过指定天数的历史对话"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        cur.execute("DELETE FROM feishu_agent_conversations WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        if deleted > 0:
            print(f"[FeishuAgent] 清理了 {deleted} 条超过 {keep_days} 天的历史对话")
        conn.commit()
        conn.close()
    except Exception as e: print(f"[FeishuAgent] 清理历史对话失败: {e}")

def get_conversation_history(version_id: int = None, limit: int = 50) -> list:
    try:
        conn = get_conn()
        cur = conn.cursor()
        if version_id:
            cur.execute("SELECT id, question, answer, agent_name, created_at FROM feishu_agent_conversations WHERE version_id = ? ORDER BY created_at DESC LIMIT ?", (version_id, limit))
        else:
            cur.execute("SELECT id, question, answer, agent_name, created_at FROM feishu_agent_conversations ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception: return []

def get_stability_data_for_analysis(version_id: int = None) -> str:
    """获取稳定性数据用于AI分析"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        if version_id:
            cur.execute("SELECT question, answer, created_at FROM feishu_agent_conversations WHERE version_id = ? ORDER BY created_at DESC LIMIT 20", (version_id,))
        else:
            cur.execute("SELECT question, answer, created_at FROM feishu_agent_conversations ORDER BY created_at DESC LIMIT 20")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        if not rows: return "暂无稳定性测试专家对话数据"
        lines = ["=== 稳定性测试专家对话记录 ==="]
        for r in rows:
            lines.append(f"[{r['created_at'][:16]}] 问: {r['question'][:100]}")
            lines.append(f"答: {r['answer'][:500]}")
        return "\n".join(lines)
    except Exception as e: return f"获取稳定性数据失败: {str(e)}"
