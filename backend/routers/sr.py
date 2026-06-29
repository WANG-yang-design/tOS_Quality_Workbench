import re
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..database import get_conn
from ..utils import now_iso
from ..services.cache_service import (
    save_sr_details_to_cache, load_sr_details_from_cache,
    save_sr_issues_to_cache, load_sr_issues_from_cache
)
from ..services.alm_service import (
    get_alm_config, alm_query_sr_detail, alm_batch_find_users, alm_query_third_dept
)

router = APIRouter()


def _get_sr_backlog_jql(version_id: int, jira_project: str, is_pad: bool = False) -> str:
    """
    获取 SR 遗留问题的 JQL。
    优先从 jira_filter_preset 表读取用户自定义的 sr_backlog filter JQL，
    如果用户没有自定义，则使用 build_sr_jql() 的默认逻辑。
    """
    from ..services.jira_service import build_sr_jql

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT custom_jql, default_jql FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = 'sr_backlog'
    """, (version_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        jql = row["custom_jql"] or row["default_jql"]
        if jql:
            # 替换模板变量
            primary_project = jira_project.split(",")[0].strip() if jira_project else jira_project
            jql = jql.replace("{project}", jira_project).replace("{primary_project}", primary_project)
            return jql

    # 回退：使用默认构建逻辑
    return build_sr_jql(jira_project, is_pad=is_pad)


def _normalize_sr_in_text(text: str) -> str:
    """消除 SR 编号中的空格，如 'SR- 202604-000721' → 'SR-202604-000721'"""
    text = re.sub(r'(SR-\s+)(\d)', r'SR-\2', text)
    text = re.sub(r'(SR-\d{6})\s*-\s*(\d)', r'\1-\2', text)
    return text


def extract_sr_codings_from_issues(issues: list) -> list:
    """从 Jira issue summary 中提取 SR 编号（去重保序）"""
    sr_pattern = re.compile(r"\bSR-\d{6}-\d{6}\b")
    sr_fallback_pattern = re.compile(r"\bSR-\d{6}-\d{4,8}\b")
    seen, result = set(), []
    for issue in issues:
        summary = issue.get("summary", "")
        if not summary:
            continue
        normalized_summary = _normalize_sr_in_text(summary)
        matches = sr_pattern.findall(normalized_summary)
        if not matches:
            matches = sr_fallback_pattern.findall(normalized_summary)
        for m in matches:
            if m not in seen:
                seen.add(m)
                result.append(m)
    return result


def _should_skip_sr_by_space(sr_record: dict, alm_cfg: dict) -> bool:
    """通过 ALM 的 spaceBid 判断 SR 是否属于当前版本"""
    if not sr_record or not alm_cfg:
        return False
    configured_space_bid = (alm_cfg.get("alm_space_bid") or "").strip()
    if not configured_space_bid:
        return False
    sr_space_bid = str(sr_record.get("spaceBid") or "").strip()
    if not sr_space_bid:
        return False
    return sr_space_bid != configured_space_bid

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)

@router.get("/api/versions/{version_id}/sr-detail-cached")
def get_sr_detail_cached(version_id: int):
    """从缓存快速加载 SR 需求详情（与原始后端完全一致）"""
    import json as _json
    details = load_sr_details_from_cache(version_id)
    if not details:
        return {"sr_list": [], "cached": False, "total_sr": 0}
    raw_list = list(details.values()) if isinstance(details, dict) else details

    # 数据库字段名 sr_coding → 前端期望 coding, sr_name → name 等
    sr_list = []
    for r in raw_list:
        issue_keys = r.get("issue_keys", "")
        if isinstance(issue_keys, str):
            try:
                issue_keys = _json.loads(issue_keys)
            except Exception:
                issue_keys = []
        owners = r.get("test_module_owners", "")
        if isinstance(owners, str):
            try:
                owners = _json.loads(owners)
            except Exception:
                owners = []
        # 解析 issue_severity_count
        issue_severity_count = r.get("issue_severity_count", "")
        if isinstance(issue_severity_count, str):
            try:
                issue_severity_count = _json.loads(issue_severity_count)
            except Exception:
                issue_severity_count = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
        elif not isinstance(issue_severity_count, dict):
            issue_severity_count = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
        # 解析 issue_severity_keys
        issue_severity_keys = r.get("issue_severity_keys", "")
        if isinstance(issue_severity_keys, str):
            try:
                issue_severity_keys = _json.loads(issue_severity_keys)
            except Exception:
                issue_severity_keys = {"blocker": [], "critical": [], "major": [], "other": []}
        elif not isinstance(issue_severity_keys, dict):
            issue_severity_keys = {"blocker": [], "critical": [], "major": [], "other": []}

        sr_list.append({
            "coding": r.get("sr_coding", ""),
            "name": r.get("sr_name", ""),
            "status": r.get("sr_status", ""),
            "priority": r.get("sr_priority", ""),
            "planned_acceptance": r.get("planned_acceptance", ""),
            "test_module_owners": owners,
            "test_module_owners_display": r.get("test_module_owners_display", ""),
            "issue_count": r.get("issue_count", 0),
            "issue_keys": issue_keys,
            "issue_severity_count": issue_severity_count,
            "issue_severity_keys": issue_severity_keys,
            "is_other_version": bool(r.get("is_other_version")),
            "other_version_reason": r.get("other_version_reason", ""),
            "bid": r.get("bid", ""),
            "third_dept": r.get("third_dept", ""),
            "synced_at": r.get("synced_at", ""),
        })
    current_srs = [s for s in sr_list if not s.get("is_other_version")]
    other_srs = [s for s in sr_list if s.get("is_other_version")]

    # 汇总当前版本 SR 的严重等级统计
    total_severity = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
    for s in current_srs:
        sc = s.get("issue_severity_count", {})
        for k in total_severity:
            total_severity[k] += sc.get(k, 0)

    return {
        "sr_list": sr_list,
        "cached": True,
        "total_sr": len(sr_list),
        "total_current_version": len(current_srs),
        "total_other_version": len(other_srs),
        "current_version_issue_count": sum(s.get("issue_count", 0) for s in current_srs),
        "other_version_issue_count": sum(s.get("issue_count", 0) for s in other_srs),
        "total_issues": sum(s.get("issue_count", 0) for s in sr_list),
        "current_version_severity_count": total_severity,
        "alm_page_url": "https://alm.transsion.com/#/",
        "synced_at": sr_list[0].get("synced_at") if sr_list else None,
    }

@router.post("/api/versions/{version_id}/sr-detail-refresh")
def refresh_sr_details(version_id: int):
    """刷新 SR 需求详情（从 Jira + ALM 获取并缓存到数据库）"""
    result = _get_sr_details_from_alm(version_id)
    # 保存到缓存
    if result.get("sr_list"):
        save_sr_details_to_cache(version_id, result["sr_list"])
    result["cached"] = True
    return result


def _get_sr_details_from_alm(version_id: int) -> dict:
    """
    1. 从 Jira 获取 SR 遗留问题
    2. 从 summary 中提取 SR 编号
    3. 调用 ALM 查询每个 SR 的详细信息
    4. 合并返回
    与原始后端 main.py 的 get_sr_details 完全一致。
    """
    from ..routers.versions import get_version
    from ..services.jira_service import get_valid_credential
    import requests as req_lib
    from requests.auth import HTTPBasicAuth

    # 检查 ALM 配置
    alm_cfg = get_alm_config()
    if not alm_cfg or not alm_cfg.get("alm_app_id"):
        return {"sr_list": [], "error": "请先配置 ALM 账号（点击顶部设置 ⚙️ 按钮进入 ALM 配置）"}
    if not alm_cfg.get("uac_username") or not alm_cfg.get("uac_password"):
        return {"sr_list": [], "error": "ALM 工号或密码未配置，请在设置中填写正确的员工工号（纯数字，如 18665088）和密码"}
    if not alm_cfg["uac_username"].isdigit():
        return {"sr_list": [], "error": f"ALM 工号格式错误：'{alm_cfg['uac_username']}' 不是有效的工号。请在设置中修改为纯数字工号（如 18665088）"}

    # 获取版本信息
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 获取版本级 ALM space/app bid
    version_space_bid = (version.get("alm_space_bid") or "").strip() or alm_cfg.get("alm_space_bid", "")
    version_app_bid = (version.get("alm_app_bid") or "").strip() or alm_cfg.get("alm_app_bid", "")
    if not version_space_bid or not version_app_bid:
        return {"sr_list": [], "error": "请先为该版本配置 ALM_SPACE_BID 和 ALM_APP_BID（在版本列表中点击该版本的设置按钮）"}

    jira_project = version.get("jira_project", "")
    if not jira_project:
        return {"sr_list": [], "error": "版本未配置 Jira 项目"}

    # Step 1: 从 Jira 获取 SR 遗留问题（优先使用用户自定义 JQL）
    is_pad = bool(version.get("is_pad"))
    jql = _get_sr_backlog_jql(version_id, jira_project, is_pad=is_pad)
    try:
        credential = get_valid_credential(version_id)
    except Exception:
        return {"sr_list": [], "error": "请先配置 Jira 账号"}

    try:
        resp = req_lib.post(
            f"{credential['jira_base_url'].rstrip('/')}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 5000,
                  "fields": ["summary", "status", "priority", "assignee", "labels", "customfield_13004"]},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30, verify=False,
        )
        if resp.status_code == 401:
            return {"sr_list": [], "error": "Jira 认证失败（401）：请在 ⚙️ 设置 → Jira 中重新输入密码"}
        if resp.status_code == 403:
            return {"sr_list": [], "error": f"Jira 权限不足（403）"}
        if resp.status_code >= 400:
            return {"sr_list": [], "error": f"Jira 查询失败（HTTP {resp.status_code}）：{resp.text[:120]}"}
        jira_data = resp.json()
        jira_issues = jira_data.get("issues", [])
    except Exception as e:
        return {"sr_list": [], "error": f"Jira 查询失败: {str(e)[:80]}"}

    if not jira_issues:
        return {"sr_list": [], "message": "暂无 SR 遗留问题"}

    # Step 2: 提取 SR 编号
    from ..utils import stringify_field_value
    summaries = []
    for issue in jira_issues:
        fields = issue.get("fields", {})
        # 直接使用 priority 字段作为严重等级（这是 Jira 标准字段，一定存在）
        priority = (fields.get("priority") or {}).get("name") or ""
        summaries.append({
            "issue_key": issue.get("key", ""),
            "summary": fields.get("summary") or "",
            "status": (fields.get("status") or {}).get("name") or "",
            "priority": priority,
            "assignee": (fields.get("assignee") or {}).get("displayName") or "",
            "labels": fields.get("labels") or [],
            "severity": priority,  # 直接使用 priority
        })

    sr_codings = extract_sr_codings_from_issues(summaries)
    print(f"[SR-DETAIL] 从 {len(jira_issues)} 个 issue 中提取到 {len(sr_codings)} 个 SR 编号")

    if not sr_codings:
        return {"sr_list": [], "message": "未从 issue summary 中提取到 SR 编号"}

    # Step 3: 查询 ALM
    sr_details = []
    all_job_numbers = set()

    for coding in sr_codings:
        try:
            record = alm_query_sr_detail(alm_cfg, coding, space_bid=version_space_bid, app_bid=version_app_bid)
        except Exception as e:
            print(f"[SR-DETAIL] ALM 查询失败: {coding}, error={e}")
            record = None

        if record:
            is_other_version = _should_skip_sr_by_space(record, {"alm_space_bid": version_space_bid})
            if is_other_version:
                sr_space = str(record.get("spaceBid") or "")
                sr_details.append({
                    "coding": coding,
                    "name": str(record.get("name") or ""),
                    "status": str(record.get("lifeCycleCode") or ""),
                    "priority": str(record.get("priority") or ""),
                    "planned_acceptance": "",
                    "test_module_owners": [],
                    "test_module_owners_display": "",
                    "third_dept": "",
                    "bid": "",
                    "is_other_version": True,
                    "other_version_reason": f"ALM spaceBid 不匹配（SR空间={sr_space}）",
                })
                continue

            raw_owners = record.get("testModuleResponsiblePerson") or []
            owner_list = []
            for o in raw_owners:
                o_str = str(o).strip()
                if o_str and o_str.isdigit():
                    owner_list.append(o_str)
                    all_job_numbers.add(o_str)
            sr_details.append({
                "coding": coding,
                "name": str(record.get("name") or ""),
                "status": str(record.get("lifeCycleCode") or ""),
                "priority": str(record.get("priority") or ""),
                "planned_acceptance": str(record.get("plannedAcceptanceStartTime") or ""),
                "test_module_owners": owner_list,
                "test_module_owners_display": "",
                "third_dept": "",
                "bid": str(record.get("bid") or record.get("dataBid") or ""),
                "is_other_version": False,
            })

    # Step 4: 批量查询用户姓名 + 三级部门
    if all_job_numbers:
        user_map = alm_batch_find_users(alm_cfg, list(all_job_numbers))
        for sr in sr_details:
            owners = sr.get("test_module_owners", [])
            display_parts = []
            for no in owners:
                if no in user_map:
                    name = str(user_map[no].get("name") or "")
                    display_parts.append(f"{name}({no})" if name else no)
                else:
                    display_parts.append(no)
            sr["test_module_owners_display"] = ", ".join(display_parts) if display_parts else ""
        dept_map = {}
        for no in list(all_job_numbers)[:30]:
            if no not in dept_map:
                try:
                    dept = alm_query_third_dept(alm_cfg, no)
                    if dept:
                        dept_map[no] = str(dept.get("thirdDeptName") or dept.get("secondDeptName") or "")
                except Exception:
                    pass
        for sr in sr_details:
            for no in sr.get("test_module_owners", []):
                if no in dept_map and dept_map[no]:
                    sr["third_dept"] = dept_map[no]
                    break

    # Step 5: 统计每个 SR 对应的 issue 数量（含严重等级分类）
    sr_count_pattern = re.compile(r"\bSR-\d{6}-\d{4,8}\b")
    sr_issue_map = {}  # {sr_coding: [{"issue_key": ..., "severity": ...}, ...]}
    for issue in summaries:
        normalized = _normalize_sr_in_text(issue["summary"])
        severity = issue.get("severity", "")
        for m in sr_count_pattern.findall(normalized):
            sr_issue_map.setdefault(m, []).append({
                "issue_key": issue["issue_key"],
                "severity": severity
            })

    for sr in sr_details:
        issues = sr_issue_map.get(sr["coding"], [])
        sr["issue_count"] = len(issues)
        sr["issue_keys"] = [i["issue_key"] for i in issues]
        # 统计严重等级分布，并记录每个等级对应的 issue_keys
        # 支持英文和中文值
        severity_count = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
        severity_keys = {"blocker": [], "critical": [], "major": [], "other": []}
        for i in issues:
            sev = (i["severity"] or "").lower()
            # 英文值
            if "blocker" in sev or sev == "p0":
                severity_count["blocker"] += 1
                severity_keys["blocker"].append(i["issue_key"])
            elif "critical" in sev or sev in ["p1", "highest", "high"]:
                severity_count["critical"] += 1
                severity_keys["critical"].append(i["issue_key"])
            elif "major" in sev or sev in ["p2", "medium"]:
                severity_count["major"] += 1
                severity_keys["major"].append(i["issue_key"])
            # 中文值
            elif sev in ["致命", "严重", "阻塞"]:
                severity_count["blocker"] += 1
                severity_keys["blocker"].append(i["issue_key"])
            elif sev in ["高", "较严重"]:
                severity_count["critical"] += 1
                severity_keys["critical"].append(i["issue_key"])
            elif sev in ["中", "主要", "一般"]:
                severity_count["major"] += 1
                severity_keys["major"].append(i["issue_key"])
            else:
                severity_count["other"] += 1
                severity_keys["other"].append(i["issue_key"])
        sr["issue_severity_count"] = severity_count
        sr["issue_severity_keys"] = severity_keys

    current_srs = [s for s in sr_details if not s["is_other_version"]]
    other_srs = [s for s in sr_details if s["is_other_version"]]

    # 汇总所有 SR 的严重等级统计
    total_severity = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
    for s in current_srs:
        sc = s.get("issue_severity_count", {})
        for k in total_severity:
            total_severity[k] += sc.get(k, 0)

    return {
        "sr_list": sr_details,
        "total_sr": len(sr_details),
        "total_current_version": len(current_srs),
        "total_other_version": len(other_srs),
        "current_version_issue_count": sum(s["issue_count"] for s in current_srs),
        "other_version_issue_count": sum(s["issue_count"] for s in other_srs),
        "total_issues": sum(s["issue_count"] for s in sr_details),
        "current_version_severity_count": total_severity,
        "alm_page_url": "https://alm.transsion.com/#/",
    }

@router.get("/api/versions/{version_id}/sr-details")
def get_sr_details(version_id: int):
    """获取SR需求详情"""
    details = load_sr_details_from_cache(version_id)
    if not details:
        return {"sr_list": [], "cached": False, "total_sr": 0}
    sr_list = list(details.values()) if isinstance(details, dict) else details
    return {"sr_list": sr_list, "cached": True, "total_sr": len(sr_list)}

@router.get("/api/versions/{version_id}/sr-issues-cached")
def get_sr_issues_cached(version_id: int):
    """获取缓存的SR遗留问题"""
    issues = load_sr_issues_from_cache(version_id)
    if not issues:
        return {"total": 0, "issues": [], "cached": False, "message": "暂无缓存，请点击刷新"}
    return {"total": len(issues), "issues": issues, "cached": True, "synced_at": issues[0].get("synced_at") if issues else None}

def _fetch_sr_issues_from_jira(version_id: int):
    """从 Jira 查询 SR 遗留问题（与原始后端 get_sr_issues 完全一致）"""
    from ..routers.versions import get_version
    from ..services.jira_service import get_valid_credential
    from ..utils import parse_dt
    from datetime import datetime
    from dateutil import parser as dateparser
    import requests as req_lib
    from requests.auth import HTTPBasicAuth
    from urllib.parse import quote

    default_jira_url = "http://jira.transsion.com"
    version = get_version(version_id)
    jira_project = version.get("jira_project", "")
    is_pad = bool(version.get("is_pad"))
    jql = _get_sr_backlog_jql(version_id, jira_project, is_pad=is_pad)
    jira_url = f"{default_jira_url}/issues/?jql={quote(jql)}"

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    base_url = credential["jira_base_url"].rstrip("/")
    sr_fields = ["summary", "status", "priority", "assignee", "reporter", "created", "updated", "labels"]

    try:
        resp = req_lib.post(
            f"{base_url}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 5000, "fields": sr_fields},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30, verify=False,
        )
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 查询失败: {str(e)[:80]}"}

    if resp.status_code == 401:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 认证失败（401）：请在 ⚙️ 设置 → Jira 中重新输入密码"}
    if resp.status_code == 403:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 权限不足（403）"}
    if resp.status_code >= 400:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira HTTP {resp.status_code}: {resp.text[:120]}"}

    try:
        data = resp.json()
    except Exception:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON"}

    raw_issues = data.get("issues", [])
    total = data.get("total", 0)

    sr_issues = []
    for issue in raw_issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        created_time = parse_dt(fields.get("created"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - datetime.fromisoformat(created_time)).days
            except Exception:
                pass
        summary = fields.get("summary") or ""
        # 基于 summary 的部门归类（Jira 无三级部门信息，仅能按 summary 规则归类）
        dept_classified = ""
        summary_lower = summary.lower()
        if "oversea" in summary_lower:
            dept_classified = "海外测试"
        elif any(kw in summary for kw in ["易景团队", "天珑团队", "萨瑞团队"]):
            dept_classified = "DT_外研测试部"

        sr_issues.append({
            "issue_key": issue.get("key", ""),
            "summary": summary,
            "status": (fields.get("status") or {}).get("name") or "未知",
            "priority": (fields.get("priority") or {}).get("name") or "未设置",
            "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
            "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
            "created_time": created_time,
            "aging_days": aging_days,
            "labels": fields.get("labels") or [],
            "dept_classified": dept_classified,
        })

    sr_issues.sort(key=lambda x: ({"Blocker": 0, "Critical": 1, "Major": 2}.get(x.get("priority", ""), 99), -(x.get("aging_days") or 0)))

    return {"total": total, "issues": sr_issues, "jql": jql, "jira_url": jira_url}


@router.get("/api/versions/{version_id}/sr-issues")
def get_sr_issues(version_id: int):
    """获取SR遗留问题（直接查询Jira，与原始后端一致）"""
    result = _fetch_sr_issues_from_jira(version_id)
    return result


@router.post("/api/versions/{version_id}/sr-issues-refresh")
def refresh_sr_issues(version_id: int, force: bool = Query(False)):
    """刷新SR遗留问题（从Jira获取并缓存）。

    默认使用缓存：如果 30 分钟内已刷新过，直接返回缓存数据。
    传 force=true 可强制从 Jira 刷新。
    """
    import json as _json
    from datetime import datetime, timedelta

    # 检查缓存是否新鲜（30 分钟内）
    if not force:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT synced_at FROM sr_issue_cache WHERE version_id = ? ORDER BY synced_at DESC LIMIT 1", (version_id,))
            row = cur.fetchone()
            conn.close()
            if row and row["synced_at"]:
                clean_ts = row["synced_at"].replace("Z", "").replace("T", " ").split("+")[0].split(".")[0]
                cached_time = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S") if len(clean_ts) >= 19 else datetime.fromisoformat(clean_ts)
                if datetime.now() - cached_time < timedelta(minutes=30):
                    from ..services.cache_service import load_sr_issues_from_cache
                    issues = load_sr_issues_from_cache(version_id)
                    if issues:
                        print(f"[SR-CACHE-HIT] version_id={version_id}, {len(issues)} issues")
                        return {"total": len(issues), "issues": issues, "cached": True, "synced_at": row["synced_at"], "from_cache": True}
        except Exception as e:
            print(f"[SR-CACHE-ERROR] {e}")

    result = _fetch_sr_issues_from_jira(version_id)

    # 保存到缓存（labels 需要转为 string）
    if result.get("issues"):
        cache_issues = []
        for issue in result["issues"]:
            cached = dict(issue)
            if isinstance(cached.get("labels"), list):
                cached["labels"] = ",".join(cached["labels"])
            cache_issues.append(cached)
        save_sr_issues_to_cache(version_id, cache_issues)
        result["cached"] = True
        result["synced_at"] = now_iso()

    return result

@router.get("/api/versions/{version_id}/sr-ai-analysis")
def get_sr_ai_analysis(version_id: int):
    """获取SR AI分析结果"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_ai_analysis WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"analyses": {r["sr_coding"]: {"analysis": r["analysis"], "analyzed_at": r["analyzed_at"]} for r in rows}}

