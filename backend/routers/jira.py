from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from ..database import get_conn
from ..models.schemas import CredentialSave, SyncRequest
from ..utils import now_iso
from ..services.jira_service import (
    save_credential, credential_status, get_global_credential, set_global_credential,
    get_valid_credential, get_sync_progress, delete_version_credential, test_jira_connection,
    sync_jira_data, build_sr_jql
)
from ..config import DEFAULT_JIRA_BASE_URL

router = APIRouter()

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)

def load_issues(version_id: int, stage: str):
    """从数据库加载Issues"""
    conn = get_conn()
    cur = conn.cursor()
    
    if stage == "ALL":
        cur.execute("""
        SELECT * FROM jira_issue_cache
        WHERE version_id = ?
        ORDER BY risk_score DESC, created_time DESC
        """, (version_id,))
    else:
        cur.execute("""
        SELECT * FROM jira_issue_cache
        WHERE version_id = ? AND str_stage = ?
        ORDER BY risk_score DESC, created_time DESC
        """, (version_id, stage))
    
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@router.post("/api/versions/{version_id}/credential")
def api_save_credential(version_id: int, req: CredentialSave):
    """保存Jira凭据"""
    return save_credential(version_id, req)

@router.get("/api/versions/{version_id}/credential/status")
def api_credential_status(version_id: int):
    """获取凭据状态"""
    return credential_status(version_id)

@router.delete("/api/versions/{version_id}/credential")
def api_delete_version_credential(version_id: int):
    """删除版本Jira凭据"""
    return delete_version_credential(version_id)

@router.get("/api/versions/{version_id}/jira-test")
def api_test_jira_connection(version_id: int):
    """测试Jira连接"""
    return test_jira_connection(version_id)

@router.post("/api/versions/{version_id}/sync")
def api_sync_jira_data(version_id: int, req: SyncRequest, stage: str = Query("STR1")):
    """同步Jira数据"""
    return sync_jira_data(version_id, req, stage)

@router.get("/api/sync-progress")
def api_get_sync_progress():
    """获取同步进度"""
    return get_sync_progress()

@router.get("/api/jira/global-credential")
def api_get_global_credential():
    """获取全局Jira凭据"""
    cred = get_global_credential()
    if not cred:
        return {"configured": False}
    return {
        "configured": True,
        "jira_base_url": cred["jira_base_url"],
        "username": cred["username"],
    }

@router.post("/api/jira/global-credential")
def api_set_global_credential(
    username: str = Body(...),
    password: str = Body(...),
    base_url: str = Body(DEFAULT_JIRA_BASE_URL),
):
    """设置全局Jira凭据"""
    set_global_credential(username, password, base_url)
    return {"message": "全局Jira凭据已保存"}

