from fastapi import APIRouter, HTTPException
import re
from ..database import get_conn

router = APIRouter()

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def _scan_for_reason_columns(values, data_start_row, conclusion_col, col_map):
    """在数据区域附近扫描，寻找可能的JIRA单/备注列。"""
    if data_start_row >= len(values):
        return
    gr_ng_rows = []
    for r in range(data_start_row, min(data_start_row + 30, len(values))):
        row = values[r]
        if conclusion_col < len(row):
            cv = (row[conclusion_col] or "").strip().upper()
            if cv in ("GR", "NG"):
                gr_ng_rows.append(r)
    if not gr_ng_rows:
        return
    if "remark" not in col_map and conclusion_col is not None:
        col_scores = {}
        for r in gr_ng_rows[:10]:
            row = values[r]
            for c in range(conclusion_col + 1, min(conclusion_col + 6, len(row))):
                v = (row[c] or "").strip()
                if v and len(v) > 2:
                    col_scores[c] = col_scores.get(c, 0) + 1
        if col_scores:
            best_col = max(col_scores, key=col_scores.get)
            if col_scores[best_col] >= 2:
                col_map.setdefault("remark", best_col)


def _detect_col_by_values(values, start_row, search_from_col, valid_set):
    """扫描数据行，找到第一个包含 valid_set 中值的列。"""
    col_votes = {}
    for r in range(start_row, min(start_row + 30, len(values))):
        row = values[r]
        for c in range(search_from_col, len(row)):
            val = (row[c] or "").strip().upper()
            if val in valid_set:
                col_votes[c] = col_votes.get(c, 0) + 1
    if not col_votes:
        return None
    return max(col_votes, key=col_votes.get)


def is_device_sheet_name(title: str) -> bool:
    """判断 sheet 名称是否为机型名。与原始后端 main.py 完全一致。"""
    if not title:
        return False
    title = title.strip()
    title_lower = title.lower()
    exclude_keywords = [
        "汇总", "总览", "说明", "模板", "目录", "概览",
        "统计", "数据", "配置", "设置", "备注", "计划",
        "时间", "进度", "template", "summary", "index",
        "readme", "版本", "阶段",
        "str1", "str2", "str3", "str4", "str5", "sta5", "1+n版本火车",
        "点击切换", "切换机型", "sheet",
    ]
    for kw in exclude_keywords:
        if kw in title_lower:
            return False
    if len(title) > 40:
        return False
    if "指标合并" in title:
        return True
    stripped = title
    stripped = re.sub(r'[（(]?\s*指标合并\s*[）)]?', '', stripped).strip()
    if stripped:
        has_digit = any(c.isdigit() for c in stripped)
        has_alpha = any(c.isalpha() for c in stripped)
        if has_digit and has_alpha:
            return True
    ascii_alpha = [c for c in title if c.isascii() and c.isalpha()]
    has_digit = any(c.isdigit() for c in title)
    if has_digit and ascii_alpha:
        return True
    if len(title) <= 10 and ascii_alpha and not any(c in title for c in "的和与在"):
        return True
    return False


