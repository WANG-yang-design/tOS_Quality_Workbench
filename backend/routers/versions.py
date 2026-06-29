import sqlite3
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from ..database import get_conn
from ..utils import now_iso
from ..models.schemas import VersionCreate, VersionUpdate, StageBatchUpdate

router = APIRouter()

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)

def get_version(version_id: int):
    """获取版本信息"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")
    return row

def get_stage(version_id: int, stage_name: str):
    """获取阶段信息"""
    if stage_name == "ALL":
        return None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ? AND stage_name = ?
    """, (version_id, stage_name))
    row = row_to_dict(cur.fetchone())
    conn.close()
    return row

@router.get("/api/versions")
def list_versions():
    """获取所有版本列表"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config ORDER BY id ASC")
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@router.post("/api/versions")
def create_version(req: VersionCreate):
    """创建新版本"""
    conn = get_conn()
    cur = conn.cursor()

    fix_version = req.jira_fix_version or req.version_name

    # PAD 版本自动继承同基础版本的 ALM BID
    alm_space = req.alm_space_bid or ""
    alm_app = req.alm_app_bid or ""
    if req.is_pad and not alm_space:
        # 从版本名提取基础版本（如 "tOS16.3 PAD" → "tOS16.3"）
        import re
        base_name = re.sub(r'\s*PAD\s*$', '', req.version_name, flags=re.IGNORECASE).strip()
        if base_name and base_name != req.version_name:
            cur.execute("SELECT alm_space_bid, alm_app_bid FROM version_config WHERE version_name = ? AND (is_pad = 0 OR is_pad IS NULL)", (base_name,))
            base_row = cur.fetchone()
            if base_row:
                alm_space = alm_space or (base_row["alm_space_bid"] or "")
                alm_app = alm_app or (base_row["alm_app_bid"] or "")
                print(f"[CREATE] PAD version inheriting ALM BID from '{base_name}': space={alm_space}, app={alm_app}")

    try:
        cur.execute("""
        INSERT INTO version_config (
            version_name, jira_project, jira_fix_version, owner_name, is_train_version, is_pad, utp_owner_codes, created_at,
            baseline_date, branch_name, device_count, device_list, coverage_scope, project_status,
            alm_space_bid, alm_app_bid, owner_code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.version_name,
            req.jira_project,
            fix_version,
            req.owner_name,
            1 if req.is_train_version else 0,
            1 if req.is_pad else 0,
            req.utp_owner_codes or "",
            now_iso(),
            req.baseline_date or "",
            req.branch_name or f"{req.version_name}_release",
            req.device_count or 6,
            req.device_list or "",
            req.coverage_scope or "手机+PAD",
            req.project_status or "进行中",
            alm_space,
            alm_app,
            req.owner_code or "",
        ))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="该版本已存在")

    version_id = cur.lastrowid

    today = date.today()
    # 创建 概念启动 + STR1-4 + STR4A + STR5 + 1+N版本火车 阶段
    stage_names = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"]
    for i, stage_name in enumerate(stage_names):
        start = today + timedelta(days=i * 7)
        end = start + timedelta(days=6)
        cur.execute("""
        INSERT INTO str_stage_config (
            version_id, stage_name, start_date, end_date, current_flag
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            version_id,
            stage_name,
            start.isoformat(),
            end.isoformat(),
            1 if i == 0 else 0
        ))

    # 播种默认 Jira Filter Presets
    from ..database import _seed_filter_presets
    _seed_filter_presets(cur, force_update=False)

    conn.commit()
    conn.close()

    return {"id": version_id, "message": "版本创建成功"}

@router.get("/api/versions/{version_id}/stages")
def list_stages(version_id: int):
    """获取版本的所有阶段"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ?
    ORDER BY stage_name ASC
    """, (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@router.delete("/api/versions/{version_id}")
def delete_version(version_id: int):
    """删除版本及其所有关联数据"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    version_name = row["version_name"]

    # 删除所有关联数据
    tables = [
        "str_stage_config", "jira_credential", "jira_issue_cache",
        "analysis_snapshot", "sr_issue_cache", "sr_ai_analysis",
        "sr_detail_cache", "sr_ai_priority", "stability_data",
        "test_plans", "value_points", "jira_filter_preset",
        "utp_pending_cache", "ai_analysis_cache",
        "alm_locked_sr_cache", "alm_locked_sr_snapshot",
        "jira_issue_api_cache", "utp_weekly_cache",
        "test_activities", "work_hours", "test_activity_ai_analysis",
    ]
    for table in tables:
        cur.execute(f"DELETE FROM {table} WHERE version_id = ?", (version_id,))

    # 删除版本本身
    cur.execute("DELETE FROM version_config WHERE id = ?", (version_id,))
    conn.commit()
    conn.close()

    print(f"[DELETE] Version '{version_name}' (id={version_id}) and all related data deleted")
    return {"message": f"版本 '{version_name}' 已删除"}


@router.put("/api/versions/{version_id}")
def update_version(version_id: int, req: VersionUpdate):
    """更新版本信息"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    update_fields = []
    update_values = []

    if req.version_name is not None:
        update_fields.append("version_name = ?")
        update_values.append(req.version_name)
    if req.jira_project is not None:
        update_fields.append("jira_project = ?")
        update_values.append(req.jira_project)
    if req.jira_fix_version is not None:
        update_fields.append("jira_fix_version = ?")
        update_values.append(req.jira_fix_version)
    if req.owner_name is not None:
        update_fields.append("owner_name = ?")
        update_values.append(req.owner_name)
    if req.is_train_version is not None:
        update_fields.append("is_train_version = ?")
        update_values.append(1 if req.is_train_version else 0)
    if req.is_pad is not None:
        update_fields.append("is_pad = ?")
        update_values.append(1 if req.is_pad else 0)
    if req.utp_owner_codes is not None:
        update_fields.append("utp_owner_codes = ?")
        update_values.append(req.utp_owner_codes)
    if req.baseline_date is not None:
        update_fields.append("baseline_date = ?")
        update_values.append(req.baseline_date)
    if req.branch_name is not None:
        update_fields.append("branch_name = ?")
        update_values.append(req.branch_name)
    if req.device_count is not None:
        update_fields.append("device_count = ?")
        update_values.append(req.device_count)
    if req.device_list is not None:
        update_fields.append("device_list = ?")
        update_values.append(req.device_list)
    if req.coverage_scope is not None:
        update_fields.append("coverage_scope = ?")
        update_values.append(req.coverage_scope)
    if req.project_status is not None:
        update_fields.append("project_status = ?")
        update_values.append(req.project_status)
    if req.feishu_sheet_url is not None:
        update_fields.append("feishu_sheet_url = ?")
        update_values.append(req.feishu_sheet_url)
    if req.perf_sheet_url is not None:
        update_fields.append("perf_sheet_url = ?")
        update_values.append(req.perf_sheet_url)
    if req.battery_sheet_url is not None:
        update_fields.append("battery_sheet_url = ?")
        update_values.append(req.battery_sheet_url)
    if req.alm_space_bid is not None:
        update_fields.append("alm_space_bid = ?")
        update_values.append(req.alm_space_bid)
    if req.alm_app_bid is not None:
        update_fields.append("alm_app_bid = ?")
        update_values.append(req.alm_app_bid)
    if req.owner_code is not None:
        update_fields.append("owner_code = ?")
        update_values.append(req.owner_code)

    if update_fields:
        update_values.append(version_id)
        sql = f"UPDATE version_config SET {', '.join(update_fields)} WHERE id = ?"
        cur.execute(sql, update_values)

    conn.commit()
    conn.close()

    return {"message": "版本信息更新成功"}

@router.put("/api/versions/{version_id}/stages/batch")
def batch_update_stages(version_id: int, req: StageBatchUpdate):
    """
    批量更新STR阶段的截止时间。
    只需传入每个阶段的 end_date，start_date 自动根据上一阶段截止+1天计算。
    STR1 的开始日期 = 项目基线日期（若未设置则取 STR1 end_date 前推7天）。
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    # 收集截止时间，按阶段顺序
    stage_order = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"]
    end_dates = {}
    current_stage = None

    for stage in req.stages:
        name = stage.get("stage_name", "")
        end_date = stage.get("end_date", "").strip()
        if name in stage_order and end_date:
            end_dates[name] = end_date
        if stage.get("current_flag"):
            current_stage = name

    # 计算每个阶段的开始和结束日期
    baseline_date = version.get("baseline_date", "")
    for i, stage_name in enumerate(stage_order):
        if stage_name not in end_dates:
            continue

        end_date = end_dates[stage_name]
        if stage_name == "概念启动":
            # 概念启动的开始日期 = 基线日期 或 end_date - 7天
            if baseline_date:
                start_date = baseline_date
            else:
                from datetime import datetime
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_date = (end_dt - timedelta(days=7)).strftime("%Y-%m-%d")
        else:
            # 其他阶段的开始日期 = 上一阶段的结束日期 + 1天
            prev_stage = stage_order[i - 1] if i > 0 else None
            if prev_stage and prev_stage in end_dates:
                from datetime import datetime
                prev_end = datetime.strptime(end_dates[prev_stage], "%Y-%m-%d")
                start_date = (prev_end + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                start_date = ""

        cur.execute("""
        UPDATE str_stage_config
        SET start_date = ?, end_date = ?, current_flag = ?
        WHERE version_id = ? AND stage_name = ?
        """, (
            start_date,
            end_date,
            1 if stage_name == current_stage else 0,
            version_id,
            stage_name
        ))

    conn.commit()
    conn.close()

    return {"message": "阶段时间更新成功"}

@router.put("/api/versions/{version_id}/stages/{stage_name}")
def update_stage(version_id: int, stage_name: str, req):
    """更新单个阶段"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ? AND stage_name = ?
    """, (version_id, stage_name))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="阶段不存在")

    update_fields = []
    update_values = []

    if req.start_date is not None:
        update_fields.append("start_date = ?")
        update_values.append(req.start_date)
    if req.end_date is not None:
        update_fields.append("end_date = ?")
        update_values.append(req.end_date)
    if req.current_flag is not None:
        update_fields.append("current_flag = ?")
        update_values.append(req.current_flag)

    if update_fields:
        update_values.append(version_id)
        update_values.append(stage_name)
        sql = f"UPDATE str_stage_config SET {', '.join(update_fields)} WHERE version_id = ? AND stage_name = ?"
        cur.execute(sql, update_values)

    conn.commit()
    conn.close()

    return {"message": f"阶段 {stage_name} 更新成功"}


