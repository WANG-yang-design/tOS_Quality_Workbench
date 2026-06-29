import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException
from ..config import APP_DIR
from ..database import get_conn
from ..utils import now_iso, safe_json

# 飞书 OAuth 配置（从环境变量读取）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_USER_TOKEN_PATH = APP_DIR / "feishu_user_token_cache.json"


def _detect_lan_ip():
    """自动检测本机局域网 IP 地址"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# 默认使用本机 LAN IP，可通过环境变量 FEISHU_LAN_IP 或 FEISHU_REDIRECT_URI 覆盖
FEISHU_LAN_IP = os.environ.get("FEISHU_LAN_IP", _detect_lan_ip())
FEISHU_REDIRECT_URI = os.environ.get("FEISHU_REDIRECT_URI", f"http://{FEISHU_LAN_IP}:8000/api/feishu/callback")
print(f"[飞书OAuth] LAN IP: {FEISHU_LAN_IP}, Redirect URI: {FEISHU_REDIRECT_URI}")

FEISHU_OAUTH_SCOPES = [
    "wiki:node:read",
    "wiki:wiki:readonly",
    "sheets:spreadsheet:read",
    "sheets:spreadsheet.meta:read",
    "drive:drive.metadata:readonly",
]

def load_json_file(path: Path):
    """加载JSON文件"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_json_file(path: Path, data):
    """保存JSON文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def now_ts():
    """获取当前时间戳"""
    return int(time.time())

def get_cached_user_token():
    """获取可用的 user_access_token，过期自动用 refresh_token 刷新。"""
    cache = load_json_file(FEISHU_USER_TOKEN_PATH)
    if not cache:
        print("[飞书Token] 未找到 token 缓存文件，需要重新授权")
        return None

    access_token = cache.get("access_token", "")
    refresh_token = cache.get("refresh_token", "")
    expires_at = int(cache.get("expires_at") or 0)
    refresh_expires_at = int(cache.get("refresh_expires_at") or 0)

    # 未过期（留 5 分钟缓冲）
    if access_token and expires_at > now_ts() + 300:
        return access_token

    # 检查 refresh_token 是否也已过期
    if refresh_token and refresh_expires_at and refresh_expires_at <= now_ts():
        print(f"[飞书Token] refresh_token 已过期（过期时间: {datetime.fromtimestamp(refresh_expires_at).isoformat()}），需要重新授权")
        return None

    # 尝试用 refresh_token 刷新
    if refresh_token:
        remaining = (expires_at - now_ts()) if expires_at else -1
        print(f"[飞书Token] access_token 已过期（剩余 {remaining} 秒），尝试 refresh...")
        try:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "client_id": FEISHU_APP_ID,
                    "client_secret": FEISHU_APP_SECRET,
                    "refresh_token": refresh_token,
                },
                timeout=15,
            )
            data = resp.json()
            code = data.get("code", -1)
            if code != 0:
                msg = data.get("msg", "未知错误")
                print(f"[飞书Token] refresh 请求失败: code={code}, msg={msg}")
                # code=20026 表示 refresh_token 已失效，需要重新授权
                if code in (20026, 20032, 20033):
                    print("[飞书Token] refresh_token 无效或已过期，需要重新授权")
                return None

            token_data = data.get("data", data)
            new_access = token_data.get("access_token")
            new_refresh = token_data.get("refresh_token") or refresh_token
            expires_in = int(token_data.get("expires_in") or 7200)
            refresh_expires_in = int(token_data.get("refresh_expires_in") or 2592000)  # 默认 30 天

            if new_access:
                save_json_file(FEISHU_USER_TOKEN_PATH, {
                    "access_token": new_access,
                    "refresh_token": new_refresh,
                    "expires_in": expires_in,
                    "expires_at": now_ts() + expires_in,
                    "refresh_expires_in": refresh_expires_in,
                    "refresh_expires_at": now_ts() + refresh_expires_in,
                    "refreshed_at": now_iso(),
                })
                print(f"[飞书Token] 刷新成功，access_token 有效期 {expires_in}s，refresh_token 有效期 {refresh_expires_in}s")
                return new_access
            else:
                print(f"[飞书Token] 刷新响应中无 access_token: {json.dumps(data, ensure_ascii=False)[:200]}")
        except requests.exceptions.Timeout:
            print("[飞书Token] 刷新请求超时（15s）")
        except requests.exceptions.ConnectionError as e:
            print(f"[飞书Token] 刷新请求连接失败: {e}")
        except Exception as e:
            print(f"[飞书Token] 刷新异常: {type(e).__name__}: {e}")

    else:
        print("[飞书Token] 无 refresh_token，需要重新授权")

    return None

def get_feishu_config():
    """获取飞书应用配置（secret 脱敏显示）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM feishu_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"app_id": "", "app_secret_masked": ""}
    row_dict = dict(row)
    app_id = row_dict.get("app_id", "")
    secret = row_dict.get("app_secret", "")
    masked = (secret[:6] + "***") if len(secret) > 6 else ("***" if secret else "")
    return {"app_id": app_id, "app_secret_masked": masked}

