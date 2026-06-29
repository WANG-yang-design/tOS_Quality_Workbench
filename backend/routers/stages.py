from fastapi import APIRouter, HTTPException
from ..database import get_conn
from ..utils import now_iso
from ..models.schemas import FeishuImportRequest

router = APIRouter()

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)

@router.post("/api/versions/{version_id}/stages/import-feishu")
def import_feishu_stages(version_id: int, req: FeishuImportRequest):
    """
    从飞书表格导入STR时间表。
    使用 OAuth user_access_token 访问飞书表格。
    支持按版本名称匹配对应行（同一张表中不同版本有不同行）。
    """
    from ..services.feishu_service import get_cached_user_token, parse_feishu_url, feishu_cell_to_str
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    version_name = version.get("version_name", "")

    # ---- 使用 OAuth user_access_token ----
    access_token = get_cached_user_token()
    if not access_token:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="请先完成飞书 OAuth 授权。点击「飞书登录」按钮，在弹出的窗口中完成授权。"
        )

    # ---- 解析飞书 URL ----
    feishu_url = req.feishu_url.strip()
    wiki_token, sheet_id = parse_feishu_url(feishu_url)

    if not wiki_token:
        conn.close()
        raise HTTPException(status_code=400, detail="无法从URL中解析出wiki token，请检查URL格式")

    print(f"飞书URL解析: wiki_token={wiki_token}, sheet_id={sheet_id}")

    try:
        import requests
        import re
        from ..utils import safe_json
        
        headers = {"Authorization": f"Bearer {access_token}"}

        # 通过 wiki token 获取实际的 spreadsheet token
        obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

        # 获取表格元信息
        meta_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
            headers=headers,
            timeout=10
        )
        meta_data = safe_json(meta_resp, "获取表格元信息")

        if meta_data.get("code") != 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"无法访问飞书表格（code={meta_data.get('code')}，token={obj_token}）。\n"
                    f"请按以下步骤排查：\n"
                    f"1. 打开飞书文档 → 右上角「分享」→ 添加应用机器人为「可阅读」协作者\n"
                    f"2. 确保飞书应用已发布（开发中的应用无法调用API）\n"
                    f"3. 确保应用已开通 sheets:spreadsheet:read 权限\n"
                    f"原始错误: {meta_data.get('msg', '')}"
                )
            )

        sheets = meta_data.get("data", {}).get("sheets", [])
        if not sheets:
            conn.close()
            raise HTTPException(status_code=400, detail="飞书文档中没有找到表格")

        # 使用指定的 sheet_id 或默认第一个
        target_sheet = None
        if sheet_id:
            for s in sheets:
                if s.get("sheet_id") == sheet_id:
                    target_sheet = s
                    break
        if not target_sheet:
            target_sheet = sheets[0]
            sheet_id = target_sheet.get("sheet_id")

        print(f"使用表格: {target_sheet.get('title', '')}, sheet_id={sheet_id}")

        # 读取表格数据（扩大到 100 行）
        range_str = f"{sheet_id}!A1:Z100"
        data_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
            headers=headers,
            timeout=30
        )
        data_json = safe_json(data_resp, "读取表格数据")

        if data_json.get("code") != 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"读取飞书表格数据失败: {data_json.get('msg', '未知错误')}"
            )

        raw_values = data_json.get("data", {}).get("valueRange", {}).get("values", [])
        if not raw_values or len(raw_values) < 3:
            conn.close()
            raise HTTPException(status_code=400, detail="飞书表格数据行数不足，至少需要3行（表头+阶段名+日期）")

        print(f"读取到 {len(raw_values)} 行数据")

        # =============================================
        # 数据清洗：富文本转纯文本
        # =============================================
        values = []
        for row in raw_values:
            values.append([feishu_cell_to_str(cell) for cell in (row or [])])

        # =============================================
        # 智能解析表格结构
        # =============================================

        TARGET_STAGES = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5"]
        str_pattern = re.compile(r'^STR\s*(\d+[A-Za-z]?)$', re.IGNORECASE)
        concept_keywords = {"概念启动", "概念阶段启动", "概念启动会", "concept"}

        # ---- 第1步：在"里程碑"行中严格匹配 STR 列 + 概念启动 ----
        stage_col_map = {}  # {"STR1": col_idx, "概念启动": col_idx, ...}
        milestone_row_idx = None

        def normalize_stage(match_val: str) -> str:
            """将正则匹配到的值规范化为阶段名，如 '4A' -> 'STR4A'"""
            return f"STR{match_val.upper()}"

        def match_cell_to_stage(cell_text: str):
            """匹配单元格文本到阶段名，支持 STR 模式和概念启动关键词"""
            if not cell_text:
                return None
            text = cell_text.strip()
            # STR 模式匹配
            m = str_pattern.match(text)
            if m:
                return normalize_stage(m.group(1))
            # 概念启动关键词匹配
            text_lower = text.lower().replace(" ", "")
            for kw in concept_keywords:
                if kw.lower().replace(" ", "") in text_lower or text_lower in kw.lower().replace(" ", ""):
                    return "概念启动"
            return None

        for row_idx, row in enumerate(values):
            if not row:
                continue
            has_milestone = any(c and "里程碑" in c for c in row)
            if not has_milestone:
                continue
            # 找到"里程碑"行，匹配 STR 列和概念启动
            temp_map = {}
            for col_idx, cell in enumerate(row):
                stage = match_cell_to_stage(cell)
                if stage and stage in TARGET_STAGES and stage not in temp_map:
                    temp_map[stage] = col_idx
            # 找到 >= 3 个 STR 列才认为是正确的里程碑行
            if len(temp_map) >= 3:
                stage_col_map = temp_map
                milestone_row_idx = row_idx
                print(f"里程碑行: row={row_idx}, STR列={stage_col_map}")
                break

        # 兜底：没有"里程碑"行，扫描所有行严格匹配
        if not stage_col_map:
            print("未找到里程碑行，使用全表扫描兜底")
            for row_idx, row in enumerate(values):
                if not row:
                    continue
                for col_idx, cell in enumerate(row):
                    stage = match_cell_to_stage(cell)
                    if stage and stage in TARGET_STAGES and stage not in stage_col_map:
                        stage_col_map[stage] = col_idx

        print(f"最终STR列位置: {stage_col_map}")

        if not stage_col_map:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="未能从表格中识别出任何STR阶段名称（如 STR1、STR2 等）。请确保表格中包含这些标识。"
            )

        # ---- 第2步：从里程碑行下方开始，找版本行和最新的"计划"行 ----
        # 关键：必须从里程碑行（表头结束）下方开始扫描
        search_start = (milestone_row_idx + 1) if milestone_row_idx is not None else 0
        vn_lower = version_name.lower().replace(" ", "")
        version_row_idx = None
        date_row_idx = None

        # 表格结构（里程碑行下方）：
        #   row N:   版本 | tOS16.3 | | 215天 | 计划V0.2 | ...  ← 版本行
        #   row N+1: | | | | 计划V1.1 | ...                      ← 计划子行（第一列为空）
        #   row N+3: | | | | 实际 | ...                           ← 实际行
        #
        # 版本行特征：任意列包含版本名
        # 计划子行特征：第一列为空（子行），且包含"计划"的列以"计划"开头

        for row_idx in range(search_start, len(values)):
            row = values[row_idx]
            if not row:
                continue
            first_cell = (row[0] or "").strip()

            if version_row_idx is None:
                # 寻找版本行：任意列包含版本名（查全部列，不仅仅是前5列）
                row_text = " ".join(str(c or "") for c in row).lower().replace(" ", "")
                if vn_lower in row_text:
                    version_row_idx = row_idx
                    print(f"匹配到版本行: row={row_idx}, first_cell='{first_cell}'")
                    continue
            else:
                # 版本行已找到，在其下方找"计划"子行
                # 计划子行特征：第一列为空（子行），且某个单元格以"计划"开头
                if not first_cell:
                    for cell in row:
                        cell_s = (cell or "").strip().replace(" ", "")
                        if cell_s.startswith("计划") or cell_s.lower().startswith("plan"):
                            date_row_idx = row_idx  # 不 break，继续找更靠下的（取最新）
                            break

        # 兜底：如果版本行已找到但没找到计划行，找日期最多的子行
        if date_row_idx is None and version_row_idx is not None:
            best_row = None
            best_count = 0
            for row_idx in range(version_row_idx, len(values)):
                row = values[row_idx]
                if not row:
                    continue
                # 跳过"实际"行
                has_shiji = any((c or "").strip().replace(" ", "") == "实际" for c in row)
                if has_shiji:
                    continue
                cnt = 0
                for _, col_idx in stage_col_map.items():
                    if col_idx < len(row):
                        raw_cell = raw_values[row_idx][col_idx] if row_idx < len(raw_values) and col_idx < len(raw_values[row_idx]) else None
                        if isinstance(raw_cell, (int, float)):
                            if normalize_feishu_date(raw_cell):
                                cnt += 1
                        elif row[col_idx] and normalize_feishu_date(row[col_idx]):
                            cnt += 1
                if cnt > best_count:
                    best_count = cnt
                    best_row = row_idx
            date_row_idx = best_row

        print(f"版本名={version_name}, 版本行={version_row_idx}, 计划行={date_row_idx}")

        if date_row_idx is None:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"未能找到「{version_name}」对应的日期行。"
                    f"已识别到STR列位置: {stage_col_map}，搜索起始行: {search_start}。"
                    f"请确认表格中里程碑行下方存在「计划Vx.x」行。"
                )
            )

        # ---- 第3步：从计划行提取日期（优先用 raw_values 处理 Excel 日期序列号） ----
        from datetime import datetime, timedelta
        date_row_data = values[date_row_idx]
        raw_date_row = raw_values[date_row_idx] if date_row_idx < len(raw_values) else []

        stage_dates = {}
        for stage, col_idx in stage_col_map.items():
            if col_idx is None or col_idx >= len(date_row_data):
                continue
            # 优先用 raw_values（Excel 日期序列号不会被 feishu_cell_to_str 转坏）
            raw_cell = raw_date_row[col_idx] if col_idx < len(raw_date_row) else None
            if raw_cell:
                parsed = normalize_feishu_date(raw_cell)
                if parsed:
                    stage_dates[stage] = parsed
                    continue
            # 兜底用清洗后的文本
            cell_str = date_row_data[col_idx]
            if cell_str:
                parsed = normalize_feishu_date(cell_str)
                if parsed:
                    stage_dates[stage] = parsed

        print(f"提取到的日期: {stage_dates}")

        if not stage_dates:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"未能从日期行中提取到有效的截止时间。日期行内容: {date_row_data[:10]}"
            )

        # ---- 第4步：更新数据库 ----
        for stage_name, end_date in stage_dates.items():
            cur.execute("""
            UPDATE str_stage_config
            SET end_date = ?
            WHERE version_id = ? AND stage_name = ?
            """, (end_date, version_id, stage_name))

        # 计算开始日期（每个阶段的开始日期 = 上一阶段的结束日期 + 1天）
        stage_order = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5"]
        for i, stage_name in enumerate(stage_order):
            if stage_name not in stage_dates:
                continue

            if i == 0:
                # 第一个阶段的开始日期 = 基线日期 或 end_date - 7天
                baseline_date = version.get("baseline_date", "")
                if baseline_date:
                    start_date = baseline_date
                else:
                    end_dt = datetime.strptime(stage_dates[stage_name], "%Y-%m-%d")
                    start_date = (end_dt - timedelta(days=7)).strftime("%Y-%m-%d")
            else:
                # 其他阶段的开始日期 = 上一阶段的结束日期 + 1天
                prev_stage = stage_order[i - 1]
                if prev_stage in stage_dates:
                    prev_end = datetime.strptime(stage_dates[prev_stage], "%Y-%m-%d")
                    start_date = (prev_end + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    continue

            cur.execute("""
            UPDATE str_stage_config
            SET start_date = ?
            WHERE version_id = ? AND stage_name = ?
            """, (start_date, version_id, stage_name))

        conn.commit()
        conn.close()

        return {
            "message": f"成功从飞书导入 {len(stage_dates)} 个阶段的时间",
            "imported_stages": stage_dates
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")

def resolve_wiki_to_spreadsheet_token(headers: dict, wiki_token: str) -> str:
    """将 wiki token 解析为实际的 spreadsheet token"""
    import requests
    from ..utils import safe_json
    
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={wiki_token}",
        headers=headers,
        timeout=10
    )
    data = safe_json(resp, "解析wiki token")
    
    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail=f"解析wiki token失败: {data.get('msg')}")
    
    node = data.get("data", {}).get("node", {})
    obj_token = node.get("obj_token", "")
    
    if not obj_token:
        raise HTTPException(status_code=400, detail="无法从wiki节点获取obj_token")
    
    return obj_token

