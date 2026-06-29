import json
import time
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from ..config import APP_DIR
from ..database import get_conn
from ..encryption import encrypt_text, decrypt_text
from ..utils import now_iso

# ALM token 缓存路径
ALM_TOKEN_CACHE_PATH = APP_DIR / "alm_token_cache.json"

def get_alm_config():
    """从数据库读取 ALM 配置"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alm_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    row_dict = dict(row)
    # 解密密码
    pwd = ""
    if row_dict.get("encrypted_password"):
        try:
            pwd = decrypt_text(row_dict["encrypted_password"])
        except Exception:
            pass
    return {
        "uac_gateway": row_dict.get("uac_gateway", "").rstrip("/"),
        "alm_app_id": row_dict.get("alm_app_id", ""),
        "uac_username": row_dict.get("uac_username", ""),
        "uac_password": pwd,
        "uac_source": row_dict.get("uac_source", "ALM"),
        "alm_base_url": row_dict.get("alm_base_url", "").rstrip("/"),
        "alm_space_bid": row_dict.get("alm_space_bid", ""),
        "alm_app_bid": row_dict.get("alm_app_bid", ""),
    }

def api_get_alm_config():
    """获取ALM配置（API接口）"""
    cfg = get_alm_config()
    if not cfg:
        return {"configured": False, "username": "", "alm_app_id": ""}
    has_creds = bool(cfg["alm_app_id"] and cfg["uac_username"] and cfg["uac_password"])
    # 检查工号格式是否正确
    username = cfg["uac_username"]
    username_valid = username.isdigit() if username else True
    warning = ""
    if username and not username_valid:
        warning = f"工号 '{username}' 格式不正确，ALM 需要纯数字工号（如 18665088），请重新配置。"
    return {
        "configured": has_creds,
        "uac_gateway": cfg["uac_gateway"],
        "alm_app_id": cfg["alm_app_id"],
        "uac_username": cfg["uac_username"],
        "uac_source": cfg["uac_source"],
        "alm_base_url": cfg["alm_base_url"],
        "alm_space_bid": cfg["alm_space_bid"],
        "alm_app_bid": cfg["alm_app_bid"],
        "username_valid": username_valid,
        "warning": warning,
    }

def api_save_alm_config(req):
    """保存ALM配置（API接口）"""
    if not req.alm_app_id or not req.uac_username or not req.uac_password:
        raise HTTPException(status_code=400, detail="App ID、工号和密码不能为空")
    # 验证 ALM 工号格式：必须是纯数字（如 18665088）
    username = req.uac_username.strip()
    if not username.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"ALM 工号必须是纯数字（如 18665088），当前输入 '{username}' 不是有效工号。"
                   f"注意：ALM 使用的是员工工号，不是 Jira 域账号。"
        )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE alm_config SET
            uac_gateway=?, alm_app_id=?, uac_username=?, encrypted_password=?,
            uac_source=?, alm_base_url=?, alm_space_bid=?, alm_app_bid=?, updated_at=?
        WHERE id=1
    """, (
        req.uac_gateway.rstrip("/"), req.alm_app_id.strip(), req.uac_username.strip(),
        encrypt_text(req.uac_password), req.uac_source, req.alm_base_url.rstrip("/"),
        req.alm_space_bid, req.alm_app_bid, now_iso()
    ))
    conn.commit()
    conn.close()
    # 清除旧 token 缓存
    if ALM_TOKEN_CACHE_PATH.exists():
        ALM_TOKEN_CACHE_PATH.unlink()
    return {"message": "ALM 配置已保存"}

def _alm_rsa_encrypt(password: str, public_key_b64: str) -> str:
    """ALM RSA加密"""
    der = base64.b64decode(public_key_b64)
    pub_key = serialization.load_der_public_key(der)
    encrypted = pub_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("utf-8")