def save_feishu_config(req):
    """保存飞书应用配置"""
    if not req.app_id or not req.app_secret:
        raise HTTPException(status_code=400, detail="App ID 和 App Secret 不能为空")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE feishu_config SET app_id = ?, app_secret = ?, updated_at = ?
        WHERE id = 1
    """, (req.app_id.strip(), req.app_secret.strip(), now_iso()))
    conn.commit()
    conn.close()
    return {"message": "飞书配置已保存"}

def get_feishu_config_decrypted():
    """获取飞书配置（内部使用）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM feishu_config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    row_dict = dict(row)
    if not row_dict.get("app_id") or not row_dict.get("app_secret"):
        return None
    return {"app_id": row_dict["app_id"], "app_secret": row_dict["app_secret"]}

def feishu_login():
    """跳转到飞书 OAuth 授权页面"""
    from secrets import token_urlsafe
    from urllib.parse import quote
    from fastapi.responses import RedirectResponse
    
    scope_str = " ".join(FEISHU_OAUTH_SCOPES)
    state = token_urlsafe(16)
    auth_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={quote(FEISHU_APP_ID)}"
        f"&redirect_uri={quote(FEISHU_REDIRECT_URI, safe='')}"
        f"&scope={quote(scope_str, safe='')}"
        f"&state={state}"
    )
    return RedirectResponse(url=auth_url)

def feishu_callback(code: str = "", state: str = "", error: str = ""):
    """飞书 OAuth 回调：用 code 换取 user_access_token"""
    from fastapi.responses import Response
    
    if error:
        return Response(
            f"<html><body><h3>授权失败: {error}</h3><p>请关闭此窗口重试。</p></body></html>",
            media_type="text/html; charset=utf-8",
        )
    if not code:
        return Response(
            "<html><body><h3>回调缺少 code</h3></body></html>",
            media_type="text/html; charset=utf-8",
        )
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": FEISHU_APP_ID,
                "client_secret": FEISHU_APP_SECRET,
                "code": code,
                "redirect_uri": FEISHU_REDIRECT_URI,
            },
            timeout=15,
        )
        data = resp.json()
        token_data = data.get("data", data)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in") or 7200)
        refresh_expires_in = int(token_data.get("refresh_expires_in") or 2592000)  # 默认 30 天

        if not access_token:
            return Response(
                f"<html><body><h3>换取 token 失败</h3><pre>{json.dumps(data, ensure_ascii=False, indent=2)}</pre></body></html>",
                media_type="text/html; charset=utf-8",
            )

        save_json_file(FEISHU_USER_TOKEN_PATH, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "expires_at": now_ts() + expires_in,
            "refresh_expires_in": refresh_expires_in,
            "refresh_expires_at": now_ts() + refresh_expires_in,
            "authorized_at": now_iso(),
        })
        print(f"[飞书Token] 授权成功，access_token 有效期 {expires_in}s，refresh_token 有效期 {refresh_expires_in}s")

        return Response(
            """<html><body>
            <h3>✅ 飞书授权成功！</h3>
            <p>此窗口将在 2 秒后自动关闭...</p>
            <script>
                setTimeout(function() {
                    try { window.close(); } catch(e) {}
                    if (window.opener) { window.opener.postMessage('feishu_auth_ok', '*'); }
                }, 2000);
            </script>
            </body></html>""",
            media_type="text/html; charset=utf-8",
        )
    except Exception as e:
        return Response(
            f"<html><body><h3>授权异常</h3><p>{str(e)}</p></body></html>",
            media_type="text/html; charset=utf-8",
        )