@router.delete("/api/versions/{version_id}/sr-ai-analysis")
def delete_sr_ai_analysis(version_id: int, sr_coding: List[str] = Query(..., alias="sr_coding")):
    """删除SR AI分析结果"""
    conn = get_conn()
    cur = conn.cursor()
    
    for coding in sr_coding:
        cur.execute("DELETE FROM sr_ai_analysis WHERE version_id = ? AND sr_coding = ?", (version_id, coding))
    
    conn.commit()
    conn.close()
    
    return {"message": f"已删除 {len(sr_coding)} 条分析结果"}

@router.post("/api/versions/{version_id}/sr-ai-analysis")
def run_sr_ai_analysis(version_id: int, sr_coding: List[str] = Query(..., alias="sr_coding")):
    """运行SR AI分析"""
    from ..services.ai_service import call_ai
    from ..utils import now_iso

    conn = get_conn()
    cur = conn.cursor()

    results = {}
    for coding in sr_coding:
        # 获取SR详情
        cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? AND sr_coding = ?", (version_id, coding))
        sr_detail = cur.fetchone()

        if not sr_detail:
            continue

        sr_dict = dict(sr_detail)

        # 获取SR相关问题
        cur.execute("SELECT * FROM sr_issue_cache WHERE version_id = ? AND issue_key LIKE ?", (version_id, f"%{coding}%"))
        sr_issues = [dict(r) for r in cur.fetchall()]

        # 构建分析上下文
        context = f"SR编码: {coding}\nSR名称: {sr_dict.get('sr_name', '')}\nSR状态: {sr_dict.get('sr_status', '')}\n"
        context += f"计划验收时间: {sr_dict.get('planned_acceptance', '')}\n"
        context += f"关联问题数: {len(sr_issues)}\n"

        if sr_issues:
            context += "\n关联问题:\n"
            for issue in sr_issues[:5]:  # 只显示前5个
                context += f"- {issue.get('issue_key', '')}: {issue.get('summary', '')} [{issue.get('status', '')}]\n"

        # 调用AI分析
        system_prompt = "你是软件测试质量分析专家。针对以下SR需求，给出简短的风险分析和测试建议。"
        user_prompt = f"请分析以下SR需求的风险和测试建议：\n{context}"

        try:
            analysis = call_ai(system_prompt, user_prompt)
            analyzed_at = now_iso()

            # 保存分析结果
            cur.execute("""
            INSERT OR REPLACE INTO sr_ai_analysis (version_id, sr_coding, analysis, analyzed_at)
            VALUES (?, ?, ?, ?)
            """, (version_id, coding, analysis, analyzed_at))

            results[coding] = {"analysis": analysis, "analyzed_at": analyzed_at}
        except Exception as e:
            results[coding] = {"error": str(e)}

    conn.commit()
    conn.close()

    return {"results": results, "total": len(results)}