def parse_test_result_sheet(values):
    """从飞书表格中解析测试结果（性能专项）。与原始后端 main.py 完全一致。"""
    if not values or len(values) < 4:
        return None

    header_row_idx = -1
    for i, row in enumerate(values[:10]):
        if not row:
            continue
        row_text = " ".join(str(c or "") for c in row)
        if ("价值方向" in row_text or "目标模型" in row_text) and "指标" in row_text:
            header_row_idx = i
            break

    if header_row_idx < 0:
        return None

    headers = values[header_row_idx]
    conclusion_col = None
    col_map = {}
    for i, h in enumerate(headers):
        h_clean = (h or "").strip()
        if not h_clean:
            continue
        h_lower = h_clean.lower()
        if "目标模型" in h_clean:
            col_map.setdefault("model", i)
        elif "指标优先级" in h_clean:
            col_map.setdefault("priority", i)
        elif "指标" in h_clean and "优先级" not in h_clean and "达成" not in h_clean:
            col_map.setdefault("metric", i)
        elif "评估结论" in h_clean:
            if conclusion_col is None:
                conclusion_col = i
        elif "测试结果" in h_clean:
            col_map.setdefault("test_result", i)
        elif "jira" in h_lower:
            col_map.setdefault("jira", i)
        elif "备注" in h_clean:
            col_map.setdefault("remark", i)

    if "metric" not in col_map:
        return None

    if "priority" not in col_map:
        _PRI_VALS = {"P0", "P1", "P2"}
        for c in range(col_map.get("model", 0), min(col_map.get("metric", 5) + 1, len(headers))):
            hit = 0
            for r in range(header_row_idx + 1, min(header_row_idx + 8, len(values))):
                if c < len(values[r]) and (values[r][c] or "").strip() in _PRI_VALS:
                    hit += 1
            if hit >= 2:
                col_map["priority"] = c
                break

    if conclusion_col is None:
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False}

    go_count = 0
    gr_count = 0
    ng_count = 0
    fail_items = []
    last_target_model = ""
    last_metric = ""
    categories = {}

    def _ensure_cat(name):
        name = name.replace("\n", " ").strip()
        if name not in categories:
            categories[name] = {"name": name, "go": 0, "gr": 0, "ng": 0, "fail_items": []}
        return categories[name]

    for r in range(header_row_idx + 1, len(values)):
        row = values[r]
        if conclusion_col >= len(row):
            continue
        if "model" in col_map and col_map["model"] < len(row):
            v = (row[col_map["model"]] or "").strip()
            if v:
                last_target_model = v
        if "metric" in col_map and col_map["metric"] < len(row):
            v = (row[col_map["metric"]] or "").replace("\n", " ").strip()
            if v:
                last_metric = v

        val = (row[conclusion_col] or "").strip().upper()
        if not val or val not in ("GO", "GR", "NG"):
            continue

        cat_name = last_target_model or "未分类"
        cat = _ensure_cat(cat_name)

        if val == "GO":
            go_count += 1
            cat["go"] += 1
        elif val == "GR":
            gr_count += 1
            cat["gr"] += 1
        elif val == "NG":
            ng_count += 1
            cat["ng"] += 1

        if val in ("GR", "NG"):
            reason_parts = []
            SKIP = {"GO", "GR", "NG", "PASS", "FAIL", "", "/"}
            jira_c = col_map.get("jira")
            if jira_c is not None and jira_c < len(row):
                jv = (row[jira_c] or "").strip()
                if jv and jv.upper() not in SKIP:
                    reason_parts.append(jv)
            remark_c = col_map.get("remark")
            if remark_c is not None and remark_c < len(row):
                rv = (row[remark_c] or "").strip()
                if rv and rv.upper() not in SKIP:
                    reason_parts.append(rv)
            left_col = conclusion_col - 1
            if 0 <= left_col < len(row):
                lv = (row[left_col] or "").strip()
                if lv and lv.upper() not in SKIP and lv not in reason_parts:
                    reason_parts.append(lv)
            right_col = conclusion_col + 1
            if 0 <= right_col < len(row):
                rv = (row[right_col] or "").strip()
                if rv and rv.upper() not in SKIP and rv not in reason_parts:
                    reason_parts.append(rv)
            fail_reason = "；".join(reason_parts) if reason_parts else ""

            metric = last_metric
            priority = (row[col_map["priority"]] if "priority" in col_map and col_map["priority"] < len(row) else "").strip()
            test_result = (row[col_map["test_result"]] if "test_result" in col_map and col_map["test_result"] < len(row) else "").strip()

            item = {
                "target_model": cat_name,
                "metric": metric,
                "priority": priority,
                "test_result": test_result,
                "conclusion": val,
                "fail_reason": fail_reason,
            }
            fail_items.append(item)
            cat["fail_items"].append(item)

    cat_list = list(categories.values())
    return {
        "go_count": go_count, "gr_count": gr_count, "ng_count": ng_count,
        "fail_items": fail_items, "categories": cat_list, "has_conclusion": True,
    }


