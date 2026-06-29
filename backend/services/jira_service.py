import json
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import quote
import requests
from requests.auth import HTTPBasicAuth
from fastapi import HTTPException
from ..config import (
    DEFAULT_JIRA_BASE_URL, JIRA_CUSTOM_FIELDS, JIRA_SEARCH_FIELDS,
    CLOSED_STATUS, HIGH_PRIORITY
)
from ..database import get_conn
from ..encryption import encrypt_text, decrypt_text
from ..utils import (
    now_iso, parse_dt, stringify_field_value, priority_to_grade,
    is_must_fix_enhanced, calc_risk_score
)

# 同步进度跟踪
sync_progress = {
    "active": False,
    "phase": "",       # "fetching" / "saving" / "analyzing" / "done" / "error"
    "fetched": 0,
    "total": 0,
    "message": "",
}

# 全局凭据路径
from ..config import APP_DIR
GLOBAL_CRED_PATH = APP_DIR / "global_jira_cred.json"

def set_global_cred_path(path):
    """设置全局凭据文件路径"""
    global GLOBAL_CRED_PATH
    GLOBAL_CRED_PATH = path

def save_credential(version_id: int, req):
    """保存Jira凭据"""
    expire_at = datetime.now() + timedelta(days=7)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    encrypted = encrypt_text(req.password_or_token)

    cur.execute("""
    INSERT INTO jira_credential (
        version_id, jira_base_url, username, encrypted_password, expire_at, last_login_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(version_id)
    DO UPDATE SET
        jira_base_url = excluded.jira_base_url,
        username = excluded.username,
        encrypted_password = excluded.encrypted_password,
        expire_at = excluded.expire_at,
        last_login_at = excluded.last_login_at
    """, (
        version_id,
        req.jira_base_url.rstrip("/"),
        req.username,
        encrypted,
        expire_at.isoformat(timespec="seconds"),
        now_iso()
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Jira账号已保存，有效期7天",
        "expire_at": expire_at.isoformat(timespec="seconds")
    }

def credential_status(version_id: int):
    """获取凭据状态"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT jira_base_url, username, expire_at, last_login_at
    FROM jira_credential
    WHERE version_id = ?
    """, (version_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "configured": False,
            "valid": False,
            "message": "未配置Jira账号"
        }

    expire_at = datetime.fromisoformat(row["expire_at"])
    valid = datetime.now() < expire_at

    return {
        "configured": True,
        "valid": valid,
        "jira_base_url": row["jira_base_url"],
        "username": row["username"],
        "expire_at": row["expire_at"],
        "last_login_at": row["last_login_at"],
        "message": "Jira已连接" if valid else "Jira登录已过期，请重新输入"
    }

def get_global_credential():
    """获取全局 Jira 凭据"""
    if not GLOBAL_CRED_PATH or not GLOBAL_CRED_PATH.exists():
        return None
    try:
        data = json.loads(GLOBAL_CRED_PATH.read_text(encoding="utf-8"))
        return {
            "jira_base_url": data.get("jira_base_url", DEFAULT_JIRA_BASE_URL),
            "username": data.get("username", ""),
            "password": decrypt_text(data.get("encrypted_password", "")),
        }
    except Exception:
        return None

def set_global_credential(username: str, password: str, base_url: str = DEFAULT_JIRA_BASE_URL):
    """保存全局 Jira 凭据"""
    if not GLOBAL_CRED_PATH:
        raise HTTPException(status_code=500, detail="全局凭据路径未设置")
    
    from ..database import ensure_app_dir
    ensure_app_dir()
    
    data = {
        "jira_base_url": base_url.rstrip("/"),
        "username": username,
        "encrypted_password": encrypt_text(password),
        "updated_at": now_iso(),
    }
    GLOBAL_CRED_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def get_valid_credential(version_id: int = 0):
    """获取 Jira 凭据（统一使用全局凭据）"""
    global_cred = get_global_credential()
    if global_cred and global_cred["username"] and global_cred["password"]:
        print(f"[CRED] 使用全局凭据: user={global_cred['username']}, url={global_cred['jira_base_url']}, pwd_len={len(global_cred['password'])}")
        return global_cred

    raise HTTPException(status_code=400, detail="请先在 ⚙️ 设置 → Jira 中配置账号密码")

def get_latest_sync_time(version_id: int, stage_name: str) -> Optional[str]:
    """
    查询本地缓存中 issue 的最新 Jira 更新时间（updated_time），用于增量同步。
    返回 ISO 格式时间字符串，如 "2026-06-01T10:30:00"。
    如果本地无数据，返回 None。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(updated_time) as latest
        FROM jira_issue_cache
        WHERE version_id = ? AND str_stage = ?
          AND updated_time IS NOT NULL AND updated_time != ''
    """, (version_id, stage_name))
    row = cur.fetchone()
    conn.close()
    if row and row["latest"]:
        return row["latest"]
    return None