@router.get("/api/versions/{version_id}/sr-ai-priority")
def get_sr_ai_priority(version_id: int):
    """获取SR AI风险等级分析结果"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ?", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    results = {}
    for row in rows:
        results[row["sr_coding"]] = {
            "risk_level": row.get("risk_level", ""),
            "analysis": row.get("analysis", ""),
            "issue_count": row.get("issue_count", 0),
            "analyzed_at": row.get("analyzed_at", ""),
        }
    
    return {"results": results, "total": len(results)}

def _compute_issue_keys_hash(issue_keys: list) -> str:
    """计算 issue_keys 列表的哈希值，用于判断是否需要重新分析"""
    import hashlib
    text = ",".join(sorted(issue_keys))
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _build_sr_priority_context(sr_list: list, all_issues: list) -> str:
    """为 AI 构建所有 SR + 关联 issue 的完整上下文（与原始后端 main.py 完全一致）"""
    from dateutil import parser as dateparser
    from datetime import datetime

    issue_map = {}
    for issue in all_issues:
        issue_map[issue.get("issue_key", "")] = issue

    lines = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"当前日期：{today_str}")
    lines.append("")
    lines.append("DI值说明：DI(Defect Index) = A类×10 + B类×3 + C类×1 + 其他×0.1")
    lines.append("其中 A类=Blocker, B类=Critical, C类=Major")
    lines.append("DI值>=30为高风险，10-30为中风险，<10为低风险")
    lines.append("")

    for sr in sr_list:
        coding = sr.get("coding", "")
        name = sr.get("name", "")
        status = sr.get("status", "")
        priority = sr.get("priority", "")
        planned = sr.get("planned_acceptance", "")
        issue_count = sr.get("issue_count", 0)
        owners = sr.get("test_module_owners_display", "")
        issue_keys = sr.get("issue_keys", [])
        sev_count = sr.get("issue_severity_count", {})
        di_score = sr.get("di_score", 0)

        days_info = ""
        if planned:
            try:
                planned_dt = dateparser.parse(planned[:10])
                days_diff = (planned_dt - datetime.now()).days
                if days_diff < 0:
                    days_info = f"（已逾期 {abs(days_diff)} 天）"
                elif days_diff <= 7:
                    days_info = f"（{days_diff} 天后到期）"
                else:
                    days_info = f"（还有 {days_diff} 天）"
            except Exception:
                pass

        lines.append(f"## {coding}")
        lines.append(f"- 需求名称：{name}")
        lines.append(f"- 状态：{status} | 优先级：{priority}")
        lines.append(f"- 计划验收：{planned or '未设置'} {days_info}")
        lines.append(f"- 测试主责人：{owners or '未设置'}")
        lines.append(f"- 关联 Issue 数：{issue_count}")
        lines.append(f"- 问题等级分布：A类(Blocker)={sev_count.get('blocker',0)}个, B类(Critical)={sev_count.get('critical',0)}个, C类(Major)={sev_count.get('major',0)}个")
        lines.append(f"- DI风险值：{di_score:.1f}（{'高风险' if di_score >= 30 else '中风险' if di_score >= 10 else '低风险'}）")

        if issue_keys:
            lines.append(f"- 关联 Issue 列表：")
            for ik in issue_keys:
                issue_data = issue_map.get(ik)
                if issue_data:
                    aging = issue_data.get("aging_days") or "?"
                    lines.append(f"  - {ik}: 状态={issue_data.get('status','')}, 优先级={issue_data.get('priority','')}, "
                                 f"负责人={issue_data.get('assignee','')}, 遗留={aging}天, "
                                 f"描述={issue_data.get('summary','')[:80]}")
                else:
                    lines.append(f"  - {ik}: (详细信息未知)")
        lines.append("")

    return "\n".join(lines)


@router.get("/api/versions/{version_id}/sr-ai-priority")
def get_sr_ai_priority(version_id: int):
    """获取 SR AI 风险等级分析结果（从缓存，按风险等级排序）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ? ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, issue_count DESC", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    results = {}
    for r in rows:
        results[r["sr_coding"]] = {
            "risk_level": r["risk_level"],
            "analysis": r["analysis"],
            "issue_count": r["issue_count"],
            "analyzed_at": r["analyzed_at"],
        }
    return {"results": results, "total": len(results)}


