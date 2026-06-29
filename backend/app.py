import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import os
import time
from collections import OrderedDict
from pathlib import Path

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装时跳过

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 支持直接运行和作为包导入两种方式
try:
    from .database import init_db
    from .routers import versions, stages, jira, feishu, alm, ai, analysis, stability, performance, battery, sr, alm_locked_sr, utp_weekly, custom_risks, agent, trend_analysis, auto_refresh, test_activities, sr_progress, utp_plan_progress, feishu_agent
except ImportError:
    from database import init_db
    from routers import versions, stages, jira, feishu, alm, ai, analysis, stability, performance, battery, sr, alm_locked_sr, utp_weekly, custom_risks, agent, trend_analysis, auto_refresh, test_activities, sr_progress, utp_plan_progress, feishu_agent

app = FastAPI(title="tOS Quality Workbench API", version="0.2.0")

# CORS 配置（从环境变量读取，默认允许本地开发）
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 在线连接追踪 ──
_active_clients: OrderedDict[str, float] = OrderedDict()  # ip -> last_seen_timestamp
_ACTIVE_TIMEOUT = 300  # 5 分钟无活动视为离线

class ConnectionTrackerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        # 排除前端静态资源请求（只追踪 API 请求）
        if request.url.path.startswith("/api/"):
            _active_clients[client_ip] = time.time()
            # 清理超时的 IP
            now = time.time()
            expired = [ip for ip, ts in _active_clients.items() if now - ts > _ACTIVE_TIMEOUT]
            for ip in expired:
                del _active_clients[ip]
        return await call_next(request)

app.add_middleware(ConnectionTrackerMiddleware)

# 注册路由
app.include_router(versions.router)
app.include_router(stages.router)
app.include_router(jira.router)
app.include_router(feishu.router)
app.include_router(alm.router)
app.include_router(ai.router)
app.include_router(analysis.router)
app.include_router(stability.router)
app.include_router(performance.router)
app.include_router(battery.router)
app.include_router(sr.router)
app.include_router(alm_locked_sr.router)
app.include_router(utp_weekly.router)
app.include_router(custom_risks.router)
app.include_router(agent.router)
app.include_router(trend_analysis.router)
app.include_router(auto_refresh.router)
app.include_router(test_activities.router)
app.include_router(sr_progress.router)
app.include_router(utp_plan_progress.router)
app.include_router(feishu_agent.router)

@app.on_event("startup")
def startup():
    init_db()
    # 启动全平台自动刷新调度器（工作日 9:30-18:30 每 30 分钟）
    try:
        from .services.auto_refresh_service import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[启动] 自动刷新调度器启动失败: {e}")

@app.get("/api/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "tOS Quality Workbench API is running"}

@app.get("/api/active-connections")
def get_active_connections():
    """获取当前在线连接列表（5 分钟内有 API 请求的 IP）"""
    now = time.time()
    clients = []
    for ip, ts in list(_active_clients.items()):
        if now - ts <= _ACTIVE_TIMEOUT:
            clients.append({"ip": ip, "last_seen": ts, "idle_seconds": int(now - ts)})
    clients.sort(key=lambda x: x["last_seen"], reverse=True)
    return {"total": len(clients), "clients": clients, "timeout_seconds": _ACTIVE_TIMEOUT}

@app.get("/api/config/defaults")
def get_config_defaults():
    """获取默认配置"""
    return {
        "default_jira_url": "http://jira.transsion.com",
        "stages": ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"],
    }

@app.post("/api/admin/reset-db")
def reset_database():
    """重置数据库（危险操作）"""
    from .database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    # 删除所有数据表
    tables = [
        "version_config", "str_stage_config", "jira_credential", "jira_issue_cache",
        "analysis_snapshot", "feishu_config", "ai_config", "sr_issue_cache",
        "sr_ai_analysis", "sr_detail_cache", "sr_ai_priority", "stability_data",
        "alm_config", "test_plans", "value_points", "jira_filter_preset",
        "alm_locked_sr_cache", "alm_locked_sr_snapshot", "jira_issue_api_cache", "utp_weekly_cache",
        "custom_risks", "chapter2_ai_summary", "utp_pending_cache", "ai_analysis_cache",
        "agent_conversations", "agent_tasks", "jira_trend_analysis_cache", "refresh_config",
        "test_activities", "work_hours", "test_activity_ai_analysis", "utp_sr_progress_cache", "utp_plan_cache",
    ]
    
    for table in tables:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    
    conn.commit()
    conn.close()
    
    # 重新初始化数据库
    init_db()
    
    return {"message": "数据库已重置"}

@app.post("/api/admin/clear-cache")
def clear_cache():
    """清空缓存数据"""
    from .services.cache_service import clear_cache as clear_cache_func
    return clear_cache_func()

@app.get("/api/output/reports")
def list_reports():
    """列出所有报告文件"""
    from pathlib import Path
    output_dir = Path.home() / ".tos_quality_workbench" / "output"
    
    if not output_dir.exists():
        return {"reports": []}
    
    reports = []
    for file in output_dir.glob("*.md"):
        reports.append({
            "filename": file.name,
            "size": file.stat().st_size,
            "modified": file.stat().st_mtime,
        })
    
    return {"reports": reports}

@app.get("/api/output/reports/{filename}")
def get_report(filename: str):
    """获取报告内容"""
    from pathlib import Path
    from fastapi.responses import Response
    
    output_dir = Path.home() / ".tos_quality_workbench" / "output"
    file_path = output_dir / filename
    
    if not file_path.exists():
        return Response(content="报告不存在", status_code=404)
    
    content = file_path.read_text(encoding="utf-8")
    return Response(content=content, media_type="text/plain; charset=utf-8")