def build_jql(version: Dict[str, Any], stage: Optional[Dict[str, Any]], incremental_since: Optional[str] = None):
    """
    构建 JQL 查询语句。
    优先使用数据库中用户自定义的 main_sync filter JQL。
    如果用户没有自定义，则使用数据库中的默认 JQL。
    """
    from ..database import get_conn

    version_id = version["id"]

    # 从数据库读取 main_sync filter 的 JQL
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT custom_jql, default_jql FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = 'main_sync'
    """, (version_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        jql = row["custom_jql"] or row["default_jql"]
    else:
        # 如果数据库中没有 filter，使用旧的逻辑（兼容）
        project = version["jira_project"]
        primary_project = project.split(",")[0].strip()
        jql = f'project = {primary_project} AND issuetype in (Bug) ORDER BY updated DESC'

    # 增量同步：只抓取上次同步时间之后更新过的 issue
    if incremental_since:
        # 在 ORDER BY 之前插入 updated >= 条件
        order_idx = jql.upper().find("ORDER BY")
        if order_idx > 0:
            main_part = jql[:order_idx].rstrip()
            order_part = jql[order_idx:]
            jql = f'{main_part} AND updated >= "{incremental_since}" {order_part}'
        else:
            jql = f'{jql} AND updated >= "{incremental_since}"'

    print(f"构建 JQL: {jql}")
    return jql

def jira_fetch_issues(credential: Dict[str, Any], jql: str, use_post: bool = True):
    """
    从 Jira 获取 Issues。（增强版，使用完整的字段列表）
    """
    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/search"

    all_issues = []
    start_at = 0
    max_results = 100

    print(f"开始Jira同步: {url}")
    print(f"JQL: {jql}")
    print(f"用户: {credential['username']}")

    while True:
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": JIRA_SEARCH_FIELDS
        }

        try:
            if use_post:
                resp = requests.post(
                    url,
                    json=payload,
                    auth=HTTPBasicAuth(credential["username"], credential["password"]),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    timeout=30,
                    verify=False  # 禁用SSL证书验证（公司Jira可能使用自签名证书）
                )
            else:
                resp = requests.get(
                    url,
                    params=payload,
                    auth=HTTPBasicAuth(credential["username"], credential["password"]),
                    headers={"Accept": "application/json"},
                    timeout=30,
                    verify=False  # 禁用SSL证书验证
                )
        except requests.exceptions.ConnectionError as e:
            print(f"连接Jira失败: {e}")
            raise HTTPException(status_code=502, detail=f"无法连接到Jira服务器: {base_url}")
        except requests.exceptions.Timeout as e:
            print(f"请求超时: {e}")
            raise HTTPException(status_code=504, detail="Jira请求超时")

        print(f"Jira响应状态码: {resp.status_code}")

        if resp.status_code == 401:
            print(f"认证失败: {resp.text[:200]}")
            raise HTTPException(status_code=401, detail="Jira认证失败，请检查账号密码")

        if resp.status_code == 403:
            print(f"权限不足: {resp.text[:200]}")
            raise HTTPException(status_code=403, detail="Jira权限不足，请检查账号权限")

        if resp.status_code == 400:
            print(f"请求错误: {resp.text[:500]}")
            raise HTTPException(
                status_code=400,
                detail=f"Jira请求错误（可能是JQL语法问题）: {resp.text[:300]}"
            )

        if resp.status_code >= 400:
            print(f"请求失败: {resp.status_code} - {resp.text[:500]}")
            raise HTTPException(
                status_code=400,
                detail=f"Jira同步失败：HTTP {resp.status_code} - {resp.text[:300]}"
            )

        data = resp.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)

        all_issues.extend(issues)

        # 上报进度
        sync_progress["fetched"] = len(all_issues)
        sync_progress["total"] = total
        sync_progress["message"] = f"正在采集... {len(all_issues)} / {total}"

        print(f"Jira 分页: startAt={start_at}, 本页={len(issues)}, 累计={len(all_issues)}, 总数={total}")

        start_at += max_results
        if start_at >= total:
            break

        # 安全上限
        if len(all_issues) >= 50000:
            print(f"达到安全上限 50000 条，停止拉取")
            break

    print(f"Jira 数据获取完成: {len(all_issues)} 条, Jira报告总数={total}")
    return all_issues, total

def normalize_issue(issue, version_id, version_name, stage_name):
    """
    解析 Jira Issue 数据，包括自定义字段。（增强版）
    """
    fields = issue.get("fields", {})

    # 基础字段
    components = fields.get("components") or []
    module_name = components[0].get("name") if components else "未归类"

    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    labels = fields.get("labels") or []

    # 自定义字段
    must_fix = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["must_fix"]))
    severity = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["severity"]))
    model = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["model"]))
    issue_category = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["issue_category"]))
    frequency = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["frequency"]))
    module_category = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["module_category"]))
    project_code = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["project_code"]))
    os_version = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["os_version"]))
    android_version = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["android_version"]))
    migration = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["migration"]))

    # 计算字段
    priority = (fields.get("priority") or {}).get("name") or "未设置"
    status = (fields.get("status") or {}).get("name") or "未知"
    labels_text = ",".join(labels)
    created_time = parse_dt(fields.get("created"))
    updated_time = parse_dt(fields.get("updated"))

    # A/B/C 等级
    grade = priority_to_grade(priority, severity, must_fix)

    # 必解标记
    must_fix_flag = 1 if is_must_fix_enhanced(must_fix, labels_text, priority, migration) else 0

    # 遗留天数
    aging_days = None
    if created_time:
        try:
            created_dt = datetime.fromisoformat(created_time)
            aging_days = (datetime.now() - created_dt).days
        except Exception:
            aging_days = None

    # 未更新天数
    stale_days = None
    if updated_time:
        try:
            updated_dt = datetime.fromisoformat(updated_time)
            stale_days = (datetime.now() - updated_dt).days
        except Exception:
            stale_days = None

    # 风险评分
    risk_score = calc_risk_score(grade, status, priority, aging_days, stale_days, must_fix_flag == 1)

    return {
        "version_id": version_id,
        "version_name": version_name,
        "str_stage": stage_name,
        "issue_key": issue.get("key"),
        "summary": fields.get("summary") or "",
        "description": fields.get("description") or "",
        "status": status,
        "priority": priority,
        "issue_type": (fields.get("issuetype") or {}).get("name") or "未知",
        "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
        "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
        "module_name": module_name,
        "labels": labels_text,
        "created_time": created_time,
        "updated_time": updated_time,
        "resolved_time": parse_dt(fields.get("resolutiondate")),
        "raw_payload": json.dumps(issue, ensure_ascii=False),
        "synced_at": now_iso(),
        # 自定义字段
        "must_fix": must_fix,
        "severity": severity,
        "model": model,
        "issue_category": issue_category,
        "frequency": frequency,
        "module_category": module_category,
        "project_code": project_code,
        "os_version": os_version,
        "android_version": android_version,
        # 计算字段
        "grade": grade,
        "must_fix_flag": must_fix_flag,
        "aging_days": aging_days,
        "stale_days": stale_days,
        "risk_score": risk_score,
    }

def save_issues(issues: List[Dict[str, Any]]):
    """保存 Issues 到数据库（增强版，包含自定义字段）"""
    conn = get_conn()
    cur = conn.cursor()

    for item in issues:
        cur.execute("""
        INSERT INTO jira_issue_cache (
            version_id, version_name, str_stage, issue_key,
            summary, description, status, priority, issue_type,
            assignee, reporter, module_name, labels,
            created_time, updated_time, resolved_time,
            raw_payload, synced_at,
            must_fix, severity, model, issue_category, frequency,
            module_category, project_code, os_version, android_version,
            grade, must_fix_flag, aging_days, stale_days, risk_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, str_stage, issue_key)
        DO UPDATE SET
            summary = excluded.summary,
            description = excluded.description,
            status = excluded.status,
            priority = excluded.priority,
            issue_type = excluded.issue_type,
            assignee = excluded.assignee,
            reporter = excluded.reporter,
            module_name = excluded.module_name,
            labels = excluded.labels,
            created_time = excluded.created_time,
            updated_time = excluded.updated_time,
            resolved_time = excluded.resolved_time,
            raw_payload = excluded.raw_payload,
            synced_at = excluded.synced_at,
            must_fix = excluded.must_fix,
            severity = excluded.severity,
            model = excluded.model,
            issue_category = excluded.issue_category,
            frequency = excluded.frequency,
            module_category = excluded.module_category,
            project_code = excluded.project_code,
            os_version = excluded.os_version,
            android_version = excluded.android_version,
            grade = excluded.grade,
            must_fix_flag = excluded.must_fix_flag,
            aging_days = excluded.aging_days,
            stale_days = excluded.stale_days,
            risk_score = excluded.risk_score
        """, (
            item["version_id"],
            item["version_name"],
            item["str_stage"],
            item["issue_key"],
            item["summary"],
            item["description"],
            item["status"],
            item["priority"],
            item["issue_type"],
            item["assignee"],
            item["reporter"],
            item["module_name"],
            item["labels"],
            item["created_time"],
            item["updated_time"],
            item["resolved_time"],
            item["raw_payload"],
            item["synced_at"],
            item.get("must_fix"),
            item.get("severity"),
            item.get("model"),
            item.get("issue_category"),
            item.get("frequency"),
            item.get("module_category"),
            item.get("project_code"),
            item.get("os_version"),
            item.get("android_version"),
            item.get("grade"),
            item.get("must_fix_flag", 0),
            item.get("aging_days"),
            item.get("stale_days"),
            item.get("risk_score", 0),
        ))

    conn.commit()
    conn.close()
    print(f"已保存 {len(issues)} 条 Issue 到数据库")

def generate_mock_issues(version_id: int, version_name: str, stage_name: str, count: int = 320):
    """生成模拟 Issue 数据（增强版，包含自定义字段）"""
    modules = ["Framework", "Settings", "Launcher", "Stability", "MemoryManage", "Notification", "Power", "Camera"]
    assignees = ["张三", "李四", "王五", "赵六", "陈七", "未分配"]
    priorities = ["Blocker", "Critical", "Major", "High", "Medium", "Low"]
    statuses = ["Submitted", "Modifying", "Resolved", "Verified", "Closed", "Reopen", "In Progress"]
    severities = ["高", "中", "低"]
    models = ["X6879", "X6878", "X6891", "CN5", "X6840", "LK7K", "LK6"]
    must_fix_options = ["MP Block", "Not MP Block", ""]

    today = datetime.now()
    issues = []

    for i in range(count):
        created = today - timedelta(days=random.randint(0, 35))
        updated = created + timedelta(days=random.randint(0, 10))
        status = random.choice(statuses)
        resolved = None
        if status in CLOSED_STATUS:
            resolved = updated + timedelta(days=random.randint(0, 3))

        module = random.choice(modules)
        priority = random.choice(priorities)
        severity = random.choice(severities)
        model = random.choice(models)
        must_fix = random.choice(must_fix_options)

        # 计算字段
        aging_days = (today - created).days
        stale_days = (today - updated).days
        grade = priority_to_grade(priority, severity, must_fix)
        must_fix_flag = 1 if is_must_fix_enhanced(must_fix, "mock,tos", priority, "") else 0
        risk_score = calc_risk_score(grade, status, priority, aging_days, stale_days, must_fix_flag == 1)

        issues.append({
            "version_id": version_id,
            "version_name": version_name,
            "str_stage": stage_name,
            "issue_key": f"{version_name.replace('.', '').replace('+', 'N')}-{10000 + i}",
            "summary": f"{module} 模块在主流程/异常恢复场景下出现稳定性问题 #{i}",
            "description": f"示例问题：{module} 相关场景需要重点验证，包含启动、切后台、恢复、异常退出等路径。",
            "status": status,
            "priority": priority,
            "issue_type": "Bug",
            "assignee": random.choice(assignees),
            "reporter": "测试同学",
            "module_name": module,
            "labels": "mock,tos",
            "created_time": created.isoformat(timespec="seconds"),
            "updated_time": updated.isoformat(timespec="seconds"),
            "resolved_time": resolved.isoformat(timespec="seconds") if resolved else None,
            "raw_payload": "{}",
            "synced_at": now_iso(),
            # 自定义字段
            "must_fix": must_fix,
            "severity": severity,
            "model": model,
            "issue_category": random.choice(["Stability", "Performance", "UI", "Function", ""]),
            "frequency": random.choice(["Always", "Often", "Sometimes", "Rarely", ""]),
            "module_category": module,
            "project_code": model,
            "os_version": version_name,
            "android_version": "14",
            # 计算字段
            "grade": grade,
            "must_fix_flag": must_fix_flag,
            "aging_days": aging_days,
            "stale_days": stale_days,
            "risk_score": risk_score,
        })

    return issues

def sync_jira_data(version_id: int, req, stage: str = "STR1"):
    """同步Jira数据"""
    from ..database import get_conn
    from ..routers.versions import get_version, get_stage
    from ..services.analysis_engine import build_analysis
    
    version = get_version(version_id)
    stage_config = get_stage(version_id, stage)
    stage_name = stage if stage != "ALL" else "ALL"

    if req.use_mock:
        issues = generate_mock_issues(
            version_id=version_id,
            version_name=version["version_name"],
            stage_name=stage_name,
            count=520 if stage == "ALL" else 260
        )
        save_issues(issues)
        analysis = build_analysis(version_id, stage_name)
        return {
            "message": "示例数据已生成",
            "synced_count": len(issues),
            "analysis": analysis
        }

    global sync_progress
    sync_progress = {"active": True, "phase": "connecting", "fetched": 0, "total": 0, "message": "正在连接 Jira..."}

    try:
        credential = get_valid_credential(version_id)

        # ---- 增量同步：查询本地最新 Jira 更新时间，只抓取该时间之后更新过的 issue ----
        latest_sync = None if req.force_full else get_latest_sync_time(version_id, stage_name)
        incremental = False
        if latest_sync:
            incremental_since = latest_sync[:16].replace("T", " ")  # "2026-06-05 14:30"
            jql = build_jql(version, stage_config, incremental_since=incremental_since)
            incremental = True
            print(f"[增量同步] 本地最新 updated_time={latest_sync}，只抓取 updated >= \"{incremental_since}\"")
            sync_progress["message"] = f"增量同步：只抓取 {incremental_since} 之后更新的数据..."
        else:
            jql = build_jql(version, stage_config)
            print("[全量同步] 本地无数据，执行全量同步")

        sync_progress["phase"] = "fetching"
        sync_progress["message"] = "正在采集数据..."
        raw_issues, total_count = jira_fetch_issues(credential, jql)

        sync_progress["phase"] = "saving"
        sync_progress["message"] = f"正在保存 {len(raw_issues)} 条数据..."

        normalized = [
            normalize_issue(
                issue=i,
                version_id=version_id,
                version_name=version["version_name"],
                stage_name=stage_name
            )
            for i in raw_issues
        ]

        conn = get_conn()
        cur = conn.cursor()
        if not incremental:
            # 全量同步：先清空当前版本+阶段的旧数据，再写入新数据
            cur.execute("DELETE FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
            print(f"[全量同步] 已清空 version_id={version_id}, stage={stage_name} 的旧缓存")
        # 删除旧的分析快照，重新生成
        cur.execute("DELETE FROM analysis_snapshot WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
        conn.commit()
        conn.close()

        save_issues(normalized)

        sync_progress["phase"] = "analyzing"
        sync_progress["message"] = "正在生成分析报告..."
        analysis = build_analysis(version_id, stage_name)

        # 计算本地总缓存量
        conn = get_conn()
        cur = conn.cursor()
        if stage_name == "ALL":
            cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id = ?", (version_id,))
        else:
            cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
        local_total = cur.fetchone()["c"]
        conn.close()

        sync_msg = f"同步完成：本次抓取 {len(normalized)} 条，本地共 {local_total} 条"
        if incremental:
            sync_msg += f"（增量，Jira匹配 {total_count} 条）"
        else:
            sync_msg += f"（全量，Jira共 {total_count} 条）"

        sync_progress = {"active": False, "phase": "done", "fetched": len(normalized), "total": total_count, "message": sync_msg}

        # 清除该版本的 API 缓存，确保子板块下次请求拿到最新数据
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM jira_issue_api_cache WHERE version_id = ?", (version_id,))
            conn.commit()
            conn.close()
            print(f"[同步] 已清除 version_id={version_id} 的 API 缓存")
        except Exception:
            pass

        return {
            "message": "Jira数据同步完成",
            "jql": jql,
            "synced_count": len(normalized),
            "total_count": total_count,
            "local_total": local_total,
            "incremental": incremental,
            "analysis": analysis
        }
    except Exception as e:
        sync_progress = {"active": False, "phase": "error", "fetched": 0, "total": 0, "message": f"同步失败：{str(e)[:100]}"}
        raise

def get_sync_progress():
    """获取同步进度"""
    return sync_progress

def delete_version_credential(version_id: int):
    """删除版本 Jira 凭据（回退到使用全局凭据）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM jira_credential WHERE version_id = ?", (version_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"已删除 {deleted} 条凭据"}