@router.post("/api/versions/{version_id}/sr-ai-priority")
def run_sr_ai_priority(version_id: int, force: bool = Query(False)):
    """
    AI 综合分析所有当前版本 SR 的风险等级（与原始后端 main.py 完全一致）。
    批量分析：所有 SR 打包成一次 AI 调用，用 issue_keys_hash 判断哪些需要重新分析。
    """
    from ..services.ai_service import call_ai
    from ..routers.versions import get_version
    from ..routers.jira import load_issues
    import json as _json

    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    conn = get_conn()
    cur = conn.cursor()

    # 1. 从缓存读取 SR 列表（仅当前版本）
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? AND is_other_version = 0 ORDER BY issue_count DESC", (version_id,))
    sr_rows = [dict(r) for r in cur.fetchall()]

    if not sr_rows:
        conn.close()
        return {"results": {}, "total": 0, "message": "请先查询 SR 需求详情（ALM）"}

    sr_list = []
    for r in sr_rows:
        issue_keys = []
        issue_severity_count = {"blocker": 0, "critical": 0, "major": 0, "other": 0}
        try:
            issue_keys = _json.loads(r.get("issue_keys") or "[]")
        except Exception:
            pass
        try:
            issue_severity_count = _json.loads(r.get("issue_severity_count") or '{"blocker":0,"critical":0,"major":0,"other":0}')
        except Exception:
            pass
        # 计算DI值
        di_score = (
            issue_severity_count.get("blocker", 0) * 10 +
            issue_severity_count.get("critical", 0) * 3 +
            issue_severity_count.get("major", 0) * 1 +
            issue_severity_count.get("other", 0) * 0.1
        )
        sr_list.append({
            "coding": r["sr_coding"],
            "name": r["sr_name"],
            "status": r["sr_status"],
            "priority": r["sr_priority"],
            "planned_acceptance": r["planned_acceptance"],
            "test_module_owners_display": r["test_module_owners_display"],
            "issue_count": r["issue_count"],
            "issue_keys": issue_keys,
            "issue_severity_count": issue_severity_count,
            "di_score": di_score,
        })

    # 2. 如果是强制重新分析，先清除之前的分析结果
    if force:
        cur.execute("DELETE FROM sr_ai_priority WHERE version_id = ?", (version_id,))
        conn.commit()
        existing = {}
    else:
        # 读取已有分析结果
        cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ?", (version_id,))
        existing = {r["sr_coding"]: dict(r) for r in cur.fetchall()}

    # 3. 判断哪些 SR 需要重新分析
    needs_analysis = []
    preserved = {}
    for sr in sr_list:
        coding = sr["coding"]
        new_hash = _compute_issue_keys_hash(sr["issue_keys"])
        old = existing.get(coding)

        if not force and old and old.get("issue_keys_hash") == new_hash and old.get("risk_level"):
            preserved[coding] = {
                "risk_level": old["risk_level"],
                "analysis": old["analysis"],
                "issue_count": old["issue_count"],
                "analyzed_at": old["analyzed_at"],
            }
        else:
            needs_analysis.append(sr)

    if not needs_analysis and not force:
        conn.close()
        all_results = {**preserved}
        sorted_results = dict(sorted(all_results.items(), key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x[1]["risk_level"], 3), -(x[1]["issue_count"] or 0))))
        return {"results": sorted_results, "total": len(sorted_results), "changed": 0}

    # 4. 加载关联 issue 详情
    all_issues = load_issues(version_id, "ALL")

    # 5. 构建 AI prompt（所有 SR 打包成一次调用）
    context = _build_sr_priority_context(needs_analysis, all_issues)
    sr_codings = [s["coding"] for s in needs_analysis]

    system_prompt = (
        "你是软件测试质量风险分析专家。请综合分析以下 SR 需求的风险等级。\n\n"
        "分析维度：\n"
        "1. 关联 Issue 数量和状态（未关闭越多风险越高）\n"
        "2. Issue 优先级分布（Blocker/Critical 越多风险越高）\n"
        "3. Issue 遗留天数（越久风险越高）\n"
        "4. 计划验收时间紧迫度（越临近或已逾期风险越高）\n"
        "5. SR 本身的状态和优先级\n\n"
        "请严格按以下 JSON 格式输出，不要输出其他内容：\n"
        "```json\n"
        '[\n'
        '  {"coding": "SR-XXXXXX-XXXXXX", "risk_level": "high", "analysis": "3-4句分析"},\n'
        '  {"coding": "SR-YYYYYY-YYYYYY", "risk_level": "medium", "analysis": "2-3句分析"},\n'
        '  {"coding": "SR-ZZZZZZ-ZZZZZZ", "risk_level": "low", "analysis": "1句简述"}\n'
        "]\n"
        "```\n\n"
        "risk_level 只能是 high/medium/low 三个值。\n"
        "每个 SR 都必须输出，不可遗漏。\n"
        "analysis 字段给出简洁的风险分析和测试建议。"
    )

    user_prompt = (
        f"当前版本：{version['version_name']}\n"
        f"需要分析的 SR 数量：{len(needs_analysis)}\n\n"
        f"{context}"
    )

    # 6. 调用 AI（一次调用分析所有 SR）
    print(f"[SR-PRIORITY] 开始 AI 分析 {len(needs_analysis)} 个 SR")
    result_text = call_ai(system_prompt, user_prompt)
    print(f"[SR-PRIORITY] AI 返回 {len(result_text)} 字符")

    # 7. 解析 JSON 结果（兼容 markdown 包裹和纯文本）
    parsed_results = []
    try:
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            parsed_results = _json.loads(json_match.group())
    except Exception as e:
        print(f"[SR-PRIORITY] JSON 解析失败: {e}")
        # 兜底：逐行提取
        for sr in needs_analysis:
            coding = sr["coding"]
            idx = result_text.find(coding)
            if idx >= 0:
                snippet = result_text[idx:idx + 300]
                level = "medium"
                if "high" in snippet.lower():
                    level = "high"
                elif "low" in snippet.lower():
                    level = "low"
                parsed_results.append({"coding": coding, "risk_level": level, "analysis": snippet[:200]})

    # 8. 写入数据库
    analyzed_at = now_iso()
    new_results = {}
    for item in parsed_results:
        coding = item.get("coding", "")
        if not coding:
            continue
        risk_level = item.get("risk_level", "medium")
        if risk_level not in ("high", "medium", "low"):
            risk_level = "medium"
        analysis = item.get("analysis", "")
        issue_count = next((s["issue_count"] for s in sr_list if s["coding"] == coding), 0)
        issue_keys = next((s["issue_keys"] for s in sr_list if s["coding"] == coding), [])
        issue_hash = _compute_issue_keys_hash(issue_keys)

        cur.execute("""
            INSERT INTO sr_ai_priority (version_id, sr_coding, risk_level, analysis, issue_count, issue_keys_hash, issue_keys, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET
                risk_level = excluded.risk_level,
                analysis = excluded.analysis,
                issue_count = excluded.issue_count,
                issue_keys_hash = excluded.issue_keys_hash,
                issue_keys = excluded.issue_keys,
                analyzed_at = excluded.analyzed_at
        """, (version_id, coding, risk_level, analysis, issue_count, issue_hash, _json.dumps(issue_keys, ensure_ascii=False), analyzed_at))

        new_results[coding] = {
            "risk_level": risk_level,
            "analysis": analysis,
            "issue_count": issue_count,
            "analyzed_at": analyzed_at,
        }

    # 同时更新 sr_ai_analysis 表
    for coding, data in new_results.items():
        cur.execute("""
            INSERT INTO sr_ai_analysis (version_id, sr_coding, analysis, analyzed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET
                analysis = excluded.analysis,
                analyzed_at = excluded.analyzed_at
        """, (version_id, coding, data["analysis"], analyzed_at))

    conn.commit()
    conn.close()

    # 合并保留的和新分析的结果
    all_results = {**preserved, **new_results}
    sorted_results = dict(sorted(all_results.items(), key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x[1]["risk_level"], 3), -(x[1].get("issue_count") or 0))))

    print(f"[SR-PRIORITY] 完成：新分析 {len(new_results)} 个，保留 {len(preserved)} 个")
    return {"results": sorted_results, "total": len(sorted_results), "changed": len(new_results)}

