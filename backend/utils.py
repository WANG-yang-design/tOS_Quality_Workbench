import json
from datetime import datetime
from typing import Any
from dateutil import parser
from fastapi import HTTPException

def now_iso():
    """获取当前时间的ISO格式字符串"""
    return datetime.now().isoformat(timespec="seconds")

def safe_json(resp, context: str = "") -> dict:
    """安全解析 HTTP 响应为 JSON，避免 Extra data 等异常"""
    try:
        return resp.json()
    except Exception as e:
        body = resp.text[:300] if resp.text else "(空)"
        print(f"[safe_json] {context} 解析失败: {e}, 状态码={resp.status_code}, 响应体={body}")
        raise HTTPException(
            status_code=400,
            detail=f"飞书接口返回非JSON格式（{context}）。状态码={resp.status_code}，响应={body}"
        )

def parse_dt(value):
    """解析日期时间字符串"""
    if not value:
        return None
    try:
        return parser.parse(value).replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        return None

def stringify_field_value(value: Any) -> str:
    """
    Jira 自定义字段可能是字符串、数字、对象、列表。
    统一转成易读字符串。
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, dict):
        # 处理嵌套对象（如 child 字段）
        if "child" in value and isinstance(value.get("child"), dict):
            parent = value.get("value") or value.get("name") or ""
            child = value["child"].get("value") or value["child"].get("name") or ""
            return f"{parent}/{child}" if child else str(parent)

        for k in ["value", "name", "displayName", "key"]:
            if k in value and value[k] is not None:
                return str(value[k])

        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, list):
        # 处理列表（如多值字段）
        parts = []
        for item in value:
            if isinstance(item, dict):
                for k in ["value", "name", "displayName", "key"]:
                    if k in item and item[k] is not None:
                        parts.append(str(item[k]))
                        break
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return ", ".join(parts)

    return str(value)

def safe_get(d: Any, *keys, default=None):
    """安全获取嵌套字典的值"""
    if d is None:
        return default
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
            current = current[key]
        else:
            return default
        if current is None:
            return default
    return current if current is not None else default

def has_exact_option(value: str, target: str) -> bool:
    """检查字符串是否包含精确的选项（用于Jira字段匹配）"""
    if not value or not target:
        return False
    # 处理可能的多个值（用逗号分隔）
    values = [v.strip() for v in value.split(",")]
    return target in values

def priority_to_grade(priority: str, severity: str = "", must_fix: str = "") -> str:
    """将优先级转换为等级（用于风险计算）"""
    priority = (priority or "").strip()
    severity = (severity or "").strip()
    must_fix = (must_fix or "").strip()

    # 基于优先级的映射
    priority_map = {
        "Blocker": "S1",
        "Critical": "S1",
        "Major": "S2",
        "Highest": "S1",
        "High": "S2",
        "P0": "S1",
        "P1": "S2",
        "严重": "S1",
        "高": "S2",
    }

    # 基于严重程度的映射
    severity_map = {
        "Blocker": "S1",
        "Critical": "S1",
        "Major": "S2",
        "Minor": "S3",
        "Trivial": "S4",
    }

    # 如果有严重程度，优先使用
    if severity:
        grade = severity_map.get(severity, "")
        if grade:
            return grade

    # 否则使用优先级
    if priority:
        grade = priority_map.get(priority, "")
        if grade:
            return grade

    # 默认为S3
    return "S3"

def is_must_fix_enhanced(must_fix: str, labels: str, priority: str, migration: str = "") -> bool:
    """增强的必解判断逻辑"""
    must_fix = (must_fix or "").strip().lower()
    labels = (labels or "").strip().lower()
    priority = (priority or "").strip().lower()
    migration = (migration or "").strip().lower()

    # 直接检查 must_fix 字段
    if must_fix in ["mp block", "block", "must fix", "必解", "是"]:
        return True

    # 检查标签
    if labels:
        label_list = [l.strip() for l in labels.split(",")]
        for label in label_list:
            if any(keyword in label for keyword in ["mustfix", "must-fix", "必解", "block"]):
                return True

    # 检查优先级
    if priority in ["blocker", "critical", "p0", "p1", "严重", "高"]:
        return True

    # 检查迁移字段
    if migration:
        if any(keyword in migration for keyword in ["mustfix", "must-fix", "必解", "block"]):
            return True

    return False

def calc_risk_score(grade: str, status: str, priority: str, aging_days: int, stale_days: int, must_fix: bool) -> int:
    """计算风险分数"""
    score = 0

    # 等级分数
    grade_scores = {"S1": 10, "S2": 7, "S3": 4, "S4": 2}
    score += grade_scores.get(grade, 0)

    # 状态分数
    status_lower = (status or "").lower()
    if status_lower in ["open", "reopened", "submitted", "modifying", "测试执行中", "重新打开", "测试中"]:
        score += 5
    elif status_lower in ["in progress", "进行中"]:
        score += 3

    # 优先级分数
    priority_lower = (priority or "").lower()
    if priority_lower in ["blocker", "critical", "p0", "p1", "严重", "高"]:
        score += 3

    # 老化分数
    if aging_days and aging_days > 7:
        score += min(aging_days // 7, 5)  # 每周加1分，最多5分

    # 停滞分数
    if stale_days and stale_days > 3:
        score += min(stale_days // 3, 3)  # 每3天加1分，最多3分

    # 必解加分
    if must_fix:
        score += 5

    return score