def excel_serial_to_date(value: float) -> str:
    """飞书/Excel 日期序列号转 YYYY-MM-DD。基准日 1899-12-30。"""
    try:
        from datetime import datetime, timedelta
        base_date = datetime(1899, 12, 30)
        date_value = base_date + timedelta(days=float(value))
        return date_value.strftime("%Y-%m-%d")
    except Exception:
        return ""


def normalize_feishu_date(raw) -> str:
    """
    将飞书表格中的各种日期格式统一为 YYYY-MM-DD。
    支持：
    - Unix 时间戳（秒级 10位 / 毫秒级 13位）
    - Excel/飞书日期序列号（如 45897 → 2025-08-29）
    - 字符串时间戳、YYYY/MM/DD、YYYY年M月D日、M月D日 等
    """
    import re
    from datetime import datetime, timedelta, timezone

    if raw is None:
        return ""

    CST = timezone(timedelta(hours=8))

    # ---------- 数字类型 ----------
    if isinstance(raw, (int, float)):
        raw_num = raw
    elif isinstance(raw, str):
        raw = raw.strip().lstrip("\t")
        try:
            raw_num = float(raw)
        except (ValueError, TypeError):
            raw_num = None
    else:
        raw_num = None

    if raw_num is not None:
        # 1) Unix 毫秒时间戳（13 位）
        if 1000000000000 <= raw_num <= 9999999999999:
            try:
                return datetime.fromtimestamp(raw_num / 1000.0, tz=CST).strftime("%Y-%m-%d")
            except Exception:
                pass
        # 2) Unix 秒级时间戳（10 位）
        if 1000000000 <= raw_num <= 9999999999:
            try:
                return datetime.fromtimestamp(raw_num, tz=CST).strftime("%Y-%m-%d")
            except Exception:
                pass
        # 3) Excel 日期序列号（典型 38000-55000，覆盖 2009-2036 年）
        if 38000 <= raw_num <= 55000:
            result = excel_serial_to_date(raw_num)
            if result:
                return result
        # 4) 其他数字不作为日期
        return ""

    # ---------- 字符串类型 ----------
    if not raw:
        return ""
    raw = raw.lstrip("\t").strip()
    if not raw:
        return ""

    # 1) YYYY年M月D日
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?', raw)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 2) M月D日（无年份取当前年）
    m = re.match(r'(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?', raw)
    if m:
        return f"{datetime.now().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    # 3) 标准格式 YYYY/MM/DD、YYYY-MM-DD 等
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(raw, yearfirst=True).strftime("%Y-%m-%d")
    except Exception:
        pass

    # 4) 最后尝试直接转字符串
    return str(raw).strip()