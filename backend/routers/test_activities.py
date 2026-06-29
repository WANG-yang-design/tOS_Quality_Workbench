"""
重点测试活动 & 工时管理 API
"""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from ..database import get_conn
from ..utils import now_iso

router = APIRouter()

# ═══════════════════════════════════════════════════════════════
# 阶段与活动配置
# ═══════════════════════════════════════════════════════════════
STAGE_ACTIVITIES: Dict[str, List[str]] = {
    "概念启动": [
        "确定测试代表组建测试团队",
        "同频tOS版本规划阶段信息",
        "领域需求收集与分析，输出测试端意见与阶段",
        "需求RAT/TMG评审",
        "IR测试工作量评估",
        "需求RMT预评审",
        "需求RMT正式评审",
        "规划阶段评审",
    ],
    "STR1": [
        "二次确定测试维度PDT成员清单",
        "同频概念阶段信息",
        "IR需求串讲测试输出评审结论",
        "制定并输出IR需求测试方案",
        "测试维度风险识别和应对",
        "STR1评审",
    ],
    "STR2": [
        "同频tOS版本计划阶段信息",
        "SR需求串讲评审输出测试端意见",
        "SR测试工作量评估",
        "tOS版本测试维度总人力资源评估",
        "SR需求测试方案的输出与评审",
        "制定需求体验验收标准",
        "评审价值点指标输出测试端结论",
        "制定价值点需求策略",
        "制定tOS版本测试策略",
        "当前阶段测试维度风险识别",
        "STR2评审",
    ],
    "STR3": [
        "同频当前阶段信息",
        "盘点和申请基线样机资源",
        "SR需求排期输出测试端意见",
        "粉丝运营计划",
        "tOS版本测试计划",
        "tOS版本项目启动会",
        "当前阶段测试维度风险识别",
        "STR3评审",
    ],
    "STR4": [
        "同频当前阶段信息",
        "完成当前阶段任务下发",
        "SR需求测试与验证",
        "基础公共weekly滚动测试",
        "tOS基线前置测试",
        "问题验证与闭环",
        "当前阶段测试维度风险识别",
        "STR4评审",
    ],
    "STR4A": [
        "同频当前阶段信息",
        "完成此阶段任务下发",
        "SR需求测试与验证",
        "基础公共weekly滚动测试",
        "tOS基线前置测试",
        "问题验证与闭环",
        "系统集成测试",
        "主观体验测试",
        "价值点测试",
        "粉丝运营",
        "当前阶段测试维度风险识别",
        "STR4A评审",
    ],
    "STR5": [
        "同频当前阶段信息",
        "完成此阶段任务下发",
        "白名单SR需求测试与验证",
        "基础公共weekly滚动测试",
        "tOS基线前置测试",
        "白名单价值点需求测试",
        "must resolved必解问题标签标记",
        "预量产测试",
    ],
    "1+N版本火车": [
        "1+n版本火车团队组建",
        "制定1+N版本火车策略",
        "完成1+N版本火车测试验收",
        "评审并发布MR版本",
        "收编测试团队组建",
        "制定MP分支收编策略",
        "完成收编版本测试验收",
        "分支收编评审",
        "完成tOS版本复盘",
        "输出tOS版本项目转维清单",
        "参与转维评审",
        "MR版本迭代测试与发布",
    ],
}

ALL_STAGES = list(STAGE_ACTIVITIES.keys())


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def ensure_activities_exist(conn, version_id: int, stage_name: str):
    """确保指定版本+阶段的活动项已播种到数据库（如未播种则自动创建）"""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM test_activities WHERE version_id = ? AND stage_name = ?",
        (version_id, stage_name),
    )
    count = cur.fetchone()["c"]
    if count > 0:
        return

    activities = STAGE_ACTIVITIES.get(stage_name, [])
    ts = now_iso()
    for idx, name in enumerate(activities):
        cur.execute(
            """INSERT OR IGNORE INTO test_activities
               (version_id, stage_name, activity_index, activity_name, status, operator, employee_id, remark, updated_at)
               VALUES (?, ?, ?, ?, 'unconfirmed', '', '', '', ?)""",
            (version_id, stage_name, idx, name, ts),
        )
    conn.commit()


# ═══════════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════════

class ActivityUpdateReq(BaseModel):
    status: str  # "pass" | "fail" | "unconfirmed"
    operator: str  # 必填：操作人姓名
    employee_id: str  # 必填：操作人工号
    remark: Optional[str] = None


