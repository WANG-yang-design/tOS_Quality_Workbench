# -*- coding: utf-8 -*-
"""ALM locked SR data router.

Provides:
  GET  /api/versions/{version_id}/alm-locked-srs        -> read from DB cache
  POST /api/versions/{version_id}/alm-locked-srs/refresh -> fetch from ALM, cache, compute delta

Data source: ALM platform, queried by version spaceBid + lockFlag=YES_LOCK.
Storage: alm_locked_sr_cache (detail) + alm_locked_sr_snapshot (summary).
Delta tracking: compares with daily snapshots to show today's/this week's new SRs.
  - Each daily snapshot stores the set of SR codings present on that day.
  - "Today's new" = SRs in today's snapshot but NOT in yesterday's snapshot.
  - "This week's new" = SRs in today's snapshot but NOT in last Monday's snapshot.
  - Daily snapshots are kept for 14 days, older ones are auto-cleaned.
"""
import json as _json
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from ..database import get_conn
from ..utils import now_iso
from ..services.alm_service import (
    get_alm_config, alm_query_locked_srs, alm_summarize_locked_srs, alm_normalize_locked_sr,
    ALM_SR_STATUS_ORDER, ALM_SR_STATUS_NAME_MAP,
)

router = APIRouter()

DAILY_SNAPSHOT_KEEP_DAYS = 14  # 保留最近 14 天的每日快照


def _row_to_dict(row):
    return dict(row) if row else None


