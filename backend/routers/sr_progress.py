"""
SR 测试进度：从 UTP 拉取需求任务计划，与本地 SR 数据匹配，展示测试进度。
"""
import json
import re
from fastapi import APIRouter, HTTPException
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()


def row_to_dict(row):
    return dict(row) if row else None


def _extract_sr_coding(text: str) -> str:
    """从 remark/dataSourceRemark 中提取 SR 编号，如 SR-202603-003366"""
    if not text:
        return ""
    m = re.search(r'(SR-\d{6}-\d{6})', text)
    return m.group(1) if m else ""


@router.get("/api/versions/{version_id}/sr-test-progress")
def get_sr_test_progress(version_id: int, force: bool = False):
    """
    获取 SR 测试进度：
    1. 从 UTP 拉取当前版本的需求任务计划列表
    2. 对进度 <100% 的计划拉取详情，提取 SR 编号
    3. 与本地 SR 缓存匹配，返回每个 SR 的测试进度
    4. 进度 100% 的计划缓存后不再重复拉取
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    ver = cur.fetchone()
    if not ver:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")
    version_name = ver["version_name"]

    # 从已有缓存读取
    cur.execute(
        "SELECT * FROM utp_sr_progress_cache WHERE version_id = ? ORDER BY plan_id, sr_coding",
        (version_id,)
    )
    cached_rows = [row_to_dict(r) for r in cur.fetchall()]

    # 如果有缓存且不强制刷新，直接返回
    if cached_rows and not force:
        conn.close()
        return _build_response(cached_rows, version_name)

    # 从 UTP 拉取数据
    try:
        plan_list = _fetch_utp_plan_list(version_name)
    except Exception as e:
        # UTP 拉取失败，返回已有缓存
        if cached_rows:
            conn.close()
            return _build_response(cached_rows, version_name, warning=f"UTP 拉取失败: {str(e)[:100]}")
        conn.close()
        raise HTTPException(status_code=502, detail=f"UTP 拉取失败: {str(e)[:200]}")

    if not plan_list:
        conn.close()
        return _build_response(cached_rows, version_name, warning=f"UTP 中未找到 {version_name} 的需求任务计划")

    # 已有缓存的 plan_id → execute_schedule 映射
    cached_plan_progress = {}
    for r in cached_rows:
        pid = r["plan_id"]
        if pid not in cached_plan_progress:
            cached_plan_progress[pid] = r["execute_schedule"]

    new_cache_rows = []
    plans_to_fetch = []

    for plan in plan_list:
        pid = plan["id"]
        progress = plan.get("executeSchedule", 0)

        if progress >= 100:
            # 进度 100%：如果缓存中已有，标记为 100% 即可
            if pid in cached_plan_progress:
                # 更新进度为 100%
                cur.execute(
                    "UPDATE utp_sr_progress_cache SET execute_schedule = 100, synced_at = ? WHERE version_id = ? AND plan_id = ?",
                    (now_iso(), version_id, pid)
                )
            else:
                # 需要拉取详情来获取 SR 列表
                plans_to_fetch.append(plan)
        else:
            # 进度 <100%：检查是否有变化
            old_progress = cached_plan_progress.get(pid)
            if old_progress is not None and old_progress == progress and not force:
                # 进度没变，用缓存
                continue
            plans_to_fetch.append(plan)

    # 拉取需要更新的计划详情
    for plan in plans_to_fetch:
        try:
            detail = _fetch_utp_plan_detail(plan["id"])
            sr_entries = _extract_sr_from_plan(plan, detail)
            # 删除该计划的旧缓存
            cur.execute(
                "DELETE FROM utp_sr_progress_cache WHERE version_id = ? AND plan_id = ?",
                (version_id, plan["id"])
            )
            ts = now_iso()
            for entry in sr_entries:
                cur.execute(
                    """INSERT INTO utp_sr_progress_cache
                       (version_id, plan_id, plan_name, plan_code, plan_status,
                        execute_schedule, strategy_schedule, sr_coding, sr_name,
                        group_name, owner_name, start_time, end_time, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (version_id, entry["plan_id"], entry["plan_name"], entry["plan_code"],
                     entry["plan_status"], entry["execute_schedule"], entry["strategy_schedule"],
                     entry["sr_coding"], entry["sr_name"], entry["group_name"], entry["owner_name"],
                     entry["start_time"], entry["end_time"], ts)
                )
        except Exception as e:
            print(f"[SR进度] 拉取计划 {plan['id']} 详情失败: {e}")

    conn.commit()

    # 重新读取缓存
    cur.execute(
        "SELECT * FROM utp_sr_progress_cache WHERE version_id = ? ORDER BY plan_id, sr_coding",
        (version_id,)
    )
    cached_rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    return _build_response(cached_rows, version_name)