class WorkHoursImportReq(BaseModel):
    data: List[Dict[str, Any]]


class WorkHoursAIAnalysisReq(BaseModel):
    ai_text: str


# ═══════════════════════════════════════════════════════════════
# 重点测试活动 API
# ═══════════════════════════════════════════════════════════════

@router.get("/api/versions/{version_id}/test-activities")
def list_test_activities(version_id: int, stage: str = ""):
    """获取指定版本的重点测试活动（按当前阶段过滤）"""
    conn = get_conn()
    cur = conn.cursor()

    # 确认版本存在
    cur.execute("SELECT id FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    if not stage:
        # 如果未指定阶段，返回所有阶段的活动
        result = {}
        for s in ALL_STAGES:
            ensure_activities_exist(conn, version_id, s)
            cur.execute(
                "SELECT * FROM test_activities WHERE version_id = ? AND stage_name = ? ORDER BY activity_index",
                (version_id, s),
            )
            result[s] = [row_to_dict(r) for r in cur.fetchall()]
        conn.close()
        return {"activities": result, "stage_config": STAGE_ACTIVITIES}

    ensure_activities_exist(conn, version_id, stage)
    cur.execute(
        "SELECT * FROM test_activities WHERE version_id = ? AND stage_name = ? ORDER BY activity_index",
        (version_id, stage),
    )
    rows = [row_to_dict(r) for r in cur.fetchall()]

    # 统计
    total = len(rows)
    pass_count = sum(1 for r in rows if r["status"] == "pass")
    fail_count = sum(1 for r in rows if r["status"] == "fail")
    unconfirmed = total - pass_count - fail_count

    conn.close()
    return {
        "activities": rows,
        "stats": {
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "unconfirmed": unconfirmed,
            "completion_rate": round(pass_count / total * 100, 1) if total > 0 else 0,
        },
        "stage_config": STAGE_ACTIVITIES.get(stage, []),
    }


@router.put("/api/versions/{version_id}/test-activities/{activity_id}")
def update_test_activity(version_id: int, activity_id: int, req: ActivityUpdateReq):
    """更新单个活动项状态（必须提供操作人姓名和工号）"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM test_activities WHERE id = ? AND version_id = ?",
        (activity_id, version_id),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="活动项不存在")

    status = req.status.lower().strip()
    if status not in ("pass", "fail", "unconfirmed"):
        conn.close()
        raise HTTPException(status_code=400, detail="状态值无效，仅支持 pass/fail/unconfirmed")

    operator = (req.operator or "").strip()
    employee_id = (req.employee_id or "").strip()
    if not operator or not employee_id:
        conn.close()
        raise HTTPException(status_code=400, detail="操作人姓名和工号为必填项")

    ts = now_iso()
    row_dict = row_to_dict(row)
    remark = req.remark if req.remark is not None else row_dict.get("remark", "")

    # 兼容旧表：确保 employee_id 列存在
    try:
        cur.execute(
            """UPDATE test_activities
               SET status = ?, operator = ?, employee_id = ?, remark = ?, updated_at = ?
               WHERE id = ? AND version_id = ?""",
            (status, operator, employee_id, remark, ts, activity_id, version_id),
        )
    except Exception:
        # 如果 employee_id 列不存在，用不含该列的 SQL
        cur.execute(
            """UPDATE test_activities
               SET status = ?, operator = ?, remark = ?, updated_at = ?
               WHERE id = ? AND version_id = ?""",
            (status, operator, remark, ts, activity_id, version_id),
        )
    conn.commit()

    cur.execute("SELECT * FROM test_activities WHERE id = ?", (activity_id,))
    updated = row_to_dict(cur.fetchone())
    conn.close()
    return {"message": "活动状态已更新", "activity": updated}


@router.get("/api/versions/{version_id}/test-activities/stats")
def get_activity_stats(version_id: int, stage: str = ""):
    """获取活动统计（所有阶段或指定阶段）"""
    conn = get_conn()
    result = {}

    stages_to_check = [stage] if stage and stage in ALL_STAGES else ALL_STAGES

    for s in stages_to_check:
        ensure_activities_exist(conn, version_id, s)
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM test_activities WHERE version_id = ? AND stage_name = ?",
            (version_id, s),
        )
        rows = cur.fetchall()
        total = len(rows)
        pass_count = sum(1 for r in rows if r["status"] == "pass")
        fail_count = sum(1 for r in rows if r["status"] == "fail")
        unconfirmed = total - pass_count - fail_count
        result[s] = {
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "unconfirmed": unconfirmed,
            "completion_rate": round(pass_count / total * 100, 1) if total > 0 else 0,
        }

    conn.close()
    return {"stats": result}


@router.get("/api/versions/{version_id}/test-activities/ai-analysis")
def get_activity_ai_analysis(version_id: int, stage: str = ""):
    """获取重点测试活动 AI 风险分析结果"""
    conn = get_conn()
    cur = conn.cursor()

    if stage:
        cur.execute(
            "SELECT * FROM test_activity_ai_analysis WHERE version_id = ? AND stage_name = ?",
            (version_id, stage),
        )
        row = row_to_dict(cur.fetchone())
        conn.close()
        return {"analysis": row}
    else:
        cur.execute(
            "SELECT * FROM test_activity_ai_analysis WHERE version_id = ?",
            (version_id,),
        )
        rows = [row_to_dict(r) for r in cur.fetchall()]
        conn.close()
        return {"analyses": rows}


@router.post("/api/versions/{version_id}/test-activities/ai-analysis")
def generate_activity_ai_analysis(version_id: int, stage: str = ""):
    """触发 AI 风险分析（返回分析结果，同时缓存到数据库）"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    ver = cur.fetchone()
    if not ver:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")
    version_name = ver["version_name"]

    # 收集当前阶段活动数据
    stages_to_analyze = [stage] if stage and stage in ALL_STAGES else ALL_STAGES
    activity_data = {}
    for s in stages_to_analyze:
        ensure_activities_exist(conn, version_id, s)
        cur.execute(
            "SELECT * FROM test_activities WHERE version_id = ? AND stage_name = ? ORDER BY activity_index",
            (version_id, s),
        )
        rows = [row_to_dict(r) for r in cur.fetchall()]
        if rows:
            activity_data[s] = rows

    # 调用 AI 分析
    from ..services.ai_service import call_ai

    system_prompt, user_prompt = build_activity_analysis_prompt(version_name, activity_data)
    ai_result = call_ai(system_prompt, user_prompt)

    # 缓存结果
    ts = now_iso()
    for s in stages_to_analyze:
        cur.execute(
            """INSERT INTO test_activity_ai_analysis (version_id, stage_name, analysis_text, generated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(version_id, stage_name) DO UPDATE SET
                 analysis_text = excluded.analysis_text,
                 generated_at = excluded.generated_at""",
            (version_id, s, ai_result, ts),
        )
    conn.commit()
    conn.close()

    return {"analysis": ai_result, "generated_at": ts}


def build_activity_analysis_prompt(version_name: str, activity_data: Dict[str, list]) -> tuple:
    """构建 AI 分析 prompt，返回 (system_prompt, user_prompt)"""
    system_prompt = (
        "你是一位资深的软件测试项目管理专家，擅长识别测试活动中的风险并给出改进建议。\n"
        "要求：\n1. 用中文回答\n2. 结构清晰，使用编号列表\n"
        "3. 重点关注 Fail 项风险、未确认项、完成率\n4. 给出具体可执行的建议\n5. 控制在 600 字以内"
    )

    lines = [
        f"以下是 tOS 版本「{version_name}」各阶段的重点测试活动执行数据：",
        "",
    ]
    for stage, rows in activity_data.items():
        total = len(rows)
        pass_n = sum(1 for r in rows if r["status"] == "pass")
        fail_n = sum(1 for r in rows if r["status"] == "fail")
        unconf = total - pass_n - fail_n
        rate = round(pass_n / total * 100, 1) if total else 0
        lines.append(f"【{stage}】共 {total} 项 | Pass {pass_n} | Fail {fail_n} | 未确认 {unconf} | 完成率 {rate}%")
        fail_items = [r for r in rows if r["status"] == "fail"]
        for fi in fail_items:
            remark = fi.get("remark", "") or "无备注"
            lines.append(f"  - ❌ Fail: {fi['activity_name']}（备注：{remark}，操作人：{fi.get('operator', '未知')}）")
        unconf_items = [r for r in rows if r["status"] == "unconfirmed"]
        for ui in unconf_items:
            lines.append(f"  - ⚪ 未确认: {ui['activity_name']}")
        lines.append("")

    lines.append("请从以下维度进行风险分析：")
    lines.append("1. Fail 项的风险影响（是否阻塞阶段评审）")
    lines.append("2. 未确认项的时效风险")
    lines.append("3. 当前阶段完成率是否健康")
    lines.append("4. 需要重点关注的活动项")
    lines.append("5. 具体改进建议")

    return system_prompt, "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 工时管理 API
# ═══════════════════════════════════════════════════════════════

@router.get("/api/versions/{version_id}/work-hours")
def get_work_hours(version_id: int):
    """获取工时数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM work_hours WHERE version_id = ?", (version_id,))
    row = row_to_dict(cur.fetchone())
    conn.close()

    if not row:
        return {"data": [], "ai_analysis": "", "imported_at": None}

    try:
        data = json.loads(row.get("data_json", "[]"))
    except Exception:
        data = []

    return {
        "data": data,
        "ai_analysis": row.get("ai_analysis", ""),
        "imported_at": row.get("imported_at"),
        "analyzed_at": row.get("analyzed_at"),
    }


@router.post("/api/versions/{version_id}/work-hours/import")
def import_work_hours(version_id: int, req: WorkHoursImportReq):
    """导入工时数据（标准化 JSON）"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    ts = now_iso()
    data_json = json.dumps(req.data, ensure_ascii=False)

    cur.execute(
        """INSERT INTO work_hours (version_id, data_json, imported_at)
           VALUES (?, ?, ?)
           ON CONFLICT(version_id) DO UPDATE SET
             data_json = excluded.data_json,
             imported_at = excluded.imported_at""",
        (version_id, data_json, ts),
    )
    conn.commit()
    conn.close()

    return {"message": f"成功导入 {len(req.data)} 条工时记录", "count": len(req.data)}


@router.post("/api/versions/{version_id}/work-hours/ai-analysis")
def generate_work_hours_ai_analysis(version_id: int):
    """AI 分析工时数据"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    ver = cur.fetchone()
    if not ver:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    cur.execute("SELECT * FROM work_hours WHERE version_id = ?", (version_id,))
    row = row_to_dict(cur.fetchone())
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="暂无工时数据，请先导入")

    try:
        data = json.loads(row.get("data_json", "[]"))
    except Exception:
        data = []

    if not data:
        conn.close()
        raise HTTPException(status_code=400, detail="工时数据为空")

    version_name = ver["version_name"]

    # 调用 AI
    from ..services.ai_service import call_ai

    system_prompt, user_prompt = build_work_hours_analysis_prompt(version_name, data)
    ai_result = call_ai(system_prompt, user_prompt)

    ts = now_iso()
    cur.execute(
        """UPDATE work_hours SET ai_analysis = ?, analyzed_at = ? WHERE version_id = ?""",
        (ai_result, ts, version_id),
    )
    conn.commit()
    conn.close()

    return {"analysis": ai_result, "analyzed_at": ts}


def build_work_hours_analysis_prompt(version_name: str, data: list) -> tuple:
    """构建工时分析 prompt，返回 (system_prompt, user_prompt)"""
    system_prompt = (
        "你是一位资深的软件测试项目管理专家，擅长分析测试团队工时分配和人力投入情况。\n"
        "要求：\n1. 用中文回答\n2. 结构清晰，使用编号列表\n"
        "3. 重点关注工时分配合理性、人力瓶颈\n4. 给出具体可执行的优化建议\n5. 控制在 500 字以内"
    )

    lines = [
        f"以下是 tOS 版本「{version_name}」的工时数据：",
        "",
        "```json",
        json.dumps(data[:50], ensure_ascii=False, indent=2),
        "```",
        "",
        "请从以下维度进行分析：",
        "1. 各人员的总工时和工时分布",
        "2. 工时过高或过低的人员识别",
        "3. 测试/回归/其他工时占比是否合理",
        "4. 整体人力投入是否充足",
        "5. 优化建议",
    ]

    return system_prompt, "\n".join(lines)


@router.get("/api/versions/{version_id}/work-hours/ai-analysis")
def get_work_hours_ai_analysis(version_id: int):
    """获取已缓存的工时 AI 分析"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ai_analysis, analyzed_at FROM work_hours WHERE version_id = ?", (version_id,))
    row = row_to_dict(cur.fetchone())
    conn.close()

    if not row:
        return {"analysis": "", "analyzed_at": None}

    return {"analysis": row.get("ai_analysis", ""), "analyzed_at": row.get("analyzed_at")}
