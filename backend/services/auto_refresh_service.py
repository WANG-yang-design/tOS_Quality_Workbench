"""
全平台自动/手动刷新服务
- 自动：读取 refresh_config 表配置（间隔、工作时间、版本列表）
- 手动：只刷当前版本
- 刷新内容：Jira 同步 + UTP Weekly + ALM 加锁 SR（不含 SR 需求详情，太慢）
- 不含 AI 分析（需手动触发）
"""

import time
import threading
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

CST = timezone(timedelta(hours=8))

_refresh_status: Dict[str, Any] = {
    "is_refreshing": False,
    "mode": "",
    "last_refresh": None,
    "last_error": None,
    "progress": "",
    "steps": [],
    "errors": [],
}

_scheduler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def get_refresh_status() -> Dict[str, Any]:
    return dict(_refresh_status)


def _get_config() -> Dict[str, Any]:
    """从数据库读取刷新配置"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM refresh_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"enabled": True, "interval_minutes": 30, "work_start": "09:30",
                "work_end": "18:30", "weekdays": "0,1,2,3,4", "version_ids": ""}
    return dict(row)


def _is_work_hours(cfg: Dict) -> bool:
    now = datetime.now(CST)
    weekdays = [int(d.strip()) for d in (cfg.get("weekdays") or "0,1,2,3,4").split(",") if d.strip()]
    if now.weekday() not in weekdays:
        return False
    try:
        h_s, m_s = map(int, cfg.get("work_start", "09:30").split(":"))
        h_e, m_e = map(int, cfg.get("work_end", "18:30").split(":"))
    except Exception:
        h_s, m_s, h_e, m_e = 9, 30, 18, 30
    now_min = now.hour * 60 + now.minute
    return h_s * 60 + m_s <= now_min <= h_e * 60 + m_e


def _get_target_versions(mode: str, version_id: int = None) -> List[Dict]:
    """获取要刷新的版本列表"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    if mode == "manual" and version_id:
        cur.execute("SELECT id, version_name FROM version_config WHERE id = ?", (version_id,))
    else:
        cfg = _get_config()
        vids_str = (cfg.get("version_ids") or "").strip()
        if vids_str:
            vids = [int(v.strip()) for v in vids_str.split(",") if v.strip().isdigit()]
            if vids:
                placeholders = ",".join("?" * len(vids))
                cur.execute(f"SELECT id, version_name FROM version_config WHERE id IN ({placeholders}) ORDER BY id", vids)
            else:
                cur.execute("SELECT id, version_name FROM version_config ORDER BY id")
        else:
            cur.execute("SELECT id, version_name FROM version_config ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _refresh_jira(version_id: int, version_name: str) -> Dict:
    from ..database import get_conn
    from ..services.jira_service import sync_jira_data, get_valid_credential
    from ..models.schemas import SyncRequest
    result = {"step": "Jira", "ok": False, "detail": ""}
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT stage_name FROM str_stage_config WHERE version_id = ? AND current_flag = 1", (version_id,))
        row = cur.fetchone()
        conn.close()
        stage = row["stage_name"] if row else "ALL"
        try:
            get_valid_credential(version_id)
        except Exception:
            result["detail"] = "凭据未配置"
            return result
        req = SyncRequest(use_mock=False, force_full=True)
        sync_result = sync_jira_data(version_id, req, stage)
        result["ok"] = True
        result["detail"] = f"同步 {sync_result.get('synced_count', 0)} 条"
    except Exception as e:
        result["detail"] = str(e)[:100]
    return result


def _refresh_utp(version_id: int, version_name: str) -> Dict:
    result = {"step": "UTP", "ok": False, "detail": ""}
    try:
        from ..routers.utp_weekly import refresh_utp_weekly
        refresh_utp_weekly(version_id)
        result["ok"] = True
        result["detail"] = "已刷新"
    except Exception as e:
        result["detail"] = str(e)[:100]
    return result


def _refresh_alm_locked_sr(version_id: int, version_name: str) -> Dict:
    result = {"step": "ALM加锁SR", "ok": False, "detail": ""}
    try:
        from ..routers.alm_locked_sr import refresh_alm_locked_srs
        refresh_alm_locked_srs(version_id)
        result["ok"] = True
        result["detail"] = "已刷新"
    except Exception as e:
        result["detail"] = str(e)[:100]
    return result


def _refresh_version(version_id: int, version_name: str) -> List[Dict]:
    """刷新单个版本的所有数据（不含 SR 需求详情和 AI）"""
    steps = []
    steps.append(_refresh_jira(version_id, version_name))
    steps.append(_refresh_sr_backlog(version_id, version_name))
    steps.append(_refresh_utp(version_id, version_name))
    steps.append(_refresh_utp_pending(version_id, version_name))
    steps.append(_refresh_alm_locked_sr(version_id, version_name))
    # 清除所有 API 缓存，确保前端下次请求获取最新数据
    _clear_all_api_cache(version_id)
    # 清除趋势分析缓存，下次访问时自动重新计算
    _clear_trend_cache(version_id)
    return steps


def _refresh_utp_pending(version_id: int, version_name: str) -> Dict:
    """刷新 UTP 待验证问题数据"""
    result = {"step": "UTP待验证", "ok": False, "detail": ""}
    try:
        from ..routers.jira import api_utp_pending_verification_refresh
        api_utp_pending_verification_refresh(version_id)
        result["ok"] = True
        result["detail"] = "已刷新"
    except Exception as e:
        result["detail"] = str(e)[:100]
    return result


def _refresh_sr_backlog(version_id: int, version_name: str) -> Dict:
    """刷新 SR 遗留问题缓存（从 Jira 查询，强制刷新）"""
    result = {"step": "SR遗留问题", "ok": False, "detail": ""}
    try:
        from ..routers.sr import refresh_sr_issues
        refresh_sr_issues(version_id, force=True)
        result["ok"] = True
        result["detail"] = "已刷新"
    except Exception as e:
        result["detail"] = str(e)[:100]
    return result


def _clear_trend_cache(version_id: int):
    """清除趋势分析缓存，确保下次读取时重新计算"""
    try:
        from ..database import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM jira_trend_analysis_cache WHERE version_id = ?", (version_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _clear_all_api_cache(version_id: int):
    """清除所有 API 查询缓存，确保前端刷新后获取最新数据"""
    try:
        from ..database import get_conn
        conn = get_conn()
        cur = conn.cursor()
        # 清除通用 Jira issue API 缓存（Open/Reopened, Submitted/Modifying 等）
        cur.execute("DELETE FROM jira_issue_api_cache WHERE version_id = ?", (version_id,))
        conn.commit()
        conn.close()
        print(f"[AutoRefresh] 已清除 version_id={version_id} 的 API 缓存")
    except Exception as e:
        print(f"[AutoRefresh] 清除 API 缓存失败: {e}")


def refresh_versions(mode: str = "manual", version_id: int = None) -> Dict[str, Any]:
    """刷新数据。mode='manual' 刷单版本，mode='auto' 刷配置中的所有版本。"""
    global _refresh_status
    if _refresh_status["is_refreshing"]:
        return {"message": "正在刷新中，请稍后", "status": dict(_refresh_status)}

    versions = _get_target_versions(mode, version_id)
    if not versions:
        return {"message": "无目标版本", "results": []}

    _refresh_status.update({
        "is_refreshing": True, "mode": mode, "progress": f"准备刷新 {len(versions)} 个版本...",
        "steps": [], "errors": [], "last_error": None,
    })

    all_results = []
    try:
        for i, v in enumerate(versions):
            vid, vname = v["id"], v["version_name"]
            _refresh_status["progress"] = f"[{i+1}/{len(versions)}] 正在刷新 {vname}..."
            v_result = {"version_id": vid, "version_name": vname, "steps": []}
            steps = _refresh_version(vid, vname)
            v_result["steps"] = steps
            v_result["ok"] = all(s["ok"] for s in steps)
            for s in steps:
                if not s["ok"] and s["detail"]:
                    _refresh_status["errors"].append(f"{vname}/{s['step']}: {s['detail']}")
            all_results.append(v_result)
            _refresh_status["steps"] = all_results

        _refresh_status["last_refresh"] = datetime.now(CST).isoformat(timespec="seconds")
        _refresh_status["progress"] = "刷新完成"
        return {"message": "刷新完成", "mode": mode, "results": all_results,
                "completed": len(versions), "errors": _refresh_status["errors"]}
    except Exception as e:
        _refresh_status["last_error"] = str(e)[:200]
        return {"message": f"刷新出错: {str(e)[:100]}", "error": str(e)}
    finally:
        _refresh_status["is_refreshing"] = False


def _scheduler_loop():
    # 启动后先等 60 秒，避免刚启动就刷新（用户可能正在手动操作）
    _stop_event.wait(60)
    while not _stop_event.is_set():
        try:
            cfg = _get_config()
            now = datetime.now(CST)
            enabled = bool(cfg.get("enabled"))
            in_hours = _is_work_hours(cfg)
            weekdays_str = cfg.get("weekdays", "0,1,2,3,4")
            work_start = cfg.get("work_start", "09:30")
            work_end = cfg.get("work_end", "18:30")
            interval = cfg.get("interval_minutes", 30)

            if not enabled:
                print(f"[AutoRefresh] 自动刷新已关闭，{interval}分钟后重试")
            elif not in_hours:
                print(f"[AutoRefresh] 非工作时间 (当前{now.strftime('%H:%M')} weekday={now.weekday()}, 配置{work_start}-{work_end} wd={weekdays_str})，{interval}分钟后重试")
            else:
                print(f"[AutoRefresh] 工作时间，开始自动刷新...")
                refresh_versions(mode="auto")
                print(f"[AutoRefresh] 自动刷新完成，{interval}分钟后重试")
        except Exception as e:
            print(f"[AutoRefresh] 调度异常: {e}")
            interval = 30
        _stop_event.wait(interval * 60)


def start_scheduler():
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        print("[AutoRefresh] 调度器已在运行，跳过")
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="auto-refresh")
    _scheduler_thread.start()
    cfg = _get_config()
    now = datetime.now(CST)
    print(f"[AutoRefresh] 调度器已启动 | 当前时间: {now.strftime('%Y-%m-%d %H:%M')} weekday={now.weekday()}")
    print(f"[AutoRefresh] 配置: enabled={cfg.get('enabled')}, 间隔={cfg.get('interval_minutes',30)}分钟, "
          f"工作时间={cfg.get('work_start','09:30')}-{cfg.get('work_end','18:30')}, "
          f"工作日={cfg.get('weekdays','0,1,2,3,4')}, "
          f"版本={cfg.get('version_ids','全部') or '全部'}")
    print(f"[AutoRefresh] 首次检查将在 60 秒后进行")


def stop_scheduler():
    _stop_event.set()