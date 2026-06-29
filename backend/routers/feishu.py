from fastapi import APIRouter
from ..services.feishu_service import (
    get_feishu_config, save_feishu_config, feishu_login, feishu_callback,
    feishu_callback_compat, feishu_token_status
)
from ..models.schemas import FeishuConfigSave

router = APIRouter()

@router.get("/api/feishu/config")
def api_get_feishu_config():
    """获取飞书应用配置"""
    return get_feishu_config()

@router.post("/api/feishu/config")
def api_save_feishu_config(req: FeishuConfigSave):
    """保存飞书应用配置"""
    return save_feishu_config(req)

@router.get("/api/feishu/login")
def api_feishu_login():
    """跳转到飞书 OAuth 授权页面"""
    return feishu_login()

@router.get("/api/feishu/callback")
def api_feishu_callback(code: str = "", state: str = "", error: str = ""):
    """飞书 OAuth 回调"""
    return feishu_callback(code=code, state=state, error=error)

@router.get("/callback")
def api_feishu_callback_compat(code: str = "", state: str = "", error: str = ""):
    """兼容路由：飞书应用配置的回调地址是 /callback"""
    return feishu_callback_compat(code=code, state=state, error=error)

@router.get("/api/feishu/token-status")
def api_feishu_token_status():
    """查询飞书 OAuth 登录状态"""
    return feishu_token_status()