def test_jira_connection(version_id: int):
    """测试Jira连接"""
    # 判断凭据来源
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, expire_at FROM jira_credential WHERE version_id = ?", (version_id,))
    ver_row = cur.fetchone()
    conn.close()

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"ok": False, "error": f"获取凭据失败: {str(e)}"}

    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/myself"

    cred_source = "版本凭据" if ver_row else "全局凭据"
    print(f"[JIRA-TEST] 测试连接: {url}, user={credential['username']}, pwd_len={len(credential['password'])}, 来源={cred_source}")

    try:
        resp = requests.get(url, auth=HTTPBasicAuth(credential["username"], credential["password"]),
                            headers={"Accept": "application/json"}, timeout=15, verify=False)
        print(f"[JIRA-TEST] myself 响应: {resp.status_code}")

        result = {
            "ok": False,
            "cred_source": cred_source,
            "url": url,
            "username": credential["username"],
            "pwd_len": len(credential["password"]),
            "status_code": resp.status_code,
        }

        if resp.status_code == 200:
            user_info = resp.json()
            result["ok"] = True
            result["display_name"] = user_info.get("displayName", "")
            result["name"] = user_info.get("name", "")
            # 再测试一个简单 JQL
            from ..routers.versions import get_version
            version = get_version(version_id)
            jql_resp = requests.post(
                f"{base_url}/rest/api/2/search",
                json={"jql": f"project = {version.get('jira_project', 'OS162')} AND summary ~ 'SR' AND priority in (Blocker, Critical, Major) ORDER BY created DESC", "startAt": 0, "maxResults": 1, "fields": ["summary"]},
                auth=HTTPBasicAuth(credential["username"], credential["password"]),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=15, verify=False,
            )
            result["jql_status"] = jql_resp.status_code
            if jql_resp.status_code != 200:
                result["jql_error"] = jql_resp.text[:300]
        else:
            result["body"] = resp.text[:500]

        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