def parse_battery_result_sheet(values):
    """续航温升专用解析函数。与原始后端 main.py 完全一致。"""
    if not values or len(values) < 3:
        return None

    STRUCTURAL_KEYWORDS = {"指标": 10, "价值方向": 5, "目标模型": 5}
    DATA_KEYWORDS = {
        "评估结论": 1, "业务评估结论": 1, "研测确认结果": 1,
        "测试结果": 1, "JIRA": 1, "jira": 1, "备注": 1,
    }
    ALL_KEYWORDS = {**STRUCTURAL_KEYWORDS, **DATA_KEYWORDS}

    header_row_idx = -1
    best_score = 0
    for i, row in enumerate(values[:10]):
        if not row:
            continue
        row_text = " ".join(str(c or "") for c in row)
        score = sum(w for kw, w in ALL_KEYWORDS.items() if kw in row_text)
        if score > best_score:
            best_score = score
            header_row_idx = i

    if header_row_idx < 0 or best_score < 2:
        return None

    conclusion_col = None
    conclusion_is_ok = False
    conclusion_candidates = []
    col_map = {}

    scan_end = min(header_row_idx + 5, len(values))
    for scan_row_idx in range(header_row_idx, scan_end):
        row = values[scan_row_idx]
        if not row:
            continue
        for i, h in enumerate(row):
            h_clean = (h or "").strip()
            if not h_clean:
                continue
            if h_clean == "评估结论":
                conclusion_candidates.append((i, False, 0))
            elif h_clean == "业务评估结论":
                conclusion_candidates.append((i, False, 1))
            elif h_clean == "研测确认结果":
                conclusion_candidates.append((i, True, 2))
            elif "目标模型" in h_clean:
                col_map.setdefault("model", i)
            elif "价值方向" in h_clean:
                col_map.setdefault("category", i)
            elif "指标" in h_clean and "优先级" not in h_clean and "达成" not in h_clean:
                col_map.setdefault("metric", i)
            elif "测试结果" in h_clean:
                col_map.setdefault("test_result", i)
            elif any(kw in h_clean for kw in ["备注", "说明", "remark", "note", "Remark"]):
                col_map.setdefault("remark", i)

    if "jira" not in col_map:
        for scan_row_idx in range(header_row_idx, scan_end):
            row = values[scan_row_idx]
            if not row:
                continue
            for i, h in enumerate(row):
                h_clean = (h or "").strip()
                if not h_clean:
                    continue
                h_upper = h_clean.upper()
                if ("JIRA" in h_upper or "问题单" in h_clean or "问题链接" in h_clean or "bug" in h_upper):
                    col_map["jira"] = i
                    break
            if "jira" in col_map:
                break

    if conclusion_candidates:
        conclusion_candidates.sort(key=lambda x: x[2])
        best = conclusion_candidates[0]
        conclusion_col = best[0]
        conclusion_is_ok = best[1]

    if conclusion_col is None:
        for scan_row_idx in range(header_row_idx, scan_end):
            row = values[scan_row_idx]
            if not row:
                continue
            for i, h in enumerate(row):
                h_clean = (h or "").strip()
                if not h_clean:
                    continue
                if "结论" in h_clean and "评估" in h_clean:
                    conclusion_col = i
                    break
                if "确认结果" in h_clean:
                    conclusion_col = i
                    conclusion_is_ok = True
                    break
            if conclusion_col is not None:
                break

    if "metric" not in col_map and "category" in col_map:
        col_map["metric"] = col_map["category"]

    if "metric" not in col_map:
        for c in range(min(8, len(values[header_row_idx]))):
            h = (values[header_row_idx][c] or "").strip() if c < len(values[header_row_idx]) else ""
            if h and any('一' <= ch <= '鿿' for ch in h):
                col_map.setdefault("metric", c)
                break

    if conclusion_col is None:
        go_gr_ng_set = {"GO", "GR", "NG", "OK"}
        detected_col = _detect_col_by_values(values, header_row_idx + 1, 0, go_gr_ng_set)
        if detected_col is not None:
            conclusion_col = detected_col

    data_start_row = header_row_idx + 1
    if conclusion_col is not None:
        for r in range(header_row_idx + 1, min(header_row_idx + 8, len(values))):
            row = values[r]
            if conclusion_col < len(row):
                cv = (row[conclusion_col] or "").strip().upper()
                if cv in ("GO", "GR", "NG", "OK"):
                    data_start_row = r
                    break
            data_start_row = r + 1

    if "jira" not in col_map or "remark" not in col_map:
        _scan_for_reason_columns(values, data_start_row, conclusion_col, col_map)

    if "metric" not in col_map:
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False}
    if conclusion_col is None:
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False}

    go_count = 0
    gr_count = 0
    ng_count = 0
    fail_items = []
    last_target_model = ""
    last_metric = ""
    categories = {}

    def _ensure_cat(name):
        name = name.replace("\n", " ").strip()
        if name not in categories:
            categories[name] = {"name": name, "go": 0, "gr": 0, "ng": 0, "fail_items": []}
        return categories[name]

    def _clean(s):
        return (s or "").replace("\n", " ").strip()

    OK_EQUIVALENTS = {"OK", "OKAY", "PASS", "通过"}
    metric_col = col_map.get("metric")
    model_col = col_map.get("model") or col_map.get("category")
    test_result_col = col_map.get("test_result")
    jira_col = col_map.get("jira")
    remark_col = col_map.get("remark")

    for r in range(data_start_row, len(values)):
        row = values[r]
        if conclusion_col >= len(row):
            continue
        if model_col is not None and model_col < len(row):
            v = _clean(row[model_col])
            if v:
                last_target_model = v
        if metric_col is not None and metric_col < len(row):
            v = _clean(row[metric_col])
            if v:
                last_metric = v

        raw_val = (row[conclusion_col] or "").strip()
        val_upper = raw_val.upper()

        if val_upper in ("GO", "GR", "NG"):
            val = val_upper
        elif conclusion_is_ok and val_upper in OK_EQUIVALENTS:
            val = "GO"
        else:
            continue

        cat_name = last_target_model or "未分类"
        cat = _ensure_cat(cat_name)

        if val == "GO":
            go_count += 1
            cat["go"] += 1
        elif val == "GR":
            gr_count += 1
            cat["gr"] += 1
        elif val == "NG":
            ng_count += 1
            cat["ng"] += 1

        if val in ("GR", "NG"):
            reason_parts = []
            if jira_col is not None and jira_col < len(row):
                jv = _clean(row[jira_col])
                if jv:
                    reason_parts.append(jv)
            if remark_col is not None and remark_col < len(row):
                rv = _clean(row[remark_col])
                if rv:
                    reason_parts.append(rv)
            SKIP = {"GO", "GR", "NG", "PASS", "FAIL", "OK", "", "/"}
            left_col = conclusion_col - 1
            if 0 <= left_col < len(row):
                lv = _clean(row[left_col])
                if lv and lv.upper() not in SKIP and lv not in reason_parts:
                    reason_parts.append(lv)
            right_col = conclusion_col + 1
            if 0 <= right_col < len(row):
                rv = _clean(row[right_col])
                if rv and rv.upper() not in SKIP and rv not in reason_parts:
                    reason_parts.append(rv)
            fail_reason = "；".join(reason_parts) if reason_parts else ""

            metric = last_metric if last_metric else ""
            test_result = _clean(row[test_result_col]) if test_result_col is not None and test_result_col < len(row) else ""

            item = {
                "target_model": cat_name,
                "metric": metric,
                "priority": "",
                "test_result": test_result,
                "conclusion": val,
                "fail_reason": fail_reason,
            }
            fail_items.append(item)
            cat["fail_items"].append(item)

    cat_list = list(categories.values())
    return {
        "go_count": go_count, "gr_count": gr_count, "ng_count": ng_count,
        "fail_items": fail_items, "categories": cat_list, "has_conclusion": True,
    }