@router.get("/api/versions/{version_id}/device-info")
def get_device_info(version_id: int):
    """
    从飞书管理书表格中读取机型信息，按分类（首发/衍生/存量SR适配）返回。
    逻辑与原始后端 main.py 完全一致。
    """
    import re
    from collections import Counter
    from ..services.feishu_service import (
        get_cached_user_token, parse_feishu_url, feishu_cell_to_str,
        resolve_wiki_to_spreadsheet_token, safe_json
    )
    import requests as req_lib

    version = get_version(version_id)
    feishu_url = (version.get("feishu_sheet_url") or "").strip()

    if not feishu_url:
        return {"categories": {}, "text": "", "message": "未配置管理书地址"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"categories": {}, "text": "", "message": "请先完成飞书授权"}

    try:
        wiki_token, sheet_id = parse_feishu_url(feishu_url)
        if not wiki_token:
            return {"categories": {}, "text": "", "message": "URL格式无法解析"}

        headers = {"Authorization": f"Bearer {access_token}"}
        obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

        # 获取表格元信息 → 选 sheet
        meta_resp = req_lib.get(
            f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
            headers=headers, timeout=10
        )
        meta_data = safe_json(meta_resp, "获取表格元信息")
        if meta_data.get("code") != 0:
            return {"categories": {}, "text": "", "message": f"无法访问飞书表格: {meta_data.get('msg', '')}"}

        sheets = meta_data.get("data", {}).get("sheets", [])
        if not sheets:
            return {"categories": {}, "text": "", "message": "飞书文档中没有表格"}

        target_sheet = None
        if sheet_id:
            for s in sheets:
                if s.get("sheet_id") == sheet_id:
                    target_sheet = s
                    break
        if not target_sheet:
            target_sheet = sheets[0]
            sheet_id = target_sheet.get("sheet_id")

        # 读取表格（扩大范围覆盖机型区域）
        range_str = f"{sheet_id}!A1:Z200"
        data_resp = req_lib.get(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
            headers=headers, timeout=30
        )
        data_json = safe_json(data_resp, "读取表格数据")
        if data_json.get("code") != 0:
            return {"categories": {}, "text": "", "message": f"读取表格失败: {data_json.get('msg', '')}"}

        raw_values = data_json.get("data", {}).get("valueRange", {}).get("values", [])
        if not raw_values:
            return {"categories": {}, "text": "", "message": "表格数据为空"}

        # 富文本转纯文本
        values = [[feishu_cell_to_str(cell) for cell in (row or [])] for row in raw_values]

        # ---- 机型提取逻辑（与原始后端完全一致）----
        CATEGORY_KEYWORDS = {"首发", "衍生", "存量SR适配"}
        NON_DEVICE_VALUES = CATEGORY_KEYWORDS | {
            "项目计划", "平台-版本", "开发周期", "需求名称", "测试内容",
            "计划", "实际", "规划阶段", "规划启动", "概念阶段", "概念启动",
        }
        categories = {}

        # 第1步：全表扫描，找分类关键词所在的列
        keyword_positions = {}
        for row_idx, row in enumerate(values):
            if not row:
                continue
            for col_idx, cell in enumerate(row):
                kw = (cell or "").strip()
                if kw in CATEGORY_KEYWORDS:
                    keyword_positions.setdefault(kw, []).append((row_idx, col_idx))

        if not keyword_positions:
            return {"categories": {}, "text": "", "message": "未找到机型分类关键词"}

        col_counter = Counter()
        for positions in keyword_positions.values():
            for _, col in positions:
                col_counter[col] += 1
        cat_col = col_counter.most_common(1)[0][0]
        device_col = cat_col + 1

        def is_valid_device_name(name: str) -> bool:
            if not name:
                return False
            if name in NON_DEVICE_VALUES:
                return False
            if re.match(r'^[\d/\-:.年月日\s]+$', name):
                return False
            if re.match(r'^\d+$', name):
                return False
            if '：' in name or ':' in name:
                return False
            if name.startswith("-") or name.startswith("\\"):
                return False
            return True

        # 第2步：对每个分类，读取设备列
        for kw, positions in keyword_positions.items():
            rows_in_cat_col = sorted([r for r, c in positions if c == cat_col])
            if not rows_in_cat_col:
                continue

            start = rows_in_cat_col[0]
            all_cat_rows = []
            for kw2, pos2 in keyword_positions.items():
                for r2, c2 in pos2:
                    if c2 == cat_col and r2 > start:
                        all_cat_rows.append(r2)
            end = min(all_cat_rows) if all_cat_rows else len(values)

            devices = []
            for r in range(start, end):
                if r >= len(values):
                    break
                row = values[r]
                if device_col >= len(row):
                    continue
                dev = (row[device_col] or "").strip()
                if not dev:
                    continue
                if not is_valid_device_name(dev):
                    continue
                lines = [ln.strip() for ln in dev.split("\n") if ln.strip()]
                cleaned = [ln for ln in lines if ln not in {"暂停", "停止", "取消", "\\"}]
                if cleaned:
                    devices.append("\n".join(cleaned))
            if devices:
                categories[kw] = list(dict.fromkeys(devices))

        # 构建显示文本
        display_parts = []
        for cat in ["存量SR适配", "首发", "衍生"]:
            devices = categories.get(cat, [])
            if not devices:
                continue
            seen = set()
            unique = []
            for d in devices:
                if d not in seen:
                    seen.add(d)
                    unique.append(d)
            display_parts.append(f"{cat}：{'、'.join(unique)}")

        text = "\n".join(display_parts) if display_parts else ""
        return {"categories": categories, "text": text, "message": "ok" if text else "未找到机型信息"}

    except Exception as e:
        print(f"读取机型信息异常: {e}")
        return {"categories": {}, "text": "", "message": f"读取失败: {str(e)[:100]}"}