def feishu_callback_compat(code: str = "", state: str = "", error: str = ""):
    """兼容路由：飞书应用配置的回调地址是 /callback"""
    return feishu_callback(code=code, state=state, error=error)

def feishu_token_status():
    """查询飞书 OAuth 登录状态（含诊断信息）"""
    cache = load_json_file(FEISHU_USER_TOKEN_PATH)
    if not cache:
        return {"logged_in": False, "reason": "未授权"}

    access_token = cache.get("access_token", "")
    refresh_token = cache.get("refresh_token", "")
    expires_at = int(cache.get("expires_at") or 0)
    refresh_expires_at = int(cache.get("refresh_expires_at") or 0)
    authorized_at = cache.get("authorized_at", "")
    refreshed_at = cache.get("refreshed_at", "")

    # 尝试获取有效 token（会自动刷新）
    token = get_cached_user_token()

    if token:
        expire_ts = int(cache.get("expires_at") or 0)
        return {
            "logged_in": True,
            "expire_at": expire_ts,
            "refresh_expires_at": refresh_expires_at,
            "authorized_at": authorized_at,
            "refreshed_at": refreshed_at,
        }

    # 未登录，返回原因
    reason = "未知"
    if not refresh_token:
        reason = "无 refresh_token，需重新授权"
    elif refresh_expires_at and refresh_expires_at <= now_ts():
        reason = "refresh_token 已过期，需重新授权"
    elif not access_token:
        reason = "无 access_token"

    return {
        "logged_in": False,
        "reason": reason,
        "authorized_at": authorized_at,
        "refresh_expires_at": refresh_expires_at,
    }

def normalize_feishu_date(raw) -> str:
    """规范化飞书日期格式"""
    if not raw:
        return ""
    if isinstance(raw, (int, float)):
        # 飞书日期可能是时间戳（秒或毫秒）
        if raw > 1e12:
            raw = raw / 1000
        try:
            return datetime.fromtimestamp(raw).strftime("%Y-%m-%d")
        except Exception:
            return str(raw)
    return str(raw).strip()

def parse_feishu_url(url: str):
    """解析飞书表格URL，提取 wiki_node_token（或 spreadsheet_token）和 sheet_id。
    支持两种格式：
    - wiki: https://xxx.feishu.cn/wiki/XXX?sheet=YYY
    - sheets: https://xxx.feishu.cn/sheets/XXX?sheet=YYY
    """
    import re
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sheet_id = params.get("sheet", [None])[0]

    # 兜底正则提取 sheet_id
    if not sheet_id:
        m = re.search(r'[?&]sheet=([^&]+)', url)
        if m:
            sheet_id = m.group(1)

    # wiki 格式
    m = re.search(r'/wiki/([a-zA-Z0-9]+)', url)
    if m:
        return m.group(1), sheet_id

    # sheets 格式
    m = re.search(r'/sheets/([a-zA-Z0-9]+)', url)
    if m:
        return m.group(1), sheet_id

    # space 格式
    m = re.search(r'/space/([a-zA-Z0-9]+)', url)
    if m:
        return m.group(1), sheet_id

    raise HTTPException(status_code=400, detail=f"无法解析飞书表格URL: {url[:80]}")

def feishu_cell_to_str(cell) -> str:
    """将飞书单元格值转换为字符串"""
    if cell is None:
        return ""
    if isinstance(cell, list):
        # 处理富文本格式
        parts = []
        for item in cell:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(cell)

def get_feishu_access_token(app_id: str, app_secret: str) -> str:
    """获取飞书应用访问令牌"""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={
            "app_id": app_id,
            "app_secret": app_secret,
        },
        timeout=10,
    )
    data = safe_json(resp, "获取飞书access_token")
    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail=f"获取飞书token失败: {data.get('msg')}")
    return data.get("tenant_access_token")