@router.get("/api/versions/{version_id}/performance")
def get_performance_data(version_id: int):
    """
    从飞书表格读取性能专项数据。
    优先使用 perf_sheet_url，如果没有则回退到 feishu_sheet_url。
    遍历所有 sheet，如果 sheet 名是机型名，则读取其中的测试结果数据。
    与原始后端 main.py 完全一致。
    """
    from ..services.feishu_service import get_cached_user_token, read_feishu_all_sheets

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, feishu_sheet_url, perf_sheet_url FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    feishu_url = (version.get("perf_sheet_url") or "").strip()
    if not feishu_url:
        feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"devices": [], "message": "请先在飞书设置中配置「性能体验表」URL"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"devices": [], "message": "请先完成飞书授权"}

    try:
        sheets_meta, all_data = read_feishu_all_sheets(feishu_url, access_token)
        devices = []
        base_sheet_url = feishu_url.split("?")[0] if feishu_url else ""

        for s in sheets_meta:
            title = s["title"]
            if not is_device_sheet_name(title):
                continue

            values = all_data.get(s["sheet_id"], [])
            result = parse_test_result_sheet(values)
            if result:
                result["device_name"] = title
                result["sheet_url"] = f"{base_sheet_url}?sheet={s['sheet_id']}" if base_sheet_url else ""
                devices.append(result)

        if not devices:
            return {"devices": [], "message": "未找到机型命名的 Sheet（请确认飞书表格中有以机型名命名的 Sheet）"}

        return {"devices": devices}

    except ValueError as e:
        return {"devices": [], "error": str(e)}
    except Exception as e:
        print(f"读取性能数据异常: {e}")
        return {"devices": [], "error": f"读取失败: {str(e)[:100]}"}