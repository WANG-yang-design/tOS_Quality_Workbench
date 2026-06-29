from fastapi import APIRouter, HTTPException
from ..database import get_conn

router = APIRouter()

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)


@router.get("/api/versions/{version_id}/battery")
def get_battery_data(version_id: int):
    """
    从飞书表格读取续航温升数据。
    优先使用 battery_sheet_url，如果没有则回退到 feishu_sheet_url。
    遍历所有 sheet，如果 sheet 名是机型名，则读取其中的测试结果数据。
    与原始后端 main.py 完全一致。
    """
    from ..services.feishu_service import get_cached_user_token, read_feishu_all_sheets
    from .performance import is_device_sheet_name, parse_battery_result_sheet

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, feishu_sheet_url, battery_sheet_url FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    feishu_url = (version.get("battery_sheet_url") or "").strip()
    if not feishu_url:
        feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"devices": [], "message": "请先在飞书设置中配置「续航体验表」URL"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"devices": [], "message": "请先完成飞书授权"}

    try:
        sheets_meta, all_data = read_feishu_all_sheets(feishu_url, access_token)
        devices = []
        base_sheet_url = feishu_url.split("?")[0] if feishu_url else ""

        for s in sheets_meta:
            title = s["title"]
            is_device = is_device_sheet_name(title)
            values = all_data.get(s["sheet_id"], [])
            result = parse_battery_result_sheet(values) if is_device else None
            if result:
                result["device_name"] = title
                result["sheet_url"] = f"{base_sheet_url}?sheet={s['sheet_id']}" if base_sheet_url else ""
                devices.append(result)

        if not devices:
            return {"devices": [], "message": "未找到机型命名的 Sheet"}

        return {"devices": devices}

    except ValueError as e:
        return {"devices": [], "error": str(e)}
    except Exception as e:
        print(f"读取续航数据异常: {e}")
        return {"devices": [], "error": f"读取失败: {str(e)[:100]}"}

def parse_battery_result_sheet(values: list) -> dict:
    """解析续航结果sheet"""
    if not values or len(values) < 2:
        return None
    
    # 第一行通常是表头
    headers = values[0]
    data_rows = values[1:]
    
    result = {
        "items": [],
        "summary": {}
    }
    
    for row in data_rows:
        if not row:
            continue
        
        item = {}
        for i, header in enumerate(headers):
            if header and i < len(row):
                item[str(header).strip()] = str(row[i]).strip() if row[i] else ""
        
        if item:
            result["items"].append(item)
    
    return result if result["items"] else None