@router.get("/api/versions/{version_id}/jira-issues/{filter_key}")
def api_get_jira_issues(
    version_id: int,
    filter_key: str,
    stage: str = Query("ALL"),
    use_cache: bool = Query(True),
):
    """通用接口：用指定 filter 的 JQL 查询 Jira 并返回 issue 列表。

    use_cache=True（默认）：优先返回 30 分钟内的缓存数据，避免每次切换版本都查询 Jira。
    use_cache=False：强制从 Jira 获取最新数据。
    """
    import json as _json
    from datetime import datetime, timedelta
    from ..routers.versions import get_version
    from ..services.jira_service import jira_fetch_issues, build_sr_jql
    from urllib.parse import quote

    version = get_version(version_id)
    jira_project = version.get("jira_project", "")
    default_jira_url = "http://jira.transsion.com"

    # ── 缓存检查（use_cache=True 时，30 分钟内直接返回缓存）──
    import time as _time
    cache_key = f"{filter_key}:{stage}"
    CACHE_TTL_SECONDS = 30 * 60  # 30 分钟

    if use_cache:
        try:
            conn = get_conn()
            cur = conn.cursor()
            # 确保表存在（使用 cache_key 列）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jira_issue_api_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id INTEGER NOT NULL,
                    cache_key TEXT NOT NULL DEFAULT '',
                    data_json TEXT DEFAULT '',
                    synced_at TEXT,
                    UNIQUE(version_id, cache_key)
                )
            """)
            # 兼容旧表：确保 cache_key 列存在
            try:
                cur.execute("ALTER TABLE jira_issue_api_cache ADD COLUMN cache_key TEXT NOT NULL DEFAULT ''")
                conn.commit()
            except Exception:
                pass
            cur.execute(
                "SELECT data_json, synced_at FROM jira_issue_api_cache WHERE version_id = ? AND cache_key = ?",
                (version_id, cache_key),
            )
            cached_row = cur.fetchone()
            conn.close()

            if cached_row and cached_row["data_json"]:
                synced_at = cached_row["synced_at"] or ""
                if synced_at:
                    # 使用 Unix 时间戳比较（简单可靠）
                    try:
                        cached_ts = float(synced_at)
                        age_seconds = _time.time() - cached_ts
                        if age_seconds < CACHE_TTL_SECONDS:
                            result = _json.loads(cached_row["data_json"])
                            result["from_cache"] = True
                            result["cache_age_minutes"] = round(age_seconds / 60, 1)
                            print(f"[CACHE-HIT] {cache_key} (age={result['cache_age_minutes']}min)")
                            return result
                        else:
                            print(f"[CACHE-STALE] {cache_key} (age={round(age_seconds/60)}min)")
                    except (ValueError, TypeError):
                        # synced_at 不是数字格式，跳过缓存
                        print(f"[CACHE-INVALID-TS] {cache_key}: synced_at={synced_at}")
        except Exception as e:
            print(f"[CACHE-ERROR] {cache_key}: {e}")

    # 获取 filter JQL
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT custom_jql, default_jql FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = ?
    """, (version_id, filter_key))
    filter_row = cur.fetchone()
    conn.close()

    if not filter_row:
        raise HTTPException(status_code=404, detail="Filter 不存在")

    # 直接使用数据库中的 JQL，不再动态修改
    jql = filter_row["custom_jql"] or filter_row["default_jql"]

    jira_url = f"{default_jira_url}/issues/?jql={quote(jql)}"

    # 获取凭据（失败时返回错误而非抛异常）
    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    try:
        raw_issues, total = jira_fetch_issues(credential, jql)
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    # 标准化 issue 格式（与原始后端一致）
    from datetime import datetime
    from ..config import JIRA_CUSTOM_FIELDS
    from ..utils import stringify_field_value, parse_dt

    issues = []
    for issue in raw_issues:
        f = issue.get("fields", {})
        assignee = f.get("assignee") or {}
        reporter = f.get("reporter") or {}
        created_time = parse_dt(f.get("created"))
        updated_time = parse_dt(f.get("updated"))
        resolved_time = parse_dt(f.get("resolutiondate"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - datetime.fromisoformat(created_time)).days
            except Exception:
                pass
        stale_days = None
        if updated_time:
            try:
                stale_days = (datetime.now() - datetime.fromisoformat(updated_time)).days
            except Exception:
                pass

        components = f.get("components") or []
        module_name = components[0].get("name") if components else "未归类"

        issues.append({
            "issue_key": issue.get("key", ""),
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "assignee": assignee.get("displayName", "") or assignee.get("name", ""),
            "reporter": reporter.get("displayName", "") or reporter.get("name", ""),
            "created_time": created_time,
            "updated_time": updated_time,
            "resolved_time": resolved_time,
            "aging_days": aging_days,
            "stale_days": stale_days,
            "module_name": module_name,
            "must_fix": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["must_fix"])),
            "severity": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["severity"])),
            "model": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["model"])),
        })

    result = {
        "total": total,
        "issues": issues,
        "jql": jql,
        "jira_url": jira_url,
        "synced_at": now_iso(),
    }

    # ── 保存到缓存（使用 Unix 时间戳，简单可靠）──
    import time as _time
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jira_issue_api_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                cache_key TEXT NOT NULL DEFAULT '',
                data_json TEXT DEFAULT '',
                synced_at TEXT,
                UNIQUE(version_id, cache_key)
            )
        """)
        # 兼容旧表
        try:
            cur.execute("ALTER TABLE jira_issue_api_cache ADD COLUMN cache_key TEXT NOT NULL DEFAULT ''")
            conn.commit()
        except Exception:
            pass
        cur.execute("""
            INSERT INTO jira_issue_api_cache (version_id, cache_key, data_json, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(version_id, cache_key) DO UPDATE SET
                data_json = excluded.data_json,
                synced_at = excluded.synced_at
        """, (version_id, cache_key, _json.dumps(result, ensure_ascii=False, default=str), str(_time.time())))
        conn.commit()
        conn.close()
        print(f"[CACHE-SAVE] {cache_key} (version_id={version_id})")
    except Exception as e:
        print(f"[CACHE-SAVE-ERROR] {cache_key}: {e}")

    return result

@router.get("/api/versions/{version_id}/sr-issues")
def api_get_sr_issues(version_id: int, stage: str = Query("STR1")):
    """获取SR遗留问题"""
    from ..services.cache_service import load_sr_issues_from_cache
    
    issues = load_sr_issues_from_cache(version_id)
    return {"issues": issues, "total": len(issues)}

@router.get("/api/versions/{version_id}/sr-blocking-test-issues")
def api_get_sr_blocking_test_issues(version_id: int, stage: str = Query("STR1")):
    """获取SR阻塞测试的问题（按 labels=阻塞测试 筛选）"""
    from ..services.cache_service import load_sr_issues_from_cache

    issues = load_sr_issues_from_cache(version_id)
    # 过滤出阻塞测试的问题：labels 中包含"阻塞测试"
    blocking = []
    for i in issues:
        labels = i.get("labels") or []
        # 兼容 labels 是字符串或列表的情况
        if isinstance(labels, str):
            try:
                import json
                labels = json.loads(labels)
            except:
                labels = [labels] if labels else []
        if "阻塞测试" in labels:
            blocking.append(i)
    return {"issues": blocking, "total": len(blocking)}

@router.get("/api/versions/{version_id}/filters")
def api_get_filters(version_id: int):
    """获取版本的所有过滤器"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT filter_key, label, description, default_jql, custom_jql, updated_at
    FROM jira_filter_preset
    WHERE version_id = ?
    ORDER BY id ASC
    """, (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"filters": rows}

class FilterUpdate(BaseModel):
    custom_jql: str

@router.put("/api/versions/{version_id}/filters/{filter_key}")
def api_update_filter(version_id: int, filter_key: str, body: FilterUpdate):
    """更新过滤器"""
    from ..utils import now_iso
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Filter 不存在")

    updated_at = now_iso()
    cur.execute("""
    UPDATE jira_filter_preset
    SET custom_jql = ?, updated_at = ?
    WHERE version_id = ? AND filter_key = ?
    """, (body.custom_jql.strip(), updated_at, version_id, filter_key))

    # 清除所有相关的缓存，确保下次查询使用新的 JQL
    # 清除该 filter 的所有阶段缓存
    cur.execute("""
    DELETE FROM jira_issue_api_cache
    WHERE version_id = ? AND cache_key LIKE ?
    """, (version_id, f"{filter_key}:%"))
    # 清除分析缓存
    cur.execute("""
    DELETE FROM jira_issue_api_cache
    WHERE version_id = ? AND cache_key LIKE ?
    """, (version_id, "analysis:%"))
    # 如果是 main_sync，还要清除 jira_issue_cache 表
    if filter_key == "main_sync":
        cur.execute("""
        DELETE FROM jira_issue_cache
        WHERE version_id = ?
        """, (version_id,))
        print(f"[FILTER-UPDATE] 已清除 version_id={version_id} 的 jira_issue_cache")
    # 如果是 sr_backlog，清除 SR 专用缓存，确保 SR 遗留问题数据跟随 JQL 更新
    if filter_key == "sr_backlog":
        try:
            cur.execute("DELETE FROM sr_issue_cache WHERE version_id = ?", (version_id,))
            cur.execute("DELETE FROM sr_detail_cache WHERE version_id = ?", (version_id,))
            print(f"[FILTER-UPDATE] 已清除 version_id={version_id} 的 sr_issue_cache 和 sr_detail_cache")
        except Exception as e:
            print(f"[FILTER-UPDATE] 清除 SR 缓存失败: {e}")

    conn.commit()

    # 返回更新后的 filter 数据
    cur.execute("""
    SELECT filter_key, label, description, default_jql, custom_jql, updated_at
    FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = ?
    """, (version_id, filter_key))
    updated_filter = dict(cur.fetchone())
    conn.close()

    print(f"[FILTER-UPDATE] filter_key={filter_key}, custom_jql={body.custom_jql[:50]}...")
    return {"message": "Filter 已更新", "filter": updated_filter}

@router.post("/api/versions/{version_id}/filters/{filter_key}/reset")
def api_reset_filter(version_id: int, filter_key: str):
    """重置过滤器为默认值"""
    from ..utils import now_iso
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Filter 不存在")

    updated_at = now_iso()
    cur.execute("""
    UPDATE jira_filter_preset
    SET custom_jql = NULL, updated_at = ?
    WHERE version_id = ? AND filter_key = ?
    """, (updated_at, version_id, filter_key))

    # 清除相关的缓存，确保下次查询使用新的 JQL
    cur.execute("""
    DELETE FROM jira_issue_api_cache
    WHERE version_id = ? AND (cache_key LIKE ? OR cache_key LIKE ?)
    """, (version_id, f"{filter_key}:%", "analysis:%"))
    # 如果是 sr_backlog，清除 SR 专用缓存
    if filter_key == "sr_backlog":
        try:
            cur.execute("DELETE FROM sr_issue_cache WHERE version_id = ?", (version_id,))
            cur.execute("DELETE FROM sr_detail_cache WHERE version_id = ?", (version_id,))
        except Exception:
            pass

    conn.commit()

    # 返回更新后的 filter 数据
    cur.execute("""
    SELECT filter_key, label, description, default_jql, custom_jql, updated_at
    FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = ?
    """, (version_id, filter_key))
    updated_filter = dict(cur.fetchone())
    conn.close()

    return {"message": "Filter 已还原为默认设定", "filter": updated_filter}

@router.get("/api/versions/{version_id}/jql/{filter_key}")
def api_get_jql(version_id: int, filter_key: str, stage: str = Query("ALL")):
    """获取有效的 JQL（直接从数据库读取，不再动态修改）"""
    from urllib.parse import quote

    default_jira_url = "http://jira.transsion.com"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT custom_jql, default_jql FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = ?
    """, (version_id, filter_key))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Filter 不存在")

    jql = row["custom_jql"] or row["default_jql"]
    is_custom = bool(row["custom_jql"])

    jira_url = f"{default_jira_url}/issues/?jql={quote(jql)}"

    return {
        "filter_key": filter_key,
        "jql_resolved": jql,
        "jira_url": jira_url,
        "is_custom": is_custom,
    }