def resolve_wiki_to_spreadsheet_token(headers: dict, wiki_node_token: str) -> str:
    """
    将 wiki_node_token 解析为实际的 spreadsheet_token。
    """
    wiki_apis = [
        f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={wiki_node_token}",
        f"https://open.feishu.cn/open-apis/wiki/v2/nodes/{wiki_node_token}",
    ]
    for api_path in wiki_apis:
        try:
            wiki_resp = requests.get(api_path, headers=headers, timeout=10)
            if wiki_resp.status_code != 200:
                continue
            wiki_data = wiki_resp.json()
            if wiki_data.get("code") == 0:
                node = wiki_data.get("data", {}).get("node", {})
                obj_token = node.get("obj_token", wiki_node_token)
                print(f"飞书文档信息: obj_token={obj_token}, obj_type={node.get('obj_type', '')}")
                return obj_token
        except Exception as e:
            print(f"Wiki API {api_path} 异常: {e}，跳过")

    # 兜底：直接用 wiki_token 当作 spreadsheet_token
    print(f"Wiki API 均无法解析，尝试直接用 wiki_token={wiki_node_token} 作为 spreadsheet_token")
    return wiki_node_token


def read_feishu_sheet_data(feishu_url: str, access_token: str, sheet_id_filter: str = None):
    """读取飞书表格数据（支持 wiki 和 sheets 两种 URL 格式）"""
    wiki_token, sheet_id = parse_feishu_url(feishu_url)
    if sheet_id_filter:
        sheet_id = sheet_id_filter

    headers = {"Authorization": f"Bearer {access_token}"}

    # 将 wiki token 解析为 spreadsheet token
    obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

    if not sheet_id:
        raise HTTPException(status_code=400, detail="URL中缺少sheet参数")

    # 获取表格元数据
    meta_url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/{sheet_id}"
    resp = requests.get(meta_url, headers=headers, timeout=10)
    meta_data = safe_json(resp, "获取飞书表格元数据")

    if meta_data.get("code") != 0:
        raise HTTPException(status_code=400, detail=f"获取表格元数据失败: {meta_data.get('msg')}")

    # 读取数据
    data_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{sheet_id}"
    resp = requests.get(data_url, headers=headers, timeout=30)
    data = safe_json(resp, "读取飞书表格数据")

    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail=f"读取表格数据失败: {data.get('msg')}")

    return data.get("data", {}).get("valueRange", {}).get("values", [])


def read_feishu_all_sheets(feishu_url: str, access_token: str):
    """
    读取飞书表格的所有 sheet 数据。
    返回 (sheets_meta, all_data)：
    - sheets_meta: [{"sheet_id": "...", "title": "..."}, ...]
    - all_data: {"sheet_id": [[cell, ...], ...], ...}
    与原始后端 main.py 的 read_feishu_sheet_data 行为一致。
    """
    wiki_token, _ = parse_feishu_url(feishu_url)
    headers = {"Authorization": f"Bearer {access_token}"}
    obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

    # 获取所有 sheet 元信息
    meta_resp = requests.get(
        f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
        headers=headers, timeout=10
    )
    meta_data = safe_json(meta_resp, "获取表格元信息")
    if meta_data.get("code") != 0:
        raise ValueError(f"获取表格元信息失败: {meta_data.get('msg', '')}")

    sheets_raw = meta_data.get("data", {}).get("sheets", [])
    sheets_meta = [{"sheet_id": s.get("sheet_id", ""), "title": s.get("title", "")} for s in sheets_raw]

    # 逐个 sheet 读取数据（与原始后端 main.py 一致：A1:AX2000）
    all_data = {}
    for s in sheets_meta:
        sid = s["sheet_id"]
        try:
            range_str = f"{sid}!A1:AX2000"
            data_resp = requests.get(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
                headers=headers, timeout=30
            )
            data_json = safe_json(data_resp, f"读取表格 {s['title']}")
            if data_json.get("code") == 0:
                raw = data_json.get("data", {}).get("valueRange", {}).get("values", [])
                all_data[sid] = [[feishu_cell_to_str(cell) for cell in (row or [])] for row in (raw or [])]
            else:
                print(f"读取 sheet {s['title']} 失败: {data_json.get('msg', '')}")
                all_data[sid] = []
        except Exception as e:
            print(f"读取 sheet {sid} 失败: {e}")
            all_data[sid] = []

    return sheets_meta, all_data