@router.get("/api/versions/{version_id}/sr-daily-risk-report")
def get_sr_daily_risk_report(version_id: int, include_ai: bool = Query(True)):
    """生成每日 SR 风险总结报告"""
    import re
    import json
    from datetime import datetime
    from pathlib import Path
    from ..config import CLOSED_STATUS, HIGH_PRIORITY
    from ..services.ai_service import call_ai

    OUTPUT_DIR = Path.home() / ".tos_quality_workbench" / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 收集数据
    data = collect_sr_risk_data(version_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])

    version_name = data.get("version_name", "unknown")
    report_date = datetime.now().strftime("%Y%m%d")
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 生成报告文本
    report_text = generate_sr_risk_report_text(data)

    # AI 整体分析
    ai_analysis = ""
    if include_ai:
        try:
            from ..services.ai_service import get_ai_config_decrypted
            cfg = get_ai_config_decrypted()
            if cfg and cfg.get("api_key"):
                summary = data.get("summary", {})

                # 构建完整的 AI 上下文：包含所有重要数据
                ai_context = {
                    "version": version_name,
                    "stage": data.get("stage_name", ""),
                    "report_time": data.get("report_time", ""),
                    "summary": summary,
                    "high_risk_sr_list": [
                        {"coding": s.get("coding"), "name": s.get("name", "")[:50],
                         "status": s.get("status"), "issue_count": s.get("issue_count"),
                         "ai_analysis": s.get("ai_analysis", "")[:80]}
                        for s in data.get("high_risk_sr", [])
                    ],
                    "medium_risk_sr_list": [
                        {"coding": s.get("coding"), "name": s.get("name", "")[:50],
                         "status": s.get("status"), "issue_count": s.get("issue_count"),
                         "ai_analysis": s.get("ai_analysis", "")[:80]}
                        for s in data.get("medium_risk_sr", [])
                    ],
                    "blocker_issues": [
                        {"key": i.get("issue_key"), "summary": i.get("summary", "")[:60],
                         "assignee": i.get("assignee"), "aging_days": i.get("aging_days")}
                        for i in data.get("sr_blocker_issues", [])
                    ],
                    "critical_issues": [
                        {"key": i.get("issue_key"), "summary": i.get("summary", "")[:60],
                         "assignee": i.get("assignee"), "aging_days": i.get("aging_days")}
                        for i in data.get("sr_critical_issues", [])[:15]
                    ],
                    "over_30_days_issues": [
                        {"key": i.get("issue_key"), "summary": i.get("summary", "")[:60],
                         "priority": i.get("priority"), "assignee": i.get("assignee"),
                         "aging_days": i.get("aging_days")}
                        for i in data.get("sr_over_30_days", [])[:15]
                    ],
                    "top_owners": data.get("top_owners", [])[:10],
                }

                system_prompt = """你是软件测试质量分析专家。根据提供的 SR 需求风险完整数据，输出一份详尽的 AI 分析报告。
要求：
1. 用中文回答
2. 重点关注：高风险 SR 的具体影响面和关联 Issue 情况、Blocker/Critical 问题的紧急程度及处理建议、超龄问题的根因分析、负责人的工作负载
3. 给出 5-8 条具体可执行的行动建议，每条需说明理由和涉及的具体 SR/Issue
4. 给出整体风险评级（高/中/低）和判断依据
5. 识别出需要立即介入的 Top 3 紧急事项
6. 控制在 800 字以内"""

                user_prompt = (
                    f"以下是 {version_name} 版本 {data.get('stage_name', '')} 阶段的完整 SR 风险数据：\n"
                    f"```json\n{json.dumps(ai_context, ensure_ascii=False, indent=2)}\n```\n\n"
                    "请基于以上完整数据生成 SR 风险 AI 分析报告。注意：数据包含了高/中风险 SR 详情、"
                    "Blocker/Critical 遗留问题、超龄问题和负责人 Top 10，请综合分析。"
                )

                ai_analysis = call_ai(system_prompt, user_prompt)
        except Exception as e:
            ai_analysis = f"（AI 分析生成失败：{str(e)[:100]}）"

    # 拼接完整报告
    full_report = report_text
    if ai_analysis:
        full_report += f"\n\n## 八、AI 整体风险分析\n\n{ai_analysis}\n"

    # 保存到文件
    safe_version = re.sub(r'[^\w\-.]', '_', version_name)
    filename = f"sr_daily_risk_report_{safe_version}_{report_date}.md"
    json_filename = f"sr_daily_risk_report_{safe_version}_{report_date}.json"
    filepath = OUTPUT_DIR / filename
    json_filepath = OUTPUT_DIR / json_filename
    filepath.write_text(full_report, encoding="utf-8")

    # 保存结构化 JSON
    json_payload = {
        "report": full_report,
        "ai_analysis": ai_analysis,
        "data": data,
        "saved_to": str(filepath),
        "filename": filename,
        "generated_at": report_time,
    }
    json_filepath.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return json_payload


