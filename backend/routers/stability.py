from typing import Optional, List
from fastapi import APIRouter, HTTPException, Body
from ..database import get_conn
from ..utils import now_iso
from ..models.schemas import StabilityDeviceData

router = APIRouter()

def row_to_dict(row):
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(row)

@router.get("/api/versions/{version_id}/stability")
def get_stability_data(version_id: int):
    """获取该版本所有机型的稳定性数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stability_data WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"devices": rows}

@router.post("/api/versions/{version_id}/stability")
def save_stability_device(version_id: int, req: StabilityDeviceData):
    """保存/更新单个机型的稳定性数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO stability_data (
            version_id, device_name, rom_version,
            sys_apr_value, sys_apr_threshold, sys_apr_duration,
            app_apr_value, app_apr_threshold, app_apr_duration,
            subsys_apr_value, subsys_apr_threshold, subsys_apr_duration,
            third_apr_value, third_apr_threshold, third_apr_duration,
            jira_keys, remark, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, device_name) DO UPDATE SET
            rom_version = excluded.rom_version,
            sys_apr_value = excluded.sys_apr_value,
            sys_apr_threshold = excluded.sys_apr_threshold,
            sys_apr_duration = excluded.sys_apr_duration,
            app_apr_value = excluded.app_apr_value,
            app_apr_threshold = excluded.app_apr_threshold,
            app_apr_duration = excluded.app_apr_duration,
            subsys_apr_value = excluded.subsys_apr_value,
            subsys_apr_threshold = excluded.subsys_apr_threshold,
            subsys_apr_duration = excluded.subsys_apr_duration,
            third_apr_value = excluded.third_apr_value,
            third_apr_threshold = excluded.third_apr_threshold,
            third_apr_duration = excluded.third_apr_duration,
            jira_keys = excluded.jira_keys,
            remark = excluded.remark,
            updated_at = excluded.updated_at
    """, (
        version_id, req.device_name, req.rom_version,
        req.sys_apr_value, req.sys_apr_threshold, req.sys_apr_duration,
        req.app_apr_value, req.app_apr_threshold, req.app_apr_duration,
        req.subsys_apr_value, req.subsys_apr_threshold, req.subsys_apr_duration,
        req.third_apr_value, req.third_apr_threshold, req.third_apr_duration,
        req.jira_keys, req.remark, now_iso(),
    ))
    conn.commit()
    conn.close()
    return {"message": "稳定性数据已保存"}

@router.post("/api/versions/{version_id}/stability/init")
def init_stability_devices(version_id: int, device_names: Optional[List[str]] = Body(None, embed=False)):
    """根据机型信息初始化稳定性数据（不覆盖已有数据）"""
    from ..routers.versions import get_version
    
    version = get_version(version_id)
    devices = []
    feishu_url = (version.get("feishu_sheet_url") or "").strip()

    # 如果前端传了设备名列表，直接使用
    if device_names:
        devices = [d.strip() for d in device_names if d.strip()]
    else:
        # 优先从飞书管理书读取机型
        if feishu_url:
            try:
                from ..services.feishu_service import get_cached_user_token, parse_feishu_url, feishu_cell_to_str
                from ..routers.stages import resolve_wiki_to_spreadsheet_token
                from ..utils import safe_json
                import requests
                
                access_token = get_cached_user_token()
                if access_token:
                    wiki_token, sheet_id = parse_feishu_url(feishu_url)
                    if wiki_token:
                        headers = {"Authorization": f"Bearer {access_token}"}
                        obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)
                        meta_resp = requests.get(
                            f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
                            headers=headers, timeout=10
                        )
                        meta_data = safe_json(meta_resp, "获取表格元信息")
                        if meta_data.get("code") == 0:
                            sheets = meta_data.get("data", {}).get("sheets", [])
                            target_sheet = None
                            if sheet_id:
                                for s in sheets:
                                    if s.get("sheet_id") == sheet_id:
                                        target_sheet = s
                                        break
                            if not target_sheet and sheets:
                                target_sheet = sheets[0]
                                sheet_id = target_sheet.get("sheet_id")
                            if target_sheet:
                                range_str = f"{sheet_id}!A1:Z200"
                                data_resp = requests.get(
                                    f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
                                    headers=headers, timeout=30
                                )
                                data_json = safe_json(data_resp, "读取表格数据")
                                if data_json.get("code") == 0:
                                    raw_values = data_json.get("data", {}).get("valueRange", {}).get("values", [])
                                    # 从表格中提取设备名称
                                    for row in raw_values:
                                        if row and len(row) > 0:
                                            cell = feishu_cell_to_str(row[0])
                                            if cell and cell.strip():
                                                devices.append(cell.strip())
            except Exception as e:
                print(f"[稳定性] 从飞书读取设备列表失败: {e}")

    # 如果还是没有设备，使用版本配置中的设备列表
    if not devices:
        device_list = version.get("device_list", "")
        if device_list:
            devices = [d.strip() for d in device_list.split(",") if d.strip()]

    # 如果还是没有，使用默认设备
    if not devices:
        devices = ["默认设备"]

    conn = get_conn()
    cur = conn.cursor()

    # 初始化设备数据（不覆盖已有数据）
    for device_name in devices:
        cur.execute("""
        INSERT OR IGNORE INTO stability_data (version_id, device_name, updated_at)
        VALUES (?, ?, ?)
        """, (version_id, device_name, now_iso()))

    conn.commit()
    conn.close()

    return {"message": f"已初始化 {len(devices)} 个设备", "devices": devices}

@router.delete("/api/versions/{version_id}/stability/{device_name:path}")
def delete_stability_device(version_id: int, device_name: str):
    """删除单个机型的稳定性数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM stability_data WHERE version_id = ? AND device_name = ?", (version_id, device_name))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    
    if deleted == 0:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    return {"message": f"已删除设备 {device_name}"}