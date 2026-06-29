from fastapi import APIRouter, Query, Body
from ..services.auto_refresh_service import refresh_versions, get_refresh_status, _get_config
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()


@router.post("/api/auto-refresh")
def api_auto_refresh(version_id: int = Query(None)):
    """手动触发刷新。
    传 version_id 时只刷该版本；不传则刷配置中的所有版本。
    不含 SR 需求详情（ALM）和 AI 分析。
    """
    mode = "manual"
    result = refresh_versions(mode=mode, version_id=version_id)
    return result


@router.get("/api/auto-refresh/status")
def api_auto_refresh_status():
    return get_refresh_status()


@router.get("/api/auto-refresh/config")
def api_get_refresh_config():
    cfg = _get_config()
    return cfg


@router.put("/api/auto-refresh/config")
def api_update_refresh_config(
    enabled: bool = Body(None),
    interval_minutes: int = Body(None),
    work_start: str = Body(None),
    work_end: str = Body(None),
    weekdays: str = Body(None),
    version_ids: str = Body(None),
):
    conn = get_conn()
    cur = conn.cursor()
    updates = []
    vals = []
    if enabled is not None:
        updates.append("enabled = ?")
        vals.append(1 if enabled else 0)
    if interval_minutes is not None:
        updates.append("interval_minutes = ?")
        vals.append(max(5, min(240, interval_minutes)))
    if work_start is not None:
        updates.append("work_start = ?")
        vals.append(work_start)
    if work_end is not None:
        updates.append("work_end = ?")
        vals.append(work_end)
    if weekdays is not None:
        updates.append("weekdays = ?")
        vals.append(weekdays)
    if version_ids is not None:
        updates.append("version_ids = ?")
        vals.append(version_ids)
    if updates:
        updates.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(1)
        cur.execute(f"UPDATE refresh_config SET {', '.join(updates)} WHERE id = ?", vals)
        conn.commit()
    conn.close()
    return {"message": "刷新配置已保存", "config": _get_config()}