@router.get("/api/versions/{version_id}/sr-daily-risk-report/today")
def get_sr_daily_risk_report_today(version_id: int):
    """加载最近生成的 SR 风险总结报告（从 JSON 缓存读取，优先返回今天的）。"""
    import re
    import json
    from datetime import datetime
    from pathlib import Path

    OUTPUT_DIR = Path.home() / ".tos_quality_workbench" / "output"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")

    version_name = row["version_name"]
    safe_version = re.sub(r'[^\w\-.]', '_', version_name)
    report_date = datetime.now().strftime("%Y%m%d")
    json_filename = f"sr_daily_risk_report_{safe_version}_{report_date}.json"
    json_filepath = OUTPUT_DIR / json_filename

    # 优先查找今天的报告
    if json_filepath.exists():
        try:
            payload = json.loads(json_filepath.read_text(encoding="utf-8"))
            payload["from_cache"] = True
            return payload
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"读取报告缓存失败: {str(e)[:80]}")

    # 今天没有 → 查找该版本最新的报告文件（最近 7 天内）
    pattern = f"sr_daily_risk_report_{safe_version}_*.json"
    candidates = sorted(OUTPUT_DIR.glob(pattern), reverse=True)
    for f in candidates:
        # 提取日期部分
        try:
            date_part = f.stem.split("_")[-1]
            if len(date_part) == 8 and date_part.isdigit():
                file_date = datetime.strptime(date_part, "%Y%m%d")
                if (datetime.now() - file_date).days <= 7:
                    payload = json.loads(f.read_text(encoding="utf-8"))
                    payload["from_cache"] = True
                    payload["stale"] = True  # 标记为非当天
                    return payload
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="尚未生成报告")


