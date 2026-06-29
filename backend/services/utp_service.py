"""
UTP 平台服务：缺陷分析数据提取。
基于 UTP_api_test/defect_analyze_reader.py 的逻辑移植。
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
import base64

from ..config import APP_DIR

# UTP 配置
UTP_TOKEN_CACHE_PATH = APP_DIR / "utp_token_cache.json"
UTP_BASE_URL = "https://pfgatewaysz.transsion.com:9199/utp-task"
UAC_GATEWAY = "https://pfgatewaysz.transsion.com:9199"
UTP_APP_ID = "c_MjYwNjAxMDAxaA"
UAC_SOURCE = "UTP"

# 缺陷分析接口路径
DEFECT_PAGE_PATH = "/api/defectAnalyze/queryDefectPage"
DEFECT_STATISTIC_PATH = "/api/defectAnalyze/statisticBugData"

# 默认 payload 模板
DEFAULT_DEFECT_PAYLOAD = {
    "size": 100,
    "current": 1,
    "descs": "",
    "ascs": "",
    "param": {
        "queryMyTask": False,
        "queryRetestTask": False,
        "librarySourceList": [],
        "issueStatusList": [],
        "dupIssueStatusList": [],
        "projectNameList": [],
        "firstDeptNoList": [],
        "secondDeptNoList": [],
        "thirdDeptNoList": [],
        "firstDeptNoAssigneeList": [],
        "secondDeptNoAssigneeList": [],
        "thirdDeptNoAssigneeList": [],
        "fourthDeptNoAssigneeList": [],
        "thirdDeptNoReporterList": [],
        "fourthDeptNoReporterList": [],
        "fifthDeptNoReporterList": [],
        "assigneeCodeList": [],
        "openerCodeList": [],
        "priorityList": [],
        "resolutionList": [],
        "riskList": [],
        "categoryList": [],
        "componentList": [],
        "issueNatureList": [],
        "mustResolveList": [],
        "tagList": [],
        "blockProNode": [],
        "applyType": "",
        "fixVersion": "",
        "jiraKey": "",
        "label": "",
        "labelReview": "",
        "nextStep": "",
        "openTimes": "",
        "projectType": "",
        "reason": "",
        "reminderStatus": "",
        "solution": "",
        "summary": "",
        "testSuggestion": "",
        "tpmOwner": "",
    },
}

TOKEN_ERROR_CODES = {"30003", "30004", "30008", "30009"}


def _now_ts() -> int:
    return int(time.time())


def _encrypt_password(password: str, public_key_base64: str) -> str:
    der = base64.b64decode(public_key_base64)
    pub_key = serialization.load_der_public_key(der)
    encrypted = pub_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("utf-8")


def _is_token_error(data: Dict) -> bool:
    code = str(data.get("code", ""))
    msg = str(data.get("message", ""))
    if code in TOKEN_ERROR_CODES:
        return True
    if "token" in msg.lower() and ("失效" in msg or "过期" in msg or "invalid" in msg.lower() or "expired" in msg.lower()):
        return True
    return False


def _load_token_cache() -> Optional[Dict]:
    if not UTP_TOKEN_CACHE_PATH.exists():
        return None
    try:
        return json.loads(UTP_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_token_cache(token_info: Dict):
    UTP_TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UTP_TOKEN_CACHE_PATH.write_text(json.dumps(token_info, ensure_ascii=False), encoding="utf-8")


def _get_alm_credentials() -> Optional[Dict]:
    """从 ALM 配置获取 UAC 凭据（UTP 和 ALM 共用同一套 UAC 账号密码，但 app_id 不同）"""
    from ..database import get_conn
    from ..encryption import decrypt_text
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alm_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    pwd = ""
    if row.get("encrypted_password"):
        try:
            pwd = decrypt_text(row["encrypted_password"])
        except Exception:
            pass
    if not row.get("uac_username") or not pwd:
        return None
    return {
        "app_id": row.get("alm_app_id", "") or UTP_APP_ID,
        "username": row["uac_username"],
        "password": pwd,
    }


def _login(cred: Dict) -> Dict:
    """UAC 登录获取 token"""
    gw = UAC_GATEWAY
    # 1. 获取 RSA 公钥
    rsa_resp = requests.get(
        f"{gw}/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair",
        timeout=30, verify=False
    ).json()
    if str(rsa_resp.get("code")) != "200":
        raise RuntimeError(f"获取RSA公钥失败: {rsa_resp}")
    body = rsa_resp.get("data") or {}
    public_key = body.get("publicKey")
    verify_key = body.get("verifyKey")
    if not public_key or not verify_key:
        raise RuntimeError(f"RSA响应缺少字段: {rsa_resp}")

    # 2. 加密密码并登录
    enc_pwd = _encrypt_password(cred["password"], public_key)
    login_resp = requests.post(
        f"{gw}/uac-auth-service/v2/api/uac-auth/login/account",
        json={
            "appId": cred["app_id"],
            "username": cred["username"],
            "pwd": enc_pwd,
            "verifyKey": verify_key,
            "source": UAC_SOURCE,
        },
        timeout=30, verify=False
    ).json()
    if str(login_resp.get("code")) != "200":
        raise RuntimeError(f"UTP登录失败: {login_resp}")

    token_data = login_resp["data"]
    expires_in = int(token_data.get("expiresIn") or 1000)
    token_info = {
        "rtoken": token_data.get("rtoken") or token_data.get("token"),
        "utoken": token_data.get("utoken"),
        "employeeNo": token_data.get("employeeNo") or cred["username"],
        "expires_at": _now_ts() + expires_in - 60,
    }
    _save_token_cache(token_info)
    return token_info


def _refresh_token(cred: Dict, cache: Dict) -> Dict:
    """刷新 token"""
    utoken = cache.get("utoken")
    if not utoken:
        return _login(cred)
    try:
        resp = requests.post(
            f"{UAC_GATEWAY}/uac-auth-service/v2/api/uac-auth/rtoken/get",
            json={"appId": cred["app_id"], "utoken": utoken},
            timeout=30, verify=False
        ).json()
        if str(resp.get("code")) != "200":
            return _login(cred)
        token_data = resp["data"]
        expires_in = int(token_data.get("expiresIn") or 1000)
        token_info = {
            "rtoken": token_data.get("rtoken") or token_data.get("token"),
            "utoken": token_data.get("utoken") or utoken,
            "employeeNo": cache.get("employeeNo") or cred["username"],
            "expires_at": _now_ts() + expires_in - 60,
        }
        _save_token_cache(token_info)
        return token_info
    except Exception:
        return _login(cred)


def _ensure_token(cred: Dict) -> Dict:
    """确保有有效 token"""
    cache = _load_token_cache()
    if not cache:
        return _login(cred)
    if int(cache.get("expires_at") or 0) <= _now_ts():
        return _refresh_token(cred, cache)
    return cache


def _build_utp_headers(cred: Dict) -> Dict:
    """构建 UTP 请求头"""
    token = _ensure_token(cred)
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "p-auth": token["rtoken"],
        "p-rtoken": token["utoken"],
        "p-appid": cred["app_id"],
        "p-langid": "zh",
        "p-empno": token.get("employeeNo") or cred["username"],
        "P-Auth": token["rtoken"],
        "P-Rtoken": token["utoken"],
        "P-AppId": cred["app_id"],
        "P-LangId": "zh",
        "P-EmpNo": token.get("employeeNo") or cred["username"],
    }


def _utp_post(cred: Dict, path: str, payload: Dict) -> Dict:
    """发起 UTP POST 请求（含 token 自动刷新重试）"""
    url = f"{UTP_BASE_URL}{path}"
    headers = _build_utp_headers(cred)
    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"UTP 响应非 JSON: HTTP={resp.status_code}, text={resp.text[:500]}")

    if resp.status_code in (401, 403) or _is_token_error(data):
        print("[UTP] token 失效，刷新后重试...")
        _refresh_token(cred, _load_token_cache() or {})
        headers = _build_utp_headers(cred)
        resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
        data = resp.json()

    # 检查业务成功状态
    code = str(data.get("code", ""))
    success = data.get("success")
    if code not in ("200", "0") and success is not True:
        msg = data.get("message") or data.get("msg") or code
        raise RuntimeError(f"UTP 接口返回失败 (code={code}): {msg}")

    return data


def _utp_get(cred: Dict, path: str, params: Dict = None) -> Dict:
    """发起 UTP GET 请求（含 token 自动刷新重试）"""
    url = f"{UTP_BASE_URL}{path}"
    headers = _build_utp_headers(cred)
    resp = requests.get(url, headers=headers, params=params or {}, timeout=60, verify=False)
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"UTP 响应非 JSON: HTTP={resp.status_code}, text={resp.text[:500]}")

    if resp.status_code in (401, 403) or _is_token_error(data):
        print("[UTP] token 失效，刷新后重试...")
        _refresh_token(cred, _load_token_cache() or {})
        headers = _build_utp_headers(cred)
        resp = requests.get(url, headers=headers, params=params or {}, timeout=60, verify=False)
        data = resp.json()

    code = str(data.get("code", ""))
    success = data.get("success")
    if code not in ("200", "0") and success is not True:
        msg = data.get("message") or data.get("msg") or code
        raise RuntimeError(f"UTP 接口返回失败 (code={code}): {msg}")

    return data


def _clean_jira_markup(value: Any) -> str:
    """清理 Jira Wiki 标记"""
    if value is None:
        return ""
    text = str(value)
    m = re.search(r"\{color:[^}]+\}(.*?)\{color\}", text)
    if m:
        return m.group(1).strip()
    text = text.replace("(/)", "").replace("*", "")
    text = re.sub(r"\{color:[^}]+\}", "", text)
    text = text.replace("{color}", "")
    return text.strip()


# ==============================
# 部门归类规则
# ==============================

def classify_department(summary: str, assignee_third_dept: str, project_name: str = "") -> str:
    """
    根据 summary 内容和 assignee 三级部门，归类到统一部门名称。
    规则：
    1. summary 包含 oversea → 海外测试
    2. summary 包含 易景团队/天珑团队/萨瑞团队 → DT_外研测试部
    3. assignee三级部门 包含 SW_AE_ 或 包含 开发/研发/运营 → 产品开发与设计
    4. assignee三级部门 为"其他"且项目为大版本升级（特定机型） → DT_交付技术测试部
    5. DT_交付测试二部/三部/一部/DT_交付在研项目部 → 交付测试部
    """
    s = (summary or "").lower()
    dept = (assignee_third_dept or "").strip()

    # 规则1: oversea
    if "oversea" in s:
        return "海外测试"

    # 规则2: 外研团队
    for kw in ["易景团队", "天珑团队", "萨瑞团队"]:
        if kw in (summary or ""):
            return "DT_外研测试部"

    # 规则3: SW_AE_ 或 开发/研发/运营
    if dept:
        if "SW_" in dept or "AE_" in dept or "SW_AE" in dept:
            return "产品开发与设计"
        for kw in ["开发", "研发", "运营"]:
            if kw in dept:
                return "产品开发与设计"

    # 规则4: 其他 + 大版本升级项目
    if dept == "其他":
        upgrade_models = [
            "X6873", "X6876", "X6857", "X6857B", "X6855", "X6858",
            "CM6", "CM7", "CM8",
            "CLG", "CLEK", "CL8", "CL9", "CLA5", "CLA6",
            "KM9", "LJ6", "LJ7", "LJ8", "LJ8K", "LJ9",
            "X6885", "X6886", "X6850", "X6850B", "X6871",
        ]
        pn = (project_name or "").upper()
        for model in upgrade_models:
            if model.upper() in pn:
                return "DT_交付技术测试部"

    # 规则5: 统一交付测试部
    unify_map = {
        "DT_交付测试二部": "交付测试部",
        "DT_交付测试三部": "交付测试部",
        "DT_交付测试一部": "交付测试部",
        "DT_交付在研项目部": "交付测试部",
    }
    for old_name, new_name in unify_map.items():
        if old_name in dept:
            return new_name

    # 未匹配则返回原始部门
    return dept or "未分类"


def fetch_utp_defects(jira_list: List[str], status_list: List[str] = None, dup_status_list: List[str] = None, max_pages: int = 50) -> Dict:
    """
    从 UTP 缺陷分析接口获取数据。
    jira_list: 关联 JIRA 库列表，如 ["tOS17.0"]
    status_list: 缺陷状态筛选，如 ["Verified", "Resolved"]，空列表表示不限
    dup_status_list: 置重状态筛选（本地过滤），空列表表示不限
    返回: {"records": [...], "total": N, "error": "..."}
    """
    cred = _get_alm_credentials()
    if not cred:
        return {"records": [], "total": 0, "error": "请先配置 ALM/UTP 账号（设置 → ALM）"}

    all_records = []

    total = 0
    pages = 0
    consecutive_errors = 0

    for page in range(1, max_pages + 1):
        payload = json.loads(json.dumps(DEFAULT_DEFECT_PAYLOAD))
        payload["size"] = 100
        payload["current"] = page
        payload["param"]["librarySourceList"] = jira_list

        if status_list:
            payload["param"]["issueStatusList"] = status_list

        # 移除空列表字段，避免 UTP 服务端解析异常
        param = payload["param"]
        for key in list(param.keys()):
            if isinstance(param[key], list) and len(param[key]) == 0:
                del param[key]

        try:
            resp = _utp_post(cred, DEFECT_PAGE_PATH, payload)
        except Exception as e:
            print(f"[UTP] 第 {page} 页请求异常: {e}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                return {"records": all_records, "total": len(all_records), "error": f"UTP 连续请求失败: {str(e)[:80]}"}
            continue

        code = str(resp.get("code", ""))
        if code not in {"200", "0"}:
            msg = resp.get("message", "") or resp.get("msg", "") or code
            print(f"[UTP] 第 {page} 页返回异常: {msg}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                return {"records": all_records, "total": len(all_records), "error": f"UTP 返回异常: {msg}"}
            continue

        consecutive_errors = 0  # 重置连续错误计数
        data = resp.get("data") or {}
        records = data.get("records") or []
        total = int(data.get("total") or 0)
        pages = int(data.get("pages") or 0)

        print(f"[UTP] 第 {page} 页获取 {len(records)} 条，total={total}，pages={pages}")

        all_records.extend(records)

        if not records or (pages and page >= pages) or (total and len(all_records) >= total):
            break

    # 本地过滤：置重状态
    if dup_status_list:
        dup_set = set(dup_status_list)
        filtered = []
        for row in all_records:
            dup_clean = _clean_jira_markup(row.get("dupIssueStatus", ""))
            if not dup_clean or dup_clean.lower() == "none":
                dup_clean = "None"
            if dup_clean in dup_set:
                filtered.append(row)
        return {"records": filtered, "total": len(filtered)}

    return {"records": all_records, "total": len(all_records)}


# ==============================
# UTP Weekly 测试报告
# ==============================

WEEKLY_PLAN_LIST_PATH = "/api/testPlan/queryPlanList"
WEEKLY_REPORT_PATH = "/api/report/getPlanReport"


def _build_weekly_plan_payload(page: int, project_code: str, owner_codes, search_key: str = "weekly") -> Dict:
    """Build UTP plan list query payload.
    owner_codes can be a string (comma-separated) or a list.
    """
    if isinstance(owner_codes, str):
        codes = [c.strip() for c in owner_codes.split(",") if c.strip()]
    else:
        codes = list(owner_codes) if owner_codes else []
    return {
        "size": 100,
        "current": page,
        "descs": "",
        "ascs": "",
        "param": {
            "testPlanName": "",
            "projectCode": project_code,
            "testPlanStatus": "",
            "testPlanType": "",
            "level": "",
            "testStage": "",
            "ownerCodes": codes,
            "searchKey": search_key,
            "testArea": "",
            "testPlanEndTime": "",
            "testPlanStartTime": "",
        }
    }


def _get_plan_sort_time(plan: Dict):
    """Get the sort time for a plan (COMPLETE plans use finishTime)."""
    from datetime import datetime
    for key in ["finishTime", "updatedTime", "endTime", "createdTime", "startTime"]:
        value = plan.get(key)
        if value:
            try:
                return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
    return datetime.min


def _pick_latest_complete_plan(records: list, platform_keyword: str) -> Optional[Dict]:
    """Find the latest COMPLETE weekly plan matching a platform keyword ([MTK] or [Q])."""
    candidates = []
    for plan in records:
        name = plan.get("testPlanName") or ""
        status = plan.get("planStatus") or ""
        if status != "COMPLETE":
            continue
        if platform_keyword not in name:
            continue
        if "weekly" not in name.lower():
            continue
        if "模板" in name:
            continue
        candidates.append(plan)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (_get_plan_sort_time(x), int(x.get("id") or 0)), reverse=True)
    return candidates[0]


def _get_platform_name(plan_name: str) -> str:
    if "[MTK]" in plan_name:
        return "MTK"
    if "[Q]" in plan_name:
        return "Q"
    if "[展锐]" in plan_name or "[UNISOC]" in plan_name:
        return "展锐"
    return "其他"


def utp_fetch_weekly_reports(
    project_code: str,
    owner_codes: str = "18620222",
    platform_keywords: list = None,
) -> Dict:
    """Fetch UTP weekly test reports for a project.

    Returns:
        {
          "platforms": [
            {
              "platform": "MTK",
              "plan": {...},  # plan metadata
              "report": {...},  # report metadata
              "case_count": {...},  # overall case stats
              "jira_count": {...},  # overall defect stats
              "group_tasks": [...]  # business domain rows
            },
            ...
          ],
          "error": "..."
        }
    """
    if platform_keywords is None:
        platform_keywords = ["[MTK]", "[Q]"]

    cred = _get_alm_credentials()
    if not cred:
        return {"platforms": [], "error": "请先配置 ALM/UTP 账号（设置 → ALM）"}

    # Step 1: Query all plans
    all_records = []
    for page in range(1, 6):
        payload = _build_weekly_plan_payload(page, project_code, owner_codes)
        try:
            resp = _utp_post(cred, WEEKLY_PLAN_LIST_PATH, payload)
        except Exception as e:
            return {"platforms": [], "error": f"UTP 查询计划列表失败: {str(e)[:200]}"}
        data = resp.get("data") or {}
        records = data.get("records") or []
        all_records.extend(records)
        pages = int(data.get("pages") or 1)
        print(f"[UTP-WEEKLY] page {page}: {len(records)} records, total_pages={pages}")
        if page >= pages or not records:
            break

    if not all_records:
        return {"platforms": [], "error": f"未找到 UTP 测试计划（项目={project_code}, 创建人={owner_codes}, 请确认项目编码和工号是否正确）"}

    # Step 2: Find latest COMPLETE plan for each platform
    platforms = []
    for keyword in platform_keywords:
        plan = _pick_latest_complete_plan(all_records, keyword)
        if not plan:
            platforms.append({
                "platform": _get_platform_name(keyword),
                "plan": None,
                "error": f"未找到 {keyword} 的 COMPLETE Weekly 计划",
            })
            continue

        plan_id = plan.get("id")
        plan_name = plan.get("testPlanName", "")

        # Step 3: Get plan report (GET with query params, matching the script)
        try:
            report_resp = _utp_get(cred, WEEKLY_REPORT_PATH, params={"planId": plan_id})
        except Exception as e:
            err_msg = str(e)[:200]
            print(f"[UTP-WEEKLY] 获取报告失败: planId={plan_id}, error={err_msg}")
            platforms.append({
                "platform": _get_platform_name(plan_name),
                "plan_id": plan_id,
                "plan_name": plan_name,
                "error": f"获取报告失败: {err_msg}",
            })
            continue

        report_data = report_resp.get("data") or {}
        if not report_data:
            print(f"[UTP-WEEKLY] 报告数据为空: planId={plan_id}")
            platforms.append({
                "platform": _get_platform_name(plan_name),
                "plan_id": plan_id,
                "plan_name": plan_name,
                "error": "报告数据为空",
            })
            continue
        report = report_data.get("report") or {}
        report_id = report.get("id")  # 报告 ID，用于 getJiraNumIssue 接口（注意：report_id ≠ plan_id）
        case_count = report_data.get("caseCount") or {}
        jira_count = report_data.get("jiraCount") or {}
        group_tasks = report_data.get("groupTasks") or []

        # Extract relevant fields from group tasks (matching script's FIELDNAMES)
        tasks = []
        for gt in group_tasks:
            tasks.append({
                "group_name": gt.get("groupName", ""),              # 业务领域
                "group_result": gt.get("taskResult", ""),           # 业务领域结果
                "sub_group_name": gt.get("subGroupName", ""),       # 业务子领域
                "sub_result": gt.get("subTaskResult", ""),          # 子领域结果
                "progress": gt.get("progressRate", ""),             # 测试进度
                "finish_time": gt.get("finishTime", ""),            # 完成时间
                "owner_name": gt.get("strategyOwnerName", ""),      # 业务负责人_策略
                "owner_code": gt.get("strategyOwnerCode", ""),      # 业务负责人工号
                "case_count": gt.get("caseCount", 0),               # 用例数量
                "blocked": gt.get("blockCount", 0),                 # Blocked
                "pass_rate": gt.get("passingRate", ""),             # 通过率
                "na_rate": gt.get("naRate", ""),                    # NA率
                "jira_count": gt.get("jiraCount", 0),               # JIRA数量
                "executor_tl": gt.get("executeOwnerName", ""),      # 执行负责人_TL
                "executor": gt.get("executPerson", ""),             # 实际执行人
                "risk_count": gt.get("riskCount", 0),               # 风险数量
                "jira_ids": ",".join(str(x) for x in (gt.get("jiraIds") or [])),  # JIRA列表
            })

        platforms.append({
            "platform": _get_platform_name(plan_name),
            "plan_id": plan_id,
            "report_id": report_id,  # 报告 ID，用于 getJiraNumIssue（注意：report_id ≠ plan_id）
            "plan_name": plan_name,
            "plan_status": plan.get("planStatus", ""),
            "plan_finish_time": plan.get("finishTime", ""),
            "plan_start_time": plan.get("startTime", ""),
            "plan_end_time": plan.get("endTime", ""),
            "os_version": plan.get("os", ""),
            "test_stage": plan.get("testStage", ""),
            "report_result": report.get("reportResult", ""),
            "report_status": report.get("status", ""),
            "sys_summary": report.get("sysSummary", ""),
            "case_count": {
                "total": case_count.get("allCount", 0),
                "pass": case_count.get("passCount", 0),
                "fail": case_count.get("failCount", 0),
                "blocked": case_count.get("blockedCount", 0),
                "na": case_count.get("naCount", 0),
                "nt": case_count.get("ntCount", 0),
                "rate": case_count.get("rate", ""),
                "risk": case_count.get("riskCount", 0),
            },
            "jira_count": {
                "leave": jira_count.get("leaveCount", 0),
                "leave_ab": jira_count.get("leaveAbCount", 0),
                "di": jira_count.get("leaveDiCount", 0),
                "a": jira_count.get("classA", 0),
                "b": jira_count.get("classB", 0),
                "c": jira_count.get("classC", 0),
                "d": jira_count.get("classD", 0),
            },
            "group_tasks": tasks,
            "error": None,
        })

    return {"platforms": platforms}


def normalize_utp_record(row: Dict) -> Dict:
    """将 UTP 原始记录标准化为前端需要的格式"""
    summary = row.get("summary", "")
    assignee_third_dept = row.get("assigneeThirdDeptName", "")
    affect_project = row.get("affectProject", "")

    classified_dept = classify_department(summary, assignee_third_dept, affect_project)

    created = row.get("createdTime", "")
    aging_days = None
    if created:
        try:
            from dateutil import parser as dateparser
            aging_days = (dateparser.parse(str(created).replace("T", " ").split(".")[0]) - __import__("datetime").datetime.now()).days
            aging_days = abs(aging_days) if aging_days else 0
        except Exception:
            pass

    return {
        "issue_key": row.get("jiraKey", ""),
        "jira_id": row.get("jiraId", ""),
        "jira_url": row.get("jiraUrl", ""),
        "summary": summary,
        "status": row.get("status", ""),
        "priority": row.get("priority", ""),
        "resolution": _clean_jira_markup(row.get("dupIssueStatus", "")),
        "assignee": row.get("assignee", ""),
        "assignee_en_name": row.get("assigneeEnName", ""),
        "assignee_code": row.get("assigneeCode", ""),
        "assignee_third_dept": assignee_third_dept,
        "assignee_third_dept_classified": classified_dept,
        "assignee_second_dept": row.get("assigneeSecondDeptName", ""),
        "opener": row.get("opener", ""),
        "opener_third_dept": row.get("openerThirdDeptName", ""),
        "reporter": row.get("reporter", ""),
        "reporter_third_dept": row.get("reporterThirdDeptName", ""),
        "components": row.get("components", ""),
        "affect_project": affect_project,
        "must_resolve": row.get("mustResolve", ""),
        "issue_category": row.get("issueCategory", ""),
        "issue_nature": row.get("issueNature", ""),
        "risk": row.get("risk", ""),
        "labels": row.get("labels", ""),
        "tpm_owner": row.get("tpmOwner", ""),
        "created_time": str(created),
        "updated_time": str(row.get("updatedTime", "")),
        "resolved_time": str(row.get("resolved", "")),
        "aging_days": aging_days,
    }