@router.get("/api/versions/{version_id}/pending-verification-count")
def api_get_pending_verification_count(version_id: int, stage: str = Query("ALL")):
    """查询待验证问题数量（实时从 Jira 查询）"""
    from ..routers.versions import get_version
    from urllib.parse import quote
    import requests as req_lib
    from requests.auth import HTTPBasicAuth

    default_jira_url = "http://jira.transsion.com"
    version = get_version(version_id)
    jira_project = version.get("jira_project", "")

    # 获取 filter JQL
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT custom_jql, default_jql FROM jira_filter_preset
    WHERE version_id = ? AND filter_key = 'pending_verification'
    """, (version_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"total": 0, "jql": "", "jira_url": "", "error": "pending_verification filter 不存在"}

    jql_template = row["custom_jql"] or row["default_jql"]
    primary_project = jira_project.split(",")[0].strip() if jira_project else jira_project
    jql = jql_template.replace("{project}", jira_project).replace("{primary_project}", primary_project)
    jira_url = f"{default_jira_url}/issues/?jql={quote(jql)}"

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    base_url = credential["jira_base_url"].rstrip("/")
    try:
        resp = req_lib.post(
            f"{base_url}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 1, "fields": ["summary"]},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15, verify=False,
        )
    except Exception as e:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": str(e)[:80]}

    if resp.status_code != 200:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": f"Jira 返回 HTTP {resp.status_code}"}

    try:
        data = resp.json()
        total = data.get("total", 0)
    except Exception:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON"}

    return {"total": total, "jql": jql, "jira_url": jira_url}

@router.get("/api/versions/{version_id}/trends")
def api_get_trends(version_id: int, stage: str = Query("ALL")):
    """获取趋势数据"""
    conn = get_conn()
    cur = conn.cursor()
    
    # 获取历史分析快照
    cur.execute("""
    SELECT * FROM analysis_snapshot
    WHERE version_id = ? AND str_stage = ?
    ORDER BY created_at DESC
    LIMIT 30
    """, (version_id, stage))
    
    snapshots = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    # 解析快照数据
    trends = []
    for snapshot in snapshots:
        metrics = snapshot.get("metrics_json", "{}")
        if isinstance(metrics, str):
            import json
            metrics = json.loads(metrics)
        trends.append({
            "date": snapshot.get("created_at", ""),
            "total": metrics.get("total_issue_count", 0),
            "closed": metrics.get("closed_issue_count", 0),
            "unresolved": metrics.get("unresolved_issue_count", 0),
            "high_priority": metrics.get("high_unresolved_count", 0),
        })
    
    return {"trends": trends}


@router.get("/api/versions/{version_id}/utp/pending-verification")
def api_utp_pending_verification(version_id: int, stage: str = Query("ALL")):
    """从数据库缓存加载 UTP 待验证问题数据，缓存为空时自动从 UTP 抓取"""
    import json as _json

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM utp_pending_cache WHERE version_id = ? ORDER BY aging_days DESC", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT synced_at FROM utp_pending_cache WHERE version_id = ? LIMIT 1", (version_id,))
    sync_row = cur.fetchone()
    conn.close()

    if not rows:
        # 缓存为空，自动从 UTP 抓取
        return api_utp_pending_verification_refresh(version_id)

    issues = rows
    synced_at = dict(sync_row).get("synced_at", "") if sync_row else ""

    # 统计部门分布
    dept_map = {}
    for issue in issues:
        dept = issue.get("assignee_third_dept_classified") or "未分类"
        if dept not in dept_map:
            dept_map[dept] = {"name": dept, "count": 0, "resolved": 0, "verified": 0}
        dept_map[dept]["count"] += 1
        if issue.get("status") == "Resolved":
            dept_map[dept]["resolved"] += 1
        elif issue.get("status") == "Verified":
            dept_map[dept]["verified"] += 1

    dept_stats = sorted(dept_map.values(), key=lambda x: -x["count"])

    return {
        "total": len(issues),
        "issues": issues,
        "dept_stats": dept_stats,
        "synced_at": synced_at,
        "source": "UTP",
        "cached": True,
    }


@router.post("/api/versions/{version_id}/utp/pending-verification/refresh")
def api_utp_pending_verification_refresh(version_id: int):
    """从 UTP 刷新待验证问题数据并保存到数据库"""
    from ..services.utp_service import fetch_utp_defects, normalize_utp_record
    from ..routers.versions import get_version

    version = get_version(version_id)
    jira_project = version.get("jira_project", "")
    version_name = version.get("version_name", "")
    # PAD 版本使用基础版本名查询 UTP（如 "tOS17.0 PAD" → "tOS17.0"）
    import re as _re
    version_name_clean = _re.sub(r'\s*PAD\s*$', '', version_name, flags=_re.IGNORECASE).strip() or version_name

    if not jira_project:
        return {"total": 0, "issues": [], "error": "版本未配置 Jira 项目"}

    result = fetch_utp_defects(
        jira_list=[version_name_clean],
        status_list=["Verified", "Resolved"],
        dup_status_list=["Verified", "None", "Resolved", "Closed"],
        max_pages=50,
    )

    if result.get("error"):
        return {"total": 0, "issues": [], "error": result["error"]}

    # 标准化记录
    issues = [normalize_utp_record(r) for r in result["records"]]
    issues.sort(key=lambda x: -(x.get("aging_days") or 0))

    # 保存到数据库
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM utp_pending_cache WHERE version_id = ?", (version_id,))
    synced = now_iso()
    for i in issues:
        cur.execute("""
        INSERT INTO utp_pending_cache (
            version_id, issue_key, jira_url, summary, status, priority, resolution,
            assignee, assignee_third_dept, assignee_third_dept_classified,
            assignee_second_dept, reporter, components, affect_project,
            aging_days, created_time, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version_id, i.get("issue_key", ""), i.get("jira_url", ""),
            i.get("summary", ""), i.get("status", ""), i.get("priority", ""),
            i.get("resolution", ""), i.get("assignee", ""),
            i.get("assignee_third_dept", ""), i.get("assignee_third_dept_classified", ""),
            i.get("assignee_second_dept", ""), i.get("reporter", ""),
            i.get("components", ""), i.get("affect_project", ""),
            i.get("aging_days"), i.get("created_time", ""), synced,
        ))
    conn.commit()
    conn.close()

    # 统计部门分布
    dept_map = {}
    for issue in issues:
        dept = issue.get("assignee_third_dept_classified", "未分类")
        if dept not in dept_map:
            dept_map[dept] = {"name": dept, "count": 0, "resolved": 0, "verified": 0}
        dept_map[dept]["count"] += 1
        if issue.get("status") == "Resolved":
            dept_map[dept]["resolved"] += 1
        elif issue.get("status") == "Verified":
            dept_map[dept]["verified"] += 1

    dept_stats = sorted(dept_map.values(), key=lambda x: -x["count"])

    return {
        "total": len(issues),
        "issues": issues,
        "dept_stats": dept_stats,
        "synced_at": synced,
        "source": "UTP",
        "cached": True,
    }


