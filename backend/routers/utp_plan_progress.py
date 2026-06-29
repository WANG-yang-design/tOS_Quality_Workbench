"""UTP 测试计划进度"""
from fastapi import APIRouter, HTTPException
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()

def _sort_group(r):
    """根据 plan_status 和 execute_schedule 确定排序分组：0=待下发 1=执行中 2=完成 3=失效"""
    ps = (r.get("plan_status") or "").upper()
    es = r.get("execute_schedule") or 0
    if ps in ("COMPLETED", "CLOSED") or es >= 100:
        return 2
    if ps == "INVALID":
        return 3
    if ps == "RUNNING" or (0 < es < 100):
        return 1
    return 0  # INIT 或未知

def _sort_key(r):
    return (_sort_group(r), -(r.get("execute_schedule") or 0))


@router.get("/api/versions/{version_id}/utp-plan-progress")
def get_plan_progress(version_id: int, force: bool = False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, owner_code FROM version_config WHERE id = ?", (version_id,))
    ver = cur.fetchone()
    if not ver:
        conn.close()
        raise HTTPException(404, "版本不存在")
    ver = dict(ver)
    vname = ver["version_name"]
    ocode = (ver.get("owner_code") or "").strip()

    # 没配工号直接返回提示
    if not ocode:
        conn.close()
        return {"version_name": vname, "owner_code": "", "plans": [],
                "stats": _empty_stats(), "warning": "请先在版本设置中填写负责人（测试）工号"}

    # 读缓存
    cur.execute("SELECT * FROM utp_plan_cache WHERE version_id = ?", (version_id,))
    cached = [dict(r) for r in cur.fetchall()]

    if cached and not force:
        conn.close()
        cached.sort(key=_sort_key)
        return _resp(cached, vname, ocode)

    # 从 UTP 拉取（每个工号单独查）
    codes = [c.strip() for c in ocode.replace("，", ",").split(",") if c.strip()]
    try:
        raw = _fetch_all(codes, vname)
    except Exception as e:
        if cached:
            cached.sort(key=_sort_key)
            conn.close()
            return _resp(cached, vname, ocode, warning=f"UTP 拉取失败: {e}")
        conn.close()
        raise HTTPException(502, f"UTP 拉取失败: {e}")

    # 写缓存
    ts = now_iso()
    seen = set()
    old_map = {r["plan_id"]: r for r in cached}
    for p in raw:
        pid = p["id"]
        seen.add(pid)
        old = old_map.get(pid)
        ps = p.get("planStatus", "")
        es = p.get("executeSchedule", 0)
        if old and old["plan_status"] == ps and old["execute_schedule"] == es:
            continue
        cur.execute("""INSERT INTO utp_plan_cache
            (version_id,plan_id,plan_name,plan_code,plan_type,plan_status,
             test_stage,level,execute_schedule,strategy_schedule,cases_num,
             start_time,end_time,created_by_name,created_by,updated_by_name,
             updated_time,warning_status,board_status,synced_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(version_id,plan_id) DO UPDATE SET
             plan_name=excluded.plan_name, plan_status=excluded.plan_status,
             execute_schedule=excluded.execute_schedule, strategy_schedule=excluded.strategy_schedule,
             cases_num=excluded.cases_num, updated_by_name=excluded.updated_by_name,
             updated_time=excluded.updated_time, warning_status=excluded.warning_status,
             board_status=excluded.board_status, synced_at=excluded.synced_at""",
            (version_id, pid, p.get("testPlanName",""), p.get("testPlanCode",""),
             p.get("testPlanType",""), ps, p.get("testStage",""), p.get("level",""),
             es, p.get("strategySchedule",0), p.get("casesNum",0),
             p.get("startTime",""), p.get("endTime",""),
             p.get("createdByName",""), p.get("createdBy",""),
             p.get("updatedByName",""), p.get("updatedTime",""),
             p.get("warningStatus",""), p.get("boardStatus",""), ts))

    # 清理旧数据
    stale = [r["plan_id"] for r in cached if r["plan_id"] not in seen]
    if stale:
        ph = ",".join("?" * len(stale))
        cur.execute(f"DELETE FROM utp_plan_cache WHERE version_id=? AND plan_id IN ({ph})", [version_id]+stale)

    conn.commit()
    cur.execute("SELECT * FROM utp_plan_cache WHERE version_id=?", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    rows.sort(key=_sort_key)
    return _resp(rows, vname, ocode)


def _resp(rows, vname, ocode, warning=""):
    total = len(rows)
    done = 0
    ing = 0
    todo = 0
    invalid = 0
    synced_at = None
    for r in rows:
        ps = (r.get("plan_status") or "").upper()
        es = r.get("execute_schedule") or 0
        if ps in ("COMPLETED", "CLOSED") or es >= 100:
            done += 1
        elif ps == "INVALID":
            invalid += 1
        elif ps == "RUNNING" or (0 < es < 100):
            ing += 1
        else:
            todo += 1
        # 获取最新的同步时间
        r_synced = r.get("synced_at")
        if r_synced and (not synced_at or r_synced > synced_at):
            synced_at = r_synced
    avg = round(sum((r.get("execute_schedule") or 0) for r in rows) / total, 1) if total else 0
    return {"version_name": vname, "owner_code": ocode, "plans": rows, "warning": warning, "synced_at": synced_at,
            "stats": {"total": total, "completed": done, "in_progress": ing, "not_started": todo, "invalid": invalid, "avg_progress": avg}}


def _empty_stats():
    return {"total": 0, "completed": 0, "in_progress": 0, "not_started": 0, "avg_progress": 0}


def _fetch_all(codes, project_code):
    from ..services.utp_service import _get_alm_credentials, _utp_post
    cred = _get_alm_credentials()
    if not cred:
        raise RuntimeError("未配置 ALM/UTP 凭据")
    merged = {}
    for code in codes:
        payload = {"size": 200, "current": 1, "descs": "", "ascs": "",
                   "param": {"searchKey": project_code, "projectCode": "",
                             "testPlanName": "", "testPlanStatus": "", "testPlanType": "",
                             "level": "", "testStage": "", "testArea": "", "ownerCodes": [code]}}
        data = _utp_post(cred, "/api/testPlan/queryPlanList", payload)
        for r in data.get("data", {}).get("records", []):
            if r.get("projectCode", "").strip() == project_code.strip():
                merged[r["id"]] = r
    return list(merged.values())


@router.post("/api/versions/{version_id}/utp-plan-progress/save-owner-code")
def save_owner_code(version_id: int, req: dict):
    code = (req.get("owner_code") or "").strip().replace("，", ",")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE version_config SET owner_code=? WHERE id=?", (code, version_id))
    conn.commit()
    conn.close()
    return {"owner_code": code}