from ..database import get_conn
from ..utils import now_iso

def clear_cache():
    """清空 Jira 缓存数据和过期凭据（保留版本配置和阶段时间）"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM jira_issue_cache")
    cache_count = cur.fetchone()["c"]

    cur.execute("DELETE FROM jira_issue_cache")
    cur.execute("DELETE FROM analysis_snapshot")
    # 清除过期的凭据
    cur.execute(f"DELETE FROM jira_credential WHERE expire_at < '{now_iso()}'")

    conn.commit()
    conn.close()

    return {"message": f"已清空 {cache_count} 条缓存数据和过期凭据"}

def save_sr_details_to_cache(version_id: int, sr_details: list):
    """保存 SR 需求详情到缓存"""
    import json as _json
    conn = get_conn()
    cur = conn.cursor()

    # 先清空该版本的旧数据
    cur.execute("DELETE FROM sr_detail_cache WHERE version_id = ?", (version_id,))

    for sr in sr_details:
        # 字段名兼容：sr_coding / coding, sr_name / name 等
        coding = sr.get("sr_coding") or sr.get("coding", "")
        name = sr.get("sr_name") or sr.get("name", "")
        status = sr.get("sr_status") or sr.get("status", "")
        priority = sr.get("sr_priority") or sr.get("priority", "")

        # list 字段需要转为 JSON string
        owners = sr.get("test_module_owners", "")
        if isinstance(owners, list):
            owners = _json.dumps(owners, ensure_ascii=False)
        issue_keys = sr.get("issue_keys", "")
        if isinstance(issue_keys, list):
            issue_keys = _json.dumps(issue_keys, ensure_ascii=False)
        # issue_severity_count 转为 JSON string
        issue_severity_count = sr.get("issue_severity_count", {})
        if isinstance(issue_severity_count, dict):
            issue_severity_count = _json.dumps(issue_severity_count, ensure_ascii=False)
        # issue_severity_keys 转为 JSON string
        issue_severity_keys = sr.get("issue_severity_keys", {})
        if isinstance(issue_severity_keys, dict):
            issue_severity_keys = _json.dumps(issue_severity_keys, ensure_ascii=False)

        cur.execute("""
        INSERT INTO sr_detail_cache (
            version_id, sr_coding, sr_name, sr_status, sr_priority,
            planned_acceptance, test_module_owners, test_module_owners_display,
            issue_count, issue_keys, issue_severity_count, issue_severity_keys,
            is_other_version, other_version_reason, bid, third_dept, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version_id,
            coding,
            name,
            status,
            priority,
            sr.get("planned_acceptance", ""),
            owners,
            sr.get("test_module_owners_display", ""),
            sr.get("issue_count", 0),
            issue_keys,
            issue_severity_count,
            issue_severity_keys,
            1 if sr.get("is_other_version") else 0,
            sr.get("other_version_reason", ""),
            sr.get("bid", ""),
            sr.get("third_dept", ""),
            now_iso()
        ))

    conn.commit()
    conn.close()

def load_sr_details_from_cache(version_id: int) -> dict:
    """从缓存加载 SR 需求详情"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? ORDER BY issue_count DESC", (version_id,))
    rows = cur.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        rd = dict(row)
        sr_coding = rd.get("sr_coding", "")
        if sr_coding:
            result[sr_coding] = rd
    
    return result

def get_sr_detail_cached(version_id: int):
    """获取缓存的 SR 需求详情"""
    return load_sr_details_from_cache(version_id)

def save_sr_issues_to_cache(version_id: int, issues: list):
    """保存 SR 遗留问题到缓存"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 先清空该版本的旧数据
        cur.execute("DELETE FROM sr_issue_cache WHERE version_id = ?", (version_id,))

        synced = now_iso()
        for issue in issues:
            # labels 可能是 list，需要转为 string
            labels = issue.get("labels", "")
            if isinstance(labels, list):
                labels = ",".join(labels)

            cur.execute("""
            INSERT INTO sr_issue_cache (
                version_id, issue_key, summary, status, priority,
                assignee, reporter, created_time, aging_days, labels, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version_id,
                issue.get("issue_key", ""),
                issue.get("summary", ""),
                issue.get("status", ""),
                issue.get("priority", ""),
                issue.get("assignee", ""),
                issue.get("reporter", ""),
                issue.get("created_time", ""),
                issue.get("aging_days"),
                labels,
                synced
            ))

        conn.commit()
    finally:
        conn.close()

def load_sr_issues_from_cache(version_id: int) -> list:
    """从缓存加载 SR 遗留问题"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_issue_cache WHERE version_id = ? ORDER BY aging_days DESC", (version_id,))
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_sr_issues_cached(version_id: int):
    """获取缓存的 SR 遗留问题"""
    return load_sr_issues_from_cache(version_id)