def _build_response(rows: list, version_name: str, warning: str = "") -> dict:
    """构建响应"""
    # 按 SR 聚合（一个 SR 可能出现在多个测试计划中）
    sr_map = {}
    for r in rows:
        coding = r["sr_coding"]
        if not coding:
            continue
        if coding not in sr_map:
            sr_map[coding] = {
                "sr_coding": coding,
                "sr_name": r["sr_name"],
                "plans": [],
                "max_progress": 0,
            }
        sr_map[coding]["plans"].append({
            "plan_id": r["plan_id"],
            "plan_name": r["plan_name"],
            "plan_status": r["plan_status"],
            "execute_schedule": r["execute_schedule"],
            "group_name": r["group_name"],
            "owner_name": r["owner_name"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
        })
        sr_map[coding]["max_progress"] = max(
            sr_map[coding]["max_progress"], r["execute_schedule"]
        )

    # 统计
    total_srs = len(sr_map)
    completed_srs = sum(1 for s in sr_map.values() if s["max_progress"] >= 100)
    in_progress_srs = sum(1 for s in sr_map.values() if 0 < s["max_progress"] < 100)
    not_started_srs = total_srs - completed_srs - in_progress_srs
    avg_progress = round(
        sum(s["max_progress"] for s in sr_map.values()) / total_srs, 1
    ) if total_srs else 0

    return {
        "version_name": version_name,
        "sr_list": sorted(sr_map.values(), key=lambda x: x["max_progress"]),
        "stats": {
            "total": total_srs,
            "completed": completed_srs,
            "in_progress": in_progress_srs,
            "not_started": not_started_srs,
            "avg_progress": avg_progress,
        },
        "warning": warning,
    }


def _fetch_utp_plan_list(project_code: str) -> list:
    """从 UTP 获取需求任务计划列表"""
    from ..services.utp_service import _get_alm_credentials, _utp_post

    cred = _get_alm_credentials()
    if not cred:
        raise RuntimeError("未配置 ALM/UTP 凭据")

    payload = {
        "size": 50, "current": 1, "descs": "", "ascs": "",
        "param": {
            "searchKey": "需求任务",
            "projectCode": project_code,
            "testPlanName": "", "testPlanStatus": "", "testPlanType": "",
            "level": "", "testStage": "", "testArea": "", "ownerCodes": [],
        }
    }
    data = _utp_post(cred, "/api/testPlan/queryPlanList", payload)
    records = data.get("data", {}).get("records", [])
    # 只保留 projectCode 匹配的
    return [r for r in records if r.get("projectCode", "").strip() == project_code.strip()]


def _fetch_utp_plan_detail(plan_id: int) -> dict:
    """获取单个测试计划详情（含 SR 列表）"""
    from ..services.utp_service import _get_alm_credentials, _utp_post

    cred = _get_alm_credentials()
    if not cred:
        raise RuntimeError("未配置 ALM/UTP 凭据")

    data = _utp_post(cred, "/api/testPlan/queryTestPlanDetail", {"id": plan_id})
    return data.get("data", {})


def _extract_sr_from_plan(plan: dict, detail: dict) -> list:
    """从计划详情中提取 SR 信息"""
    results = []
    data_list = detail.get("dataList", [])
    seen_sr = set()

    for item in data_list:
        remark = item.get("remark", "") or item.get("dataSourceRemark", "") or ""
        sr_coding = _extract_sr_coding(remark)
        if not sr_coding or sr_coding in seen_sr:
            continue
        seen_sr.add(sr_coding)

        # 从 remark 中提取 SR 名称
        sr_name = ""
        name_match = re.search(r'SR-\d{6}-\d{6}\(([^)]+)\)', remark)
        if name_match:
            sr_name = name_match.group(1)

        results.append({
            "plan_id": plan["id"],
            "plan_name": plan.get("testPlanName", ""),
            "plan_code": plan.get("testPlanCode", ""),
            "plan_status": plan.get("planStatus", ""),
            "execute_schedule": plan.get("executeSchedule", 0),
            "strategy_schedule": plan.get("strategySchedule", 0),
            "sr_coding": sr_coding,
            "sr_name": sr_name,
            "group_name": item.get("groupName", ""),
            "owner_name": item.get("ownerName", ""),
            "start_time": item.get("startTime", ""),
            "end_time": item.get("endTime", ""),
        })

    return results