@router.get("/api/versions/{version_id}/contact-map-url")
def get_contact_map_url(version_id: int):
    """获取沟通地图URL：从管理书中查找「测试接口人」或「测试人力」sheet。"""
    from ..services.feishu_service import (
        get_cached_user_token, read_feishu_all_sheets,
        parse_feishu_url, resolve_wiki_to_spreadsheet_token,
    )
    import requests as _requests

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT feishu_sheet_url FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"url": "", "error": "版本不存在"}

    feishu_url = (row["feishu_sheet_url"] or "").strip()
    if not feishu_url:
        return {"url": "", "error": "未配置管理书 URL"}

    try:
        access_token = get_cached_user_token()
        if not access_token:
            return {"url": "", "error": "飞书未授权"}
        sheets_meta, _ = read_feishu_all_sheets(feishu_url, access_token)
        # 获取 spreadsheet_token 用于构造直达链接
        wiki_token, _ = parse_feishu_url(feishu_url)
        headers = {"Authorization": f"Bearer {access_token}"}
        spreadsheet_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)
    except Exception as e:
        return {"url": "", "error": f"读取飞书表格失败: {str(e)[:80]}"}

    # 优先查找"测试接口人"，其次"测试人力"
    target_names = ["测试接口人", "测试人力"]
    for target in target_names:
        for sm in sheets_meta:
            title = sm.get("title", "")
            if target in title:
                sheet_id = sm.get("sheet_id", "")
                if spreadsheet_token and sheet_id:
                    sheet_url = f"https://transsion.feishu.cn/sheets/{spreadsheet_token}?sheet={sheet_id}"
                    return {"url": sheet_url, "sheet_name": title}
                return {"url": feishu_url, "sheet_name": title}

    return {"url": "", "error": f"管理书中未找到「测试接口人」或「测试人力」sheet（共 {len(sheets_meta)} 个 sheet）"}