def _alm_load_token_cache():
    """加载ALM token缓存"""
    if not ALM_TOKEN_CACHE_PATH.exists():
        return None
    try:
        return json.loads(ALM_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

def _alm_save_token_cache(p_auth, p_rtoken, employee_no, expires_in=1200):
    """保存ALM token缓存"""
    data = {
        "p_auth": p_auth, "p_rtoken": p_rtoken,
        "employee_no": employee_no or "",
        "expires_at": int(time.time()) + int(expires_in or 1200),
    }
    ALM_TOKEN_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

def _alm_login(cfg):
    """ALM 用户中心 RSA 登录"""
    gw = cfg["uac_gateway"]
    # 1. 获取 RSA 公钥
    rsa_resp = requests.get(
        f"{gw}/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair",
        headers={"Accept": "application/json"}, timeout=30, verify=False
    ).json()
    if str(rsa_resp.get("code")) not in ("0", "200"):
        raise RuntimeError(f"获取RSA公钥失败: {rsa_resp}")
    body = rsa_resp.get("data") or {}
    public_key, verify_key = body.get("publicKey"), body.get("verifyKey")
    if not public_key or not verify_key:
        raise RuntimeError(f"RSA响应缺少字段: {rsa_resp}")

    # 2. 加密密码并登录
    enc_pwd = _alm_rsa_encrypt(cfg["uac_password"], public_key)
    login_resp = requests.post(
        f"{gw}/uac-auth-service/v2/api/uac-auth/login/account",
        json={"appId": cfg["alm_app_id"], "username": cfg["uac_username"],
              "pwd": enc_pwd, "verifyKey": verify_key, "source": cfg["uac_source"]},
        headers={"Content-Type": "application/json;charset=utf-8", "Accept": "application/json",
                 "P-AppId": cfg["alm_app_id"], "p-appid": cfg["alm_app_id"]},
        timeout=30, verify=False
    ).json()
    if str(login_resp.get("code")) not in ("0", "200"):
        err_msg = login_resp.get("message", "")
        err_code = login_resp.get("code", "")
        if str(err_code) == "10305":
            raise RuntimeError(
                f"ALM登录失败: 账号 '{cfg['uac_username']}' 不存在。"
                f"请确认使用的是员工工号（纯数字，如 18665088），而非 Jira 域账号。"
                f"原始错误: {login_resp}"
            )
        raise RuntimeError(f"ALM登录失败: {login_resp}")
    login_body = login_resp.get("data") or {}
    p_auth = login_body.get("rtoken") or login_body.get("token")
    p_rtoken = login_body.get("utoken")
    emp_no = login_body.get("employeeNo") or cfg["uac_username"]
    if not p_auth or not p_rtoken:
        raise RuntimeError(f"登录响应缺少token: {login_resp}")
    print(f"[ALM] 登录成功, employeeNo={emp_no}")
    return _alm_save_token_cache(p_auth, p_rtoken, emp_no, login_body.get("expiresIn", 1200))

def _alm_refresh_token(cfg, p_rtoken):
    """刷新 ALM token"""
    gw = cfg["uac_gateway"]
    resp = requests.post(
        f"{gw}/uac-auth-service/v2/api/uac-auth/rtoken/get",
        json={"appId": cfg["alm_app_id"], "utoken": p_rtoken},
        headers={"Content-Type": "application/json;charset=utf-8", "Accept": "application/json",
                 "P-AppId": cfg["alm_app_id"], "P-Rtoken": p_rtoken,
                 "p-appid": cfg["alm_app_id"], "p-rtoken": p_rtoken},
        timeout=30, verify=False
    ).json()
    if str(resp.get("code")) not in ("0", "200"):
        raise RuntimeError(f"刷新token失败: {resp}")
    body = resp.get("data") or {}
    new_auth = body.get("rtoken") or body.get("token")
    new_rtoken = body.get("utoken") or p_rtoken
    if not new_auth:
        raise RuntimeError(f"刷新响应缺少token: {resp}")
    old = _alm_load_token_cache() or {}
    print("[ALM] token 刷新成功")
    return _alm_save_token_cache(new_auth, new_rtoken, old.get("employee_no", ""), body.get("expiresIn", 1200))

def alm_get_token(cfg):
    """获取有效的 ALM token（自动缓存/刷新/重新登录）"""
    cache = _alm_load_token_cache()
    if cache and cache.get("p_auth") and cache.get("p_rtoken"):
        if int(cache.get("expires_at", 0)) > int(time.time()) + 90:
            return cache
        try:
            return _alm_refresh_token(cfg, cache["p_rtoken"])
        except Exception:
            pass
    return _alm_login(cfg)

def _alm_headers(cfg, token_cache):
    """构建ALM请求头"""
    return {
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json, text/plain, */*",
        "p-auth": token_cache["p_auth"], "p-rtoken": token_cache["p_rtoken"],
        "p-appid": cfg["alm_app_id"], "p-langid": "zh", "p-empno": token_cache.get("employee_no", ""),
        "P-Auth": token_cache["p_auth"], "P-Rtoken": token_cache["p_rtoken"],
        "P-AppId": cfg["alm_app_id"], "P-LangId": "zh", "P-EmpNo": token_cache.get("employee_no", ""),
    }

def alm_request(cfg, path, method="POST", payload=None):
    """ALM API 请求封装（自动重试 token 错误）"""
    token = alm_get_token(cfg)
    headers = _alm_headers(cfg, token)
    url = cfg["alm_base_url"] + (path if path.startswith("/") else "/" + path)
    if method.upper() == "GET":
        resp = requests.get(url, headers=headers, params=payload or {}, timeout=60, verify=False)
    else:
        resp = requests.post(url, headers=headers, json=payload or {}, timeout=60, verify=False)
    data = resp.json()
    # token 错误 → 刷新后重试一次
    if str(data.get("code", "")) in ("30003", "30004", "30008", "30009"):
        print("[ALM] token 过期，重新登录...")
        token = _alm_login(cfg)
        headers = _alm_headers(cfg, token)
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=payload or {}, timeout=60, verify=False)
        else:
            resp = requests.post(url, headers=headers, json=payload or {}, timeout=60, verify=False)
        data = resp.json()
    return data

def alm_query_sr_detail(cfg, sr_coding: str, space_bid: str = "", app_bid: str = ""):
    """查询单个 SR 的详细信息（优先使用 space/app 接口以获取 spaceBid 用于版本过滤）"""
    records = []

    # 优先使用 space/app 接口（返回 spaceBid 等完整字段，用于版本过滤）
    # 使用传入的版本级 space/app bid，若未传入则回退到全局配置
    effective_space_bid = space_bid or cfg.get("alm_space_bid", "")
    effective_app_bid = app_bid or cfg.get("alm_app_bid", "")
    if effective_space_bid and effective_app_bid:
        fb_path = f"/apm/space/{effective_space_bid}/app/{effective_app_bid}/data-driven/page"
        fb_payload = {
            "current": 1, "size": 100,
            "param": {
                "anyMatch": True,
                "queries": [
                    {"property": "coding", "condition": "LIKE", "value": sr_coding},
                    {"property": "name", "condition": "LIKE", "value": sr_coding},
                ],
                "orders": [{"desc": True, "property": "createdTime"}],
            },
        }
        try:
            data = alm_request(cfg, fb_path, "POST", fb_payload)
            if str(data.get("code")) in ("0", "200"):
                records = (data.get("data") or {}).get("data") or (data.get("data") or {}).get("records") or []
        except Exception:
            pass

    # 若 space/app 接口未返回结果，回退到通用接口
    if not records:
        path = "/data-driven/api/object-model/A02/page"
        payload = {
            "current": 1, "size": 10,
            "param": {
                "anyMatch": False,
                "queries": [{"property": "coding", "condition": "EQ", "value": sr_coding}],
                "orders": [{"desc": False, "property": "createdTime"}],
            },
        }
        data = alm_request(cfg, path, "POST", payload)
        if str(data.get("code")) in ("0", "200"):
            records = (data.get("data") or {}).get("data") or (data.get("data") or {}).get("records") or []

    # 精确匹配 coding
    for r in records:
        if str(r.get("coding", "")).strip() == sr_coding:
            return r
    return records[0] if records else None

def alm_query_locked_srs(cfg, space_bid: str, max_pages: int = 20, page_size: int = 10000) -> list:
    """查询 ALM 某个 tOS 版本空间下全部加锁（lockFlag=YES_LOCK）的系统需求 SR。

    参考: D:\\tOSworkbench\\ALM_api_test\\alm_locked_sr_status_reader.py

    Returns:
        所有加锁 SR 记录列表
    """
    MODEL_CODE = "A02"  # 系统需求 SR
    path = f"/data-driven/api/object-model/{MODEL_CODE}/page"
    all_records = []

    for page in range(1, max_pages + 1):
        payload = {
            "current": page,
            "size": page_size,
            "param": {
                "queries": [
                    {"property": "spaceBid", "condition": "EQ", "value": space_bid},
                    {"property": "lockFlag", "condition": "EQ", "value": "YES_LOCK"},
                ],
                "orders": [{"desc": True, "property": "updatedTime"}],
            },
        }
        print(f"[ALM-LOCKED] 查询第 {page} 页，spaceBid={space_bid}")
        resp_json = alm_request(cfg, path, "POST", payload)

        # token 错误已在 alm_request 内部重试，此处仅需判断业务成功
        if str(resp_json.get("code")) not in ("0", "200") or resp_json.get("success") is not True:
            raise RuntimeError(f"ALM 查询加锁 SR 失败：{str(resp_json)[:500]}")

        data_block = resp_json.get("data") or {}
        records = data_block.get("data") or data_block.get("records") or []
        total_pages = int(data_block.get("pages") or 1)

        print(f"[ALM-LOCKED] 第 {page} 页记录数：{len(records)}，总页数：{total_pages}")
        all_records.extend(records)

        if page >= total_pages or not records:
            break

    # 双保险：确保只保留 lockFlag=YES_LOCK
    before = len(all_records)
    all_records = [
        r for r in all_records
        if str(r.get("lockFlag") or "").strip().upper() == "YES_LOCK"
    ]
    print(f"[ALM-LOCKED] 最终确认 lockFlag=YES_LOCK：{before} -> {len(all_records)}")
    return all_records


# ──────────────────────────────────────────────
# 加锁 SR lifeCycleCode 状态映射
# ──────────────────────────────────────────────
ALM_SR_STATUS_NAME_MAP = {
    "INITIALIZE": "初始",
    "DESIGNING": "设计",
    "DEVELOPING": "开发",
    "TESTING": "测试",
    "UAT": "验收",
    "COMPLETED": "完成",
}

ALM_SR_STATUS_ORDER = [
    "INITIALIZE", "DESIGNING", "DEVELOPING", "TESTING", "UAT", "COMPLETED",
]


def alm_summarize_locked_srs(records: list) -> dict:
    """按 lifeCycleCode 汇总加锁 SR 数量。

    Returns:
        {
          "INITIALIZE": {"lifeCycleCode":"INITIALIZE","statusName":"初始","count":N},
          ...
          "_total": N
        }
    """
    summary: dict = {}
    for code in ALM_SR_STATUS_ORDER:
        summary[code] = {"lifeCycleCode": code, "statusName": ALM_SR_STATUS_NAME_MAP.get(code, code), "count": 0}
    unknown: dict = {}
    for row in records:
        status = str(row.get("lifeCycleCode") or "").strip()
        if status in summary:
            summary[status]["count"] += 1
        else:
            unknown.setdefault(status, {"lifeCycleCode": status or "EMPTY", "statusName": "未知/空", "count": 0})
            unknown[status]["count"] += 1
    summary.update(unknown)
    summary["_total"] = len(records)
    return summary


def alm_normalize_locked_sr(row: dict) -> dict:
    """将 ALM 加锁 SR 原始记录规范化为可存储的字典"""
    status = str(row.get("lifeCycleCode") or "").strip()
    # 提取 tag 字段（可能是 list 或 string）
    raw_tag = row.get("tag") or row.get("tags") or []
    if isinstance(raw_tag, list):
        tag_str = ",".join(str(t) for t in raw_tag)
    else:
        tag_str = str(raw_tag)

    return {
        "sr_coding": str(row.get("coding") or "").strip(),
        "sr_name": str(row.get("name") or "").strip(),
        "life_cycle_code": status,
        "life_cycle_name": ALM_SR_STATUS_NAME_MAP.get(status, status),
        "priority": str(row.get("priority") or "").strip(),
        "lock_flag": str(row.get("lockFlag") or "").strip(),
        "space_bid": str(row.get("spaceBid") or "").strip(),
        "test_representative": str(row.get("testRepresentative") or "").strip(),
        "person_responsible": str(row.get("personResponsible") or "").strip(),
        "development_representative": str(row.get("developmentRepresentative") or "").strip(),
        "planned_transfer_test_time": str(row.get("plannedTransferTestTime") or "").strip(),
        "planned_acceptance_start_time": str(row.get("plannedAcceptanceStartTime") or "").strip(),
        "actual_development_completion_time": str(row.get("actualDevelopmentCompletionTime") or "").strip(),
        "belong_domain": str(row.get("belongDomain") or "").strip(),
        "tag": tag_str,
    }


def alm_batch_find_users(cfg, job_numbers: list) -> dict:
    """批量查询用户信息（与原始后端 main.py 完全一致）"""
    if not job_numbers:
        return {}
    result = {}
    for i in range(0, len(job_numbers), 100):
        chunk = job_numbers[i:i + 100]
        try:
            data = alm_request(cfg, "/transcend/user/batchFindByEmoNo", "POST", chunk)
            if str(data.get("code")) in ("0", "200") and data.get("success"):
                for u in (data.get("data") or []):
                    jn = str(u.get("jobNumber", "")).strip()
                    if jn:
                        result[jn] = u
        except Exception as e:
            print(f"[ALM] 批量查询用户失败: {e}")
    return result


def alm_query_third_dept(cfg, job_number: str) -> dict:
    """查询测试主责人三级部门（与原始后端 main.py 完全一致）"""
    if not job_number:
        return {}
    try:
        data = alm_request(cfg, f"/apm/common/queryThreeDeptInfo/{job_number}", "GET")
        if str(data.get("code")) in ("0", "200") and data.get("success"):
            return data.get("data") or {}
    except Exception:
        pass
    return {}
    # 暂时留空，后续实现
    return False