def collect_sr_risk_data(version_id: int) -> dict:
    """收集指定版本的 SR 风险相关数据"""
    from ..config import CLOSED_STATUS, HIGH_PRIORITY
    from datetime import datetime

    conn = get_conn()
    cur = conn.cursor()

    # 1. 版本信息
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    if not version:
        conn.close()
        return {"error": "版本不存在"}

    version_name = version.get("version_name", "")

    # 2. 当前阶段
    cur.execute("SELECT * FROM str_stage_config WHERE version_id = ? AND current_flag = 1", (version_id,))
    stage = row_to_dict(cur.fetchone())
    stage_name = stage.get("stage_name", "未设置") if stage else "未设置"

    # 3. SR 需求详情
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? AND is_other_version = 0 ORDER BY issue_count DESC", (version_id,))
    sr_details = [row_to_dict(r) for r in cur.fetchall()]

    # 4. SR 遗留问题
    cur.execute("SELECT * FROM sr_issue_cache WHERE version_id = ? ORDER BY aging_days DESC", (version_id,))
    sr_issues = [row_to_dict(r) for r in cur.fetchall()]

    # 5. SR AI 风险等级分析
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ?", (version_id,))
    sr_ai_results = {}
    for r in cur.fetchall():
        rd = dict(r)
        sr_ai_results[rd["sr_coding"]] = {
            "risk_level": rd.get("risk_level", ""),
            "analysis": rd.get("analysis", ""),
            "issue_count": rd.get("issue_count", 0),
        }

    # 6. Jira Issue 缓存
    cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    all_issues = [row_to_dict(r) for r in cur.fetchall()]

    conn.close()

    # 统计汇总
    total_issues = len(all_issues)
    unresolved = [i for i in all_issues if i.get("status") not in CLOSED_STATUS]
    high_priority = [i for i in unresolved if i.get("priority") in HIGH_PRIORITY]
    must_fix = [i for i in unresolved if i.get("must_fix_flag")]

    # SR 维度统计
    total_sr = len(sr_details)
    high_risk_sr = [s for s in sr_details if sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level") == "high"]
    medium_risk_sr = [s for s in sr_details if sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level") == "medium"]
    low_risk_sr = [s for s in sr_details if s not in high_risk_sr and s not in medium_risk_sr]

    # SR 遗留问题统计
    sr_issue_total = len(sr_issues)
    sr_blocker = [i for i in sr_issues if i.get("priority") == "Blocker"]
    sr_critical = [i for i in sr_issues if i.get("priority") == "Critical"]
    sr_major = [i for i in sr_issues if i.get("priority") == "Major"]

    # 超龄问题
    sr_over_14 = [i for i in sr_issues if (i.get("aging_days") or 0) > 14]
    sr_over_30 = [i for i in sr_issues if (i.get("aging_days") or 0) > 30]

    # 负责人维度统计
    owner_map = {}
    for issue in sr_issues:
        owner = issue.get("assignee") or "未分配"
        if owner not in owner_map:
            owner_map[owner] = {"total": 0, "blocker": 0, "critical": 0, "max_aging": 0}
        owner_map[owner]["total"] += 1
        if issue.get("priority") == "Blocker":
            owner_map[owner]["blocker"] += 1
        if issue.get("priority") == "Critical":
            owner_map[owner]["critical"] += 1
        owner_map[owner]["max_aging"] = max(owner_map[owner]["max_aging"], issue.get("aging_days") or 0)

    top_owners = sorted(owner_map.items(), key=lambda x: (-x[1]["blocker"], -x[1]["critical"], -x[1]["total"]))[:10]

    return {
        "version_name": version_name,
        "stage_name": stage_name,
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_sr": total_sr,
            "high_risk_sr_count": len(high_risk_sr),
            "medium_risk_sr_count": len(medium_risk_sr),
            "low_risk_sr_count": len(low_risk_sr),
            "sr_issue_total": sr_issue_total,
            "sr_blocker_count": len(sr_blocker),
            "sr_critical_count": len(sr_critical),
            "sr_major_count": len(sr_major),
            "sr_over_14_days": len(sr_over_14),
            "sr_over_30_days": len(sr_over_30),
            "total_issues": total_issues,
            "unresolved_count": len(unresolved),
            "high_priority_count": len(high_priority),
            "must_fix_count": len(must_fix),
        },
        "high_risk_sr": [
            {
                "coding": s.get("sr_coding", ""),
                "name": s.get("sr_name", ""),
                "status": s.get("sr_status", ""),
                "issue_count": s.get("issue_count", 0),
                "ai_risk_level": sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level", ""),
                "ai_analysis": sr_ai_results.get(s.get("sr_coding", ""), {}).get("analysis", ""),
            }
            for s in high_risk_sr
        ],
        "medium_risk_sr": [
            {
                "coding": s.get("sr_coding", ""),
                "name": s.get("sr_name", ""),
                "status": s.get("sr_status", ""),
                "issue_count": s.get("issue_count", 0),
                "ai_risk_level": sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level", ""),
                "ai_analysis": sr_ai_results.get(s.get("sr_coding", ""), {}).get("analysis", ""),
            }
            for s in medium_risk_sr
        ],
        "sr_blocker_issues": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": (i.get("summary") or "")[:80],
                "status": i.get("status", ""),
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_blocker
        ],
        "sr_critical_issues": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": (i.get("summary") or "")[:80],
                "status": i.get("status", ""),
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_critical[:20]
        ],
        "sr_over_30_days": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": (i.get("summary") or "")[:80],
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_over_30[:20]
        ],
        "top_owners": [
            {"owner": o, **d}
            for o, d in top_owners
        ],
    }