# SR 遗留问题关注的高优先级（只用 Jira 中实际存在的值）
SR_HIGH_PRIORITY = {"Blocker", "Critical", "Major"}

def build_sr_jql(jira_project: str, is_pad: bool = False) -> str:
    """
    构建 SR 遗留问题的 JQL。
    动态组合：项目 + summary 包含 SR + 排除已关闭状态 + 高优先级。
    is_pad=True 时额外追加 summary ~ "PAD" 条件。
    """
    jql_closed = "Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished"
    priority_list = ", ".join(sorted(SR_HIGH_PRIORITY))
    project_cond = _build_project_condition(jira_project)
    pad_cond = ' AND summary ~ "PAD"' if is_pad else ""
    jql = (
        f'{project_cond} '
        f'AND (summary ~ "SR*"  or  SR编号  is not empty ) '
        f'{pad_cond} '
        f'AND status not in ({jql_closed}) '
        f'AND priority in ({priority_list}) '
        f'ORDER BY priority ASC, created DESC'
    )
    return jql

def _build_project_condition(jira_project: str) -> str:
    """
    根据 jira_project 构建 JQL 的 project 条件。
    支持逗号分隔的多项目（如 "TOS170, LK7KOS17, X6878OS17"），
    自动选择 project in (...) 或 project = ... 语法。
    """
    # 检测逗号分隔的多项目
    projects = [p.strip() for p in jira_project.split(",") if p.strip()]
    if len(projects) > 1:
        return f'project in ({", ".join(projects)})'
    return f'project = {jira_project.strip()}'