from fastapi import APIRouter
from ..services.alm_service import api_get_alm_config, api_save_alm_config
from ..models.schemas import ALMConfigSave

router = APIRouter()

@router.get("/api/alm/config")
def api_get_alm_config_route():
    """获取ALM配置"""
    return api_get_alm_config()

@router.post("/api/alm/config")
def api_save_alm_config_route(req: ALMConfigSave):
    """保存ALM配置"""
    return api_save_alm_config(req)