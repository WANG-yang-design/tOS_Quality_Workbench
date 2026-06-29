from fastapi import APIRouter, HTTPException, Query, Body
from ..services.trend_analysis_service import build_trend_analysis

router = APIRouter()


@router.get("/api/versions/{version_id}/jira-trend-analysis")
def api_jira_trend_analysis(version_id: int, stage: str = Query("ALL"),
                             refresh_ai: bool = Query(False),
                             force: bool = Query(False)):
    """
    Jira 趋势分析：基于上一代项目同阶段数据，多维度对比分析。
    参数：
    - stage: 当前阶段（概念启动/STR1/STR2/STR3/STR4/STR4A/STR5/1+N版本火车/ALL）
    - refresh_ai: 是否强制刷新 AI 分析（默认从缓存读取）
    - force: 是否强制重新计算数据（忽略数据缓存，但保留 AI 缓存）
    """
    result = build_trend_analysis(version_id, stage, use_cache=not (refresh_ai or force),
                                   refresh_ai=refresh_ai, force=force)
    return result


@router.post("/api/versions/{version_id}/jira-trend-analysis/refresh-ai")
def api_refresh_trend_ai(version_id: int, stage: str = Query("ALL")):
    """强制刷新 AI 趋势分析（重新计算数据 + 重新调用 AI）"""
    result = build_trend_analysis(version_id, stage, use_cache=False, refresh_ai=True)
    return result