def generate_sr_risk_report_text(data: dict) -> str:
    """将 SR 风险数据格式化为 Markdown 报告"""
    s = data.get("summary", {})
    lines = []
    lines.append(f"# {data.get('version_name', '')} 每日 SR 风险总结报告")
    lines.append(f"")
    lines.append(f"**报告时间：** {data.get('report_time', '')}")
    lines.append(f"**当前阶段：** {data.get('stage_name', '')}")
    lines.append(f"")

    # 整体概览
    lines.append(f"## 一、整体概览")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| SR 需求总数 | {s.get('total_sr', 0)} |")
    lines.append(f"| 高风险 SR | {s.get('high_risk_sr_count', 0)} |")
    lines.append(f"| 中风险 SR | {s.get('medium_risk_sr_count', 0)} |")
    lines.append(f"| 低风险 SR | {s.get('low_risk_sr_count', 0)} |")
    lines.append(f"| SR 遗留问题总数 | {s.get('sr_issue_total', 0)} |")
    lines.append(f"| 其中 Blocker | {s.get('sr_blocker_count', 0)} |")
    lines.append(f"| 其中 Critical | {s.get('sr_critical_count', 0)} |")
    lines.append(f"| 其中 Major | {s.get('sr_major_count', 0)} |")
    lines.append(f"| 超龄 >14 天 | {s.get('sr_over_14_days', 0)} |")
    lines.append(f"| 超龄 >30 天 | {s.get('sr_over_30_days', 0)} |")
    lines.append(f"| Jira 总 Issue | {s.get('total_issues', 0)} |")
    lines.append(f"| 未关闭 Issue | {s.get('unresolved_count', 0)} |")
    lines.append(f"| 高优 Issue | {s.get('high_priority_count', 0)} |")
    lines.append(f"| 必解 Issue | {s.get('must_fix_count', 0)} |")
    lines.append(f"")

    # 高风险 SR
    high_risk = data.get("high_risk_sr", [])
    if high_risk:
        lines.append(f"## 二、高风险 SR（{len(high_risk)} 个）")
        lines.append(f"")
        lines.append(f"| SR 编号 | SR 名称 | 状态 | 关联 Issue 数 | AI 分析 |")
        lines.append(f"|---------|---------|------|---------------|---------|")
        for sr in high_risk:
            analysis = (sr.get("ai_analysis") or "")[:60].replace("\n", " ")
            lines.append(f"| {sr.get('coding', '')} | {sr.get('name', '')[:30]} | {sr.get('status', '')} | {sr.get('issue_count', 0)} | {analysis} |")
        lines.append(f"")

    # 中风险 SR
    medium_risk = data.get("medium_risk_sr", [])
    if medium_risk:
        lines.append(f"## 三、中风险 SR（{len(medium_risk)} 个）")
        lines.append(f"")
        lines.append(f"| SR 编号 | SR 名称 | 状态 | 关联 Issue 数 | AI 分析 |")
        lines.append(f"|---------|---------|------|---------------|---------|")
        for sr in medium_risk[:15]:
            analysis = (sr.get("ai_analysis") or "")[:60].replace("\n", " ")
            lines.append(f"| {sr.get('coding', '')} | {sr.get('name', '')[:30]} | {sr.get('status', '')} | {sr.get('issue_count', 0)} | {analysis} |")
        if len(medium_risk) > 15:
            lines.append(f"| ... | 共 {len(medium_risk)} 个，此处显示前 15 个 | | | |")
        lines.append(f"")

    # Blocker 问题
    blocker_issues = data.get("sr_blocker_issues", [])
    if blocker_issues:
        lines.append(f"## 四、Blocker 问题（{len(blocker_issues)} 个）")
        lines.append(f"")
        lines.append(f"| Issue Key | 摘要 | 状态 | 负责人 | 老化天数 |")
        lines.append(f"|-----------|------|------|--------|----------|")
        for issue in blocker_issues[:20]:
            lines.append(f"| {issue.get('issue_key', '')} | {issue.get('summary', '')[:40]} | {issue.get('status', '')} | {issue.get('assignee', '')} | {issue.get('aging_days', 0)} |")
        lines.append(f"")

    # 超龄问题
    over_30 = data.get("sr_over_30_days", [])
    if over_30:
        lines.append(f"## 五、超龄问题（>30天，{len(over_30)} 个）")
        lines.append(f"")
        lines.append(f"| Issue Key | 摘要 | 优先级 | 负责人 | 老化天数 |")
        lines.append(f"|-----------|------|--------|--------|----------|")
        for issue in over_30[:20]:
            lines.append(f"| {issue.get('issue_key', '')} | {issue.get('summary', '')[:40]} | {issue.get('priority', '')} | {issue.get('assignee', '')} | {issue.get('aging_days', 0)} |")
        lines.append(f"")

    # 负责人维度
    top_owners = data.get("top_owners", [])
    if top_owners:
        lines.append(f"## 六、负责人维度（Top 10）")
        lines.append(f"")
        lines.append(f"| 负责人 | 问题总数 | Blocker | Critical | 最大老化天数 |")
        lines.append(f"|--------|----------|---------|----------|--------------|")
        for owner_data in top_owners[:10]:
            lines.append(f"| {owner_data.get('owner', '')} | {owner_data.get('total', 0)} | {owner_data.get('blocker', 0)} | {owner_data.get('critical', 0)} | {owner_data.get('max_aging', 0)} |")
        lines.append(f"")

    # 建议
    lines.append(f"## 七、行动建议")
    lines.append(f"")
    if s.get('sr_blocker_count', 0) > 0:
        lines.append(f"- **紧急处理 Blocker 问题**：当前有 {s.get('sr_blocker_count', 0)} 个 Blocker 问题需要立即解决")
    if s.get('sr_over_30_days', 0) > 0:
        lines.append(f"- **关注超龄问题**：有 {s.get('sr_over_30_days', 0)} 个问题超过 30 天未解决，需分析根因")
    if s.get('high_risk_sr_count', 0) > 0:
        lines.append(f"- **高风险 SR 跟进**：{s.get('high_risk_sr_count', 0)} 个高风险 SR 需要重点跟进")
    lines.append(f"- **定期同步**：建议每日同步 Jira 数据并更新 SR 风险分析")
    lines.append(f"")

    return "\n".join(lines)