# ==================== 测试计划相关 ====================

@router.get("/api/versions/{version_id}/test-plans/{plan_type}")
def get_test_plans(version_id: int, plan_type: str):
    """获取该版本指定类型的测试计划列表"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM test_plans WHERE version_id = ? AND plan_type = ? ORDER BY id", (version_id, plan_type))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"plans": rows}


@router.post("/api/versions/{version_id}/test-plans/{plan_type}")
def save_test_plan(version_id: int, plan_type: str, req):
    """保存/更新单个测试计划"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO test_plans (
            version_id, plan_type, device_name, test_items, plan_status,
            plan_start_date, plan_end_date, responsible_person, remark, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, plan_type, device_name) DO UPDATE SET
            test_items = excluded.test_items,
            plan_status = excluded.plan_status,
            plan_start_date = excluded.plan_start_date,
            plan_end_date = excluded.plan_end_date,
            responsible_person = excluded.responsible_person,
            remark = excluded.remark,
            updated_at = excluded.updated_at
    """, (
        version_id, plan_type, req.device_name, req.test_items, req.plan_status,
        req.plan_start_date, req.plan_end_date, req.responsible_person, req.remark, now_iso(),
    ))
    conn.commit()
    conn.close()
    return {"message": "测试计划已保存"}


@router.delete("/api/versions/{version_id}/test-plans/{plan_type}/{device_name}")
def delete_test_plan(version_id: int, plan_type: str, device_name: str):
    """删除单个测试计划"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM test_plans WHERE version_id = ? AND plan_type = ? AND device_name = ?",
                (version_id, plan_type, device_name))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"已删除计划: {device_name}", "deleted": deleted}


