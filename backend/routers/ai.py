from fastapi import APIRouter, Query
from ..services.ai_service import (
    get_ai_config, save_ai_config, ai_quality_summary, ai_risk_analysis, ai_weekly_report
)
from ..models.schemas import AIConfigSave

router = APIRouter()

@router.get("/api/ai/config")
def api_get_ai_config():
    """获取AI配置"""
    return get_ai_config()

@router.post("/api/ai/config")
def api_save_ai_config(req: AIConfigSave):
    """保存AI配置"""
    return save_ai_config(req)

@router.post("/api/versions/{version_id}/ai/summary")
def api_ai_quality_summary(version_id: int, stage: str = Query("ALL")):
    """AI 质量报告总结"""
    return ai_quality_summary(version_id, stage)

@router.post("/api/versions/{version_id}/ai/risk")
def api_ai_risk_analysis(version_id: int, stage: str = Query("ALL")):
    """AI 风险解读与行动建议"""
    return ai_risk_analysis(version_id, stage)

@router.post("/api/versions/{version_id}/ai/weekly")
def api_ai_weekly_report(version_id: int, stage: str = Query("ALL")):
    """AI 周报生成"""
    return ai_weekly_report(version_id, stage)