@router.get("/api/versions/{version_id}/utp/enrich-departments")
def api_utp_enrich_departments(version_id: int, jira_keys: str = Query("")):
    """
    用 UTP 数据为 Jira issue 补充三级部门信息。
    jira_keys: 逗号分隔的 Jira Key 列表，如 TOS170-1234,TOS170-5678
    返回: {departments: {"TOS170-1234": {"assignee_third_dept": "...", "classified": "..."}, ...}}
    """
    from ..services.utp_service import fetch_utp_defects, normalize_utp_record
    from ..routers.versions import get_version

    if not jira_keys:
        return {"departments": {}}

    keys = [k.strip() for k in jira_keys.split(",") if k.strip()]
    version = get_version(version_id)
    version_name = version.get("version_name", "")
    # PAD 版本使用基础版本名查询 UTP
    import re as _re
    version_name_clean = _re.sub(r'\s*PAD\s*$', '', version_name, flags=_re.IGNORECASE).strip() or version_name

    # 从 UTP 获取所有该版本的缺陷（不限状态，用于匹配 Jira Key）
    result = fetch_utp_defects(
        jira_list=[version_name_clean],
        status_list=[],  # 不限状态
        dup_status_list=[],
        max_pages=50,
    )

    if result.get("error"):
        return {"departments": {}, "error": result["error"]}

    # 构建 jira_key → 部门映射
    dept_map = {}
    keys_set = set(keys)
    for row in result["records"]:
        jk = (row.get("jiraKey") or "").strip()
        if jk in keys_set:
            normalized = normalize_utp_record(row)
            dept_map[jk] = {
                "assignee_third_dept": normalized["assignee_third_dept"],
                "classified": normalized["assignee_third_dept_classified"],
                "assignee": normalized["assignee"],
                "assignee_code": normalized["assignee_code"],
            }

    return {"departments": dept_map}


@router.get("/api/versions/{version_id}/issues/by-module")
def api_issues_by_module(version_id: int, module: str = Query(""), stage: str = Query("ALL")):
    """从本地数据库缓存按模块查询问题列表（秒级响应）"""
    conn = get_conn()
    cur = conn.cursor()

    if stage == "ALL":
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    else:
        cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage))

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # 按模块名过滤
    issues = [r for r in rows if (r.get("module_name") or "未归类") == module]

    # 剥离大字段
    HEAVY = {"raw_payload", "description"}
    issues = [{k: v for k, v in i.items() if k not in HEAVY} for i in issues]

    issues.sort(key=lambda x: x.get("risk_score") or 0, reverse=True)

    return {"issues": issues, "total": len(issues), "module": module}