# ==================== 价值点相关 ====================

@router.get("/api/versions/{version_id}/value-points")
def get_value_points(version_id: int):
    """获取该版本所有价值点数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM value_points WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    # 计算统计
    total = len(rows)
    pass_count = sum(1 for r in rows if r.get("ir_conclusion") == "PASS")
    fail_count = sum(1 for r in rows if r.get("ir_conclusion") == "FAIL")
    fail_items = [r for r in rows if r.get("ir_conclusion") == "FAIL"]
    return {
        "value_points": rows,
        "stats": {
            "total": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round(pass_count / total * 100, 1) if total > 0 else 0,
            "fail_items": fail_items,
        }
    }


@router.post("/api/versions/{version_id}/value-points")
def save_value_point(version_id: int, req):
    """保存/更新单个价值点"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO value_points (
            version_id, value_name, ir_conclusion, fail_reason, test_owner, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, value_name) DO UPDATE SET
            ir_conclusion = excluded.ir_conclusion,
            fail_reason = excluded.fail_reason,
            test_owner = excluded.test_owner,
            updated_at = excluded.updated_at
    """, (
        version_id, req.value_name, req.ir_conclusion,
        req.fail_reason, req.test_owner, now_iso(),
    ))
    conn.commit()
    conn.close()
    return {"message": "价值点已保存"}


@router.delete("/api/versions/{version_id}/value-points/{value_id}")
def delete_value_point(version_id: int, value_id: int):
    """删除单个价值点"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM value_points WHERE version_id = ? AND id = ?", (version_id, value_id))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": "已删除价值点", "deleted": deleted}