def import_feishu_stages(version_id: int, req):
    """
    从飞书表格导入STR时间表。
    使用 OAuth user_access_token 访问飞书表格。
    支持按版本名称匹配对应行（同一张表中不同版本有不同行）。
    """
    import re
    from ..models.schemas import FeishuImportRequest

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    version = dict(row) if row else None
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
    feishu_url = req.feishu_url.strip() if hasattr(req, 'feishu_url') else str(req).strip()
    wiki_token, sheet_id = parse_feishu_url(feishu_url)

    if not wiki_token:
        conn.close()
        raise HTTPException(status_code=400, detail="无法从URL中解析出wiki token，请检查URL格式")

    try:
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
                detail=f"无法访问飞书表格（code={meta_data.get('code')}）。请确保应用有权限访问该文档。"
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

        # 读取表格数据
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
            raise HTTPException(status_code=400, detail="飞书表格数据行数不足，至少需要3行")

        # 数据清洗：富文本转纯文本
        values = []
        for row_data in raw_values:
            values.append([feishu_cell_to_str(cell) for cell in (row_data or [])])

        # 智能解析表格结构
        TARGET_STAGES = ["STR1", "STR2", "STR3", "STR4", "STR5"]
        str_pattern = re.compile(r'^STR\s*(\d)$', re.IGNORECASE)

        # 在"里程碑"行中严格匹配 STR 列
        stage_col_map = {}
        milestone_row_idx = None

        for row_idx, row in enumerate(values):
            if not row:
                continue
            has_milestone = any(c and "里程碑" in c for c in row)
            if not has_milestone:
                continue
            temp_map = {}
            for col_idx, cell in enumerate(row):
                if not cell:
                    continue
                m = str_pattern.match(cell.strip())
                if m:
                    stage_name = f"STR{m.group(1)}"
                    temp_map[stage_name] = col_idx
            if len(temp_map) >= 3:
                stage_col_map = temp_map
                milestone_row_idx = row_idx
                break

        if not stage_col_map:
            conn.close()
            raise HTTPException(status_code=400, detail="未在飞书表格中找到 STR 阶段列")

        # 查找版本对应的行
        version_row_idx = None
        for row_idx in range(milestone_row_idx + 1, min(milestone_row_idx + 10, len(values))):
            row = values[row_idx]
            if not row:
                continue
            # 检查是否包含版本名称
            row_text = " ".join(str(c) for c in row if c)
            if version_name and version_name in row_text:
                version_row_idx = row_idx
                break

        if version_row_idx is None:
            # 如果找不到版本名，使用第一个数据行
            version_row_idx = milestone_row_idx + 1

        # 提取日期
        version_row = values[version_row_idx]
        stage_dates = {}
        for stage_name, col_idx in stage_col_map.items():
            if col_idx < len(version_row):
                date_str = normalize_feishu_date(version_row[col_idx])
                if date_str:
                    stage_dates[stage_name] = date_str

        if not stage_dates:
            conn.close()
            raise HTTPException(status_code=400, detail="未从飞书表格中解析到日期数据")

        # 更新数据库
        for stage_name, date_str in stage_dates.items():
            cur.execute("""
                INSERT OR REPLACE INTO str_stage_config (version_id, stage_name, start_date, end_date, current_flag)
                VALUES (?, ?, ?, ?, 0)
            """, (version_id, stage_name, date_str, date_str))

        conn.commit()
        conn.close()

        return {
            "message": f"成功导入 {len(stage_dates)} 个阶段的日期",
            "stages": stage_dates
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


def resolve_wiki_to_spreadsheet_token(headers: dict, wiki_token: str) -> str:
    """将 wiki token 解析为实际的 spreadsheet token"""
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={wiki_token}",
        headers=headers,
        timeout=10
    )
    data = safe_json(resp, "解析wiki token")
    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail=f"无法解析wiki token: {data.get('msg')}")

    node = data.get("data", {}).get("node", {})
    obj_token = node.get("obj_token", "")
    if not obj_token:
        raise HTTPException(status_code=400, detail="无法获取spreadsheet token")
    return obj_token