def _save_daily_snapshot(cur, version_id: int, new_codings: set):
    """保存今日的 SR 编码快照，并清理过期快照。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    synced = now_iso()

    cur.execute("""
        INSERT INTO alm_locked_sr_daily_snapshot (version_id, snapshot_date, total_count, sr_codings_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(version_id, snapshot_date) DO UPDATE SET
            total_count = excluded.total_count,
            sr_codings_json = excluded.sr_codings_json,
            created_at = excluded.created_at
    """, (version_id, today_str, len(new_codings), _json.dumps(sorted(new_codings), ensure_ascii=False), synced))

    # 清理超过 14 天的旧快照
    cutoff = (datetime.now() - timedelta(days=DAILY_SNAPSHOT_KEEP_DAYS)).strftime("%Y-%m-%d")
    cur.execute("DELETE FROM alm_locked_sr_daily_snapshot WHERE version_id = ? AND snapshot_date < ?",
                (version_id, cutoff))


def _load_snapshot_codings(cur, version_id: int, date_str: str) -> set:
    """加载指定日期的 SR 编码集合。"""
    cur.execute(
        "SELECT sr_codings_json FROM alm_locked_sr_daily_snapshot WHERE version_id = ? AND snapshot_date = ?",
        (version_id, date_str),
    )
    row = cur.fetchone()
    if row and row["sr_codings_json"]:
        try:
            return set(_json.loads(row["sr_codings_json"]))
        except Exception:
            pass
    return set()


def _save_locked_srs_to_db(version_id: int, records: list) -> dict:
    """Save ALM locked SR records to DB and return delta info.

    更新策略：
    - 不再 DELETE+INSERT 所有记录，而是 UPSERT（保留首次出现时间 first_seen_at）
    - 同时保存每日快照，用于精确计算"今日新增"和"本周新增"
    """
    conn = get_conn()
    cur = conn.cursor()
    synced = now_iso()

    # ── 记录旧数据，用于计算 delta ──
    cur.execute("SELECT total_count, status_json FROM alm_locked_sr_snapshot WHERE version_id = ?", (version_id,))
    old_snap = _row_to_dict(cur.fetchone())
    old_codings = set()
    if old_snap:
        cur.execute("SELECT sr_coding FROM alm_locked_sr_cache WHERE version_id = ?", (version_id,))
        old_codings = {r["sr_coding"] for r in cur.fetchall()}

    # ── 批量查询测试主责人姓名 ──
    all_job_numbers: set = set()
    normalized_records = []
    for raw in records:
        rec = alm_normalize_locked_sr(raw)
        coding = rec["sr_coding"]
        if not coding:
            continue
        normalized_records.append(rec)
        tr = rec.get("test_representative", "").strip()
        if tr and tr.isdigit():
            all_job_numbers.add(tr)
        pr = rec.get("person_responsible", "").strip()
        if pr and pr.isdigit():
            all_job_numbers.add(pr)

    user_map: dict = {}
    if all_job_numbers:
        try:
            from ..services.alm_service import get_alm_config as _get_cfg, alm_batch_find_users
            cfg = _get_cfg()
            if cfg and cfg.get("alm_app_id"):
                user_map = alm_batch_find_users(cfg, list(all_job_numbers))
        except Exception as e:
            print(f"[ALM-LOCKED] 批量查询用户姓名失败: {e}")

    # ── UPSERT 数据（保留 first_seen_at，仅更新 synced_at 和其他字段） ──
    new_codings = set()
    for rec in normalized_records:
        coding = rec["sr_coding"]
        new_codings.add(coding)

        # 解析测试主责人姓名
        tr_no = rec.get("test_representative", "").strip()
        tr_display = tr_no
        if tr_no and tr_no in user_map:
            name = str(user_map[tr_no].get("name") or "")
            tr_display = f"{name}({tr_no})" if name else tr_no

        cur.execute("""
            INSERT INTO alm_locked_sr_cache (
                version_id, sr_coding, sr_name, life_cycle_code, life_cycle_name,
                priority, lock_flag, space_bid,
                test_representative, person_responsible, development_representative,
                planned_transfer_test_time, planned_acceptance_start_time,
                actual_development_completion_time, belong_domain, tag, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET
                sr_name = excluded.sr_name,
                life_cycle_code = excluded.life_cycle_code,
                life_cycle_name = excluded.life_cycle_name,
                priority = excluded.priority,
                lock_flag = excluded.lock_flag,
                space_bid = excluded.space_bid,
                test_representative = excluded.test_representative,
                person_responsible = excluded.person_responsible,
                development_representative = excluded.development_representative,
                planned_transfer_test_time = excluded.planned_transfer_test_time,
                planned_acceptance_start_time = excluded.planned_acceptance_start_time,
                actual_development_completion_time = excluded.actual_development_completion_time,
                belong_domain = excluded.belong_domain,
                tag = excluded.tag,
                synced_at = excluded.synced_at
        """, (
            version_id, coding, rec["sr_name"], rec["life_cycle_code"], rec["life_cycle_name"],
            rec["priority"], rec["lock_flag"], rec["space_bid"],
            tr_display, rec["person_responsible"], rec["development_representative"],
            rec["planned_transfer_test_time"], rec["planned_acceptance_start_time"],
            rec["actual_development_completion_time"], rec["belong_domain"],
            rec.get("tag", ""), synced,
        ))

    # ── 删除本次 ALM 返回中不存在的 SR（已从 ALM 移除的） ──
    if new_codings:
        placeholders = ",".join("?" * len(new_codings))
        cur.execute(
            f"DELETE FROM alm_locked_sr_cache WHERE version_id = ? AND sr_coding NOT IN ({placeholders})",
            [version_id] + list(new_codings),
        )
    else:
        cur.execute("DELETE FROM alm_locked_sr_cache WHERE version_id = ?", (version_id,))

    # ── 更新统计快照 ──
    summary = alm_summarize_locked_srs(records)
    status_data = {k: v for k, v in summary.items() if k != "_total"}
    cur.execute("""
        INSERT INTO alm_locked_sr_snapshot (version_id, total_count, status_json, synced_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(version_id) DO UPDATE SET
            total_count = excluded.total_count,
            status_json = excluded.status_json,
            synced_at = excluded.synced_at
    """, (version_id, summary["_total"], _json.dumps(status_data, ensure_ascii=False), synced))

    # ── 保存今日快照（用于精确计算今日/本周新增） ──
    _save_daily_snapshot(cur, version_id, new_codings)

    conn.commit()
    conn.close()

    # ── 计算 delta ──
    added = new_codings - old_codings
    removed = old_codings - new_codings
    old_total = old_snap["total_count"] if old_snap else 0
    new_total = len(records)
    delta = new_total - old_total

    return {
        "added_codings": sorted(added),
        "removed_codings": sorted(removed),
        "added_count": len(added),
        "removed_count": len(removed),
        "old_total": old_total,
        "delta": delta,
    }


def _load_locked_srs_from_db(version_id: int) -> dict:
    """Load locked SR data from DB (snapshot + detail)."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM alm_locked_sr_snapshot WHERE version_id = ?", (version_id,))
    snap = _row_to_dict(cur.fetchone())

    if not snap:
        conn.close()
        return {"cached": False, "total_count": 0, "status_summary": {}, "sr_list": [], "delta": None}

    cur.execute(
        "SELECT * FROM alm_locked_sr_cache WHERE version_id = ? ORDER BY life_cycle_code, sr_coding",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    status_summary = _json.loads(snap.get("status_json") or "{}")
    status_summary["_total"] = snap.get("total_count", 0)

    return {
        "cached": True,
        "total_count": snap.get("total_count", 0),
        "status_summary": status_summary,
        "synced_at": snap.get("synced_at", ""),
        "sr_list": rows,
        "delta": None,  # GET 请求不返回 delta
    }


@router.get("/api/versions/{version_id}/alm-locked-srs")
def get_alm_locked_srs(version_id: int):
    """Read locked SR data from DB cache (fast response)."""
    return _load_locked_srs_from_db(version_id)


def _get_new_srs_today_and_week(version_id: int) -> dict:
    """通过对比每日快照，精确计算今日和本周新增的 SR。

    逻辑：
    - 今日新增 = 今日快照中有、昨日快照中没有的 SR（即今天才出现在 ALM 加锁列表中的 SR）
    - 本周新增 = 今日快照中有、本周一快照中没有的 SR
    - 如果某天没有刷新数据（无快照），则向前查找最近的快照作为基准
    """
    conn = get_conn()
    cur = conn.cursor()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=Monday
    week_start_str = (now - timedelta(days=weekday)).strftime("%Y-%m-%d")

    # 加载今日快照
    today_codings = _load_snapshot_codings(cur, version_id, today_str)

    if not today_codings:
        # 今日没有快照（尚未刷新过），尝试找最近的快照
        cur.execute(
            "SELECT snapshot_date, sr_codings_json FROM alm_locked_sr_daily_snapshot "
            "WHERE version_id = ? ORDER BY snapshot_date DESC LIMIT 1",
            (version_id,),
        )
        row = cur.fetchone()
        if row:
            try:
                today_codings = set(_json.loads(row["sr_codings_json"]))
                today_str = row["snapshot_date"]  # 使用实际快照日期
            except Exception:
                pass

    if not today_codings:
        conn.close()
        return {"today_new": [], "week_new": [], "today_count": 0, "week_count": 0}

    # 加载昨日快照（或向前找最近的）
    yesterday_codings = _load_snapshot_codings(cur, version_id, yesterday_str)
    if not yesterday_codings and yesterday_str != today_str:
        # 向前查找最近的快照（最多 7 天）
        for i in range(2, 8):
            check_date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            yesterday_codings = _load_snapshot_codings(cur, version_id, check_date)
            if yesterday_codings:
                break

    # 加载本周一快照（或向前找最近的）
    week_base_codings = _load_snapshot_codings(cur, version_id, week_start_str)
    if not week_base_codings:
        # 向前查找：找上周一之前的快照
        for i in range(1, 15):
            check_date = (now - timedelta(days=weekday + i)).strftime("%Y-%m-%d")
            week_base_codings = _load_snapshot_codings(cur, version_id, check_date)
            if week_base_codings:
                break

    conn.close()

    # 计算新增：今日有但基准中没有的
    today_new = sorted(today_codings - yesterday_codings) if yesterday_codings else []
    week_new = sorted(today_codings - week_base_codings) if week_base_codings else sorted(today_codings)

    return {
        "today_new": today_new,
        "week_new": week_new,
        "today_count": len(today_new),
        "week_count": len(week_new),
    }


@router.post("/api/versions/{version_id}/alm-locked-srs/refresh")
def refresh_alm_locked_srs(version_id: int):
    """Fetch locked SR data from ALM platform, cache to DB, and compute delta.

    Returns the loaded data plus a `delta` field with added/removed SR info.
    """
    from ..routers.versions import get_version

    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    alm_cfg = get_alm_config()
    if not alm_cfg or not alm_cfg.get("alm_app_id"):
        raise HTTPException(status_code=400, detail="Please configure ALM account first")
    if not alm_cfg.get("uac_username") or not alm_cfg.get("uac_password"):
        raise HTTPException(status_code=400, detail="ALM credentials not configured")

    space_bid = (version.get("alm_space_bid") or "").strip() or (alm_cfg.get("alm_space_bid") or "").strip()
    if not space_bid:
        raise HTTPException(status_code=400, detail="Please configure ALM_SPACE_BID for this version")

    try:
        records = alm_query_locked_srs(alm_cfg, space_bid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ALM query failed: {str(e)[:200]}")

    delta_info = _save_locked_srs_to_db(version_id, records)
    print(f"[ALM-LOCKED] Version {version_id} cached: {len(records)} SRs, "
          f"added: {delta_info['added_count']}, removed: {delta_info['removed_count']}")

    result = _load_locked_srs_from_db(version_id)
    result["delta"] = delta_info
    return result


@router.get("/api/versions/{version_id}/alm-locked-srs/new-today")
def get_new_locked_srs(version_id: int):
    """Get today's and this week's new locked SRs."""
    return _get_new_srs_today_and_week(version_id)