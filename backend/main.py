# ============================================================
# tOS Quality Workbench - 后端主文件(旧版，备份用2026-06-12)
# ============================================================


import json
import os
import sqlite3
import random
import re
import time
import base64
from urllib.parse import quote, urlparse, parse_qs
import urllib3
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
from typing import Optional, List, Dict, Any
from collections import Counter

CST = timezone(timedelta(hours=8))

import requests
from requests.auth import HTTPBasicAuth
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dateutil import parser
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

APP_DIR = Path.home() / ".tos_quality_workbench"
DB_PATH = APP_DIR / "tos_quality.db"
KEY_PATH = APP_DIR / "secret.key"

# ==============================
# [1] 配置常量
# ==============================
CLOSED_STATUS = {
    "Closed", "Done", "Resolved", "Verified",
    "关闭", "已解决", "已验证",
    "无法复现", "延期处理", "重复问题", "By Design", "Won't Fix", "Duplicate"
}

# 所有已知的状态列表（用于统计和展示）
ALL_KNOWN_STATUS = {
    "Open", "In Progress", "Reopened", "Submitted", "Modifying",
    "测试执行中", "重新打开", "测试中",
    "Closed", "Done", "Resolved", "Verified",
    "关闭", "已解决", "已验证",
    "无法复现", "延期处理", "重复问题", "By Design", "Won't Fix", "Duplicate"
}

HIGH_PRIORITY = {"Blocker", "Critical", "Major", "Highest", "High", "P0", "P1", "严重", "高"}

# 默认Jira服务器地址
DEFAULT_JIRA_BASE_URL = "http://jira.transsion.com"

# ==============================
# Jira 自定义字段配置（来自你的脚本）
# ==============================

JIRA_CUSTOM_FIELDS = {
    "must_fix": "customfield_15400",      # 必解标签 (MP Block / Not MP Block)
    "android_version": "customfield_13100",  # Android版本
    "os_version": "customfield_13101",       # OS版本
    "model": "customfield_15302",            # 机型/项目 (如 X6878)
    "severity": "customfield_13004",         # 严重程度/等级
    "issue_category": "customfield_10203",   # 问题类别 (如 Stability)
    "frequency": "customfield_10204",        # 出现概率 (如 Often)
    "test_type": "customfield_10900",        # 测试类型
    "migration": "customfield_11101",        # 迁移/处理结论
    "sr_feature": "customfield_13800",       # SR/特性关联
    "system_category": "customfield_15205",  # 系统分类
    "module_category": "customfield_14907",  # 模块分类
    "solution_type": "customfield_14102",    # 解决方式
    "project_code": "customfield_14205",     # 项目代号
}

# Jira API 请求的字段列表
JIRA_SEARCH_FIELDS = [
    "summary", "status", "project", "reporter", "assignee", "priority",
    "components", "labels", "created", "updated", "resolution", "resolutiondate",
    "versions", "fixVersions", "issuetype", "description", "comment",
    # 自定义字段
    "customfield_15400", "customfield_13100", "customfield_13101",
    "customfield_15302", "customfield_13004", "customfield_10203",
    "customfield_10204", "customfield_10900", "customfield_11101",
    "customfield_13800", "customfield_15205", "customfield_14907",
    "customfield_14102", "customfield_14205",
]


app = FastAPI(title="tOS Quality Workbench Local API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


def get_conn():
    ensure_app_dir()
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ==============================
# 同步进度跟踪
# ==============================
sync_progress = {
    "active": False,
    "phase": "",       # "fetching" / "saving" / "analyzing" / "done" / "error"
    "fetched": 0,
    "total": 0,
    "message": "",
}


def get_fernet() -> Fernet:
    ensure_app_dir()
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
    return Fernet(KEY_PATH.read_bytes())


def encrypt_text(text: str) -> str:
    return get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def now_iso():
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
    if not value:
        return None
    try:
        return parser.parse(value).replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        return None


def stringify_field_value(value: Any) -> str:
    """
    Jira 自定义字段可能是字符串、数字、对象、列表。
    统一转成易读字符串。（来自 jira_api_test）
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
        return ",".join([stringify_field_value(v) for v in value if stringify_field_value(v)])

    return str(value)


def safe_get(d: Any, *keys, default=None):
    """安全获取嵌套字典值"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def has_exact_option(value: str, target: str) -> bool:
    """
    精确匹配选项，避免 Not MP Block 命中 MP Block。
    （来自 jira_report_analyse）
    """
    if not value:
        return False

    target_lower = target.strip().lower()
    parts = str(value).replace("，", ",").split(",")
    return any(x.strip().lower() == target_lower for x in parts)


def priority_to_grade(priority: str, severity: str = "", must_fix: str = "") -> str:
    """
    修正版 A/B/C 分类规则。（来自 jira_report_analyse）
    - MP Block -> A
    - Blocker -> A
    - Critical -> A
    - Major -> B
    - Minor -> C
    """
    p = (priority or "").strip().lower()
    s = (severity or "").strip()
    m = (must_fix or "").strip()

    # 精确命中 MP Block
    if has_exact_option(m, "MP Block"):
        return "A"

    if p in {"blocker", "阻塞", "致命"}:
        return "A"

    if p in {"critical", "严重"}:
        return "A"

    if p in {"major", "重要"}:
        return "B"

    if p in {"minor", "一般", "次要"}:
        return "C"

    # 兜底看严重程度
    if s in {"高", "严重", "致命"}:
        return "A"

    if s in {"中", "重要"}:
        return "B"

    if s in {"低", "一般", "轻微"}:
        return "C"

    return "未分级"


def is_must_fix_enhanced(must_fix: str, labels: str, priority: str, migration: str = "") -> bool:
    """
    必解增强规则。（来自 jira_report_analyse）
    命中条件：
    1. must_fix_customfield_15400 精确等于 MP Block
    2. labels 中有 must
    3. migration 中包含 必解
    4. priority = Blocker
    """
    # 精确匹配 MP Block
    if has_exact_option(must_fix, "MP Block"):
        return True

    # labels 中的 must
    if labels:
        label_options = [x.strip().lower() for x in str(labels).replace("，", ",").split(",")]
        if any(x == "must" for x in label_options):
            return True

    # migration 中的必解
    if migration and "必解" in str(migration):
        return True

    # priority = Blocker
    if str(priority).strip().lower() == "blocker":
        return True

    return False


def calc_risk_score(grade: str, status: str, priority: str, aging_days: int, stale_days: int, must_fix: bool) -> int:
    """
    风险评分算法。（来自 jira_report_analyse）
    """
    score = 0

    if grade == "A":
        score += 100

    if priority == "Blocker":
        score += 80

    if status == "Reopened":
        score += 60

    if must_fix:
        score += 50

    # 遗留越久，分越高，最多加 60
    score += min(aging_days or 0, 60)

    # 越久未更新，分越高，最多加 30
    score += min(stale_days or 0, 30)

    return score


# ==============================
# Jira Filter Presets 默认定义
# ==============================
# 唯一需要动态替换的占位符：{project} = 当前版本的 jira_project（含多项目映射）
# 用户在前端编辑时直接写完整 JQL，不需要任何占位符
DEFAULT_JIRA_FILTERS = [
    {
        "filter_key": "main_sync",
        "label": "主数据同步 JQL",
        "description": "从 Jira 同步 issue 到本地数据库（{project} 由系统替换为当前版本项目）",
        "default_jql": 'project in ({project}) AND issuetype in (Bug) ORDER BY updated DESC',
    },
    {
        "filter_key": "sr_backlog",
        "label": "SR 遗留问题 JQL",
        "description": "查询 SR 相关的高优遗留问题（仅此 filter 支持多项目：TOS170, LK7KOS17, X6878OS17）",
        "default_jql": 'project in ({project}) AND (summary ~ "SR*" or SR编号 is not empty) AND status not in (Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished) AND priority in (Blocker, Critical, Major) ORDER BY priority ASC, created DESC',
    },
    {
        "filter_key": "open_reopen",
        "label": "遗留问题 Open/Reopened JQL",
        "description": "查询 Open 和 Reopened 状态的遗留问题",
        "default_jql": 'project in ({project}) AND status in (Open, Reopened) ORDER BY priority ASC, created DESC',
    },
    {
        "filter_key": "submitted_modifying",
        "label": "积压问题 Submitted/Modifying JQL",
        "description": "查询 Submitted 和 Modifying 状态的积压问题",
        "default_jql": 'project in ({project}) AND status in (Submitted, Modifying) ORDER BY created ASC',
    },
    {
        "filter_key": "pending_verification",
        "label": "待验证问题 JQL",
        "description": "查询已解决/已验证但待最终确认的问题",
        "default_jql": 'project in ({project}) AND issuetype in (Bug) AND status in (Resolved, Verified) AND (DupIssueStatus ~ Verified OR DupIssueStatus ~ resolved OR DupIssueStatus ~ closed or DupIssueStatus is EMPTY) ORDER BY updated DESC',
    },
]


def _seed_filter_presets(cur, force_update: bool = False):
    """播种默认 Jira Filter Presets。force_update=True 时强制更新 default_jql 并清空 custom_jql。"""
    cur.execute("SELECT id FROM version_config")
    version_ids = [row["id"] for row in cur.fetchall()]
    for vid in version_ids:
        for f in DEFAULT_JIRA_FILTERS:
            if force_update:
                cur.execute("""
                    INSERT INTO jira_filter_preset
                        (version_id, filter_key, label, description, default_jql, custom_jql, updated_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    ON CONFLICT(version_id, filter_key) DO UPDATE SET
                        default_jql = excluded.default_jql,
                        label = excluded.label,
                        description = excluded.description,
                        custom_jql = NULL,
                        updated_at = excluded.updated_at
                """, (vid, f["filter_key"], f["label"], f["description"], f["default_jql"], now_iso()))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO jira_filter_preset
                        (version_id, filter_key, label, description, default_jql, custom_jql, updated_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                """, (vid, f["filter_key"], f["label"], f["description"], f["default_jql"], now_iso()))


def _get_filter_jql(version_id: int, filter_key: str) -> Optional[str]:
    """获取指定版本和 filter_key 的有效 JQL（优先用 custom_jql，否则 default_jql）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT default_jql, custom_jql FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return (row["custom_jql"] or row["default_jql"] or "").strip()


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS version_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_name TEXT NOT NULL UNIQUE,
        jira_project TEXT,
        jira_fix_version TEXT,
        owner_name TEXT,
        is_train_version INTEGER DEFAULT 0,
        created_at TEXT,
        -- 基础信息字段
        baseline_date TEXT,
        branch_name TEXT,
        device_count INTEGER DEFAULT 0,
        device_list TEXT,
        coverage_scope TEXT,
        project_status TEXT DEFAULT '进行中'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS str_stage_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        start_date TEXT,
        end_date TEXT,
        current_flag INTEGER DEFAULT 0,
        UNIQUE(version_id, stage_name)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_credential (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL UNIQUE,
        jira_base_url TEXT NOT NULL,
        username TEXT NOT NULL,
        encrypted_password TEXT NOT NULL,
        expire_at TEXT NOT NULL,
        last_login_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_issue_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        version_name TEXT,
        str_stage TEXT,
        issue_key TEXT NOT NULL,
        summary TEXT,
        description TEXT,
        status TEXT,
        priority TEXT,
        issue_type TEXT,
        assignee TEXT,
        reporter TEXT,
        module_name TEXT,
        labels TEXT,
        created_time TEXT,
        updated_time TEXT,
        resolved_time TEXT,
        raw_payload TEXT,
        synced_at TEXT,
        -- 新增：Jira 自定义字段
        must_fix TEXT,
        severity TEXT,
        model TEXT,
        issue_category TEXT,
        frequency TEXT,
        module_category TEXT,
        project_code TEXT,
        os_version TEXT,
        android_version TEXT,
        -- 新增：计算字段
        grade TEXT,
        must_fix_flag INTEGER DEFAULT 0,
        aging_days INTEGER,
        stale_days INTEGER,
        risk_score INTEGER DEFAULT 0,
        UNIQUE(version_id, str_stage, issue_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS analysis_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        version_name TEXT,
        str_stage TEXT,
        period_start TEXT,
        period_end TEXT,
        metrics_json TEXT,
        risks_json TEXT,
        suggestions_json TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS feishu_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        app_id TEXT NOT NULL DEFAULT '',
        app_secret TEXT NOT NULL DEFAULT '',
        updated_at TEXT
    )
    """)

    # 确保 feishu_config 有默认行
    cur.execute("INSERT OR IGNORE INTO feishu_config (id, app_id, app_secret, updated_at) VALUES (1, '', '', '')")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        api_base TEXT NOT NULL DEFAULT 'https://hk-intra-paas.transsion.com/tranai-proxy/v1',
        api_key TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT 'gpt-5.2-chat',
        user_no TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        user_dept TEXT NOT NULL DEFAULT '',
        updated_at TEXT
    )
    """)

    # 兼容旧表：补充缺失的列（必须在 INSERT 之前）
    for col, default in [("user_no", ""), ("user_name", ""), ("user_dept", "")]:
        try:
            cur.execute(f"ALTER TABLE ai_config ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'")
        except Exception:
            pass

    # 迁移：version_config 新增 feishu_sheet_url 列
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN feishu_sheet_url TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    # 迁移：version_config 新增性能/续航表格URL列
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN perf_sheet_url TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN battery_sheet_url TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    # 确保 ai_config 有默认行
    cur.execute("INSERT OR IGNORE INTO ai_config (id, api_base, api_key, model, user_no, user_name, user_dept, updated_at) VALUES (1, 'https://hk-intra-paas.transsion.com/tranai-proxy/v1', '', 'gpt-5.2-chat', '', '', '', '')")

    # 迁移：ai_config 新增 sr_ai_prompt 列（全局 SR AI 分析 prompt 模板）
    try:
        cur.execute("ALTER TABLE ai_config ADD COLUMN sr_ai_prompt TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    # 设置默认 prompt 模板（如果为空）
    cur.execute("SELECT sr_ai_prompt FROM ai_config WHERE id = 1")
    row = cur.fetchone()
    if row and not (row["sr_ai_prompt"] or "").strip():
        default_sr_prompt = """你是软件测试质量分析专家。针对以下 SR 需求，给出简短的风险分析和测试建议。

分析维度：
1. 需求风险：需求复杂度、变更历史、跨模块影响
2. 测试建议：重点关注的测试场景、回归范围
3. 进度风险：计划验收时间是否合理、依赖关系

要求：每个 SR 的分析控制在 2-3 句话，简洁实用。如果 SR 状态已是 COMPLETED 且无遗留问题，可以简短标注"已完成，风险低"。

当前版本：{version_name}
当前阶段：{stage}
版本概况：总 Issue {total_issues} 个，未关闭 {unresolved} 个，高优 {high_priority} 个"""
        cur.execute("UPDATE ai_config SET sr_ai_prompt = ? WHERE id = 1", (default_sr_prompt,))

    # SR 遗留问题缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sr_issue_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        issue_key TEXT NOT NULL,
        summary TEXT,
        status TEXT,
        priority TEXT,
        assignee TEXT,
        reporter TEXT,
        created_time TEXT,
        aging_days INTEGER,
        labels TEXT,
        synced_at TEXT,
        UNIQUE(version_id, issue_key)
    )
    """)

    # SR AI 分析结果表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sr_ai_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        sr_coding TEXT NOT NULL,
        analysis TEXT,
        analyzed_at TEXT,
        UNIQUE(version_id, sr_coding)
    )
    """)

    # SR 需求详情缓存表（来自 ALM，含 issue 数量等）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sr_detail_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        sr_coding TEXT NOT NULL,
        sr_name TEXT,
        sr_status TEXT,
        sr_priority TEXT,
        planned_acceptance TEXT,
        test_module_owners TEXT,
        test_module_owners_display TEXT,
        issue_count INTEGER DEFAULT 0,
        issue_keys TEXT,
        is_other_version INTEGER DEFAULT 0,
        other_version_reason TEXT,
        bid TEXT,
        third_dept TEXT,
        synced_at TEXT,
        UNIQUE(version_id, sr_coding)
    )
    """)

    # SR AI 风险等级分析结果表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sr_ai_priority (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        sr_coding TEXT NOT NULL,
        risk_level TEXT DEFAULT '',
        analysis TEXT DEFAULT '',
        issue_count INTEGER DEFAULT 0,
        issue_keys_hash TEXT DEFAULT '',
        issue_keys TEXT DEFAULT '',
        analyzed_at TEXT,
        UNIQUE(version_id, sr_coding)
    )
    """)

    # 稳定性专项数据表（手动填写）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stability_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        device_name TEXT NOT NULL,
        rom_version TEXT DEFAULT '',
        sys_apr_value TEXT DEFAULT '',
        sys_apr_threshold TEXT DEFAULT '',
        sys_apr_duration TEXT DEFAULT '',
        app_apr_value TEXT DEFAULT '',
        app_apr_threshold TEXT DEFAULT '',
        app_apr_duration TEXT DEFAULT '',
        subsys_apr_value TEXT DEFAULT '',
        subsys_apr_threshold TEXT DEFAULT '',
        subsys_apr_duration TEXT DEFAULT '',
        third_apr_value TEXT DEFAULT '',
        third_apr_threshold TEXT DEFAULT '',
        third_apr_duration TEXT DEFAULT '',
        jira_keys TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        updated_at TEXT,
        UNIQUE(version_id, device_name)
    )
    """)

    # ALM 配置表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alm_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        uac_gateway TEXT NOT NULL DEFAULT 'https://pfgatewaysz.transsion.com:9199',
        alm_app_id TEXT NOT NULL DEFAULT '',
        uac_username TEXT NOT NULL DEFAULT '',
        encrypted_password TEXT NOT NULL DEFAULT '',
        uac_source TEXT NOT NULL DEFAULT 'ALM',
        alm_base_url TEXT NOT NULL DEFAULT 'https://pfgatewaysz.transsion.com:9199/alm-transcend-datadriven',
        alm_space_bid TEXT NOT NULL DEFAULT '1387390492731400192',
        alm_app_bid TEXT NOT NULL DEFAULT '1387390756582481922',
        updated_at TEXT
    )
    """)
    cur.execute("INSERT OR IGNORE INTO alm_config (id) VALUES (1)")

    # 旧数据迁移：更新默认地址
    cur.execute("UPDATE ai_config SET api_base = 'https://hk-intra-paas.transsion.com/tranai-proxy/v1' WHERE api_base = 'https://api.tranai.com/v1'")
    cur.execute("UPDATE ai_config SET model = 'gpt-5.2-chat' WHERE model IN ('gpt-5.4', 'gpt-4o')")

    # ---- ALM 配置迁移：修正 uac_username ----
    # ALM 鉴权使用 appId + 工号登录，工号必须是纯数字（如 18665088），
    # 不能使用 Jira 域账号（如 yang.wang5）。
    cur.execute("SELECT uac_username FROM alm_config WHERE id = 1")
    alm_row = cur.fetchone()
    if alm_row:
        alm_username = (alm_row["uac_username"] or "").strip()
        # 如果用户名不是纯数字（如 yang.wang5），说明是 Jira 域账号，不是 ALM 工号
        if alm_username and not alm_username.isdigit():
            print(f"[迁移] ALM uac_username '{alm_username}' 是 Jira 域账号，不是 ALM 工号")
            print(f"[迁移] 清除无效的 ALM 凭据，请重新配置正确的工号")
            cur.execute("UPDATE alm_config SET uac_username='', encrypted_password='' WHERE id=1")
            # 同时清除可能存在的无效 token 缓存
            if ALM_TOKEN_CACHE_PATH.exists():
                try:
                    ALM_TOKEN_CACHE_PATH.unlink()
                    print("[迁移] 已清除无效的 ALM token 缓存")
                except Exception:
                    pass

    # 测试计划表（用户手动填写的计划，用于性能/续航等专项）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        plan_type TEXT NOT NULL,
        device_name TEXT NOT NULL,
        test_items TEXT DEFAULT '',
        plan_status TEXT DEFAULT 'planned',
        plan_start_date TEXT DEFAULT '',
        plan_end_date TEXT DEFAULT '',
        responsible_person TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        updated_at TEXT,
        UNIQUE(version_id, plan_type, device_name)
    )
    """)

    # 价值点验收表（手动输入 IR 验收结论）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS value_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        value_name TEXT NOT NULL DEFAULT '',
        ir_conclusion TEXT NOT NULL DEFAULT 'PASS',
        fail_reason TEXT DEFAULT '',
        test_owner TEXT DEFAULT '',
        updated_at TEXT,
        UNIQUE(version_id, value_name)
    )
    """)

    # Jira Filter Presets 表：存储每个版本的 JQL 过滤器（默认 + 用户自定义）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_filter_preset (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        filter_key TEXT NOT NULL,
        label TEXT NOT NULL,
        description TEXT DEFAULT '',
        default_jql TEXT NOT NULL,
        custom_jql TEXT,
        updated_at TEXT,
        UNIQUE(version_id, filter_key)
    )
    """)

    conn.commit()

    # 迁移：给 version_config 添加 ALM space/app bid 列（按版本配置）
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN alm_space_bid TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN alm_app_bid TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM version_config")
    count = cur.fetchone()["c"]

    if count == 0:
        # 版本配置：(显示名称, Jira项目key, Jira版本字段, 负责人, 是否版本火车)
        # Jira中项目key就是 OS162, OS163, OS170
        # 注意：不同版本在Jira中的project key前缀不同
        # 16.2 -> OS162, 16.3 -> TOS163, 17.0 -> TOS170
        seed_versions = [
            ("tOS16.2", "OS162", "OS162", "未配置", 0),
            ("tOS16.3", "TOS163", "TOS163", "未配置", 0),
            ("tOS17.0", "TOS170", "TOS170", "未配置", 0),
        ]

        for v in seed_versions:
            cur.execute("""
            INSERT INTO version_config (
                version_name, jira_project, jira_fix_version, owner_name, is_train_version, created_at,
                baseline_date, branch_name, device_count, device_list, coverage_scope, project_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (*v, now_iso(), "", f"{v[0]}_release", 6, "", "手机+PAD", "进行中"))
            version_id = cur.lastrowid

            # 创建STR1-STR5阶段 + STA5(1+N)阶段
            today = date.today()
            stage_names = ["STR1", "STR2", "STR3", "STR4", "STR5", "STA5"]
            for i, stage_name in enumerate(stage_names):
                start = today - timedelta(days=(6 - i) * 7)
                end = start + timedelta(days=6)
                cur.execute("""
                INSERT INTO str_stage_config (
                    version_id, stage_name, start_date, end_date, current_flag
                )
                VALUES (?, ?, ?, ?, ?)
                """, (
                    version_id,
                    stage_name,
                    start.isoformat(),
                    end.isoformat(),
                    1 if i == 2 else 0  # 默认选中STR3
                ))

    # 为所有版本播种默认 Jira Filter Presets（不覆盖用户自定义的 JQL）
    _seed_filter_presets(cur, force_update=False)

    conn.commit()

    # ---- 数据迁移：修正已有数据库中 16.3 / 17.0 的 Jira project key ----
    # 16.2 -> OS162, 16.3 -> TOS163, 17.0 -> TOS170（前缀不一致）
    project_key_fixes = [
        ("OS163", "TOS163"),
        ("OS170", "TOS170"),
    ]
    for wrong_key, correct_key in project_key_fixes:
        cur.execute("""
            UPDATE version_config
            SET jira_project = ?, jira_fix_version = ?
            WHERE jira_project = ?
        """, (correct_key, correct_key, wrong_key))
        if cur.rowcount > 0:
            print(f"[迁移] 已将 jira_project '{wrong_key}' 修正为 '{correct_key}'")

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


class VersionCreate(BaseModel):
    version_name: str
    jira_project: str = "TOS"
    jira_fix_version: Optional[str] = None
    owner_name: str = "未配置"
    is_train_version: bool = False
    baseline_date: Optional[str] = None
    branch_name: Optional[str] = None
    device_count: Optional[int] = 6
    device_list: Optional[str] = ""
    coverage_scope: Optional[str] = "手机+PAD"
    project_status: Optional[str] = "进行中"
    feishu_sheet_url: Optional[str] = ""
    perf_sheet_url: Optional[str] = ""
    battery_sheet_url: Optional[str] = ""
    alm_space_bid: Optional[str] = ""
    alm_app_bid: Optional[str] = ""


class VersionUpdate(BaseModel):
    version_name: Optional[str] = None
    jira_project: Optional[str] = None
    jira_fix_version: Optional[str] = None
    owner_name: Optional[str] = None
    is_train_version: Optional[bool] = None
    baseline_date: Optional[str] = None
    branch_name: Optional[str] = None
    device_count: Optional[int] = None
    device_list: Optional[str] = None
    coverage_scope: Optional[str] = None
    project_status: Optional[str] = None
    feishu_sheet_url: Optional[str] = None
    perf_sheet_url: Optional[str] = None
    battery_sheet_url: Optional[str] = None
    alm_space_bid: Optional[str] = None
    alm_app_bid: Optional[str] = None


class StageUpdate(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    current_flag: Optional[int] = None


class CredentialSave(BaseModel):
    jira_base_url: str = DEFAULT_JIRA_BASE_URL
    username: str
    password_or_token: str


class SyncRequest(BaseModel):
    use_mock: bool = False
    force_full: bool = False  # 强制全量同步（忽略本地缓存，重新抓取全部数据）


class StageBatchUpdate(BaseModel):
    """批量更新STR阶段时间"""
    stages: List[Dict[str, Any]]  # [{"stage_name": "STR1", "start_date": "2025-01-01", "end_date": "2025-01-07", "current_flag": 0}, ...]


class FeishuImportRequest(BaseModel):
    """从飞书表格导入STR时间表"""
    feishu_url: str
    app_id: Optional[str] = None
    app_secret: Optional[str] = None


class FeishuConfigSave(BaseModel):
    app_id: str
    app_secret: str


def row_to_dict(row):
    return dict(row) if row else None


# ==============================
# 飞书配置管理
# ==============================
@app.get("/api/feishu/config")
def get_feishu_config():
    """获取飞书应用配置（secret 脱敏显示）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM feishu_config WHERE id = 1")
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row:
        return {"app_id": "", "app_secret_masked": ""}
    app_id = row.get("app_id", "")
    secret = row.get("app_secret", "")
    masked = (secret[:6] + "***") if len(secret) > 6 else ("***" if secret else "")
    return {"app_id": app_id, "app_secret_masked": masked}


@app.post("/api/feishu/config")
def save_feishu_config(req: FeishuConfigSave):
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
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row or not row.get("app_id") or not row.get("app_secret"):
        return None
    return {"app_id": row["app_id"], "app_secret": row["app_secret"]}


# ==============================
# 飞书 OAuth 用户级授权
# ==============================
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_REDIRECT_URI = "http://127.0.0.1:8000/callback"
FEISHU_USER_TOKEN_PATH = APP_DIR / "feishu_user_token_cache.json"

FEISHU_OAUTH_SCOPES = [
    "wiki:node:read",
    "wiki:wiki:readonly",
    "sheets:spreadsheet:read",
    "sheets:spreadsheet.meta:read",
    "drive:drive.metadata:readonly",
]


def load_json_file(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_ts():
    return int(time.time())


def get_cached_user_token():
    """获取可用的 user_access_token，过期自动用 refresh_token 刷新。
    改进：更完善的错误处理、日志记录、以及 refresh_token 有效性检查。"""
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


@app.get("/api/feishu/login")
def feishu_login():
    """跳转到飞书 OAuth 授权页面"""
    scope_str = " ".join(FEISHU_OAUTH_SCOPES)
    from secrets import token_urlsafe
    state = token_urlsafe(16)
    auth_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={quote(FEISHU_APP_ID)}"
        f"&redirect_uri={quote(FEISHU_REDIRECT_URI, safe='')}"
        f"&scope={quote(scope_str, safe='')}"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=auth_url)


@app.get("/api/feishu/callback")
def feishu_callback(code: str = "", state: str = "", error: str = ""):
    """飞书 OAuth 回调：用 code 换取 user_access_token"""
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


# 兼容路由：飞书应用配置的回调地址是 /callback
@app.get("/callback")
def feishu_callback_compat(code: str = "", state: str = "", error: str = ""):
    return feishu_callback(code=code, state=state, error=error)


@app.get("/api/feishu/token-status")
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


@app.get("/api/versions")
def list_versions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config ORDER BY id ASC")
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/versions")
def create_version(req: VersionCreate):
    conn = get_conn()
    cur = conn.cursor()

    fix_version = req.jira_fix_version or req.version_name

    try:
        cur.execute("""
        INSERT INTO version_config (
            version_name, jira_project, jira_fix_version, owner_name, is_train_version, created_at,
            baseline_date, branch_name, device_count, device_list, coverage_scope, project_status,
            alm_space_bid, alm_app_bid
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.version_name,
            req.jira_project,
            fix_version,
            req.owner_name,
            1 if req.is_train_version else 0,
            now_iso(),
            req.baseline_date or "",
            req.branch_name or f"{req.version_name}_release",
            req.device_count or 6,
            req.device_list or "",
            req.coverage_scope or "手机+PAD",
            req.project_status or "进行中",
            req.alm_space_bid or "",
            req.alm_app_bid or "",
        ))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="该版本已存在")

    version_id = cur.lastrowid

    today = date.today()
    # 创建 STR1-5 + STA5 阶段
    stage_names = [f"STR{i}" for i in range(1, 6)] + ["STA5"]
    for i, stage_name in enumerate(stage_names):
        start = today + timedelta(days=i * 7)
        end = start + timedelta(days=6)
        cur.execute("""
        INSERT INTO str_stage_config (
            version_id, stage_name, start_date, end_date, current_flag
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            version_id,
            stage_name,
            start.isoformat(),
            end.isoformat(),
            1 if i == 0 else 0
        ))

    conn.commit()
    conn.close()

    return {"id": version_id, "message": "版本创建成功"}


@app.get("/api/versions/{version_id}/stages")
def list_stages(version_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ?
    ORDER BY stage_name ASC
    """, (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.put("/api/versions/{version_id}")
def update_version(version_id: int, req: VersionUpdate):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    update_fields = []
    update_values = []

    if req.version_name is not None:
        update_fields.append("version_name = ?")
        update_values.append(req.version_name)
    if req.jira_project is not None:
        update_fields.append("jira_project = ?")
        update_values.append(req.jira_project)
    if req.jira_fix_version is not None:
        update_fields.append("jira_fix_version = ?")
        update_values.append(req.jira_fix_version)
    if req.owner_name is not None:
        update_fields.append("owner_name = ?")
        update_values.append(req.owner_name)
    if req.is_train_version is not None:
        update_fields.append("is_train_version = ?")
        update_values.append(1 if req.is_train_version else 0)
    if req.baseline_date is not None:
        update_fields.append("baseline_date = ?")
        update_values.append(req.baseline_date)
    if req.branch_name is not None:
        update_fields.append("branch_name = ?")
        update_values.append(req.branch_name)
    if req.device_count is not None:
        update_fields.append("device_count = ?")
        update_values.append(req.device_count)
    if req.device_list is not None:
        update_fields.append("device_list = ?")
        update_values.append(req.device_list)
    if req.coverage_scope is not None:
        update_fields.append("coverage_scope = ?")
        update_values.append(req.coverage_scope)
    if req.project_status is not None:
        update_fields.append("project_status = ?")
        update_values.append(req.project_status)
    if req.feishu_sheet_url is not None:
        update_fields.append("feishu_sheet_url = ?")
        update_values.append(req.feishu_sheet_url)
    if req.perf_sheet_url is not None:
        update_fields.append("perf_sheet_url = ?")
        update_values.append(req.perf_sheet_url)
    if req.battery_sheet_url is not None:
        update_fields.append("battery_sheet_url = ?")
        update_values.append(req.battery_sheet_url)
    if req.alm_space_bid is not None:
        update_fields.append("alm_space_bid = ?")
        update_values.append(req.alm_space_bid)
    if req.alm_app_bid is not None:
        update_fields.append("alm_app_bid = ?")
        update_values.append(req.alm_app_bid)

    if update_fields:
        update_values.append(version_id)
        sql = f"UPDATE version_config SET {', '.join(update_fields)} WHERE id = ?"
        cur.execute(sql, update_values)

    conn.commit()
    conn.close()

    return {"message": "版本信息更新成功"}


@app.put("/api/versions/{version_id}/stages/batch")
def batch_update_stages(version_id: int, req: StageBatchUpdate):
    """
    批量更新STR阶段的截止时间。
    只需传入每个阶段的 end_date，start_date 自动根据上一阶段截止+1天计算。
    STR1 的开始日期 = 项目基线日期（若未设置则取 STR1 end_date 前推7天）。
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    # 收集截止时间，按 STR1-STR5 顺序
    stage_order = ["STR1", "STR2", "STR3", "STR4", "STR5", "STA5"]
    end_dates = {}
    current_stage = None

    for stage in req.stages:
        name = stage.get("stage_name", "")
        end_date = stage.get("end_date", "").strip()
        if name in stage_order and end_date:
            end_dates[name] = end_date
        if stage.get("current_flag"):
            current_stage = name

    # 根据截止时间自动计算开始时间
    # 逻辑：每个阶段的开始 = 上一阶段截止 +1天
    # STA5 的开始始终 = STR5 截止 +1天（即使 STA5 没有截止时间）
    baseline = (version.get("baseline_date") or "").strip()
    computed = {}  # {stage_name: (start_date, end_date)}

    prev_end = None
    for name in stage_order:
        end_date = end_dates.get(name, "")

        if name == "STR1":
            if end_date:
                if baseline:
                    start = baseline
                else:
                    try:
                        start = (parser.parse(end_date) - timedelta(days=7)).strftime("%Y-%m-%d")
                    except Exception:
                        start = ""
            else:
                start = ""
        elif name == "STA5":
            # STA5 开始 = STR5 截止 +1天，无需自己有截止时间
            if prev_end:
                try:
                    start = (parser.parse(prev_end) + timedelta(days=1)).strftime("%Y-%m-%d")
                except Exception:
                    start = ""
            else:
                start = ""
        elif prev_end:
            try:
                start = (parser.parse(prev_end) + timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                start = ""
        else:
            start = ""

        computed[name] = (start, end_date)
        if end_date:
            prev_end = end_date

    # 写入数据库（存在则更新，不存在则插入）
    cur.execute("UPDATE str_stage_config SET current_flag = 0 WHERE version_id = ?", (version_id,))

    for name in stage_order:
        start_date, end_date = computed.get(name, ("", ""))
        current_flag = 1 if name == current_stage else 0
        cur.execute("""
            INSERT INTO str_stage_config (version_id, stage_name, start_date, end_date, current_flag)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(version_id, stage_name)
            DO UPDATE SET start_date = excluded.start_date, end_date = excluded.end_date, current_flag = excluded.current_flag
        """, (version_id, name, start_date, end_date, current_flag))

    conn.commit()

    # 返回更新后的完整阶段列表
    cur.execute("""
        SELECT * FROM str_stage_config WHERE version_id = ? ORDER BY stage_name ASC
    """, (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    return {"message": "STR时间表已保存", "stages": rows}


def excel_serial_to_date(value: float) -> str:
    """
    飞书/Excel 日期序列号转 YYYY-MM-DD。
    常见基准日是 1899-12-30（与 read_feishu_sheet 一致）。
    """
    try:
        base_date = datetime(1899, 12, 30)
        date_value = base_date + timedelta(days=float(value))
        return date_value.strftime("%Y-%m-%d")
    except Exception:
        return ""


def normalize_feishu_date(raw) -> str:
    """
    将飞书表格中的各种日期格式统一为 YYYY-MM-DD。
    支持：
    - Unix 时间戳（秒级 10位 / 毫秒级 13位，飞书 API 常见返回格式）
    - Excel/飞书日期序列号（数字，如 45897 → 2025-08-29）
    - 字符串形式的时间戳（如 "1748928000000"、"1748928000"）
    - 2025/01/15, 2025-01-15
    - 2025年1月15日, 2025年01月15日
    - 01月15日, 1月15日, 1月15号
    - 带制表符前缀的文本日期（Excel 安全 CSV 格式）
    """
    if raw is None:
        return ""

    # ---------- 数字类型 ----------
    if isinstance(raw, (int, float)):
        raw_num = raw
    elif isinstance(raw, str):
        raw = raw.strip().lstrip("\t")
        # 尝试将字符串解析为数字
        try:
            raw_num = float(raw)
        except (ValueError, TypeError):
            raw_num = None
    else:
        raw_num = None

    if raw_num is not None:
        # 1) Unix 毫秒时间戳（13 位，如 1748928000000）
        if 1000000000000 <= raw_num <= 9999999999999:
            try:
                dt = datetime.fromtimestamp(raw_num / 1000.0, tz=CST)
                result = dt.strftime("%Y-%m-%d")
                print(f"[日期解析] Unix毫秒时间戳 {raw} → {result}")
                return result
            except Exception:
                pass

        # 2) Unix 秒级时间戳（10 位，如 1748928000）
        if 1000000000 <= raw_num <= 9999999999:
            try:
                dt = datetime.fromtimestamp(raw_num, tz=CST)
                result = dt.strftime("%Y-%m-%d")
                print(f"[日期解析] Unix秒级时间戳 {raw} → {result}")
                return result
            except Exception:
                pass

        # 3) Excel 日期序列号（典型范围 40000-50000，覆盖 2009-2036 年）
        if 38000 <= raw_num <= 55000:
            result = excel_serial_to_date(raw_num)
            if result:
                print(f"[日期解析] Excel序列号 {raw} → {result}")
                return result

        # 4) 其他数字，不作为日期处理
        return ""

    # ---------- 字符串类型（非纯数字） ----------
    if not raw:
        return ""

    # 去除制表符前缀（Excel 安全 CSV 格式）
    raw = raw.lstrip("\t").strip()
    if not raw:
        return ""

    # 1) 尝试 "YYYY年M月D日/号" 格式（优先匹配，避免被 parser.parse 误读）
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?', raw)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            result = f"{year}-{month:02d}-{day:02d}"
            print(f"[日期解析] 中文完整日期 '{raw}' → {result}")
            return result
        except ValueError:
            pass

    # 2) 尝试 "M月D日/号" 格式（无年份时取当前年）
    m = re.match(r'(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?', raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = datetime.now().year
        try:
            result = f"{year}-{month:02d}-{day:02d}"
            print(f"[日期解析] 中文月日 '{raw}' → {result}")
            return result
        except ValueError:
            pass

    # 3) 使用 dateutil.parser 解析标准格式（2025/01/15、2025-01-15 等）
    try:
        dt = parser.parse(raw, yearfirst=True)
        result = dt.strftime("%Y-%m-%d")
        print(f"[日期解析] parser.parse '{raw}' → {result}")
        return result
    except Exception:
        pass

    print(f"[日期解析] 无法解析: '{raw}'")
    return ""


def infer_date_with_year(date_str: str, prev_date: Optional[str]) -> str:
    """
    处理无年份的日期字符串（如 "9/12"、"3/19"），按阶段时间顺序推断正确年份。
    规则：
    1. 有完整年份的日期（如 "2025-08-29"）直接返回
    2. 无年份时，按上一个阶段的日期推断：若月份倒退，说明跨年，年份 +1
    3. 若无前序日期参考，使用当前年份，但若月份在未来（>当前月+3），回退到去年
    """
    # 先用 normalize 解析原始日期（对于有年份的日期，直接返回）
    normalized = normalize_feishu_date(date_str)
    if not normalized:
        return ""

    # 检测原始日期是否包含年份信息
    raw = str(date_str).strip().lstrip("\t")
    has_year = bool(re.search(r'\d{4}', raw))  # 包含 4 位数字 → 有年份

    if has_year:
        return normalized  # 有完整年份，直接用

    # 无年份，需要推断
    try:
        dt = parser.parse(normalized)
    except Exception:
        return normalized

    month = dt.month
    year = dt.year  # dateutil 默认用当前年

    if prev_date:
        try:
            prev_dt = parser.parse(prev_date)
            prev_month = prev_dt.month
            prev_year = prev_dt.year
            # 月份倒退 → 跨年：比如 9月 → 1月 的跨度意味着从 2025 跨到 2026
            if month < prev_month - 2:
                year = prev_year + 1
            else:
                year = prev_year
        except Exception:
            pass
    else:
        # 无前序参考时的年份推断：
        # 若月份在当前月之前或当月 → 用当前年（如当前6月，month=3 → 2026）
        # 若月份在当前月之后 → 用去年（如当前6月，month=9 → 2025）
        # 原理：项目计划通常已开始（STR1在前），当前处于后期阶段
        now = datetime.now()
        if month > now.month:
            year = now.year - 1
        else:
            year = now.year

    result = dt.replace(year=year).strftime("%Y-%m-%d")
    if result != normalized:
        print(f"[年份推断] '{raw}' 原始={normalized}, 推断后={result}")
    return result


def parse_feishu_url(url: str):
    """
    解析飞书 Wiki URL，提取 wiki_node_token 和 sheet_id。
    与 read_feishu_sheet 脚本逻辑一致。
    格式: https://xxx.feishu.cn/wiki/TOKEN?sheet=SHEET_ID
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    wiki_node_token = None
    sheet_id = None

    # 方式1: 标准 wiki URL 路径
    if len(path_parts) >= 2 and path_parts[0] == "wiki":
        wiki_node_token = path_parts[1]

    # 方式2: 兜底正则匹配
    if not wiki_node_token:
        m = re.search(r'/wiki/([A-Za-z0-9]+)', url)
        if m:
            wiki_node_token = m.group(1)

    # 从 query 提取 sheet_id
    query = parse_qs(parsed.query)
    sheet_id = query.get("sheet", [None])[0]

    # 兜底正则
    if not sheet_id:
        m = re.search(r'[?&]sheet=([^&]+)', url)
        if m:
            sheet_id = m.group(1)

    return wiki_node_token, sheet_id


def rich_text_to_plain_text(cell):
    """
    飞书富文本单元格转普通文本（与 read_feishu_sheet 一致）。
    """
    if isinstance(cell, list):
        parts = []
        for item in cell:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            elif isinstance(item, list):
                parts.append(rich_text_to_plain_text(item))
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(cell, dict):
        if "text" in cell:
            return str(cell.get("text", ""))
        return json.dumps(cell, ensure_ascii=False)
    return cell


def feishu_cell_to_str(cell) -> str:
    """
    将飞书单元格值标准化为字符串。
    处理富文本、None、数字等情况。
    """
    if cell is None:
        return ""
    cell = rich_text_to_plain_text(cell)
    return str(cell).strip()


def get_feishu_access_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token"""
    token_resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10
    )
    token_data = safe_json(token_resp, "获取飞书token")
    if token_data.get("code") != 0:
        raise HTTPException(
            status_code=400,
            detail=f"获取飞书token失败: {token_data.get('msg', '未知错误')}"
        )
    return token_data["tenant_access_token"]


def resolve_wiki_to_spreadsheet_token(headers: dict, wiki_node_token: str) -> str:
    """
    将 wiki_node_token 解析为实际的 spreadsheet_token。
    尝试多种 API 路径，任何一步失败都不中断，继续 fallback。
    """
    wiki_apis = [
        f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={wiki_node_token}",
        f"https://open.feishu.cn/open-apis/wiki/v2/nodes/{wiki_node_token}",
    ]
    for api_path in wiki_apis:
        try:
            wiki_resp = requests.get(api_path, headers=headers, timeout=10)
            if wiki_resp.status_code != 200:
                print(f"Wiki API {api_path} 返回HTTP {wiki_resp.status_code}，跳过")
                continue
            wiki_data = wiki_resp.json()
            if wiki_data.get("code") == 0:
                node = wiki_data.get("data", {}).get("node", {})
                obj_token = node.get("obj_token", wiki_node_token)
                print(f"飞书文档信息: obj_token={obj_token}, obj_type={node.get('obj_type', '')}")
                return obj_token
            print(f"Wiki API {api_path} 业务错误: code={wiki_data.get('code')}, msg={wiki_data.get('msg', '')}")
        except Exception as e:
            print(f"Wiki API {api_path} 异常: {e}，跳过")

    # 兜底：直接用 wiki_token 当作 spreadsheet_token
    print(f"Wiki API 均无法解析，尝试直接用 wiki_token={wiki_node_token} 作为 spreadsheet_token")
    return wiki_node_token


@app.post("/api/versions/{version_id}/stages/import-feishu")
def import_feishu_stages(version_id: int, req: FeishuImportRequest):
    """
    从飞书表格导入STR时间表。
    使用 OAuth user_access_token 访问飞书表格。
    支持按版本名称匹配对应行（同一张表中不同版本有不同行）。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
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
    feishu_url = req.feishu_url.strip()
    wiki_token, sheet_id = parse_feishu_url(feishu_url)

    if not wiki_token:
        conn.close()
        raise HTTPException(status_code=400, detail="无法从URL中解析出wiki token，请检查URL格式")

    print(f"飞书URL解析: wiki_token={wiki_token}, sheet_id={sheet_id}")

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
                detail=(
                    f"无法访问飞书表格（code={meta_data.get('code')}，token={obj_token}）。\n"
                    f"请按以下步骤排查：\n"
                    f"1. 打开飞书文档 → 右上角「分享」→ 添加应用机器人为「可阅读」协作者\n"
                    f"2. 确保飞书应用已发布（开发中的应用无法调用API）\n"
                    f"3. 确保应用已开通 sheets:spreadsheet:read 权限\n"
                    f"原始错误: {meta_data.get('msg', '')}"
                )
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

        print(f"使用表格: {target_sheet.get('title', '')}, sheet_id={sheet_id}")

        # 读取表格数据（扩大到 100 行，与 read_feishu_sheet 一致）
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
            raise HTTPException(status_code=400, detail="飞书表格数据行数不足，至少需要3行（表头+阶段名+日期）")

        print(f"读取到 {len(raw_values)} 行数据")

        # =============================================
        # 数据清洗：富文本转纯文本（与 read_feishu_sheet 一致）
        # =============================================
        values = []
        for row in raw_values:
            values.append([feishu_cell_to_str(cell) for cell in (row or [])])

        # =============================================
        # 智能解析表格结构
        # 典型结构（多行表头 + 版本数据区）：
        #   行0: ww | | | | | | | | | | | | | |
        #   行1: 类别 | | 项目 | 开发周期 | 项目计划 | 阶段 | 规划阶段 | ... | 概念阶段 | ... | 计划阶段 | ... | 开发验证阶段
        #   行2: | | | | | 关键节点 | 立项准备 | ... | STR1 | ... | STR2 | STR3 | STR4 | STR4A | STR5
        #   行3: | | | | | 里程碑 | 规划KO | DCP1 | ... | 概念启动 | 预评审 | STR1 | 预评审 | STR2 | ... | STR5
        #   行4: 版本  tOS16.3 | 215天 | 计划V0.2 | | 9/12 | | 9/26 | 10/30 | ... | 4/15
        #   行5: | | | | 计划V0.3 | | 9/12 | | 9/28 | ... | 4/15
        #   行6: | | | | 计划V1.1 | | 9/12 | ... | 5/8
        #   行7: | | | | 实际 | | 9/12 | ... | 5/8
        #
        # 关键点：
        #   - "里程碑"行中的 "STR1" 是严格独立单元格，对应正确的列
        #   - "关键节点"行中的 "STR1" 可能和"预评审"混在一起
        #   - 日期可能没有年份（如 "9/12"），需要按阶段顺序推断年份
        #   - 取最新的"计划"行（最靠下的那个，如计划V1.1）
        # =============================================

        TARGET_STAGES = ["STR1", "STR2", "STR3", "STR4", "STR5"]
        str_pattern = re.compile(r'^STR\s*(\d)$', re.IGNORECASE)

        # ---- 第1步：在"里程碑"行中严格匹配 STR 列 ----
        # "里程碑"行中 STR1/STR2/... 是独立单元格（不是"预评审"的一部分）
        stage_col_map = {}  # {"STR1": col_idx, ...}
        milestone_row_idx = None

        for row_idx, row in enumerate(values):
            if not row:
                continue
            has_milestone = any(c and "里程碑" in c for c in row)
            if not has_milestone:
                continue
            # 找到"里程碑"行，严格匹配 STR 列
            temp_map = {}
            for col_idx, cell in enumerate(row):
                if not cell:
                    continue
                m = str_pattern.match(cell.strip())
                if m:
                    stage = f"STR{m.group(1)}"
                    if stage in TARGET_STAGES and stage not in temp_map:
                        temp_map[stage] = col_idx
            # 找到 >= 3 个 STR 列才认为是正确的里程碑行
            if len(temp_map) >= 3:
                stage_col_map = temp_map
                milestone_row_idx = row_idx
                print(f"里程碑行: row={row_idx}, STR列={stage_col_map}")
                break

        # 兜底：没有"里程碑"行，扫描所有行严格匹配
        if not stage_col_map:
            print("未找到里程碑行，使用全表扫描兜底")
            for row_idx, row in enumerate(values):
                if not row:
                    continue
                for col_idx, cell in enumerate(row):
                    if not cell:
                        continue
                    m = str_pattern.match(cell.strip())
                    if m:
                        stage = f"STR{m.group(1)}"
                        if stage in TARGET_STAGES and stage not in stage_col_map:
                            stage_col_map[stage] = col_idx

        print(f"最终STR列位置: {stage_col_map}")

        if not stage_col_map:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="未能从表格中识别出任何STR阶段名称（如 STR1、STR2 等）。请确保表格中包含这些标识。"
            )

        # ---- 第2步：从里程碑行下方开始，找版本行和最新的"计划"行 ----
        # 关键：不能从 row=0 开始扫描（会匹配到标题行如 "tOS16.3开发计划V0.4"）
        # 必须从里程碑行（表头结束）下方开始
        search_start = (milestone_row_idx + 1) if milestone_row_idx is not None else 0
        vn_lower = version_name.lower().replace(" ", "")
        version_row_idx = None
        date_row = None

        # 表格结构（里程碑行下方）：
        #   row N:   版本 | tOS16.3 | | 215天 | 计划V0.2 | ...  ← 版本行
        #   row N+1: | | | | 计划V0.3 | ...                      ← 计划子行（第一列为空）
        #   row N+2: | | | | 计划V1.1 | ...                      ← 计划子行
        #   row N+3: | | | | 实际 | ...                           ← 实际行
        #
        # 版本行特征：任意列包含版本名
        # 计划子行特征：第一列为空，"项目计划"列 以 "计划" 开头

        for row_idx in range(search_start, len(values)):
            row = values[row_idx]
            if not row:
                continue
            first_cell = (row[0] or "").strip()

            if version_row_idx is None:
                # 寻找版本行：任意列包含版本名（如 "tOS16.3"）
                row_text = " ".join(str(c or "") for c in row).lower().replace(" ", "")
                if vn_lower in row_text:
                    version_row_idx = row_idx
                    print(f"匹配到版本行: row={row_idx}, first_cell='{first_cell}'")
                    continue
            else:
                # 版本行已找到，在其下方找"计划"行
                # 计划子行特征：第一列为空（子行），且包含"计划"的列以"计划"开头
                # 排除："项目计划"（列标题，"计划"不在开头）、"实际"行
                if not first_cell:
                    # 子行：扫描所有列，找以"计划"开头的单元格
                    for cell in row:
                        cell_s = (cell or "").strip().replace(" ", "")
                        if cell_s.startswith("计划") or cell_s.lower().startswith("plan"):
                            date_row = row_idx  # 不 break，继续找更靠下的（取最新）
                            break

        # 兜底：如果版本行已找到但没找到计划行，找日期最多的子行
        if date_row is None and version_row_idx is not None:
            best_row = None
            best_count = 0
            for row_idx in range(version_row_idx, len(values)):
                row = values[row_idx]
                if not row:
                    continue
                # 跳过"实际"行
                has_shiji = any((c or "").strip().replace(" ", "") == "实际" for c in row)
                if has_shiji:
                    continue
                cnt = 0
                for _, col_idx in stage_col_map.items():
                    if col_idx < len(row):
                        raw_cell = raw_values[row_idx][col_idx] if row_idx < len(raw_values) and col_idx < len(raw_values[row_idx]) else None
                        if isinstance(raw_cell, (int, float)):
                            if normalize_feishu_date(raw_cell):
                                cnt += 1
                        elif row[col_idx] and normalize_feishu_date(row[col_idx]):
                            cnt += 1
                if cnt > best_count:
                    best_count = cnt
                    best_row = row_idx
            date_row = best_row

        print(f"版本名={version_name}, 版本行={version_row_idx}, 计划行={date_row}")

        if date_row is None:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"未能找到「{version_name}」对应的日期行。"
                    f"已识别到STR列位置: {stage_col_map}，搜索起始行: {search_start}。"
                    f"请确认表格中里程碑行下方存在「计划Vx.x」行。"
                )
            )

        # ---- 第3步：从计划行提取日期，按阶段顺序推断缺失年份 ----
        date_row_data = values[date_row]
        raw_date_row = raw_values[date_row] if date_row < len(raw_values) else []
        end_dates = {}
        prev_date = None  # 用于年份推断的前序日期

        for stage_name in TARGET_STAGES:
            col_idx = stage_col_map.get(stage_name)
            if col_idx is None or col_idx >= len(date_row_data):
                continue

            # 优先用原始数值（数字类型精度更高）
            raw_cell = raw_date_row[col_idx] if col_idx < len(raw_date_row) else None
            deadline = None
            if isinstance(raw_cell, (int, float)):
                deadline = normalize_feishu_date(raw_cell)

            # 兜底用文本
            if not deadline:
                cell_str = date_row_data[col_idx]
                if cell_str:
                    deadline = normalize_feishu_date(cell_str)

            if deadline:
                # 推断缺失年份
                cell_str = date_row_data[col_idx] if col_idx < len(date_row_data) else ""
                deadline = infer_date_with_year(cell_str, prev_date)
                end_dates[stage_name] = deadline
                prev_date = deadline
                print(f"  {stage_name} 列={col_idx} → {deadline}")

        print(f"提取到截止时间: {end_dates}")

        if not end_dates:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"未能从日期行中提取到有效的截止时间。日期行内容: {date_row_data}"
            )

        # ---- 同时保存版本的飞书 URL ----
        cur.execute("UPDATE version_config SET feishu_sheet_url = ? WHERE id = ?", (feishu_url, version_id))

        # 根据截止时间自动计算开始时间（与 batch_update 相同逻辑）
        baseline = (version.get("baseline_date") or "").strip()
        stage_order = ["STR1", "STR2", "STR3", "STR4", "STR5", "STA5"]
        computed = {}
        prev_end = None

        for name in stage_order:
            ed = end_dates.get(name, "")

            if name == "STR1":
                if ed:
                    if baseline:
                        start = baseline
                    else:
                        try:
                            start = (parser.parse(ed) - timedelta(days=7)).strftime("%Y-%m-%d")
                        except Exception:
                            start = ""
                else:
                    start = ""
            elif name == "STA5":
                if prev_end:
                    try:
                        start = (parser.parse(prev_end) + timedelta(days=1)).strftime("%Y-%m-%d")
                    except Exception:
                        start = ""
                else:
                    start = ""
            elif prev_end:
                try:
                    start = (parser.parse(prev_end) + timedelta(days=1)).strftime("%Y-%m-%d")
                except Exception:
                    start = ""
            else:
                start = ""

            computed[name] = (start, ed)
            if ed:
                prev_end = ed

        # 写入数据库（存在则更新，不存在则插入）
        for name in stage_order:
            start_date, end_date = computed.get(name, ("", ""))
            cur.execute("""
                INSERT INTO str_stage_config (version_id, stage_name, start_date, end_date, current_flag)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(version_id, stage_name)
                DO UPDATE SET start_date = excluded.start_date, end_date = excluded.end_date
            """, (version_id, name, start_date, end_date))

        conn.commit()

        # 返回结果
        imported_stages = [
            {"stage_name": n, "start_date": computed[n][0], "end_date": computed[n][1]}
            for n in stage_order if end_dates.get(n)
        ]

        cur.execute("""
            SELECT * FROM str_stage_config WHERE version_id = ? ORDER BY stage_name ASC
        """, (version_id,))
        rows = [row_to_dict(r) for r in cur.fetchall()]
        conn.close()

        return {
            "message": f"从飞书导入了 {len(imported_stages)} 个阶段的截止时间",
            "imported": imported_stages,
            "stages": rows,
            "source_url": feishu_url,
            "sheet_title": target_sheet.get("title", ""),
        }

    except requests.exceptions.ConnectionError:
        conn.close()
        raise HTTPException(status_code=502, detail="无法连接到飞书服务器")
    except requests.exceptions.Timeout:
        conn.close()
        raise HTTPException(status_code=504, detail="飞书请求超时")
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        print(f"飞书导入异常: {e}")
        raise HTTPException(status_code=500, detail=f"飞书导入失败: {str(e)}")


@app.get("/api/versions/{version_id}/device-info")
def get_device_info(version_id: int):
    """
    从飞书管理书表格中读取机型信息，按分类（首发/衍生/存量SR适配）返回。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, feishu_sheet_url FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"categories": {}, "text": "", "message": "未配置管理书地址"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"categories": {}, "text": "", "message": "请先完成飞书授权"}

    try:
        wiki_token, sheet_id = parse_feishu_url(feishu_url)
        if not wiki_token:
            return {"categories": {}, "text": "", "message": "URL格式无法解析"}

        headers = {"Authorization": f"Bearer {access_token}"}
        obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

        # 获取表格元信息 → 选 sheet
        meta_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
            headers=headers, timeout=10
        )
        meta_data = safe_json(meta_resp, "获取表格元信息")
        if meta_data.get("code") != 0:
            return {"categories": {}, "text": "", "message": f"无法访问飞书表格: {meta_data.get('msg', '')}"}

        sheets = meta_data.get("data", {}).get("sheets", [])
        if not sheets:
            return {"categories": {}, "text": "", "message": "飞书文档中没有表格"}

        target_sheet = None
        if sheet_id:
            for s in sheets:
                if s.get("sheet_id") == sheet_id:
                    target_sheet = s
                    break
        if not target_sheet:
            target_sheet = sheets[0]
            sheet_id = target_sheet.get("sheet_id")

        # 读取表格（扩大范围覆盖机型区域）
        range_str = f"{sheet_id}!A1:Z200"
        data_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
            headers=headers, timeout=30
        )
        data_json = safe_json(data_resp, "读取表格数据")
        if data_json.get("code") != 0:
            return {"categories": {}, "text": "", "message": f"读取表格失败: {data_json.get('msg', '')}"}

        raw_values = data_json.get("data", {}).get("valueRange", {}).get("values", [])
        if not raw_values:
            return {"categories": {}, "text": "", "message": "表格数据为空"}

        # 富文本转纯文本
        values = [[feishu_cell_to_str(cell) for cell in (row or [])] for row in raw_values]

        # ---- 机型提取逻辑 ----
        # 表格结构（列式布局，关键词和设备名在相邻两列）：
        #   ... | A列(分类) | B列(设备名) | ...
        #       | 首发     | P685L(T7250)|
        #       |          | CN6c(G200)  |
        #       | 衍生     | S689LN(T7300)|
        #       |          | LK7(D7400)  |
        #
        # 策略：全表扫描找"首发"，然后读取其右边一列的设备名，
        #       向下直到遇到下一个分类关键词或空行。
        #       再向前检查是否有"存量SR适配"。
        #       只读关键词右边紧邻的一列，不多读。

        CATEGORY_KEYWORDS = {"首发", "衍生", "存量SR适配"}
        # 明确的非设备值：表头/阶段名/关键词
        NON_DEVICE_VALUES = CATEGORY_KEYWORDS | {
            "项目计划", "平台-版本", "开发周期", "需求名称", "测试内容",
            "计划", "实际", "规划阶段", "规划启动", "概念阶段", "概念启动",
        }
        categories = {}

        # ---- 第1步：全表扫描，找分类关键词所在的列 ----
        keyword_positions = {}  # keyword -> [(row, col), ...]
        for row_idx, row in enumerate(values):
            if not row:
                continue
            for col_idx, cell in enumerate(row):
                kw = (cell or "").strip()
                if kw in CATEGORY_KEYWORDS:
                    keyword_positions.setdefault(kw, []).append((row_idx, col_idx))

        if not keyword_positions:
            return {"categories": {}, "text": "", "message": "未找到机型分类关键词"}

        # 确定分类列：取所有关键词位置中出现最多的列号
        from collections import Counter
        col_counter = Counter()
        for positions in keyword_positions.values():
            for _, col in positions:
                col_counter[col] += 1
        cat_col = col_counter.most_common(1)[0][0]
        device_col = cat_col + 1

        def is_valid_device_name(name: str) -> bool:
            """判断是否是合法的机型名（排除日期、阶段名、纯数字等）"""
            if not name:
                return False
            if name in NON_DEVICE_VALUES:
                return False
            if re.match(r'^[\d/\-:.年月日\s]+$', name):
                return False
            if re.match(r'^\d+$', name):
                return False
            if '：' in name or ':' in name:
                return False
            if name.startswith("-") or name.startswith("\\"):
                return False
            return True

        # ---- 第2步：对每个分类，读取设备列 ----
        for kw, positions in keyword_positions.items():
            # 只取 cat_col 列上的关键词
            rows_in_cat_col = sorted([r for r, c in positions if c == cat_col])
            if not rows_in_cat_col:
                continue

            start = rows_in_cat_col[0]
            # 确定范围结束行：下一个分类关键词行
            all_cat_rows = []
            for kw2, pos2 in keyword_positions.items():
                for r2, c2 in pos2:
                    if c2 == cat_col and r2 > start:
                        all_cat_rows.append(r2)
            end = min(all_cat_rows) if all_cat_rows else len(values)

            devices = []
            for r in range(start, end):
                if r >= len(values):
                    break
                row = values[r]
                if device_col >= len(row):
                    continue
                dev = (row[device_col] or "").strip()
                if not dev:
                    continue
                # 关键：不是合法设备名 → 跳过（遇到连续非设备值说明已离开机型区域）
                if not is_valid_device_name(dev):
                    continue
                # 清洗状态文字
                lines = [ln.strip() for ln in dev.split("\n") if ln.strip()]
                cleaned = [ln for ln in lines if ln not in {"暂停", "停止", "取消", "\\"}]
                if cleaned:
                    devices.append("\n".join(cleaned))
            if devices:
                categories[kw] = list(dict.fromkeys(devices))  # 去重保序

        # ---- 构建显示文本（分行显示） ----
        display_parts = []
        for cat in ["存量SR适配", "首发", "衍生"]:
            devices = categories.get(cat, [])
            if not devices:
                continue
            seen = set()
            unique = []
            for d in devices:
                if d not in seen:
                    seen.add(d)
                    unique.append(d)
            display_parts.append(f"{cat}：{'、'.join(unique)}")

        text = "\n".join(display_parts) if display_parts else ""
        return {"categories": categories, "text": text, "message": "ok" if text else "未找到机型信息"}

    except Exception as e:
        print(f"读取机型信息异常: {e}")
        return {"categories": {}, "text": "", "message": f"读取失败: {str(e)[:100]}"}


@app.get("/api/versions/{version_id}/contact-map-url")
def get_contact_map_url(version_id: int):
    """
    获取当前 tOS 版本管理书中 sheet 名为"测试接口人"的链接（沟通地图）。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT feishu_sheet_url FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    conn.close()

    feishu_url = (row_to_dict(row).get("feishu_sheet_url") or "").strip() if row else ""
    if not feishu_url:
        return {"url": "", "message": "未配置管理书地址"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"url": "", "message": "请先完成飞书授权"}

    try:
        wiki_token, sheet_id = parse_feishu_url(feishu_url)
        if not wiki_token:
            return {"url": "", "message": "URL格式无法解析"}

        headers = {"Authorization": f"Bearer {access_token}"}
        obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

        meta_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
            headers=headers, timeout=10
        )
        meta_data = safe_json(meta_resp, "获取表格元信息")
        if meta_data.get("code") != 0:
            return {"url": "", "message": f"无法访问飞书表格: {meta_data.get('msg', '')}"}

        sheets = meta_data.get("data", {}).get("sheets", [])
        for s in sheets:
            if s.get("title", "").strip() == "测试接口人":
                target_sheet_id = s.get("sheet_id", "")
                # 构建指向该 sheet 的链接：替换原 URL 中的 sheet 参数
                base_url = feishu_url.split("?")[0]
                contact_url = f"{base_url}?sheet={target_sheet_id}"
                return {"url": contact_url, "message": "ok"}

        return {"url": "", "message": "管理书中未找到「测试接口人」Sheet"}
    except Exception as e:
        print(f"获取沟通地图链接异常: {e}")
        return {"url": "", "message": f"获取失败: {str(e)[:100]}"}


def read_feishu_sheet_data(feishu_url: str, access_token: str, sheet_id_filter: str = None):
    """
    通用函数：从飞书表格读取数据。
    返回 (sheets_meta, all_values_by_sheet) 或抛出异常。
    sheets_meta: [{sheet_id, title, row_count, column_count}, ...]
    all_values_by_sheet: {sheet_id: [[cell, ...], ...], ...}
    """
    wiki_token, sheet_id = parse_feishu_url(feishu_url)
    if not wiki_token:
        raise ValueError("URL格式无法解析")

    headers = {"Authorization": f"Bearer {access_token}"}
    obj_token = resolve_wiki_to_spreadsheet_token(headers, wiki_token)

    # 获取表格元信息
    meta_resp = requests.get(
        f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{obj_token}/sheets/query",
        headers=headers, timeout=10
    )
    meta_data = safe_json(meta_resp, "获取表格元信息")
    if meta_data.get("code") != 0:
        raise ValueError(f"无法访问飞书表格: {meta_data.get('msg', '')}")

    sheets = meta_data.get("data", {}).get("sheets", [])
    if not sheets:
        raise ValueError("飞书文档中没有表格")

    result_sheets = []
    result_data = {}

    for s in sheets:
        sid = s.get("sheet_id", "")
        title = s.get("title", "")

        # 如果指定了 sheet_id_filter，只读取该 sheet
        if sheet_id_filter and sid != sheet_id_filter:
            continue

        # 读取表格数据（扩大范围）
        range_str = f"{sid}!A1:AX2000"
        data_resp = requests.get(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{obj_token}/values/{range_str}",
            headers=headers, timeout=30
        )
        data_json = safe_json(data_resp, f"读取表格 {title}")
        if data_json.get("code") != 0:
            print(f"读取 sheet {title} 失败: {data_json.get('msg', '')}")
            continue

        raw_values = data_json.get("data", {}).get("valueRange", {}).get("values", [])
        values = [[feishu_cell_to_str(cell) for cell in (row or [])] for row in raw_values]

        result_sheets.append({
            "sheet_id": sid,
            "title": title,
            "row_count": s.get("grid_properties", {}).get("row_count", 0),
            "column_count": s.get("grid_properties", {}).get("column_count", 0),
        })
        result_data[sid] = values

    return result_sheets, result_data


def parse_test_result_sheet(values: list):
    """
    从飞书表格中解析测试结果（性能专项 / 续航温升通用）。

    正确流程：
      1. 进入该机型 sheet，找到表头行
      2. 找"评估结论"列（含"评估结论"关键词的列头）
      3. 统计该列中的 GO / GR / NG 数量
      4. 对 GR/NG 行，fail原因 = 该GO/GR/NG单元格的 前一列内容 + 后一列内容 组合
      5. 没有"评估结论"列的 sheet -> has_conclusion=False（不做 Pass/Fail 映射）

    返回: {go_count, gr_count, ng_count, fail_items: [...], has_conclusion: bool}
    """
    if not values or len(values) < 4:
        return None

    # ---- 第1步：找表头行 ----
    header_row_idx = -1
    for i, row in enumerate(values[:10]):
        if not row:
            continue
        row_text = " ".join(str(c or "") for c in row)
        if ("价值方向" in row_text or "目标模型" in row_text) and "指标" in row_text:
            header_row_idx = i
            break

    if header_row_idx < 0:
        return None

    headers = values[header_row_idx]

    # ---- 第2步：找"评估结论"列 ----
    conclusion_col = None
    col_map = {}  # metric / priority / model / test_result / jira / remark
    for i, h in enumerate(headers):
        h_clean = (h or "").strip()
        if not h_clean:
            continue
        h_lower = h_clean.lower()
        if "目标模型" in h_clean:
            col_map.setdefault("model", i)
        elif "指标优先级" in h_clean:
            col_map.setdefault("priority", i)
        elif "指标" in h_clean and "优先级" not in h_clean and "达成" not in h_clean:
            col_map.setdefault("metric", i)
        elif "评估结论" in h_clean:
            # 取第一个匹配的"评估结论"列
            if conclusion_col is None:
                conclusion_col = i
        elif "测试结果" in h_clean:
            col_map.setdefault("test_result", i)
        elif "jira" in h_lower:
            col_map.setdefault("jira", i)
        elif "备注" in h_clean:
            col_map.setdefault("remark", i)

    if "metric" not in col_map:
        return None

    # 兜底：如果表头没找到"指标优先级"列，扫描数据行找含 P0/P1/P2 的列
    if "priority" not in col_map:
        _PRI_VALS = {"P0", "P1", "P2"}
        for c in range(col_map.get("model", 0), min(col_map.get("metric", 5) + 1, len(headers))):
            hit = 0
            for r in range(header_row_idx + 1, min(header_row_idx + 8, len(values))):
                if c < len(values[r]) and (values[r][c] or "").strip() in _PRI_VALS:
                    hit += 1
            if hit >= 2:
                col_map["priority"] = c
                break

    if conclusion_col is None:
        # 没有"评估结论"列 -> 纯数据 sheet
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False}

    # ---- 第3步：逐行统计 GO/GR/NG，按目标模型分组 ----
    go_count = 0
    gr_count = 0
    ng_count = 0
    fail_items = []
    last_target_model = ""
    last_metric = ""  # 指标列合并单元格向前填充
    # categories: {category_name: {go, gr, ng, fail_items: [...]}}
    categories = {}

    def _ensure_cat(name):
        name = name.replace("\n", " ").strip()
        if name not in categories:
            categories[name] = {"name": name, "go": 0, "gr": 0, "ng": 0, "fail_items": []}
        return categories[name]

    for r in range(header_row_idx + 1, len(values)):
        row = values[r]
        if conclusion_col >= len(row):
            continue

        # 更新 target_model（合并单元格向下填充）
        if "model" in col_map and col_map["model"] < len(row):
            v = (row[col_map["model"]] or "").strip()
            if v:
                last_target_model = v

        # 更新 metric（合并单元格向下填充）
        if "metric" in col_map and col_map["metric"] < len(row):
            v = (row[col_map["metric"]] or "").replace("\n", " ").strip()
            if v:
                last_metric = v

        val = (row[conclusion_col] or "").strip().upper()
        if not val or val not in ("GO", "GR", "NG"):
            continue

        cat_name = last_target_model or "未分类"
        cat = _ensure_cat(cat_name)

        if val == "GO":
            go_count += 1
            cat["go"] += 1
        elif val == "GR":
            gr_count += 1
            cat["gr"] += 1
        elif val == "NG":
            ng_count += 1
            cat["ng"] += 1

        # 对 GR/NG 行提取明细
        if val in ("GR", "NG"):
            reason_parts = []
            SKIP = {"GO", "GR", "NG", "PASS", "FAIL", "", "/"}

            # 来源1：检测到的JIRA/备注列
            jira_c = col_map.get("jira")
            if jira_c is not None and jira_c < len(row):
                jv = (row[jira_c] or "").strip()
                if jv and jv.upper() not in SKIP:
                    reason_parts.append(jv)

            remark_c = col_map.get("remark")
            if remark_c is not None and remark_c < len(row):
                rv = (row[remark_c] or "").strip()
                if rv and rv.upper() not in SKIP:
                    reason_parts.append(rv)

            # 来源2：评估结论的前后列（合并，不互斥）
            left_col = conclusion_col - 1
            if 0 <= left_col < len(row):
                lv = (row[left_col] or "").strip()
                if lv and lv.upper() not in SKIP and lv not in reason_parts:
                    reason_parts.append(lv)

            right_col = conclusion_col + 1
            if 0 <= right_col < len(row):
                rv = (row[right_col] or "").strip()
                if rv and rv.upper() not in SKIP and rv not in reason_parts:
                    reason_parts.append(rv)

            fail_reason = "；".join(reason_parts) if reason_parts else ""

            metric = last_metric
            priority = (row[col_map["priority"]] if "priority" in col_map and col_map["priority"] < len(row) else "").strip()
            test_result = (row[col_map["test_result"]] if "test_result" in col_map and col_map["test_result"] < len(row) else "").strip()

            item = {
                "target_model": cat_name,
                "metric": metric,
                "priority": priority,
                "test_result": test_result,
                "conclusion": val,
                "fail_reason": fail_reason,
            }
            fail_items.append(item)
            cat["fail_items"].append(item)

    # 按出现顺序排列 categories
    cat_list = list(categories.values())

    return {
        "go_count": go_count,
        "gr_count": gr_count,
        "ng_count": ng_count,
        "fail_items": fail_items,
        "categories": cat_list,
        "has_conclusion": True,
    }


def parse_battery_result_sheet(values: list):
    """
    续航温升专用解析函数。

    表格结构说明：
      - 第0行通常是顶层表头（含"价值方向"、"目标模型"、"指标"等结构性关键词）
      - 第1~4行可能是子表头（含"项目产品目标值"、"tOS STR4A"、"JIRA单"、"备注"等）
      - 实际数据行从第一个在结论列有GO/GR/NG/OK值的行开始
      - "指标"、"目标模型"等列使用合并单元格，需要向前填充

    与性能专项的区别：
      1. 评估结论列名可能是：评估结论、业务评估结论、研测确认结果
         其中"研测确认结果"显示的OK等效为GO
      2. 没有优先级列
      3. fail原因从"JIRA单"和"备注"列组合，不是评估结论的相邻列
      4. JIRA单中的编号后续在前端做成跳转链接
    """
    if not values or len(values) < 3:
        return None

    # ---- 第1步：找顶层表头行 ----
    # 结构性关键词权重远高于数据关键词，确保找到含"指标"/"价值方向"的行
    STRUCTURAL_KEYWORDS = {"指标": 10, "价值方向": 5, "目标模型": 5}
    DATA_KEYWORDS = {
        "评估结论": 1, "业务评估结论": 1, "研测确认结果": 1,
        "测试结果": 1, "JIRA": 1, "jira": 1, "备注": 1,
    }
    ALL_KEYWORDS = {**STRUCTURAL_KEYWORDS, **DATA_KEYWORDS}

    header_row_idx = -1
    best_score = 0
    for i, row in enumerate(values[:10]):
        if not row:
            continue
        row_text = " ".join(str(c or "") for c in row)
        score = sum(w for kw, w in ALL_KEYWORDS.items() if kw in row_text)
        if score > best_score:
            best_score = score
            header_row_idx = i

    if header_row_idx < 0 or best_score < 2:
        return None

    # ---- 第2步：扫描表头及子表头行，收集所有列信息 ----
    # 列头可能分布在多行（row0有"指标"，row1有"测试结果"，row2有"JIRA单"/"备注"）
    # 扫描范围扩大到 header_row + 5 行
    conclusion_col = None
    conclusion_is_ok = False
    conclusion_candidates = []  # [(col_idx, is_ok_flag, priority)]
    col_map = {}

    scan_end = min(header_row_idx + 5, len(values))
    for scan_row_idx in range(header_row_idx, scan_end):
        row = values[scan_row_idx]
        if not row:
            continue
        for i, h in enumerate(row):
            h_clean = (h or "").strip()
            if not h_clean:
                continue
            h_upper = h_clean.upper()
            # 结论列：精确匹配，收集候选
            if h_clean == "评估结论":
                conclusion_candidates.append((i, False, 0))
            elif h_clean == "业务评估结论":
                conclusion_candidates.append((i, False, 1))
            elif h_clean == "研测确认结果":
                conclusion_candidates.append((i, True, 2))
            # 其他列
            elif "目标模型" in h_clean:
                col_map.setdefault("model", i)
            elif "价值方向" in h_clean:
                col_map.setdefault("category", i)
            elif "指标" in h_clean and "优先级" not in h_clean and "达成" not in h_clean:
                col_map.setdefault("metric", i)
            elif "测试结果" in h_clean:
                col_map.setdefault("test_result", i)
            elif any(kw in h_clean for kw in ["备注", "说明", "remark", "note", "Remark"]):
                col_map.setdefault("remark", i)

    # JIRA列单独检测（列名变体多，需广泛匹配）
    if "jira" not in col_map:
        for scan_row_idx in range(header_row_idx, scan_end):
            row = values[scan_row_idx]
            if not row:
                continue
            for i, h in enumerate(row):
                h_clean = (h or "").strip()
                if not h_clean:
                    continue
                h_upper = h_clean.upper()
                if ("JIRA" in h_upper or "问题单" in h_clean
                        or "问题链接" in h_clean or "bug" in h_upper):
                    col_map["jira"] = i
                    break
            if "jira" in col_map:
                break

    # 从候选列中选择最优结论列（优先级：评估结论 > 业务评估结论 > 研测确认结果）
    if conclusion_candidates:
        conclusion_candidates.sort(key=lambda x: x[2])
        best = conclusion_candidates[0]
        conclusion_col = best[0]
        conclusion_is_ok = best[1]

    # 兜底：子串匹配
    if conclusion_col is None:
        for scan_row_idx in range(header_row_idx, scan_end):
            row = values[scan_row_idx]
            if not row:
                continue
            for i, h in enumerate(row):
                h_clean = (h or "").strip()
                if not h_clean:
                    continue
                if "结论" in h_clean and "评估" in h_clean:
                    conclusion_col = i
                    break
                if "确认结果" in h_clean:
                    conclusion_col = i
                    conclusion_is_ok = True
                    break
            if conclusion_col is not None:
                break

    # 如果没找到"指标"列，尝试用"价值方向"列作为指标列
    if "metric" not in col_map and "category" in col_map:
        col_map["metric"] = col_map["category"]

    # 还是没有指标列，用数据扫描兜底
    if "metric" not in col_map:
        for c in range(min(8, len(values[header_row_idx]))):
            h = (values[header_row_idx][c] or "").strip() if c < len(values[header_row_idx]) else ""
            if h and any('一' <= ch <= '鿿' for ch in h):
                col_map.setdefault("metric", c)
                break

    # 最终兜底：用数据扫描找 GO/GR/NG 列
    if conclusion_col is None:
        go_gr_ng_set = {"GO", "GR", "NG", "OK"}
        detected_col = _detect_col_by_values(values, header_row_idx + 1, 0, go_gr_ng_set)
        if detected_col is not None:
            conclusion_col = detected_col

    # ---- 第3步：找第一个数据行 ----
    data_start_row = header_row_idx + 1
    if conclusion_col is not None:
        for r in range(header_row_idx + 1, min(header_row_idx + 8, len(values))):
            row = values[r]
            if conclusion_col < len(row):
                cv = (row[conclusion_col] or "").strip().upper()
                if cv in ("GO", "GR", "NG", "OK"):
                    data_start_row = r
                    break
            data_start_row = r + 1

    # ---- 第3.5步：如果没有找到JIRA/备注列，扫描数据区域左侧/右侧列 ----
    # 有些表格的JIRA单/备注列不在表头关键词行，而在数据区域附近的列
    if "jira" not in col_map or "remark" not in col_map:
        _scan_for_reason_columns(values, data_start_row, conclusion_col, col_map)

    debug = {
        "header_row_idx": header_row_idx,
        "header_score": best_score,
        "headers_sample": [h for h in values[header_row_idx][:20]],
        "data_start_row": data_start_row,
        "conclusion_col": conclusion_col,
        "conclusion_is_ok": conclusion_is_ok,
        "col_map": dict(col_map),
    }

    if "metric" not in col_map:
        debug["error"] = "未找到指标列"
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False, "_debug": debug}

    if conclusion_col is None:
        debug["error"] = "未找到评估结论列"
        return {"go_count": 0, "gr_count": 0, "ng_count": 0, "fail_items": [], "has_conclusion": False, "_debug": debug}

    # ---- 第4步：逐行统计 GO/GR/NG ----
    go_count = 0
    gr_count = 0
    ng_count = 0
    fail_items = []
    last_target_model = ""
    last_metric = ""  # 指标列也需要向前填充（合并单元格）
    categories = {}
    skipped_empty = 0
    skipped_other = 0

    def _ensure_cat(name):
        name = name.replace("\n", " ").strip()
        if name not in categories:
            categories[name] = {"name": name, "go": 0, "gr": 0, "ng": 0, "fail_items": []}
        return categories[name]

    def _clean(s):
        """清理单元格文本：去首尾空白和换行"""
        return (s or "").replace("\n", " ").strip()

    OK_EQUIVALENTS = {"OK", "OKAY", "PASS", "通过"}

    metric_col = col_map.get("metric")
    model_col = col_map.get("model") or col_map.get("category")
    test_result_col = col_map.get("test_result")
    jira_col = col_map.get("jira")
    remark_col = col_map.get("remark")

    for r in range(data_start_row, len(values)):
        row = values[r]
        if conclusion_col >= len(row):
            continue

        # 更新 target_model（合并单元格向下填充）
        if model_col is not None and model_col < len(row):
            v = _clean(row[model_col])
            if v:
                last_target_model = v

        # 更新 metric（合并单元格向下填充）
        if metric_col is not None and metric_col < len(row):
            v = _clean(row[metric_col])
            if v:
                last_metric = v

        raw_val = (row[conclusion_col] or "").strip()
        val_upper = raw_val.upper()

        # 映射逻辑
        if val_upper in ("GO", "GR", "NG"):
            val = val_upper
        elif conclusion_is_ok and val_upper in OK_EQUIVALENTS:
            val = "GO"
        else:
            if not raw_val:
                skipped_empty += 1
            else:
                skipped_other += 1
            continue

        cat_name = last_target_model or "未分类"
        cat = _ensure_cat(cat_name)

        if val == "GO":
            go_count += 1
            cat["go"] += 1
        elif val == "GR":
            gr_count += 1
            cat["gr"] += 1
        elif val == "NG":
            ng_count += 1
            cat["ng"] += 1

        # 对 GR/NG 行提取明细（合并多个来源）
        if val in ("GR", "NG"):
            reason_parts = []

            # 来源1：JIRA/备注列
            if jira_col is not None and jira_col < len(row):
                jv = _clean(row[jira_col])
                if jv:
                    reason_parts.append(jv)

            if remark_col is not None and remark_col < len(row):
                rv = _clean(row[remark_col])
                if rv:
                    reason_parts.append(rv)

            # 来源2：评估结论的前后列（合并补充）
            SKIP = {"GO", "GR", "NG", "PASS", "FAIL", "OK", "", "/"}
            left_col = conclusion_col - 1
            if 0 <= left_col < len(row):
                lv = _clean(row[left_col])
                if lv and lv.upper() not in SKIP and lv not in reason_parts:
                    reason_parts.append(lv)
            right_col = conclusion_col + 1
            if 0 <= right_col < len(row):
                rv = _clean(row[right_col])
                if rv and rv.upper() not in SKIP and rv not in reason_parts:
                    reason_parts.append(rv)

            fail_reason = "；".join(reason_parts) if reason_parts else ""

            metric = last_metric if last_metric else ""
            test_result = _clean(row[test_result_col]) if test_result_col is not None and test_result_col < len(row) else ""

            item = {
                "target_model": cat_name,
                "metric": metric,
                "priority": "",
                "test_result": test_result,
                "conclusion": val,
                "fail_reason": fail_reason,
            }
            fail_items.append(item)
            cat["fail_items"].append(item)

    cat_list = list(categories.values())

    debug.update({
        "skipped_empty": skipped_empty,
        "skipped_other": skipped_other,
        "go": go_count, "gr": gr_count, "ng": ng_count,
    })

    return {
        "go_count": go_count,
        "gr_count": gr_count,
        "ng_count": ng_count,
        "fail_items": fail_items,
        "categories": cat_list,
        "has_conclusion": True,
        "_debug": debug,
    }


def _scan_for_reason_columns(values, data_start_row, conclusion_col, col_map):
    """
    在数据区域附近扫描，寻找可能的JIRA单/备注列。
    策略：在GR/NG数据行中，找结论列右侧第一个有非空文本的列作为备注候选。
    """
    if data_start_row >= len(values):
        return

    # 扫描前20个数据行中的GR/NG行
    gr_ng_rows = []
    for r in range(data_start_row, min(data_start_row + 30, len(values))):
        row = values[r]
        if conclusion_col < len(row):
            cv = (row[conclusion_col] or "").strip().upper()
            if cv in ("GR", "NG"):
                gr_ng_rows.append(r)

    if not gr_ng_rows:
        return

    # 在GR/NG行中，找结论列右侧第一个有较长文本的列（很可能是备注/说明）
    if "remark" not in col_map and conclusion_col is not None:
        col_scores = {}
        for r in gr_ng_rows[:10]:
            row = values[r]
            for c in range(conclusion_col + 1, min(conclusion_col + 6, len(row))):
                v = (row[c] or "").strip()
                if v and len(v) > 2:  # 有实质内容
                    col_scores[c] = col_scores.get(c, 0) + 1
        if col_scores:
            best_col = max(col_scores, key=col_scores.get)
            if col_scores[best_col] >= 2:  # 至少2个GR/NG行都有内容
                col_map.setdefault("remark", best_col)


def _detect_col_by_values(values: list, start_row: int, search_from_col: int, valid_set: set) -> int:
    """扫描数据行，找到第一个包含 valid_set 中值的列。返回出现次数最多的列索引。"""
    col_votes = {}
    for r in range(start_row, min(start_row + 30, len(values))):
        row = values[r]
        for c in range(search_from_col, len(row)):
            val = (row[c] or "").strip().upper()
            if val in valid_set:
                col_votes[c] = col_votes.get(c, 0) + 1
    if not col_votes:
        return None
    return max(col_votes, key=col_votes.get)

def is_device_sheet_name(title: str) -> bool:
    """
    判断 sheet 名称是否为机型名。
    机型名通常包含字母+数字的组合，如 P685L、X6879、CN6c 等。
    也可能包含中文后缀，如 "CN6C指标合并"、"LK7(指标合并）"。
    排除常见的非机型 sheet 名。
    """
    if not title:
        return False
    title = title.strip()
    title_lower = title.lower()

    # 排除常见非机型名（精确关键词，避免"指标"误伤"指标合并"）
    exclude_keywords = [
        "汇总", "总览", "说明", "模板", "目录", "概览",
        "统计", "数据", "配置", "设置", "备注", "计划",
        "时间", "进度", "template", "summary", "index",
        "readme", "版本", "阶段",
        "str1", "str2", "str3", "str4", "str5", "sta5",
        "点击切换", "切换机型", "sheet",
    ]
    for kw in exclude_keywords:
        if kw in title_lower:
            return False

    # 机型名通常较短（包含中文后缀时放宽到 40 字符）
    if len(title) > 40:
        return False

    # ---- 包含"指标合并"的 sheet 名是典型的机型 sheet ----
    # 如 "CN6C指标合并"、"LK7(指标合并）"、"P685L指标合并"
    if "指标合并" in title:
        return True

    # 去除常见中文后缀后，检查剩余部分是否像机型名
    # 如 "CN6C指标合并" -> "CN6C", "LK7(指标合并）" -> "LK7"
    stripped = title
    stripped = re.sub(r'[（(]?\s*指标合并\s*[）)]?', '', stripped).strip()
    if stripped:
        has_digit = any(c.isdigit() for c in stripped)
        has_alpha = any(c.isalpha() for c in stripped)
        if has_digit and has_alpha:
            return True

    # ---- 标准判断：包含 ASCII 字母 + 数字的组合 ----
    ascii_alpha = [c for c in title if c.isascii() and c.isalpha()]
    has_digit = any(c.isdigit() for c in title)
    if has_digit and ascii_alpha:
        return True

    # 纯字母但较短也可能是（如某些代号）
    if len(title) <= 10 and ascii_alpha and not any(c in title for c in "的和与在"):
        return True

    return False



@app.get("/api/versions/{version_id}/performance")
def get_performance_data(version_id: int):
    """
    从飞书表格读取性能专项数据。
    优先使用 perf_sheet_url，如果没有则回退到 feishu_sheet_url。
    遍历所有 sheet，如果 sheet 名是机型名，则读取其中的测试结果数据。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, feishu_sheet_url, perf_sheet_url FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 优先使用性能专用URL，没有则回退到管理书URL
    feishu_url = (version.get("perf_sheet_url") or "").strip()
    if not feishu_url:
        feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"devices": [], "message": "请先在飞书设置中配置「性能体验表」URL"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"devices": [], "message": "请先完成飞书授权"}

    try:
        sheets_meta, all_data = read_feishu_sheet_data(feishu_url, access_token)
        devices = []

        # 构建飞书基础URL（用于生成各sheet的直达链接）
        base_sheet_url = feishu_url.split("?")[0] if feishu_url else ""

        for s in sheets_meta:
            title = s["title"]
            if not is_device_sheet_name(title):
                continue

            values = all_data.get(s["sheet_id"], [])
            result = parse_test_result_sheet(values)
            if result:
                result["device_name"] = title
                result["sheet_url"] = f"{base_sheet_url}?sheet={s['sheet_id']}" if base_sheet_url else ""
                devices.append(result)

        if not devices:
            return {"devices": [], "message": "未找到机型命名的 Sheet（请确认飞书表格中有以机型名命名的 Sheet）"}

        return {"devices": devices}

    except ValueError as e:
        return {"devices": [], "error": str(e)}
    except Exception as e:
        print(f"读取性能数据异常: {e}")
        return {"devices": [], "error": f"读取失败: {str(e)[:100]}"}


@app.get("/api/versions/{version_id}/battery")
def get_battery_data(version_id: int):
    """
    从飞书表格读取续航温升数据。
    优先使用 battery_sheet_url，如果没有则回退到 feishu_sheet_url。
    遍历所有 sheet，如果 sheet 名是机型名，则读取其中的测试结果数据。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name, feishu_sheet_url, battery_sheet_url FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 优先使用续航专用URL，没有则回退到管理书URL
    feishu_url = (version.get("battery_sheet_url") or "").strip()
    if not feishu_url:
        feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"devices": [], "message": "请先在飞书设置中配置「续航体验表」URL"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"devices": [], "message": "请先完成飞书授权"}

    try:
        sheets_meta, all_data = read_feishu_sheet_data(feishu_url, access_token)
        devices = []
        debug_info = []
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

            # 收集调试信息（所有 sheet）
            debug_info.append({
                "title": title,
                "is_device": is_device,
                "total_rows": len(values),
                "parse_result": result,
                "header_preview": [row[:15] for row in values[:5]] if values else [],
            })

        if not devices:
            return {"devices": [], "message": "未找到机型命名的 Sheet（请确认飞书表格中有以机型名命名的 Sheet）", "debug": debug_info}

        return {"devices": devices, "debug": debug_info}

    except ValueError as e:
        return {"devices": [], "error": str(e)}
    except Exception as e:
        print(f"读取续航温升数据异常: {e}")
        return {"devices": [], "error": f"读取失败: {str(e)[:100]}"}


def _debug_sheet_data(version_id: int, url_field: str, label: str, parser_func=None):
    """通用调试函数：返回指定飞书表格的原始 sheet 信息和前几行数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT version_name, feishu_sheet_url, {url_field} FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    conn.close()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    feishu_url = (version.get(url_field) or "").strip()
    if not feishu_url:
        feishu_url = (version.get("feishu_sheet_url") or "").strip()
    if not feishu_url:
        return {"label": label, "error": f"未配置 {url_field}，也无 feishu_sheet_url 回退"}

    access_token = get_cached_user_token()
    if not access_token:
        return {"label": label, "error": "请先完成飞书授权"}

    try:
        sheets_meta, all_data = read_feishu_sheet_data(feishu_url, access_token)
        debug_info = []
        for s in sheets_meta:
            title = s["title"]
            is_device = is_device_sheet_name(title)
            values = all_data.get(s["sheet_id"], [])
            preview = []
            for i, row in enumerate(values[:20]):
                preview.append({"row": i, "cells": row})

            parse_result = None
            if is_device:
                _parse = parser_func or parse_test_result_sheet
                parse_result = _parse(values)

            debug_info.append({
                "sheet_id": s["sheet_id"],
                "title": title,
                "is_device_sheet": is_device,
                "total_rows": len(values),
                "total_cols": max((len(r) for r in values), default=0),
                "preview_rows": preview,
                "parse_result": parse_result,
            })

        return {"label": label, "source_url": feishu_url, "sheets": debug_info}

    except Exception as e:
        return {"label": label, "error": str(e)}


@app.get("/api/versions/{version_id}/performance/debug")
def debug_performance_data(version_id: int):
    """调试接口：返回性能专项飞书表格的原始数据"""
    return _debug_sheet_data(version_id, "perf_sheet_url", "性能专项")


@app.get("/api/versions/{version_id}/battery/debug")
def debug_battery_data(version_id: int):
    """调试接口：返回续航温升飞书表格的原始数据"""
    return _debug_sheet_data(version_id, "battery_sheet_url", "续航温升", parser_func=parse_battery_result_sheet)


@app.put("/api/versions/{version_id}/stages/{stage_name}")
def update_stage(version_id: int, stage_name: str, req: StageUpdate):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ? AND stage_name = ?
    """, (version_id, stage_name))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="阶段不存在")

    update_fields = []
    update_values = []

    if req.start_date is not None:
        update_fields.append("start_date = ?")
        update_values.append(req.start_date)
    if req.end_date is not None:
        update_fields.append("end_date = ?")
        update_values.append(req.end_date)
    if req.current_flag is not None:
        if req.current_flag == 1:
            cur.execute("""
            UPDATE str_stage_config SET current_flag = 0
            WHERE version_id = ?
            """, (version_id,))
        update_fields.append("current_flag = ?")
        update_values.append(req.current_flag)

    if update_fields:
        update_values.extend([version_id, stage_name])
        sql = f"UPDATE str_stage_config SET {', '.join(update_fields)} WHERE version_id = ? AND stage_name = ?"
        cur.execute(sql, update_values)

    conn.commit()
    conn.close()

    return {"message": "阶段信息更新成功"}


@app.post("/api/versions/{version_id}/credential")
def save_credential(version_id: int, req: CredentialSave):
    expire_at = datetime.now() + timedelta(days=7)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM version_config WHERE id = ?", (version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="版本不存在")

    encrypted = encrypt_text(req.password_or_token)

    cur.execute("""
    INSERT INTO jira_credential (
        version_id, jira_base_url, username, encrypted_password, expire_at, last_login_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(version_id)
    DO UPDATE SET
        jira_base_url = excluded.jira_base_url,
        username = excluded.username,
        encrypted_password = excluded.encrypted_password,
        expire_at = excluded.expire_at,
        last_login_at = excluded.last_login_at
    """, (
        version_id,
        req.jira_base_url.rstrip("/"),
        req.username,
        encrypted,
        expire_at.isoformat(timespec="seconds"),
        now_iso()
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Jira账号已保存，有效期7天",
        "expire_at": expire_at.isoformat(timespec="seconds")
    }


@app.get("/api/versions/{version_id}/credential/status")
def credential_status(version_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT jira_base_url, username, expire_at, last_login_at
    FROM jira_credential
    WHERE version_id = ?
    """, (version_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "configured": False,
            "valid": False,
            "message": "未配置Jira账号"
        }

    expire_at = parser.parse(row["expire_at"])
    valid = datetime.now() < expire_at

    return {
        "configured": True,
        "valid": valid,
        "jira_base_url": row["jira_base_url"],
        "username": row["username"],
        "expire_at": row["expire_at"],
        "last_login_at": row["last_login_at"],
        "message": "Jira已连接" if valid else "Jira登录已过期，请重新输入"
    }


def get_version(version_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")
    return row


def get_stage(version_id: int, stage_name: str):
    if stage_name == "ALL":
        return None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM str_stage_config
    WHERE version_id = ? AND stage_name = ?
    """, (version_id, stage_name))
    row = row_to_dict(cur.fetchone())
    conn.close()
    return row


GLOBAL_CRED_PATH = APP_DIR / "global_jira_cred.json"


def get_global_credential():
    """获取全局 Jira 凭据"""
    if not GLOBAL_CRED_PATH.exists():
        return None
    try:
        data = json.loads(GLOBAL_CRED_PATH.read_text(encoding="utf-8"))
        return {
            "jira_base_url": data.get("jira_base_url", DEFAULT_JIRA_BASE_URL),
            "username": data.get("username", ""),
            "password": decrypt_text(data.get("encrypted_password", "")),
        }
    except Exception:
        return None


def set_global_credential(username: str, password: str, base_url: str = DEFAULT_JIRA_BASE_URL):
    """保存全局 Jira 凭据"""
    ensure_app_dir()
    data = {
        "jira_base_url": base_url.rstrip("/"),
        "username": username,
        "encrypted_password": encrypt_text(password),
        "updated_at": now_iso(),
    }
    GLOBAL_CRED_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_valid_credential(version_id: int = 0):
    """获取 Jira 凭据（统一使用全局凭据）"""
    global_cred = get_global_credential()
    if global_cred and global_cred["username"] and global_cred["password"]:
        print(f"[CRED] 使用全局凭据: user={global_cred['username']}, url={global_cred['jira_base_url']}, pwd_len={len(global_cred['password'])}")
        return global_cred

    raise HTTPException(status_code=400, detail="请先在 ⚙️ 设置 → Jira 中配置账号密码")


def get_latest_sync_time(version_id: int, stage_name: str) -> Optional[str]:
    """
    查询本地缓存中 issue 的最新 Jira 更新时间（updated_time），用于增量同步。
    返回 ISO 格式时间字符串，如 "2026-06-01T10:30:00"。
    如果本地无数据，返回 None。

    注意：使用 updated_time（Jira 侧的真实更新时间）而非 synced_at（本地保存时间）。
    原因：synced_at 是本地写入时间，取其日期做增量过滤会导致下次同步的时间窗口
    与上一轮已同步的数据重叠，重复抓取大量已有的 issue。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(updated_time) as latest
        FROM jira_issue_cache
        WHERE version_id = ? AND str_stage = ?
          AND updated_time IS NOT NULL AND updated_time != ''
    """, (version_id, stage_name))
    row = cur.fetchone()
    conn.close()
    if row and row["latest"]:
        return row["latest"]
    return None


def build_jql(version: Dict[str, Any], stage: Optional[Dict[str, Any]], incremental_since: Optional[str] = None):
    """
    构建 JQL 查询语句。
    按项目 + 阶段时间范围精确过滤，只获取当前阶段的数据。
    当 incremental_since 不为 None 时，只查询该时间点之后更新的 issue（增量同步）。
    """
    project = version["jira_project"]
    parts = [f'project = {project}']

    if stage:
        stage_name = stage.get("stage_name", "")
        start_date = (stage.get("start_date") or "").strip()
        end_date = (stage.get("end_date") or "").strip()

        if stage_name == "STA5":
            # 1+N版本火车：只查 STR5 截止之后创建的 issue（无上限）
            if start_date:
                parts.append(f'created >= "{start_date}"')
        elif start_date and end_date:
            # STR1-5：精确的时间范围
            parts.append(f'created >= "{start_date}"')
            parts.append(f'created <= "{end_date}"')
        elif start_date:
            # 只有开始时间
            parts.append(f'created >= "{start_date}"')
        elif end_date:
            # 只有截止时间
            parts.append(f'created <= "{end_date}"')

    # 增量同步：只抓取上次同步时间之后更新过的 issue
    if incremental_since:
        parts.append(f'updated >= "{incremental_since}"')

    jql = " AND ".join(parts) + " ORDER BY updated DESC"
    print(f"构建 JQL: {jql}")
    return jql


def jira_fetch_issues(credential: Dict[str, Any], jql: str, use_post: bool = True):
    """
    从 Jira 获取 Issues。（增强版，使用完整的字段列表）
    """
    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/search"

    all_issues = []
    start_at = 0
    max_results = 100

    print(f"开始Jira同步: {url}")
    print(f"JQL: {jql}")
    print(f"用户: {credential['username']}")

    while True:
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": JIRA_SEARCH_FIELDS
        }

        try:
            if use_post:
                resp = requests.post(
                    url,
                    json=payload,
                    auth=HTTPBasicAuth(credential["username"], credential["password"]),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    timeout=30,
                    verify=False  # 禁用SSL证书验证（公司Jira可能使用自签名证书）
                )
            else:
                resp = requests.get(
                    url,
                    params=payload,
                    auth=HTTPBasicAuth(credential["username"], credential["password"]),
                    headers={"Accept": "application/json"},
                    timeout=30,
                    verify=False  # 禁用SSL证书验证
                )
        except requests.exceptions.ConnectionError as e:
            print(f"连接Jira失败: {e}")
            raise HTTPException(status_code=502, detail=f"无法连接到Jira服务器: {base_url}")
        except requests.exceptions.Timeout as e:
            print(f"请求超时: {e}")
            raise HTTPException(status_code=504, detail="Jira请求超时")

        print(f"Jira响应状态码: {resp.status_code}")

        if resp.status_code == 401:
            print(f"认证失败: {resp.text[:200]}")
            raise HTTPException(status_code=401, detail="Jira认证失败，请检查账号密码")

        if resp.status_code == 403:
            print(f"权限不足: {resp.text[:200]}")
            raise HTTPException(status_code=403, detail="Jira权限不足，请检查账号权限")

        if resp.status_code == 400:
            print(f"请求错误: {resp.text[:500]}")
            raise HTTPException(
                status_code=400,
                detail=f"Jira请求错误（可能是JQL语法问题）: {resp.text[:300]}"
            )

        if resp.status_code >= 400:
            print(f"请求失败: {resp.status_code} - {resp.text[:500]}")
            raise HTTPException(
                status_code=400,
                detail=f"Jira同步失败：HTTP {resp.status_code} - {resp.text[:300]}"
            )

        data = resp.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)

        all_issues.extend(issues)

        # 上报进度
        sync_progress["fetched"] = len(all_issues)
        sync_progress["total"] = total
        sync_progress["message"] = f"正在采集... {len(all_issues)} / {total}"

        print(f"Jira 分页: startAt={start_at}, 本页={len(issues)}, 累计={len(all_issues)}, 总数={total}")

        start_at += max_results
        if start_at >= total:
            break

        # 安全上限
        if len(all_issues) >= 50000:
            print(f"达到安全上限 50000 条，停止拉取")
            break

    print(f"Jira 数据获取完成: {len(all_issues)} 条, Jira报告总数={total}")
    return all_issues, total


def normalize_issue(issue, version_id, version_name, stage_name):
    """
    解析 Jira Issue 数据，包括自定义字段。（增强版）
    """
    fields = issue.get("fields", {})

    # 基础字段
    components = fields.get("components") or []
    module_name = components[0].get("name") if components else "未归类"

    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    labels = fields.get("labels") or []

    # 自定义字段
    must_fix = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["must_fix"]))
    severity = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["severity"]))
    model = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["model"]))
    issue_category = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["issue_category"]))
    frequency = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["frequency"]))
    module_category = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["module_category"]))
    project_code = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["project_code"]))
    os_version = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["os_version"]))
    android_version = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["android_version"]))
    migration = stringify_field_value(fields.get(JIRA_CUSTOM_FIELDS["migration"]))

    # 计算字段
    priority = (fields.get("priority") or {}).get("name") or "未设置"
    status = (fields.get("status") or {}).get("name") or "未知"
    labels_text = ",".join(labels)
    created_time = parse_dt(fields.get("created"))
    updated_time = parse_dt(fields.get("updated"))

    # A/B/C 等级
    grade = priority_to_grade(priority, severity, must_fix)

    # 必解标记
    must_fix_flag = 1 if is_must_fix_enhanced(must_fix, labels_text, priority, migration) else 0

    # 遗留天数
    aging_days = None
    if created_time:
        try:
            created_dt = parser.parse(created_time)
            aging_days = (datetime.now() - created_dt).days
        except Exception:
            aging_days = None

    # 未更新天数
    stale_days = None
    if updated_time:
        try:
            updated_dt = parser.parse(updated_time)
            stale_days = (datetime.now() - updated_dt).days
        except Exception:
            stale_days = None

    # 风险评分
    risk_score = calc_risk_score(grade, status, priority, aging_days, stale_days, must_fix_flag == 1)

    return {
        "version_id": version_id,
        "version_name": version_name,
        "str_stage": stage_name,
        "issue_key": issue.get("key"),
        "summary": fields.get("summary") or "",
        "description": fields.get("description") or "",
        "status": status,
        "priority": priority,
        "issue_type": (fields.get("issuetype") or {}).get("name") or "未知",
        "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
        "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
        "module_name": module_name,
        "labels": labels_text,
        "created_time": created_time,
        "updated_time": updated_time,
        "resolved_time": parse_dt(fields.get("resolutiondate")),
        "raw_payload": json.dumps(issue, ensure_ascii=False),
        "synced_at": now_iso(),
        # 自定义字段
        "must_fix": must_fix,
        "severity": severity,
        "model": model,
        "issue_category": issue_category,
        "frequency": frequency,
        "module_category": module_category,
        "project_code": project_code,
        "os_version": os_version,
        "android_version": android_version,
        # 计算字段
        "grade": grade,
        "must_fix_flag": must_fix_flag,
        "aging_days": aging_days,
        "stale_days": stale_days,
        "risk_score": risk_score,
    }


def save_issues(issues: List[Dict[str, Any]]):
    """保存 Issues 到数据库（增强版，包含自定义字段）"""
    conn = get_conn()
    cur = conn.cursor()

    for item in issues:
        cur.execute("""
        INSERT INTO jira_issue_cache (
            version_id, version_name, str_stage, issue_key,
            summary, description, status, priority, issue_type,
            assignee, reporter, module_name, labels,
            created_time, updated_time, resolved_time,
            raw_payload, synced_at,
            must_fix, severity, model, issue_category, frequency,
            module_category, project_code, os_version, android_version,
            grade, must_fix_flag, aging_days, stale_days, risk_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, str_stage, issue_key)
        DO UPDATE SET
            summary = excluded.summary,
            description = excluded.description,
            status = excluded.status,
            priority = excluded.priority,
            issue_type = excluded.issue_type,
            assignee = excluded.assignee,
            reporter = excluded.reporter,
            module_name = excluded.module_name,
            labels = excluded.labels,
            created_time = excluded.created_time,
            updated_time = excluded.updated_time,
            resolved_time = excluded.resolved_time,
            raw_payload = excluded.raw_payload,
            synced_at = excluded.synced_at,
            must_fix = excluded.must_fix,
            severity = excluded.severity,
            model = excluded.model,
            issue_category = excluded.issue_category,
            frequency = excluded.frequency,
            module_category = excluded.module_category,
            project_code = excluded.project_code,
            os_version = excluded.os_version,
            android_version = excluded.android_version,
            grade = excluded.grade,
            must_fix_flag = excluded.must_fix_flag,
            aging_days = excluded.aging_days,
            stale_days = excluded.stale_days,
            risk_score = excluded.risk_score
        """, (
            item["version_id"],
            item["version_name"],
            item["str_stage"],
            item["issue_key"],
            item["summary"],
            item["description"],
            item["status"],
            item["priority"],
            item["issue_type"],
            item["assignee"],
            item["reporter"],
            item["module_name"],
            item["labels"],
            item["created_time"],
            item["updated_time"],
            item["resolved_time"],
            item["raw_payload"],
            item["synced_at"],
            item.get("must_fix"),
            item.get("severity"),
            item.get("model"),
            item.get("issue_category"),
            item.get("frequency"),
            item.get("module_category"),
            item.get("project_code"),
            item.get("os_version"),
            item.get("android_version"),
            item.get("grade"),
            item.get("must_fix_flag", 0),
            item.get("aging_days"),
            item.get("stale_days"),
            item.get("risk_score", 0),
        ))

    conn.commit()
    conn.close()
    print(f"已保存 {len(issues)} 条 Issue 到数据库")


def generate_mock_issues(version_id: int, version_name: str, stage_name: str, count: int = 320):
    """生成模拟 Issue 数据（增强版，包含自定义字段）"""
    modules = ["Framework", "Settings", "Launcher", "Stability", "MemoryManage", "Notification", "Power", "Camera"]
    assignees = ["张三", "李四", "王五", "赵六", "陈七", "未分配"]
    priorities = ["Blocker", "Critical", "Major", "High", "Medium", "Low"]
    statuses = ["Submitted", "Modifying", "Resolved", "Verified", "Closed", "Reopen", "In Progress"]
    severities = ["高", "中", "低"]
    models = ["X6879", "X6878", "X6891", "CN5", "X6840", "LK7K", "LK6"]
    must_fix_options = ["MP Block", "Not MP Block", ""]

    today = datetime.now()
    issues = []

    for i in range(count):
        created = today - timedelta(days=random.randint(0, 35))
        updated = created + timedelta(days=random.randint(0, 10))
        status = random.choice(statuses)
        resolved = None
        if status in CLOSED_STATUS:
            resolved = updated + timedelta(days=random.randint(0, 3))

        module = random.choice(modules)
        priority = random.choice(priorities)
        severity = random.choice(severities)
        model = random.choice(models)
        must_fix = random.choice(must_fix_options)

        # 计算字段
        aging_days = (today - created).days
        stale_days = (today - updated).days
        grade = priority_to_grade(priority, severity, must_fix)
        must_fix_flag = 1 if is_must_fix_enhanced(must_fix, "mock,tos", priority, "") else 0
        risk_score = calc_risk_score(grade, status, priority, aging_days, stale_days, must_fix_flag == 1)

        issues.append({
            "version_id": version_id,
            "version_name": version_name,
            "str_stage": stage_name,
            "issue_key": f"{version_name.replace('.', '').replace('+', 'N')}-{10000 + i}",
            "summary": f"{module} 模块在主流程/异常恢复场景下出现稳定性问题 #{i}",
            "description": f"示例问题：{module} 相关场景需要重点验证，包含启动、切后台、恢复、异常退出等路径。",
            "status": status,
            "priority": priority,
            "issue_type": "Bug",
            "assignee": random.choice(assignees),
            "reporter": "测试同学",
            "module_name": module,
            "labels": "mock,tos",
            "created_time": created.isoformat(timespec="seconds"),
            "updated_time": updated.isoformat(timespec="seconds"),
            "resolved_time": resolved.isoformat(timespec="seconds") if resolved else None,
            "raw_payload": "{}",
            "synced_at": now_iso(),
            # 自定义字段
            "must_fix": must_fix,
            "severity": severity,
            "model": model,
            "issue_category": random.choice(["Stability", "Performance", "UI", "Function", ""]),
            "frequency": random.choice(["Always", "Often", "Sometimes", "Rarely", ""]),
            "module_category": module,
            "project_code": model,
            "os_version": version_name,
            "android_version": "14",
            # 计算字段
            "grade": grade,
            "must_fix_flag": must_fix_flag,
            "aging_days": aging_days,
            "stale_days": stale_days,
            "risk_score": risk_score,
        })

    return issues


@app.post("/api/versions/{version_id}/sync")
def sync_jira_data(
    version_id: int,
    req: SyncRequest,
    stage: str = Query("STR1")
):
    version = get_version(version_id)
    stage_config = get_stage(version_id, stage)
    stage_name = stage if stage != "ALL" else "ALL"

    if req.use_mock:
        issues = generate_mock_issues(
            version_id=version_id,
            version_name=version["version_name"],
            stage_name=stage_name,
            count=520 if stage == "ALL" else 260
        )
        save_issues(issues)
        analysis = build_analysis(version_id, stage_name)
        return {
            "message": "示例数据已生成",
            "synced_count": len(issues),
            "analysis": analysis
        }

    global sync_progress
    sync_progress = {"active": True, "phase": "connecting", "fetched": 0, "total": 0, "message": "正在连接 Jira..."}

    try:
        credential = get_valid_credential(version_id)

        # ---- 增量同步：查询本地最新 Jira 更新时间，只抓取该时间之后更新过的 issue ----
        latest_sync = None if req.force_full else get_latest_sync_time(version_id, stage_name)
        incremental = False
        if latest_sync:
            # 使用 updated_time（Jira 真实更新时间）而非 synced_at（本地保存时间），
            # 避免时间窗口重叠导致重复抓取。
            # 传完整时间戳（精确到分钟）给 JQL，而非只取日期部分（[:10]），
            # 确保同一天内的 issue 也不会被重复抓取。
            # Jira JQL 的 updated 字段支持 "yyyy-MM-dd HH:mm" 格式。
            # 例如 updated_time = "2026-06-05T14:30:00" → JQL: updated >= "2026-06-05 14:30"
            incremental_since = latest_sync[:16].replace("T", " ")  # "2026-06-05 14:30"
            jql = build_jql(version, stage_config, incremental_since=incremental_since)
            incremental = True
            print(f"[增量同步] 本地最新 updated_time={latest_sync}，只抓取 updated >= \"{incremental_since}\"")
            sync_progress["message"] = f"增量同步：只抓取 {incremental_since} 之后更新的数据..."
        else:
            jql = build_jql(version, stage_config)
            print("[全量同步] 本地无数据，执行全量同步")

        sync_progress["phase"] = "fetching"
        sync_progress["message"] = "正在采集数据..."
        raw_issues, total_count = jira_fetch_issues(credential, jql)

        sync_progress["phase"] = "saving"
        sync_progress["message"] = f"正在保存 {len(raw_issues)} 条数据..."

        normalized = [
            normalize_issue(
                issue=i,
                version_id=version_id,
                version_name=version["version_name"],
                stage_name=stage_name
            )
            for i in raw_issues
        ]

        conn = get_conn()
        cur = conn.cursor()
        if not incremental:
            # 全量同步：先清空当前版本+阶段的旧数据，再写入新数据
            # 这样 Jira 上已删除或已移出该阶段的 issue 也会从本地清除
            cur.execute("DELETE FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
            print(f"[全量同步] 已清空 version_id={version_id}, stage={stage_name} 的旧缓存")
        # 删除旧的分析快照，重新生成
        cur.execute("DELETE FROM analysis_snapshot WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
        conn.commit()
        conn.close()

        save_issues(normalized)

        sync_progress["phase"] = "analyzing"
        sync_progress["message"] = "正在生成分析报告..."
        analysis = build_analysis(version_id, stage_name)

        # 计算本地总缓存量
        conn = get_conn()
        cur = conn.cursor()
        if stage_name == "ALL":
            cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id = ?", (version_id,))
        else:
            cur.execute("SELECT COUNT(*) as c FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage_name))
        local_total = cur.fetchone()["c"]
        conn.close()

        sync_msg = f"同步完成：本次抓取 {len(normalized)} 条，本地共 {local_total} 条"
        if incremental:
            sync_msg += f"（增量，Jira匹配 {total_count} 条）"
        else:
            sync_msg += f"（全量，Jira共 {total_count} 条）"

        sync_progress = {"active": False, "phase": "done", "fetched": len(normalized), "total": total_count, "message": sync_msg}

        return {
            "message": "Jira数据同步完成",
            "jql": jql,
            "synced_count": len(normalized),
            "total_count": total_count,
            "local_total": local_total,
            "incremental": incremental,
            "analysis": analysis
        }
    except Exception as e:
        sync_progress = {"active": False, "phase": "error", "fetched": 0, "total": 0, "message": f"同步失败：{str(e)[:100]}"}
        raise


# ==============================
# SR 遗留问题查询
# ==============================

# 已关闭/已完结的状态集合（用于排除）
SR_CLOSED_STATUS = {
    "Closed", "Resolved", "Verified", "Abandoned",
    "Done", "Fixed", "Duplicated", "Approved", "Finished",
    "关闭", "已解决", "已验证", "无法复现", "延期处理", "重复问题",
}

# SR 遗留问题关注的高优先级
SR_HIGH_PRIORITY = {"Blocker", "Critical", "Major"}

# SR 遗留问题多项目映射：某些版本需要跨多个 Jira 项目查询 SR 遗留问题
# key: 版本的 jira_project, value: 实际需要查询的所有项目列表
SR_MULTI_PROJECT_MAP = {
    "TOS170": ["TOS170", "LK7KOS17", "X6878OS17"],
}


def _build_project_condition(jira_project: str) -> str:
    """
    根据 jira_project 构建 JQL 的 project 条件。
    如果在 SR_MULTI_PROJECT_MAP 中有映射，使用 project in (...) 语法；
    否则使用 project = ... 语法。
    """
    projects = SR_MULTI_PROJECT_MAP.get(jira_project)
    if projects and len(projects) > 1:
        return f'project in ({", ".join(projects)})'
    return f'project = {jira_project}'


def build_sr_jql(jira_project: str) -> str:
    """
    构建 SR 遗留问题的 JQL。
    动态组合：项目 + summary 包含 SR + 排除已关闭状态 + 高优先级。
    注意：JQL 中只使用英文状态名（Jira 标准），中文状态名在后端过滤时处理。
    支持多项目查询（如 tOS17.0 需要同时查询 TOS170、LK7KOS17、X6878OS17）。
    """
    # JQL 中只用英文状态名，避免中文编码问题导致 Jira 返回空结果
    jql_closed = "Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished"
    priority_list = ", ".join(sorted(SR_HIGH_PRIORITY))
    project_cond = _build_project_condition(jira_project)
    jql = (
        f'{project_cond} '
        f'AND (summary ~ "SR*"  or  SR编号  is not empty ) '
        f'AND status not in ({jql_closed}) '
        f'AND priority in ({priority_list}) '
        f'ORDER BY priority ASC, created DESC'
    )
    return jql


@app.delete("/api/versions/{version_id}/credential")
def delete_version_credential(version_id: int):
    """删除版本 Jira 凭据（回退到使用全局凭据）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM jira_credential WHERE version_id = ?", (version_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"已删除版本凭据（{deleted} 条）", "deleted": deleted}


@app.get("/api/versions/{version_id}/jira-test")
def test_jira_connection(version_id: int):
    """诊断接口：测试 Jira 认证是否正常"""
    # 判断凭据来源
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, expire_at FROM jira_credential WHERE version_id = ?", (version_id,))
    ver_row = cur.fetchone()
    conn.close()

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"ok": False, "error": f"获取凭据失败: {str(e)}"}

    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/myself"

    cred_source = "版本凭据" if ver_row else "全局凭据"
    print(f"[JIRA-TEST] 测试连接: {url}, user={credential['username']}, pwd_len={len(credential['password'])}, 来源={cred_source}")

    try:
        # 先测试 myself（最简单的认证接口）
        resp = requests.get(url, auth=HTTPBasicAuth(credential["username"], credential["password"]),
                            headers={"Accept": "application/json"}, timeout=15, verify=False)
        print(f"[JIRA-TEST] myself 响应: {resp.status_code}")

        result = {
            "cred_source": cred_source,
            "url": url,
            "username": credential["username"],
            "pwd_len": len(credential["password"]),
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
        }

        if resp.status_code == 200:
            user_info = resp.json()
            result["ok"] = True
            result["display_name"] = user_info.get("displayName", "")
            result["name"] = user_info.get("name", "")
            # 再测试一个简单 JQL
            jql_resp = requests.post(
                f"{base_url}/rest/api/2/search",
                json={"jql": f"project = {get_version(version_id).get('jira_project', 'OS162')} AND summary ~ 'SR' AND priority in (Blocker, Critical, Major) ORDER BY created DESC", "startAt": 0, "maxResults": 1, "fields": ["summary"]},
                auth=HTTPBasicAuth(credential["username"], credential["password"]),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=15, verify=False,
            )
            result["jql_status"] = jql_resp.status_code
            if jql_resp.status_code != 200:
                result["jql_error"] = jql_resp.text[:300]
                result["jql_headers"] = dict(jql_resp.headers)
        else:
            result["ok"] = False
            result["body"] = resp.text[:500]

        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/versions/{version_id}/sr-issues")
def get_sr_issues(version_id: int):
    """
    获取当前版本的 SR 遗留问题。
    直接查询 Jira（不依赖本地缓存），因为 SR issue 的创建时间
    不一定落在当前 STR 阶段的日期范围内，本地缓存可能不包含它们。
    """
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    jira_project = version.get("jira_project", "")
    if not jira_project:
        return {"total": 0, "issues": [], "jql": "", "jira_url": "", "error": "版本未配置 Jira 项目"}

    jql = build_sr_jql(jira_project)
    jira_url = f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(jql)}"

    # 获取凭据
    try:
        credential = get_valid_credential(version_id)
    except HTTPException as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": e.detail or "请先配置 Jira 账号"}
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"获取凭据失败: {str(e)[:80]}"}

    # 直接调用 Jira REST API（不复用 jira_fetch_issues，便于精确控制和调试）
    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/search"
    sr_fields = ["summary", "status", "priority", "assignee", "reporter", "created", "updated", "labels"]

    print(f"[SR] 查询 Jira: {url}")
    print(f"[SR] JQL: {jql}")
    print(f"[SR] 用户: {credential['username']}")
    print(f"[SR] 密码长度: {len(credential['password'])} 位")

    try:
        resp = requests.post(
            url,
            json={"jql": jql, "startAt": 0, "maxResults": 5000, "fields": sr_fields},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
            verify=False,
        )
    except requests.exceptions.ConnectionError as e:
        print(f"[SR] 连接失败: {e}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"无法连接 Jira: {base_url}"}
    except requests.exceptions.Timeout:
        print("[SR] 请求超时")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 请求超时"}
    except Exception as e:
        print(f"[SR] 请求异常: {e}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"请求异常: {str(e)[:80]}"}

    print(f"[SR] 响应状态码: {resp.status_code}")

    if resp.status_code == 401:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 认证失败（401）：账号或密码错误，请在 ⚙️ 设置 → Jira 中重新输入密码"}
    if resp.status_code == 403:
        print(f"[SR] 403 Forbidden: {resp.text[:500]}")
        print(f"[SR] 403 响应头: {dict(resp.headers)}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url,
                "error": f"Jira 权限不足（403）：用户 {credential['username']} 无权查询项目 {jira_project}，请检查：1) 密码是否过期，在 ⚙️ 设置 → Jira 中重新输入；2) 账号是否有该项目的浏览权限"}
    if resp.status_code == 400:
        print(f"[SR] JQL 错误: {resp.text[:300]}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"JQL 语法错误: {resp.text[:200]}"}
    if resp.status_code >= 400:
        print(f"[SR] HTTP 错误: {resp.status_code} {resp.text[:200]}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 返回 HTTP {resp.status_code}：{resp.text[:120]}"}

    try:
        data = resp.json()
    except Exception:
        print(f"[SR] 响应非 JSON: {resp.text[:200]}")
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON 响应"}

    raw_issues = data.get("issues", [])
    total = data.get("total", 0)
    print(f"[SR] Jira 返回: total={total}, 本页={len(raw_issues)}")

    # 标准化为前端需要的格式（不过滤，全部展示）
    sr_issues = []
    for issue in raw_issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        created_time = parse_dt(fields.get("created"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - parser.parse(created_time)).days
            except Exception:
                pass
        sr_issues.append({
            "issue_key": issue.get("key", ""),
            "summary": fields.get("summary") or "",
            "status": (fields.get("status") or {}).get("name") or "未知",
            "priority": (fields.get("priority") or {}).get("name") or "未设置",
            "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
            "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
            "created_time": created_time,
            "aging_days": aging_days,
        })

    # 按优先级排序
    priority_order = {"Blocker": 0, "Critical": 1, "Major": 2}
    sr_issues.sort(key=lambda x: (priority_order.get(x.get("priority", ""), 99), -(x.get("aging_days") or 0)))

    print(f"[SR] 最终结果: {len(sr_issues)} 条")
    return {"total": total, "issues": sr_issues, "jql": jql, "jira_url": jira_url}


# ---- 阻塞测试 JQL ----

def build_sr_blocking_jql(jira_project: str) -> str:
    """构建阻塞测试的 SR JQL（在基础 SR JQL 上加 AND labels = 阻塞测试）"""
    jql_closed = "Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished"
    priority_list = ", ".join(sorted(SR_HIGH_PRIORITY))
    project_cond = _build_project_condition(jira_project)
    jql = (
        f'{project_cond} '
        f'AND (summary ~ "SR*"  or  SR编号  is not empty ) '
        f'AND status not in ({jql_closed}) '
        f'AND priority in ({priority_list}) '
        f'AND labels = 阻塞测试 '
        f'ORDER BY priority ASC, created DESC'
    )
    return jql


def _fetch_sr_issues_by_jql(version_id: int, jql: str) -> dict:
    """通用函数：用指定 JQL 查询 SR 遗留问题并标准化返回"""
    version = get_version(version_id)
    jira_project = version.get("jira_project", "")
    jira_url = f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(jql)}"

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    base_url = credential["jira_base_url"].rstrip("/")
    sr_fields = ["summary", "status", "priority", "assignee", "reporter", "created", "updated", "labels"]

    try:
        resp = requests.post(
            f"{base_url}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 5000, "fields": sr_fields},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30, verify=False,
        )
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 查询失败: {str(e)[:80]}"}

    if resp.status_code == 401:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 认证失败（401）"}
    if resp.status_code == 403:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 权限不足（403）"}
    if resp.status_code >= 400:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira HTTP {resp.status_code}: {resp.text[:120]}"}

    try:
        data = resp.json()
    except Exception:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON"}

    raw_issues = data.get("issues", [])
    total = data.get("total", 0)

    sr_issues = []
    for issue in raw_issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        created_time = parse_dt(fields.get("created"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - parser.parse(created_time)).days
            except Exception:
                pass
        sr_issues.append({
            "issue_key": issue.get("key", ""),
            "summary": fields.get("summary") or "",
            "status": (fields.get("status") or {}).get("name") or "未知",
            "priority": (fields.get("priority") or {}).get("name") or "未设置",
            "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
            "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
            "created_time": created_time,
            "aging_days": aging_days,
        })

    sr_issues.sort(key=lambda x: ({"Blocker": 0, "Critical": 1, "Major": 2}.get(x.get("priority", ""), 99), -(x.get("aging_days") or 0)))

    return {"total": total, "issues": sr_issues, "jql": jql, "jira_url": jira_url}


@app.get("/api/versions/{version_id}/sr-blocking-test-issues")
def get_sr_blocking_test_issues(version_id: int):
    """获取阻塞测试的 SR 遗留问题（labels = 阻塞测试）"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    jira_project = version.get("jira_project", "")
    if not jira_project:
        return {"total": 0, "issues": [], "error": "版本未配置 Jira 项目"}
    jql = build_sr_blocking_jql(jira_project)
    return _fetch_sr_issues_by_jql(version_id, jql)


# ==============================
# Jira Filter Presets CRUD
# ==============================

@app.get("/api/versions/{version_id}/filters")
def get_version_filters(version_id: int):
    """获取指定版本的所有 Jira Filter Presets"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT filter_key, label, description, default_jql, custom_jql, updated_at
        FROM jira_filter_preset WHERE version_id = ?
        ORDER BY id ASC
    """, (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # 如果该版本还没有 filter presets，动态播种
    if not rows:
        conn = get_conn()
        cur = conn.cursor()
        _seed_filter_presets(cur)
        conn.commit()
        cur.execute("""
            SELECT filter_key, label, description, default_jql, custom_jql, updated_at
            FROM jira_filter_preset WHERE version_id = ?
            ORDER BY id ASC
        """, (version_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

    return {"filters": rows}


class FilterUpdate(BaseModel):
    custom_jql: str


@app.put("/api/versions/{version_id}/filters/{filter_key}")
def update_version_filter(version_id: int, filter_key: str, body: FilterUpdate):
    """更新指定 filter 的自定义 JQL"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Filter 不存在")
    cur.execute("""
        UPDATE jira_filter_preset SET custom_jql = ?, updated_at = ?
        WHERE version_id = ? AND filter_key = ?
    """, (body.custom_jql.strip(), now_iso(), version_id, filter_key))
    conn.commit()
    conn.close()
    return {"message": "Filter 已更新", "filter_key": filter_key}


@app.post("/api/versions/{version_id}/filters/{filter_key}/reset")
def reset_version_filter(version_id: int, filter_key: str):
    """将指定 filter 还原为初始默认设定"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Filter 不存在")
    cur.execute("""
        UPDATE jira_filter_preset SET custom_jql = NULL, updated_at = ?
        WHERE version_id = ? AND filter_key = ?
    """, (now_iso(), version_id, filter_key))
    conn.commit()
    conn.close()
    return {"message": "Filter 已还原为默认设定", "filter_key": filter_key}


@app.get("/api/versions/{version_id}/jql/{filter_key}")
def get_resolved_jql(version_id: int, filter_key: str, stage: str = Query("ALL")):
    """获取解析后的有效 JQL（替换 {project}，main_sync 追加阶段时间），前端用于展示和跳转 Jira"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    jql_template = _get_filter_jql(version_id, filter_key)
    if not jql_template:
        raise HTTPException(status_code=404, detail="Filter 不存在")

    jira_project = version.get("jira_project", "")

    # 仅 sr_backlog 使用多项目映射，其余一律用单项目
    if filter_key == "sr_backlog":
        projects = SR_MULTI_PROJECT_MAP.get(jira_project)
        project_str = ", ".join(projects) if projects and len(projects) > 1 else jira_project
    else:
        project_str = jira_project

    resolved = jql_template.replace("{project}", project_str)

    # main_sync 追加阶段时间条件
    if filter_key == "main_sync" and stage and stage != "ALL":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT start_date, end_date FROM str_stage_config WHERE version_id = ? AND stage_name = ?", (version_id, stage))
        stg = cur.fetchone()
        conn.close()
        if stg:
            start_date = (stg["start_date"] or "").strip()
            end_date = (stg["end_date"] or "").strip()
            # 在 ORDER BY 之前插入时间条件
            order_idx = resolved.upper().find("ORDER BY")
            main_part = resolved[:order_idx].rstrip() if order_idx > 0 else resolved.rstrip()
            order_part = resolved[order_idx:] if order_idx > 0 else ""
            if stage == "STA5":
                if start_date:
                    main_part += f' AND created >= "{start_date}"'
            else:
                if start_date:
                    main_part += f' AND created >= "{start_date}"'
                if end_date:
                    main_part += f' AND created <= "{end_date}"'
            resolved = main_part + " " + order_part if order_part else main_part

    jira_url = f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(resolved)}"

    return {
        "filter_key": filter_key,
        "jql_resolved": resolved,
        "jira_url": jira_url,
        "is_custom": bool(_get_filter_custom(version_id, filter_key)),
    }


def _get_filter_custom(version_id: int, filter_key: str) -> Optional[str]:
    """获取 filter 的自定义 JQL（仅 custom_jql，不回退 default）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT custom_jql FROM jira_filter_preset WHERE version_id = ? AND filter_key = ?", (version_id, filter_key))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row["custom_jql"]


@app.get("/api/versions/{version_id}/pending-verification-count")
def get_pending_verification_count(version_id: int):
    """查询待验证问题数量（实时从 Jira 查询）"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    jql_template = _get_filter_jql(version_id, "pending_verification")
    if not jql_template:
        return {"total": 0, "jql": "", "jira_url": "", "error": "pending_verification filter 不存在"}

    jira_project = version.get("jira_project", "")
    jql = jql_template.replace("{project}", jira_project)
    jira_url = f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(jql)}"

    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    base_url = credential["jira_base_url"].rstrip("/")
    try:
        resp = requests.post(
            f"{base_url}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 1, "fields": ["summary"]},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15, verify=False,
        )
    except requests.exceptions.ConnectionError:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": "无法连接 Jira"}
    except requests.exceptions.Timeout:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": "Jira 请求超时"}
    except Exception as e:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": str(e)[:80]}

    if resp.status_code == 401:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": "Jira 认证失败，请重新输入密码"}
    if resp.status_code != 200:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": f"Jira 返回 HTTP {resp.status_code}"}

    try:
        data = resp.json()
        total = data.get("total", 0)
    except Exception:
        return {"total": 0, "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON"}

    return {"total": total, "jql": jql, "jira_url": jira_url}


@app.get("/api/versions/{version_id}/jira-issues/{filter_key}")
def get_jira_issues_by_filter(version_id: int, filter_key: str, stage: str = Query("ALL")):
    """通用接口：用指定 filter 的 JQL 查询 Jira 并返回 issue 列表（各板块独立刷新用）"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    jql_template = _get_filter_jql(version_id, filter_key)
    if not jql_template:
        raise HTTPException(status_code=404, detail="Filter 不存在")

    jira_project = version.get("jira_project", "")

    # 项目替换
    if filter_key == "sr_backlog":
        projects = SR_MULTI_PROJECT_MAP.get(jira_project)
        project_str = ", ".join(projects) if projects and len(projects) > 1 else jira_project
    else:
        project_str = jira_project

    jql = jql_template.replace("{project}", project_str)

    # main_sync 追加阶段时间
    if filter_key == "main_sync" and stage and stage != "ALL":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT start_date, end_date FROM str_stage_config WHERE version_id = ? AND stage_name = ?", (version_id, stage))
        stg = cur.fetchone()
        conn.close()
        if stg:
            start_date = (stg["start_date"] or "").strip()
            end_date = (stg["end_date"] or "").strip()
            order_idx = jql.upper().find("ORDER BY")
            main_part = jql[:order_idx].rstrip() if order_idx > 0 else jql.rstrip()
            order_part = jql[order_idx:] if order_idx > 0 else ""
            if stage == "STA5":
                if start_date:
                    main_part += f' AND created >= "{start_date}"'
            else:
                if start_date:
                    main_part += f' AND created >= "{start_date}"'
                if end_date:
                    main_part += f' AND created <= "{end_date}"'
            jql = main_part + " " + order_part if order_part else main_part

    jira_url = f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(jql)}"

    # 获取凭据
    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:100]}

    base_url = credential["jira_base_url"].rstrip("/")
    fields = ["summary", "status", "priority", "assignee", "reporter", "created", "updated",
              "components", "labels", "resolution", "resolutiondate",
              "customfield_15400", "customfield_13004", "customfield_15302"]

    try:
        resp = requests.post(
            f"{base_url}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 5000, "fields": fields},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30, verify=False,
        )
    except requests.exceptions.ConnectionError:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "无法连接 Jira"}
    except requests.exceptions.Timeout:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 请求超时"}
    except Exception as e:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": str(e)[:80]}

    if resp.status_code == 401:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 认证失败，请重新输入密码"}
    if resp.status_code == 400:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"JQL 语法错误: {resp.text[:200]}"}
    if resp.status_code != 200:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": f"Jira 返回 HTTP {resp.status_code}"}

    try:
        data = resp.json()
    except Exception:
        return {"total": 0, "issues": [], "jql": jql, "jira_url": jira_url, "error": "Jira 返回非 JSON"}

    raw_issues = data.get("issues", [])
    total = data.get("total", 0)

    # 标准化 issue 格式
    issues = []
    for issue in raw_issues:
        f = issue.get("fields", {})
        assignee = f.get("assignee") or {}
        reporter = f.get("reporter") or {}
        created_time = parse_dt(f.get("created"))
        updated_time = parse_dt(f.get("updated"))
        resolved_time = parse_dt(f.get("resolutiondate"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - datetime.fromisoformat(created_time)).days
            except Exception:
                pass
        stale_days = None
        if updated_time:
            try:
                stale_days = (datetime.now() - datetime.fromisoformat(updated_time)).days
            except Exception:
                pass

        issues.append({
            "issue_key": issue.get("key", ""),
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "assignee": assignee.get("displayName", "") or assignee.get("name", ""),
            "reporter": reporter.get("displayName", "") or reporter.get("name", ""),
            "created_time": created_time,
            "updated_time": updated_time,
            "resolved_time": resolved_time,
            "aging_days": aging_days,
            "stale_days": stale_days,
            "must_fix": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["must_fix"])),
            "severity": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["severity"])),
            "model": stringify_field_value(f.get(JIRA_CUSTOM_FIELDS["model"])),
        })

    return {"total": total, "issues": issues, "jql": jql, "jira_url": jira_url, "synced_at": now_iso()}


# ==============================
# ALM 平台集成
# ==============================

ALM_TOKEN_CACHE_PATH = APP_DIR / "alm_token_cache.json"

# ALM modelCode 映射
ALM_MODEL_CODE_MAP = {"IR": "A01", "SR": "A02", "AR": "A03"}


def get_alm_config():
    """从数据库读取 ALM 配置"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alm_config WHERE id = 1")
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row:
        return None
    # 解密密码
    pwd = ""
    if row.get("encrypted_password"):
        try:
            pwd = decrypt_text(row["encrypted_password"])
        except Exception:
            pass
    return {
        "uac_gateway": row.get("uac_gateway", "").rstrip("/"),
        "alm_app_id": row.get("alm_app_id", ""),
        "uac_username": row.get("uac_username", ""),
        "uac_password": pwd,
        "uac_source": row.get("uac_source", "ALM"),
        "alm_base_url": row.get("alm_base_url", "").rstrip("/"),
        "alm_space_bid": row.get("alm_space_bid", ""),
        "alm_app_bid": row.get("alm_app_bid", ""),
    }


class ALMConfigSave(BaseModel):
    uac_gateway: str = "https://pfgatewaysz.transsion.com:9199"
    alm_app_id: str
    uac_username: str
    uac_password: str
    uac_source: str = "ALM"
    alm_base_url: str = "https://pfgatewaysz.transsion.com:9199/alm-transcend-datadriven"
    alm_space_bid: Optional[str] = ""
    alm_app_bid: Optional[str] = ""


@app.get("/api/alm/config")
def api_get_alm_config():
    cfg = get_alm_config()
    if not cfg:
        return {"configured": False, "username": "", "alm_app_id": ""}
    has_creds = bool(cfg["alm_app_id"] and cfg["uac_username"] and cfg["uac_password"])
    # 检查工号格式是否正确
    username = cfg["uac_username"]
    username_valid = username.isdigit() if username else True
    warning = ""
    if username and not username_valid:
        warning = f"工号 '{username}' 格式不正确，ALM 需要纯数字工号（如 18665088），请重新配置。"
    return {
        "configured": has_creds,
        "uac_gateway": cfg["uac_gateway"],
        "alm_app_id": cfg["alm_app_id"],
        "uac_username": cfg["uac_username"],
        "uac_source": cfg["uac_source"],
        "alm_base_url": cfg["alm_base_url"],
        "alm_space_bid": cfg["alm_space_bid"],
        "alm_app_bid": cfg["alm_app_bid"],
        "username_valid": username_valid,
        "warning": warning,
    }


@app.post("/api/alm/config")
def api_save_alm_config(req: ALMConfigSave):
    if not req.alm_app_id or not req.uac_username or not req.uac_password:
        raise HTTPException(status_code=400, detail="App ID、工号和密码不能为空")
    # 验证 ALM 工号格式：必须是纯数字（如 18665088）
    username = req.uac_username.strip()
    if not username.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"ALM 工号必须是纯数字（如 18665088），当前输入 '{username}' 不是有效工号。"
                   f"注意：ALM 使用的是员工工号，不是 Jira 域账号。"
        )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE alm_config SET
            uac_gateway=?, alm_app_id=?, uac_username=?, encrypted_password=?,
            uac_source=?, alm_base_url=?, alm_space_bid=?, alm_app_bid=?, updated_at=?
        WHERE id=1
    """, (
        req.uac_gateway.rstrip("/"), req.alm_app_id.strip(), req.uac_username.strip(),
        encrypt_text(req.uac_password), req.uac_source, req.alm_base_url.rstrip("/"),
        req.alm_space_bid, req.alm_app_bid, now_iso()
    ))
    conn.commit()
    conn.close()
    # 清除旧 token 缓存
    if ALM_TOKEN_CACHE_PATH.exists():
        ALM_TOKEN_CACHE_PATH.unlink()
    return {"message": "ALM 配置已保存"}


# ---- ALM 鉴权 ----

def _alm_rsa_encrypt(password: str, public_key_b64: str) -> str:
    der = base64.b64decode(public_key_b64)
    pub_key = serialization.load_der_public_key(der)
    encrypted = pub_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("utf-8")


def _alm_load_token_cache():
    if not ALM_TOKEN_CACHE_PATH.exists():
        return None
    try:
        return json.loads(ALM_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _alm_save_token_cache(p_auth, p_rtoken, employee_no, expires_in=1200):
    data = {
        "p_auth": p_auth, "p_rtoken": p_rtoken,
        "employee_no": employee_no or "",
        "expires_at": int(time.time()) + int(expires_in or 1200),
    }
    ALM_TOKEN_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _alm_login(cfg):
    """ALM 用户中心 RSA 登录"""
    gw = cfg["uac_gateway"]
    # 1. 获取 RSA 公钥
    rsa_resp = requests.get(
        f"{gw}/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair",
        headers={"Accept": "application/json"}, timeout=30, verify=False
    ).json()
    if str(rsa_resp.get("code")) not in ("0", "200"):
        raise RuntimeError(f"获取RSA公钥失败: {rsa_resp}")
    body = rsa_resp.get("data") or {}
    public_key, verify_key = body.get("publicKey"), body.get("verifyKey")
    if not public_key or not verify_key:
        raise RuntimeError(f"RSA响应缺少字段: {rsa_resp}")

    # 2. 加密密码并登录
    enc_pwd = _alm_rsa_encrypt(cfg["uac_password"], public_key)
    login_resp = requests.post(
        f"{gw}/uac-auth-service/v2/api/uac-auth/login/account",
        json={"appId": cfg["alm_app_id"], "username": cfg["uac_username"],
              "pwd": enc_pwd, "verifyKey": verify_key, "source": cfg["uac_source"]},
        headers={"Content-Type": "application/json;charset=utf-8", "Accept": "application/json",
                 "P-AppId": cfg["alm_app_id"], "p-appid": cfg["alm_app_id"]},
        timeout=30, verify=False
    ).json()
    if str(login_resp.get("code")) not in ("0", "200"):
        err_msg = login_resp.get("message", "")
        err_code = login_resp.get("code", "")
        if str(err_code) == "10305":
            raise RuntimeError(
                f"ALM登录失败: 账号 '{cfg['uac_username']}' 不存在。"
                f"请确认使用的是员工工号（纯数字，如 18665088），而非 Jira 域账号。"
                f"原始错误: {login_resp}"
            )
        raise RuntimeError(f"ALM登录失败: {login_resp}")
    login_body = login_resp.get("data") or {}
    p_auth = login_body.get("rtoken") or login_body.get("token")
    p_rtoken = login_body.get("utoken")
    emp_no = login_body.get("employeeNo") or cfg["uac_username"]
    if not p_auth or not p_rtoken:
        raise RuntimeError(f"登录响应缺少token: {login_resp}")
    print(f"[ALM] 登录成功, employeeNo={emp_no}")
    return _alm_save_token_cache(p_auth, p_rtoken, emp_no, login_body.get("expiresIn", 1200))


def _alm_refresh_token(cfg, p_rtoken):
    """刷新 ALM token"""
    gw = cfg["uac_gateway"]
    resp = requests.post(
        f"{gw}/uac-auth-service/v2/api/uac-auth/rtoken/get",
        json={"appId": cfg["alm_app_id"], "utoken": p_rtoken},
        headers={"Content-Type": "application/json;charset=utf-8", "Accept": "application/json",
                 "P-AppId": cfg["alm_app_id"], "P-Rtoken": p_rtoken,
                 "p-appid": cfg["alm_app_id"], "p-rtoken": p_rtoken},
        timeout=30, verify=False
    ).json()
    if str(resp.get("code")) not in ("0", "200"):
        raise RuntimeError(f"刷新token失败: {resp}")
    body = resp.get("data") or {}
    new_auth = body.get("rtoken") or body.get("token")
    new_rtoken = body.get("utoken") or p_rtoken
    if not new_auth:
        raise RuntimeError(f"刷新响应缺少token: {resp}")
    old = _alm_load_token_cache() or {}
    print("[ALM] token 刷新成功")
    return _alm_save_token_cache(new_auth, new_rtoken, old.get("employee_no", ""), body.get("expiresIn", 1200))


def alm_get_token(cfg):
    """获取有效的 ALM token（自动缓存/刷新/重新登录）"""
    cache = _alm_load_token_cache()
    if cache and cache.get("p_auth") and cache.get("p_rtoken"):
        if int(cache.get("expires_at", 0)) > int(time.time()) + 90:
            return cache
        try:
            return _alm_refresh_token(cfg, cache["p_rtoken"])
        except Exception:
            pass
    return _alm_login(cfg)


def _alm_headers(cfg, token_cache):
    return {
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json, text/plain, */*",
        "p-auth": token_cache["p_auth"], "p-rtoken": token_cache["p_rtoken"],
        "p-appid": cfg["alm_app_id"], "p-langid": "zh", "p-empno": token_cache.get("employee_no", ""),
        "P-Auth": token_cache["p_auth"], "P-Rtoken": token_cache["p_rtoken"],
        "P-AppId": cfg["alm_app_id"], "P-LangId": "zh", "P-EmpNo": token_cache.get("employee_no", ""),
    }


def alm_request(cfg, path, method="POST", payload=None):
    """ALM API 请求封装（自动重试 token 错误）"""
    token = alm_get_token(cfg)
    headers = _alm_headers(cfg, token)
    url = cfg["alm_base_url"] + (path if path.startswith("/") else "/" + path)
    if method.upper() == "GET":
        resp = requests.get(url, headers=headers, params=payload or {}, timeout=60, verify=False)
    else:
        resp = requests.post(url, headers=headers, json=payload or {}, timeout=60, verify=False)
    data = resp.json()
    # token 错误 → 刷新后重试一次
    if str(data.get("code", "")) in ("30003", "30004", "30008", "30009"):
        print("[ALM] token 过期，重新登录...")
        token = _alm_login(cfg)
        headers = _alm_headers(cfg, token)
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=payload or {}, timeout=60, verify=False)
        else:
            resp = requests.post(url, headers=headers, json=payload or {}, timeout=60, verify=False)
        data = resp.json()
    return data


# ---- ALM 查询函数 ----

def alm_query_sr_detail(cfg, sr_coding: str, space_bid: str = "", app_bid: str = ""):
    """查询单个 SR 的详细信息（优先使用 space/app 接口以获取 spaceBid 用于版本过滤）"""
    records = []

    # 优先使用 space/app 接口（返回 spaceBid 等完整字段，用于版本过滤）
    # 使用传入的版本级 space/app bid，若未传入则回退到全局配置
    effective_space_bid = space_bid or cfg.get("alm_space_bid", "")
    effective_app_bid = app_bid or cfg.get("alm_app_bid", "")
    if effective_space_bid and effective_app_bid:
        fb_path = f"/apm/space/{effective_space_bid}/app/{effective_app_bid}/data-driven/page"
        fb_payload = {
            "current": 1, "size": 100,
            "param": {
                "anyMatch": True,
                "queries": [
                    {"property": "coding", "condition": "LIKE", "value": sr_coding},
                    {"property": "name", "condition": "LIKE", "value": sr_coding},
                ],
                "orders": [{"desc": True, "property": "createdTime"}],
            },
        }
        try:
            data = alm_request(cfg, fb_path, "POST", fb_payload)
            if str(data.get("code")) in ("0", "200"):
                records = (data.get("data") or {}).get("data") or (data.get("data") or {}).get("records") or []
        except Exception:
            pass

    # 若 space/app 接口未返回结果，回退到通用接口
    if not records:
        path = "/data-driven/api/object-model/A02/page"
        payload = {
            "current": 1, "size": 10,
            "param": {
                "anyMatch": False,
                "queries": [{"property": "coding", "condition": "EQ", "value": sr_coding}],
                "orders": [{"desc": False, "property": "createdTime"}],
            },
        }
        data = alm_request(cfg, path, "POST", payload)
        if str(data.get("code")) in ("0", "200"):
            records = (data.get("data") or {}).get("data") or (data.get("data") or {}).get("records") or []

    # 精确匹配 coding
    for r in records:
        if str(r.get("coding", "")).strip() == sr_coding:
            return r
    return records[0] if records else None


def alm_batch_find_users(cfg, job_numbers: list) -> dict:
    """批量查询用户信息"""
    if not job_numbers:
        return {}
    result = {}
    for i in range(0, len(job_numbers), 100):
        chunk = job_numbers[i:i + 100]
        data = alm_request(cfg, "/transcend/user/batchFindByEmoNo", "POST", chunk)
        if str(data.get("code")) in ("0", "200") and data.get("success"):
            for u in (data.get("data") or []):
                jn = str(u.get("jobNumber", "")).strip()
                if jn:
                    result[jn] = u
    return result


def alm_query_third_dept(cfg, job_number: str) -> dict:
    """查询测试主责人三级部门"""
    if not job_number:
        return {}
    try:
        data = alm_request(cfg, f"/apm/common/queryThreeDeptInfo/{job_number}", "GET")
        if str(data.get("code")) in ("0", "200") and data.get("success"):
            return data.get("data") or {}
    except Exception:
        pass
    return {}


# ---- ALM SR 详情端点 ----

def _normalize_sr_in_text(text: str) -> str:
    """
    消除 SR 编号中的空格，如 'SR- 202604-000721' → 'SR-202604-000721'
    规则：SR- 后紧跟的空格去掉；年月-序号中间的空格去掉
    """
    # SR- 后面紧跟数字前的空格: SR- 202604 → SR-202604
    text = re.sub(r'(SR-\s+)(\d)', r'SR-\2', text)
    # 年月-序号之间的空格: SR-202604 -000721 → SR-202604-000721
    text = re.sub(r'(SR-\d{6})\s*-\s*(\d)', r'\1-\2', text)
    return text


def extract_sr_codings_from_issues(issues: list) -> list:
    """
    从 Jira issue summary 中提取 SR 编号（去重保序）。
    标准格式: SR-YYYYMM-NNNNNN (6位年月 + 6位序号)
    兼容格式: SR-YYYYMM-NNNN (序号可为4-8位), SR-YYYYMM-NNN (同上)
    会自动消除 SR 编号中的空格，如 SR- 202604-000721 → SR-202604-000721
    """
    # 主模式: SR-YYYYMM-NNNNNN (标准格式)
    sr_pattern = re.compile(r"\bSR-\d{6}-\d{6}\b")
    # 兜底模式: 序号位数不固定 (4-8位)
    sr_fallback_pattern = re.compile(r"\bSR-\d{6}-\d{4,8}\b")
    seen, result = set(), []
    for issue in issues:
        summary = issue.get("summary", "")
        if not summary:
            continue
        # 先消除 SR 编号中的空格
        normalized_summary = _normalize_sr_in_text(summary)
        matches = sr_pattern.findall(normalized_summary)
        if not matches:
            # 兜底: 尝试更宽松的模式
            matches = sr_fallback_pattern.findall(normalized_summary)
        if matches:
            for m in matches:
                if m not in seen:
                    seen.add(m)
                    result.append(m)
        else:
            # 调试: 如果 summary 中包含 "SR" 但未匹配，打印详情
            if "SR" in summary.upper():
                # 提取包含 SR 的上下文（用原文调试）
                sr_context = re.findall(r"SR[-\s]?[\d\-]+", summary, re.IGNORECASE)
                if sr_context:
                    print(f"[SR-DETAIL] summary 含 SR 但未匹配标准格式: key={issue.get('issue_key','')}, "
                          f"sr_candidates={sr_context}, summary={summary[:120]}")
    return result


def _extract_tos_version_from_name(version_name: str) -> str:
    """
    从版本名提取 tOS 版本号，如 'tOS16.3 测试' → '16.3', '16.2' → '16.2'
    返回字符串形式的版本号（major.minor），如 '16.3'
    若无法提取返回空字符串。
    """
    m = re.search(r'(\d+\.\d+)', version_name)
    return m.group(1) if m else ""


def _should_skip_sr_by_space(sr_record: dict, alm_cfg: dict) -> bool:
    """
    通过 ALM 的 spaceBid 判断 SR 是否属于当前版本。

    每个 tOS 版本在 ALM 中有独立的 space（spaceBid 和 spaceAppBid 不同），
    如 16.1 的 spaceBid=1359860883913269248, 16.2 的 spaceBid=1387390492731400192,
    16.3 的 spaceBid=1408550301319528448。

    比较 SR 记录中的 spaceBid 与当前 ALM 配置的 alm_space_bid：
    - 不匹配 → 该 SR 属于其他版本，应跳过
    - 匹配或 SR 中无 spaceBid → 保留
    """
    if not sr_record or not alm_cfg:
        return False

    configured_space_bid = (alm_cfg.get("alm_space_bid") or "").strip()
    if not configured_space_bid:
        return False

    sr_space_bid = str(sr_record.get("spaceBid") or "").strip()
    if not sr_space_bid:
        # SR 中没有 spaceBid，无法判断，不跳过
        return False

    return sr_space_bid != configured_space_bid


def _should_skip_issue_by_labels(labels: list, current_version: str) -> bool:
    """
    根据 Jira issue 的 labels 判断该 issue 是否属于其他版本的 SR（辅助判断）。

    逻辑：
    1. 从 labels 中提取所有 tOS 版本号，如 ['tOS16.1.0解决', '申请tOS16.2解决'] → {'16.1', '16.2'}
       规则：tOS 后跟数字+点+数字的形式（忽略末尾 .0 等补丁号）
    2. 如果没有提取到任何版本信息 → 不跳过（可能是当前版本）
    3. 如果提取到的版本中包含当前版本 → 不跳过
    4. 如果提取到的版本中只有其他版本 → 跳过
    """
    if not labels or not current_version:
        return False

    label_text = " ".join(labels)
    # 提取 tOS 后跟的版本号，如 tOS16.1.0 → 16.1, tOS15.X → 15
    version_patterns = re.findall(r'tOS\s*(\d+(?:\.\d+){0,2})', label_text, re.IGNORECASE)

    if not version_patterns:
        return False

    # 归一化：取 major.minor（忽略补丁号），如 16.1.0 → 16.1, 16.2 → 16.2
    extracted_versions = set()
    for vp in version_patterns:
        parts = vp.split(".")
        if len(parts) >= 2:
            extracted_versions.add(f"{parts[0]}.{parts[1]}")
        else:
            extracted_versions.add(parts[0])

    # 检查当前版本是否在提取到的版本中
    if current_version in extracted_versions:
        return False

    # 只有其他版本的标记，跳过
    return True


# ---- SR 详情缓存端点 ----

def save_sr_details_to_cache(version_id: int, sr_details: list):
    """将 SR 需求详情保存到缓存表"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sr_detail_cache WHERE version_id = ?", (version_id,))
    for sr in sr_details:
        cur.execute("""
            INSERT OR REPLACE INTO sr_detail_cache
            (version_id, sr_coding, sr_name, sr_status, sr_priority, planned_acceptance,
             test_module_owners, test_module_owners_display, issue_count, issue_keys,
             is_other_version, other_version_reason, bid, third_dept, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version_id,
            sr.get("coding", ""),
            sr.get("name", ""),
            sr.get("status", ""),
            sr.get("priority", ""),
            sr.get("planned_acceptance", ""),
            json.dumps(sr.get("test_module_owners", []), ensure_ascii=False),
            sr.get("test_module_owners_display", ""),
            sr.get("issue_count", 0),
            json.dumps(sr.get("issue_keys", []), ensure_ascii=False),
            1 if sr.get("is_other_version") else 0,
            sr.get("other_version_reason", ""),
            sr.get("bid", ""),
            sr.get("third_dept", ""),
            now_iso(),
        ))
    conn.commit()
    conn.close()


def load_sr_details_from_cache(version_id: int) -> dict:
    """从缓存加载 SR 需求详情"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? ORDER BY issue_count DESC", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return {"sr_list": [], "cached": False, "total_sr": 0}

    sr_list = []
    for r in rows:
        owners = []
        try:
            owners = json.loads(r.get("test_module_owners") or "[]")
        except Exception:
            pass
        issue_keys = []
        try:
            issue_keys = json.loads(r.get("issue_keys") or "[]")
        except Exception:
            pass
        sr_list.append({
            "coding": r["sr_coding"],
            "name": r["sr_name"],
            "status": r["sr_status"],
            "priority": r["sr_priority"],
            "planned_acceptance": r["planned_acceptance"],
            "test_module_owners": owners,
            "test_module_owners_display": r["test_module_owners_display"],
            "issue_count": r["issue_count"],
            "issue_keys": issue_keys,
            "is_other_version": bool(r["is_other_version"]),
            "other_version_reason": r.get("other_version_reason", ""),
            "bid": r.get("bid", ""),
            "third_dept": r.get("third_dept", ""),
        })

    current_srs = [s for s in sr_list if not s["is_other_version"]]
    other_srs = [s for s in sr_list if s["is_other_version"]]

    return {
        "sr_list": sr_list,
        "cached": True,
        "total_sr": len(sr_list),
        "total_current_version": len(current_srs),
        "total_other_version": len(other_srs),
        "current_version_issue_count": sum(s["issue_count"] for s in current_srs),
        "other_version_issue_count": sum(s["issue_count"] for s in other_srs),
        "total_issues": sum(s["issue_count"] for s in sr_list),
        "alm_page_url": "https://alm.transsion.com/#/",
        "synced_at": rows[0].get("synced_at") if rows else None,
    }


@app.get("/api/versions/{version_id}/sr-detail-cached")
def get_sr_detail_cached(version_id: int):
    """从缓存快速加载 SR 需求详情"""
    return load_sr_details_from_cache(version_id)


@app.post("/api/versions/{version_id}/sr-detail-refresh")
def refresh_sr_details(version_id: int):
    """刷新 SR 需求详情（从 Jira + ALM 获取并缓存到数据库）"""
    result = get_sr_details(version_id)
    # 保存到缓存
    if result.get("sr_list"):
        save_sr_details_to_cache(version_id, result["sr_list"])
    result["cached"] = True
    return result


@app.get("/api/versions/{version_id}/sr-details")
def get_sr_details(version_id: int):
    """
    1. 从 Jira 获取 SR 遗留问题
    2. 从 summary 中提取 SR 编号
    3. 调用 ALM 查询每个 SR 的详细信息
    4. 合并返回
    """
    # 检查 ALM 配置
    alm_cfg = get_alm_config()
    if not alm_cfg or not alm_cfg.get("alm_app_id"):
        return {"sr_list": [], "error": "请先配置 ALM 账号（点击顶部设置 ⚙️ 按钮进入 ALM 配置）"}
    if not alm_cfg.get("uac_username") or not alm_cfg.get("uac_password"):
        return {"sr_list": [], "error": "ALM 工号或密码未配置，请在设置中填写正确的员工工号（纯数字，如 18665088）和密码"}
    if not alm_cfg["uac_username"].isdigit():
        return {"sr_list": [], "error": f"ALM 工号格式错误：'{alm_cfg['uac_username']}' 不是有效的工号。请在设置中修改为纯数字工号（如 18665088）"}

    # 获取版本信息
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 获取版本级 ALM space/app bid（优先使用版本配置，回退到全局配置）
    version_space_bid = (version.get("alm_space_bid") or "").strip() or alm_cfg.get("alm_space_bid", "")
    version_app_bid = (version.get("alm_app_bid") or "").strip() or alm_cfg.get("alm_app_bid", "")
    if not version_space_bid or not version_app_bid:
        return {"sr_list": [], "error": "请先为该版本配置 ALM_SPACE_BID 和 ALM_APP_BID（在版本列表中点击该版本的设置按钮）"}

    jira_project = version.get("jira_project", "")
    if not jira_project:
        return {"sr_list": [], "error": "版本未配置 Jira 项目"}

    # Step 1: 从 Jira 获取 SR 遗留问题（复用 SR 端点逻辑）
    jql = build_sr_jql(jira_project)
    try:
        credential = get_valid_credential(version_id)
    except Exception:
        return {"sr_list": [], "error": "请先配置 Jira 账号"}

    try:
        resp = requests.post(
            f"{credential['jira_base_url'].rstrip('/')}/rest/api/2/search",
            json={"jql": jql, "startAt": 0, "maxResults": 5000,
                  "fields": ["summary", "status", "priority", "assignee", "labels"]},
            auth=HTTPBasicAuth(credential["username"], credential["password"]),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30, verify=False,
        )
        if resp.status_code == 401:
            return {"sr_list": [], "error": "Jira 认证失败（401）：请在 ⚙️ 设置 → Jira 中重新输入密码"}
        if resp.status_code == 403:
            return {"sr_list": [], "error": f"Jira 权限不足（403）：用户 {credential['username']} 无权查询项目 {jira_project}，请在 ⚙️ 设置 → Jira 中重新输入密码或检查权限"}
        if resp.status_code >= 400:
            return {"sr_list": [], "error": f"Jira 查询失败（HTTP {resp.status_code}）：{resp.text[:120]}"}
        jira_data = resp.json()
        jira_issues = jira_data.get("issues", [])
    except Exception as e:
        return {"sr_list": [], "error": f"Jira 查询失败: {str(e)[:80]}"}

    if not jira_issues:
        return {"sr_list": [], "message": "暂无 SR 遗留问题"}

    # Step 2: 提取 SR 编号（不过滤，全部提取）
    summaries = []
    for issue in jira_issues:
        fields = issue.get("fields", {})
        summaries.append({
            "issue_key": issue.get("key", ""),
            "summary": fields.get("summary") or "",
            "status": (fields.get("status") or {}).get("name") or "",
            "priority": (fields.get("priority") or {}).get("name") or "",
            "assignee": (fields.get("assignee") or {}).get("displayName") or "",
            "labels": fields.get("labels") or [],
        })

    sr_codings = extract_sr_codings_from_issues(summaries)
    print(f"[SR-DETAIL] 从 {len(jira_issues)} 个 issue 中提取到 {len(sr_codings)} 个 SR 编号: {sr_codings}")

    if not sr_codings:
        return {"sr_list": [], "message": "未从 issue summary 中提取到 SR 编号"}

    # Step 3: 查询 ALM，同时通过 spaceBid 判断是否为当前版本的 SR
    sr_details = []
    all_job_numbers = set()
    alm_errors = []
    other_version_count = 0

    for coding in sr_codings:
        print(f"[SR-DETAIL] 查询 ALM: {coding}")
        try:
            record = alm_query_sr_detail(alm_cfg, coding, space_bid=version_space_bid, app_bid=version_app_bid)
        except Exception as e:
            err_str = str(e)
            print(f"[SR-DETAIL] ALM 查询失败: {coding}, error={err_str}")
            alm_errors.append(f"{coding}: {err_str[:100]}")
            record = None

        if record:
            # 通过 spaceBid 判断 SR 是否属于当前版本
            is_other_version = _should_skip_sr_by_space(record, {"alm_space_bid": version_space_bid})
            if is_other_version:
                other_version_count += 1
                sr_space = str(record.get("spaceBid") or "")
                cfg_space = version_space_bid
                print(f"[SR-DETAIL] SR {coding} 属于其他版本 (spaceBid={sr_space}, 当前={cfg_space})，标记为其他版本")
                sr_details.append({
                    "coding": coding,
                    "name": str(record.get("name") or ""),
                    "status": str(record.get("lifeCycleCode") or ""),
                    "priority": str(record.get("priority") or ""),
                    "planned_acceptance": "",
                    "test_module_owners": [],
                    "test_module_owners_display": "",
                    "third_dept": "",
                    "bid": "",
                    "is_other_version": True,
                    "other_version_reason": f"ALM spaceBid 不匹配（SR空间={sr_space}）",
                })
                continue

            # 提取测试模块主责人（数组）
            raw_owners = record.get("testModuleResponsiblePerson") or []
            owner_list = []
            for o in raw_owners:
                o_str = str(o).strip()
                if o_str and o_str.isdigit():
                    owner_list.append(o_str)
                    all_job_numbers.add(o_str)
            sr_details.append({
                "coding": coding,
                "name": str(record.get("name") or ""),
                "status": str(record.get("lifeCycleCode") or ""),
                "priority": str(record.get("priority") or ""),
                "planned_acceptance": str(record.get("plannedAcceptanceStartTime") or ""),
                "test_module_owners": owner_list,
                "test_module_owners_display": "",  # 填充姓名后更新
                "third_dept": "",
                "bid": str(record.get("bid") or record.get("dataBid") or ""),
                "is_other_version": False,
            })
        else:
            # ALM 未找到该 SR，跳过不展示
            print(f"[SR-DETAIL] SR {coding} 在 ALM 中未找到，跳过")
            continue

    if other_version_count > 0:
        print(f"[SR-DETAIL] 通过 spaceBid 过滤掉 {other_version_count} 个其他版本的 SR")

    # Step 4: 批量查询用户姓名 + 三级部门
    if all_job_numbers:
        user_map = alm_batch_find_users(alm_cfg, list(all_job_numbers))
        for sr in sr_details:
            owners = sr.get("test_module_owners", [])
            display_parts = []
            for no in owners:
                if no in user_map:
                    name = str(user_map[no].get("name") or "")
                    display_parts.append(f"{name}({no})" if name else no)
                else:
                    display_parts.append(no)
            sr["test_module_owners_display"] = ", ".join(display_parts) if display_parts else ""
        # 查询三级部门（取第一个主责人的部门）
        dept_map = {}
        for no in list(all_job_numbers)[:30]:  # 限制避免过多请求
            if no not in dept_map:
                dept = alm_query_third_dept(alm_cfg, no)
                if dept:
                    dept_map[no] = str(dept.get("thirdDeptName") or dept.get("secondDeptName") or "")
        for sr in sr_details:
            for no in sr.get("test_module_owners", []):
                if no in dept_map and dept_map[no]:
                    sr["third_dept"] = dept_map[no]
                    break

    # Step 5: 统计每个 SR 对应的 issue 数量（使用与提取相同的模式，含空格归一化）
    sr_issue_map = {}
    sr_count_pattern = re.compile(r"\bSR-\d{6}-\d{4,8}\b")
    for issue in summaries:
        normalized = _normalize_sr_in_text(issue["summary"])
        for m in sr_count_pattern.findall(normalized):
            sr_issue_map.setdefault(m, []).append(issue["issue_key"])

    for sr in sr_details:
        sr["issue_count"] = len(sr_issue_map.get(sr["coding"], []))
        sr["issue_keys"] = sr_issue_map.get(sr["coding"], [])

    # ALM 平台链接
    alm_page_url = "https://alm.transsion.com/#/"

    # 计算各版本关联 issue 数
    current_version_issue_count = sum(
        len(sr_issue_map.get(s["coding"], [])) for s in sr_details if not s.get("is_other_version")
    )
    other_version_issue_count = sum(
        len(sr_issue_map.get(s["coding"], [])) for s in sr_details if s.get("is_other_version")
    )

    result = {
        "sr_list": sr_details,
        "total_sr": len(sr_details),
        "total_current_version": sum(1 for s in sr_details if not s.get("is_other_version")),
        "total_other_version": sum(1 for s in sr_details if s.get("is_other_version")),
        "current_version_issue_count": current_version_issue_count,
        "other_version_issue_count": other_version_issue_count,
        "total_issues": len(jira_issues),
        "alm_page_url": alm_page_url,
    }
    # 如果有 ALM 查询错误，返回给前端提示
    if alm_errors:
        # 检查是否是登录失败（所有查询都失败且原因是认证问题）
        all_login_fail = all("登录失败" in e or "10305" in e for e in alm_errors)
        if all_login_fail:
            result["error"] = "ALM 登录失败，请检查 ALM 配置中的工号和密码是否正确（注意：需要使用员工工号，不是 Jira 域账号）"
        else:
            result["warning"] = f"部分 SR 查询失败: {'; '.join(alm_errors[:3])}"
    return result


# ---- SR 遗留问题缓存 ----

def save_sr_issues_to_cache(version_id: int, issues: list):
    """将 SR 遗留问题保存到缓存"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sr_issue_cache WHERE version_id = ?", (version_id,))
    for i in issues:
        cur.execute("""
            INSERT OR REPLACE INTO sr_issue_cache
            (version_id, issue_key, summary, status, priority, assignee, reporter, created_time, aging_days, labels, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (version_id, i["issue_key"], i["summary"], i["status"], i["priority"],
              i.get("assignee", ""), i.get("reporter", ""), i.get("created_time", ""),
              i.get("aging_days"), json.dumps(i.get("labels", []), ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()


def load_sr_issues_from_cache(version_id: int) -> list:
    """从缓存加载 SR 遗留问题"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_issue_cache WHERE version_id = ? ORDER BY aging_days DESC", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    result = []
    for r in rows:
        labels = []
        try:
            labels = json.loads(r.get("labels") or "[]")
        except Exception:
            pass
        result.append({k: r[k] for k in ["issue_key", "summary", "status", "priority", "assignee", "reporter", "created_time", "aging_days", "synced_at"]})
        result[-1]["labels"] = labels
    return result


@app.get("/api/versions/{version_id}/sr-issues-cached")
def get_sr_issues_cached(version_id: int):
    """从缓存获取 SR 遗留问题（快速加载）"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    issues = load_sr_issues_from_cache(version_id)
    if not issues:
        return {"total": 0, "issues": [], "cached": False, "message": "暂无缓存，请点击刷新"}
    return {"total": len(issues), "issues": issues, "cached": True, "synced_at": issues[0].get("synced_at") if issues else None}


@app.post("/api/versions/{version_id}/sr-issues-refresh")
def refresh_sr_issues(version_id: int):
    """从 Jira 刷新 SR 遗留问题并更新缓存"""
    # 复用 get_sr_issues 的逻辑
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    jira_project = version.get("jira_project", "")
    if not jira_project:
        return {"total": 0, "issues": [], "error": "版本未配置 Jira 项目"}

    jql = build_sr_jql(jira_project)
    try:
        credential = get_valid_credential(version_id)
    except Exception as e:
        return {"total": 0, "issues": [], "error": str(e)}

    base_url = credential["jira_base_url"].rstrip("/")
    url = f"{base_url}/rest/api/2/search"
    sr_fields = ["summary", "status", "priority", "assignee", "reporter", "created", "updated", "labels"]

    try:
        resp = requests.post(url, json={"jql": jql, "startAt": 0, "maxResults": 5000, "fields": sr_fields},
                             auth=HTTPBasicAuth(credential["username"], credential["password"]),
                             headers={"Accept": "application/json", "Content-Type": "application/json"},
                             timeout=30, verify=False)
    except Exception as e:
        return {"total": 0, "issues": [], "error": f"Jira 查询失败: {str(e)[:80]}"}

    if resp.status_code == 401:
        return {"total": 0, "issues": [], "error": "Jira 认证失败（401）：请在 ⚙️ 设置 → Jira 中重新输入密码"}
    if resp.status_code == 403:
        return {"total": 0, "issues": [], "error": f"Jira 权限不足（403）：请在浏览器登录 Jira 完成验证码验证，或使用 API Token"}
    if resp.status_code >= 400:
        return {"total": 0, "issues": [], "error": f"Jira 返回 HTTP {resp.status_code}"}

    data = resp.json()
    raw_issues = data.get("issues", [])
    sr_issues = []
    for issue in raw_issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        created_time = parse_dt(fields.get("created"))
        aging_days = None
        if created_time:
            try:
                aging_days = (datetime.now() - parser.parse(created_time)).days
            except Exception:
                pass
        sr_issues.append({
            "issue_key": issue.get("key", ""),
            "summary": fields.get("summary") or "",
            "status": (fields.get("status") or {}).get("name") or "未知",
            "priority": (fields.get("priority") or {}).get("name") or "未设置",
            "assignee": assignee.get("displayName") or assignee.get("name") or "未分配",
            "reporter": reporter.get("displayName") or reporter.get("name") or "未知",
            "created_time": created_time,
            "aging_days": aging_days,
            "labels": fields.get("labels") or [],
        })

    sr_issues.sort(key=lambda x: ({"Blocker": 0, "Critical": 1, "Major": 2}.get(x.get("priority", ""), 99), -(x.get("aging_days") or 0)))

    # 保存到缓存
    save_sr_issues_to_cache(version_id, sr_issues)

    return {"total": len(sr_issues), "issues": sr_issues, "cached": True, "synced_at": now_iso(), "jql": jql,
            "jira_url": f"{DEFAULT_JIRA_BASE_URL}/issues/?jql={quote(jql)}"}


# ---- SR AI 分析 ----

@app.get("/api/versions/{version_id}/sr-ai-analysis")
def get_sr_ai_analysis(version_id: int):
    """获取 SR AI 分析结果（从缓存）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_ai_analysis WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"analyses": {r["sr_coding"]: {"analysis": r["analysis"], "analyzed_at": r["analyzed_at"]} for r in rows}}


@app.delete("/api/versions/{version_id}/sr-ai-analysis")
def delete_sr_ai_analysis(version_id: int, sr_codings: List[str] = Query(..., alias="sr_coding")):
    """删除指定 SR 的 AI 分析结果"""
    conn = get_conn()
    cur = conn.cursor()
    for coding in sr_codings:
        cur.execute("DELETE FROM sr_ai_analysis WHERE version_id = ? AND sr_coding = ?", (version_id, coding))
    conn.commit()
    conn.close()
    return {"deleted": len(sr_codings)}


@app.post("/api/versions/{version_id}/sr-ai-analysis")
def run_sr_ai_analysis(version_id: int, sr_codings: List[str] = Query(..., alias="sr_coding")):
    """对指定 SR 列表执行 AI 分析"""
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 获取 AI prompt 模板
    ai_cfg = get_ai_config_decrypted()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT sr_ai_prompt FROM ai_config WHERE id = 1")
    row = cur.fetchone()
    prompt_template = (row and row["sr_ai_prompt"]) or "分析 SR 需求 {sr_coding} 的风险并给出测试建议。"
    conn.close()

    # 获取 SR 详情数据
    sr_details_data = []
    try:
        # 调用内部逻辑获取 SR 详情
        alm_cfg = get_alm_config()
        for coding in sr_codings:
            record = None
            if alm_cfg and alm_cfg.get("alm_app_id"):
                try:
                    version_space_bid = (version.get("alm_space_bid") or "").strip() or alm_cfg.get("alm_space_bid", "")
                    version_app_bid = (version.get("alm_app_bid") or "").strip() or alm_cfg.get("alm_app_bid", "")
                    record = alm_query_sr_detail(alm_cfg, coding, space_bid=version_space_bid, app_bid=version_app_bid)
                except Exception:
                    pass
            sr_info = {"coding": coding, "name": "", "status": "", "priority": "", "planned_acceptance": "", "owners": ""}
            if record:
                sr_info.update({
                    "name": str(record.get("name") or ""),
                    "status": str(record.get("lifeCycleCode") or ""),
                    "priority": str(record.get("priority") or ""),
                    "planned_acceptance": str(record.get("plannedAcceptanceStartTime") or ""),
                })
            sr_details_data.append(sr_info)
    except Exception:
        sr_details_data = [{"coding": c, "name": "", "status": "", "priority": ""} for c in sr_codings]

    # 获取版本上下文
    issues = load_issues(version_id, "ALL")
    total_issues = len(issues)
    unresolved = sum(1 for i in issues if i["status"] not in CLOSED_STATUS)
    high_priority = sum(1 for i in issues if i["priority"] in HIGH_PRIORITY)

    # 构建 prompt
    sr_data_text = "\n".join([
        f"- {s['coding']}: {s['name']} | 状态={s['status']} | 优先级={s['priority']} | 计划验收={s.get('planned_acceptance', '')}"
        for s in sr_details_data
    ])

    system_prompt = prompt_template.format(
        version_name=version["version_name"],
        stage="ALL",
        total_issues=total_issues,
        unresolved=unresolved,
        high_priority=high_priority,
    )

    user_prompt = (
        f"请逐一分析以下 SR 需求的风险和测试建议。\n"
        f"【重要】每个 SR 必须以 SR 编号开头（如 SR-202508-000335:），每个 SR 分析 2-3 句话，用空行分隔。\n\n"
        f"{sr_data_text}"
    )

    result = call_ai(system_prompt, user_prompt)

    # 按 SR 编号批量解析结果
    parsed = _parse_sr_analyses_from_result(result, sr_codings)

    # 保存到数据库
    conn = get_conn()
    cur = conn.cursor()
    analyzed_at = now_iso()
    for coding in sr_codings:
        analysis_text = parsed.get(coding, "")
        cur.execute("""
            INSERT INTO sr_ai_analysis (version_id, sr_coding, analysis, analyzed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET analysis = excluded.analysis, analyzed_at = excluded.analyzed_at
        """, (version_id, coding, analysis_text, analyzed_at))
    conn.commit()
    conn.close()

    return {"analyses": {coding: {"analysis": parsed.get(coding, ""), "analyzed_at": analyzed_at} for coding in sr_codings},
            "raw_result": result}


# ---- SR AI 风险等级分析（综合排序） ----

def _compute_issue_keys_hash(issue_keys: list) -> str:
    """计算 issue_keys 列表的哈希值，用于判断是否需要重新分析"""
    import hashlib
    text = ",".join(sorted(issue_keys))
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _build_sr_priority_context(sr_list: list, all_issues: list) -> str:
    """为 AI 构建所有 SR + 关联 issue 的完整上下文"""
    issue_map = {}
    for issue in all_issues:
        issue_map[issue.get("issue_key", "")] = issue

    lines = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"当前日期：{today_str}")
    lines.append("")

    for sr in sr_list:
        coding = sr.get("coding", "")
        name = sr.get("name", "")
        status = sr.get("status", "")
        priority = sr.get("priority", "")
        planned = sr.get("planned_acceptance", "")
        issue_count = sr.get("issue_count", 0)
        owners = sr.get("test_module_owners_display", "")
        issue_keys = sr.get("issue_keys", [])

        # 计算距计划验收的天数
        days_info = ""
        if planned:
            try:
                planned_dt = parser.parse(planned[:10])
                days_diff = (planned_dt - datetime.now()).days
                if days_diff < 0:
                    days_info = f"（已逾期 {abs(days_diff)} 天）"
                elif days_diff <= 7:
                    days_info = f"（{days_diff} 天后到期）"
                else:
                    days_info = f"（还有 {days_diff} 天）"
            except Exception:
                pass

        lines.append(f"## {coding}")
        lines.append(f"- 需求名称：{name}")
        lines.append(f"- 状态：{status} | 优先级：{priority}")
        lines.append(f"- 计划验收：{planned or '未设置'} {days_info}")
        lines.append(f"- 测试主责人：{owners or '未设置'}")
        lines.append(f"- 关联 Issue 数：{issue_count}")

        if issue_keys:
            lines.append(f"- 关联 Issue 列表：")
            for ik in issue_keys:
                issue_data = issue_map.get(ik)
                if issue_data:
                    aging = issue_data.get("aging_days") or "?"
                    lines.append(f"  - {ik}: 状态={issue_data.get('status','')}, 优先级={issue_data.get('priority','')}, "
                                 f"负责人={issue_data.get('assignee','')}, 遗留={aging}天, "
                                 f"描述={issue_data.get('summary','')[:80]}")
                else:
                    lines.append(f"  - {ik}: (详细信息未知)")
        lines.append("")

    return "\n".join(lines)


@app.get("/api/versions/{version_id}/sr-ai-priority")
def get_sr_ai_priority(version_id: int):
    """获取 SR AI 风险等级分析结果（从缓存）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ? ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, issue_count DESC", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    results = {}
    for r in rows:
        results[r["sr_coding"]] = {
            "risk_level": r["risk_level"],
            "analysis": r["analysis"],
            "issue_count": r["issue_count"],
            "analyzed_at": r["analyzed_at"],
        }
    return {"results": results, "total": len(results)}


@app.post("/api/versions/{version_id}/sr-ai-priority")
def run_sr_ai_priority(version_id: int, force: bool = Query(False)):
    """
    AI 综合分析所有当前版本 SR 的风险等级。
    - 从 sr_detail_cache 读取 SR 列表
    - 从 sr_issue_cache 读取关联 issue 详情
    - 用 issue_keys_hash 判断哪些 SR 的 issue 发生了变化，只重新分析变化的
    - force=true 时强制重新分析所有
    """
    version = get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    conn = get_conn()
    cur = conn.cursor()

    # 1. 从缓存读取 SR 列表
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? AND is_other_version = 0 ORDER BY issue_count DESC", (version_id,))
    sr_rows = [row_to_dict(r) for r in cur.fetchall()]

    if not sr_rows:
        conn.close()
        return {"results": {}, "total": 0, "message": "请先查询 SR 需求详情（ALM）"}

    sr_list = []
    for r in sr_rows:
        issue_keys = []
        try:
            issue_keys = json.loads(r.get("issue_keys") or "[]")
        except Exception:
            pass
        sr_list.append({
            "coding": r["sr_coding"],
            "name": r["sr_name"],
            "status": r["sr_status"],
            "priority": r["sr_priority"],
            "planned_acceptance": r["planned_acceptance"],
            "test_module_owners_display": r["test_module_owners_display"],
            "issue_count": r["issue_count"],
            "issue_keys": issue_keys,
        })

    # 2. 读取已有分析结果
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ?", (version_id,))
    existing = {r["sr_coding"]: row_to_dict(r) for r in cur.fetchall()}

    # 3. 判断哪些 SR 需要重新分析
    needs_analysis = []
    preserved = {}
    for sr in sr_list:
        coding = sr["coding"]
        new_hash = _compute_issue_keys_hash(sr["issue_keys"])
        old = existing.get(coding)

        if not force and old and old.get("issue_keys_hash") == new_hash and old.get("risk_level"):
            # issue 无变化且已有分析结果，保留
            preserved[coding] = {
                "risk_level": old["risk_level"],
                "analysis": old["analysis"],
                "issue_count": old["issue_count"],
                "analyzed_at": old["analyzed_at"],
            }
        else:
            needs_analysis.append(sr)

    if not needs_analysis:
        conn.close()
        # 直接返回已有结果
        all_results = {**preserved}
        sorted_results = dict(sorted(all_results.items(), key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x[1]["risk_level"], 3), -(x[1]["issue_count"] or 0))))
        return {"results": sorted_results, "total": len(sorted_results), "changed": 0}

    # 4. 加载关联 issue 详情
    all_issues = load_issues(version_id, "ALL")
    issue_map = {i.get("issue_key", ""): i for i in all_issues}

    # 5. 构建 AI prompt
    context = _build_sr_priority_context(needs_analysis, all_issues)
    sr_codings = [s["coding"] for s in needs_analysis]

    system_prompt = (
        "你是软件测试质量风险分析专家。请综合分析以下 SR 需求的风险等级。\n\n"
        "分析维度：\n"
        "1. 关联 Issue 数量和状态（未关闭越多风险越高）\n"
        "2. Issue 优先级分布（Blocker/Critical 越多风险越高）\n"
        "3. Issue 遗留天数（越久风险越高）\n"
        "4. 计划验收时间紧迫度（越临近或已逾期风险越高）\n"
        "5. SR 本身的状态和优先级\n\n"
        "请严格按以下 JSON 格式输出，不要输出其他内容：\n"
        "```json\n"
        '[\n'
        '  {"coding": "SR-XXXXXX-XXXXXX", "risk_level": "high", "analysis": "3-4句分析"},\n'
        '  {"coding": "SR-YYYYYY-YYYYYY", "risk_level": "medium", "analysis": "2-3句分析"},\n'
        '  {"coding": "SR-ZZZZZZ-ZZZZZZ", "risk_level": "low", "analysis": "1句简述"}\n'
        "]\n"
        "```\n\n"
        "risk_level 只能是 high/medium/low 三个值。\n"
        "每个 SR 都必须输出，不可遗漏。\n"
        "analysis 字段给出简洁的风险分析和测试建议。"
    )

    user_prompt = (
        f"当前版本：{version['version_name']}\n"
        f"需要分析的 SR 数量：{len(needs_analysis)}\n\n"
        f"{context}"
    )

    # 6. 调用 AI
    print(f"[SR-PRIORITY] 开始 AI 分析 {len(needs_analysis)} 个 SR")
    result_text = call_ai(system_prompt, user_prompt)
    print(f"[SR-PRIORITY] AI 返回 {len(result_text)} 字符")

    # 7. 解析 JSON 结果
    parsed_results = []
    try:
        # 提取 JSON 块
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            parsed_results = json.loads(json_match.group())
    except Exception as e:
        print(f"[SR-PRIORITY] JSON 解析失败: {e}")
        # 兜底：尝试逐行解析
        for sr in needs_analysis:
            coding = sr["coding"]
            idx = result_text.find(coding)
            if idx >= 0:
                snippet = result_text[idx:idx + 300]
                level = "medium"
                if "high" in snippet.lower():
                    level = "high"
                elif "low" in snippet.lower():
                    level = "low"
                parsed_results.append({"coding": coding, "risk_level": level, "analysis": snippet[:200]})

    # 8. 写入数据库
    analyzed_at = now_iso()
    new_results = {}
    for item in parsed_results:
        coding = item.get("coding", "")
        if not coding:
            continue
        risk_level = item.get("risk_level", "medium")
        if risk_level not in ("high", "medium", "low"):
            risk_level = "medium"
        analysis = item.get("analysis", "")
        issue_count = next((s["issue_count"] for s in sr_list if s["coding"] == coding), 0)
        issue_keys = next((s["issue_keys"] for s in sr_list if s["coding"] == coding), [])
        issue_hash = _compute_issue_keys_hash(issue_keys)

        cur.execute("""
            INSERT INTO sr_ai_priority (version_id, sr_coding, risk_level, analysis, issue_count, issue_keys_hash, issue_keys, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET
                risk_level = excluded.risk_level,
                analysis = excluded.analysis,
                issue_count = excluded.issue_count,
                issue_keys_hash = excluded.issue_keys_hash,
                issue_keys = excluded.issue_keys,
                analyzed_at = excluded.analyzed_at
        """, (version_id, coding, risk_level, analysis, issue_count, issue_hash, json.dumps(issue_keys, ensure_ascii=False), analyzed_at))

        new_results[coding] = {
            "risk_level": risk_level,
            "analysis": analysis,
            "issue_count": issue_count,
            "analyzed_at": analyzed_at,
        }

    # 同时更新 sr_ai_analysis 表（复用单个 SR 分析结果）
    for coding, data in new_results.items():
        cur.execute("""
            INSERT INTO sr_ai_analysis (version_id, sr_coding, analysis, analyzed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(version_id, sr_coding) DO UPDATE SET
                analysis = excluded.analysis,
                analyzed_at = excluded.analyzed_at
        """, (version_id, coding, data["analysis"], analyzed_at))

    conn.commit()
    conn.close()

    # 合并保留的和新分析的结果
    all_results = {**preserved, **new_results}
    sorted_results = dict(sorted(all_results.items(), key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x[1]["risk_level"], 3), -(x[1]["issue_count"] or 0))))

    return {"results": sorted_results, "total": len(sorted_results), "changed": len(needs_analysis)}


def _parse_sr_analyses_from_result(full_text: str, sr_codings: list) -> dict:
    """
    从 AI 完整回复中按 SR 编号切分，返回 {sr_coding: analysis_text}。
    先用所有 SR 编号把文本切成段落，再匹配到对应 coding。
    """
    if not sr_codings:
        return {}

    # 构建匹配所有 SR 编号的正则（含可选的 markdown 粗体、序号前缀）
    # 匹配：SR-202508-000335、**SR-202508-000335**、1. SR-202508-000335 等
    escaped = [re.escape(c) for c in sr_codings]
    split_pattern = re.compile(
        r'(?:^|\n)\s*(?:\d+[\.\)、:：\s]*\s*)?(?:\*{1,2})?(' + '|'.join(escaped) + r')(?:\*{1,2})?[\s:：\-]*',
        re.IGNORECASE | re.MULTILINE
    )

    # 找到所有 SR 编号在文本中的位置
    matches = list(split_pattern.finditer(full_text))

    result = {}
    for i, m in enumerate(matches):
        coding = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        segment = full_text[start:end].strip()
        # 截断过长内容
        if len(segment) > 600:
            segment = segment[:600] + "..."
        result[coding] = segment

    # 对于没有匹配到的 coding，尝试模糊搜索
    for coding in sr_codings:
        if coding not in result:
            # 简单搜索：找包含 coding 的行及其后续内容
            idx = full_text.lower().find(coding.lower())
            if idx >= 0:
                snippet = full_text[idx:idx + 400].strip()
                result[coding] = snippet
            else:
                result[coding] = ""

    return result


def _extract_sr_analysis_from_result(full_text: str, sr_coding: str) -> str:
    """从 AI 完整回复中提取单个 SR 的分析（兼容旧调用）"""
    results = _parse_sr_analyses_from_result(full_text, [sr_coding])
    return results.get(sr_coding, "")


def load_issues(version_id: int, stage: str, include_raw: bool = False):
    """
    从数据库加载 issue 列表。
    include_raw=False 时跳过 raw_payload 字段（体积最大的字段），提升查询性能。
    """
    conn = get_conn()
    cur = conn.cursor()

    if include_raw:
        columns = "*"
    else:
        # 排除 raw_payload（每条可能几百KB 的 Jira 原始 JSON）
        columns = (
            "id, version_id, version_name, str_stage, issue_key, "
            "summary, description, status, priority, issue_type, "
            "assignee, reporter, module_name, labels, "
            "created_time, updated_time, resolved_time, synced_at, "
            "must_fix, severity, model, issue_category, frequency, "
            "module_category, project_code, os_version, android_version, "
            "grade, must_fix_flag, aging_days, stale_days, risk_score"
        )

    if stage == "ALL":
        cur.execute(f"SELECT {columns} FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    else:
        cur.execute(f"SELECT {columns} FROM jira_issue_cache WHERE version_id = ? AND str_stage = ?", (version_id, stage))

    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def safe_dt(value):
    if not value:
        return None
    try:
        return parser.parse(value)
    except Exception:
        return None


def calc_aging_days(issue):
    """计算问题遗留天数"""
    created = safe_dt(issue.get("created_time"))
    if not created:
        return None
    return (datetime.now() - created).days


def is_must_fix_issue(issue):
    """判断是否为必解问题"""
    labels = issue.get("labels") or ""
    priority = issue.get("priority") or ""
    summary = issue.get("summary") or ""

    keywords = ["必解", "mustfix", "must_fix", "MP", "阻塞", "block"]

    if priority in {"Blocker", "Critical", "P0"}:
        return True

    source = f"{labels} {summary}".lower()
    return any(k.lower() in source for k in keywords)


def build_analysis(version_id: int, stage: str):
    """
    构建分析报告（增强版，使用数据库中已计算的字段）
    """
    version = get_version(version_id)
    issues = load_issues(version_id, stage)

    total = len(issues)

    if total == 0:
        return {
            "metrics": {"version_name": version["version_name"], "stage": stage, "cache_count": 0},
            "risks": {},
        }

    # 使用数据库中已存储的字段
    closed = [i for i in issues if i["status"] in CLOSED_STATUS or i.get("resolved_time")]
    unresolved = [i for i in issues if i["status"] not in CLOSED_STATUS and not i.get("resolved_time")]
    high_unresolved = [i for i in unresolved if i["priority"] in HIGH_PRIORITY]

    # 使用数据库中的 aging_days 和 stale_days
    issue_14 = [i for i in unresolved if (i.get("aging_days") or 0) >= 14]
    issue_30 = [i for i in unresolved if (i.get("aging_days") or 0) >= 30]
    long_unupdated = [i for i in unresolved if (i.get("stale_days") or 0) >= 7]

    net = total - len(closed)
    close_new_ratio = round(len(closed) / total * 100, 1) if total else 0
    unresolved_ratio = round(len(unresolved) / total * 100, 1) if total else 0
    high_unresolved_ratio = round(len(high_unresolved) / len(unresolved) * 100, 1) if unresolved else 0

    # 状态分布统计
    status_distribution = dict(Counter(i.get("status") or "未知" for i in issues))

    # Open/Reopen 统计
    open_reopen_status = {"Open", "Reopen", "Reopened", "打开", "重新打开"}
    open_reopen_issues = [i for i in issues if i.get("status") in open_reopen_status]
    open_reopen_count = len(open_reopen_issues)

    # Open/Reopen 高风险问题列表（使用数据库中的 risk_score）
    open_reopen_high_risk = sorted(
        [i for i in open_reopen_issues if i.get("priority") in HIGH_PRIORITY],
        key=lambda x: x.get("risk_score") or 0,
        reverse=True
    )

    # Submitted / Modifying 时效分布 + 问题列表
    submitted_issues = [i for i in issues if i.get("status") == "Submitted"]
    modifying_issues = [i for i in issues if i.get("status") == "Modifying"]
    submitted_modifying_issues = sorted(
        submitted_issues + modifying_issues,
        key=lambda x: x.get("risk_score") or 0, reverse=True
    )
    submitted_modifying_aging = {
        "lt3": {"Submitted": 0, "Modifying": 0},
        "d3_7": {"Submitted": 0, "Modifying": 0},
        "gt7": {"Submitted": 0, "Modifying": 0},
    }

    for i in submitted_modifying_issues:
        status = i.get("status")
        aging = i.get("aging_days")
        if aging is None:
            continue
        if aging < 3:
            submitted_modifying_aging["lt3"][status] += 1
        elif aging <= 7:
            submitted_modifying_aging["d3_7"][status] += 1
        else:
            submitted_modifying_aging["gt7"][status] += 1

    # Open/Reopened 详细列表（全部，按 risk_score 排序）
    open_reopen_all = sorted(
        open_reopen_issues,
        key=lambda x: x.get("risk_score") or 0, reverse=True
    )
    open_reopen_high_count = len([i for i in open_reopen_issues if i.get("priority") in HIGH_PRIORITY])
    open_reopen_avg_aging = round(sum(i.get("aging_days") or 0 for i in open_reopen_issues) / max(len(open_reopen_issues), 1), 1)

    # 必解问题（使用数据库中的 must_fix_flag）
    must_fix_issues = [i for i in issues if i.get("must_fix_flag") == 1]
    must_fix_unresolved = [i for i in must_fix_issues if i["status"] not in CLOSED_STATUS]

    must_fix_total_count = len(must_fix_issues)
    must_fix_pending_count = len(must_fix_unresolved)
    must_fix_timeout_count = len([i for i in must_fix_unresolved if (i.get("aging_days") or 0) > 3])
    must_fix_pass_count = len([i for i in must_fix_issues if i["status"] in {"Verified", "Closed", "Done", "Resolved"}])

    # A/B/C 等级分布
    grade_distribution = dict(Counter(i.get("grade") or "未分级" for i in issues))

    # 机型分布
    model_distribution = dict(Counter(i.get("model") or "未填写" for i in issues if i.get("model")))

    # 问题类别分布
    issue_category_distribution = dict(Counter(i.get("issue_category") or "未填写" for i in issues if i.get("issue_category")))

    # 模块分类分布
    module_category_distribution = dict(Counter(i.get("module_category") or "未填写" for i in issues if i.get("module_category")))

    # 遗留天数分布
    aging_bucket = {"0-3天": 0, "4-7天": 0, "8-14天": 0, "15-30天": 0, "31-60天": 0, ">60天": 0}
    for i in issues:
        aging = i.get("aging_days")
        if aging is None:
            continue
        if aging <= 3:
            aging_bucket["0-3天"] += 1
        elif aging <= 7:
            aging_bucket["4-7天"] += 1
        elif aging <= 14:
            aging_bucket["8-14天"] += 1
        elif aging <= 30:
            aging_bucket["15-30天"] += 1
        elif aging <= 60:
            aging_bucket["31-60天"] += 1
        else:
            aging_bucket[">60天"] += 1

    # 模块/负责人统计
    module_map = {}
    owner_map = {}

    for i in issues:
        m = i.get("module_name") or "未归类"
        a = i.get("assignee") or "未分配"

        module_map.setdefault(m, {"name": m, "total": 0, "unresolved": 0, "high": 0, "must_fix": 0})
        owner_map.setdefault(a, {"name": a, "total": 0, "unresolved": 0, "high": 0, "long_unupdated": 0, "must_fix": 0})

        module_map[m]["total"] += 1
        owner_map[a]["total"] += 1

        if i in unresolved:
            module_map[m]["unresolved"] += 1
            owner_map[a]["unresolved"] += 1

        if i.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
            owner_map[a]["high"] += 1

        if i in long_unupdated:
            owner_map[a]["long_unupdated"] += 1

        if i.get("must_fix_flag") == 1:
            module_map[m]["must_fix"] += 1
            owner_map[a]["must_fix"] += 1

    top_modules = sorted(
        module_map.values(),
        key=lambda x: (x["high"], x["must_fix"], x["unresolved"], x["total"]),
        reverse=True
    )[:10]

    top_owners = sorted(
        owner_map.values(),
        key=lambda x: (x["high"], x["must_fix"], x["long_unupdated"], x["unresolved"]),
        reverse=True
    )[:10]

    # Top 风险问题（使用 risk_score）
    typical_issues = sorted(
        unresolved,
        key=lambda x: x.get("risk_score") or 0,
        reverse=True
    )[:10]

    # 风险等级判断
    risk_level = "低"
    if len(high_unresolved) > 30 or unresolved_ratio > 60 or len(issue_30) > 20 or must_fix_pending_count > 10:
        risk_level = "高"
    elif len(high_unresolved) > 10 or unresolved_ratio > 35 or must_fix_pending_count > 5:
        risk_level = "中"

    metrics = {
        "version_name": version["version_name"],
        "stage": stage,
        "total_issue_count": total,
        "new_issue_count": total,
        "closed_issue_count": len(closed),
        "net_issue_count": net,
        "unresolved_issue_count": len(unresolved),
        "high_unresolved_count": len(high_unresolved),
        "close_new_ratio": close_new_ratio,
        "unresolved_ratio": unresolved_ratio,
        "high_unresolved_ratio": high_unresolved_ratio,
        "issue_14_count": len(issue_14),
        "issue_30_count": len(issue_30),
        "long_unupdated_count": len(long_unupdated),
        "risk_level": risk_level,
        "last_sync": max([i["synced_at"] for i in issues], default=None),
        "cache_count": total,
        # 状态分布
        "status_distribution": status_distribution,
        "open_reopen_count": open_reopen_count,
        # 时效分布
        "submitted_modifying_aging": submitted_modifying_aging,
        "aging_bucket": aging_bucket,
        # 必解统计
        "must_fix_total_count": must_fix_total_count,
        "must_fix_pending_count": must_fix_pending_count,
        "must_fix_timeout_count": must_fix_timeout_count,
        "must_fix_pass_count": must_fix_pass_count,
        # A/B/C 等级
        "grade_distribution": grade_distribution,
        # 机型/模块分布
        "model_distribution": model_distribution,
        "issue_category_distribution": issue_category_distribution,
        "module_category_distribution": module_category_distribution,
    }

    # 剥离大字段，减少 API 响应体积
    HEAVY_FIELDS = {"raw_payload", "description"}  # 前端不需要的大字段

    def slim_issues(issue_list):
        """剥离大字段，只保留前端展示需要的字段"""
        return [{k: v for k, v in i.items() if k not in HEAVY_FIELDS} for i in issue_list]
    risks = {
        "top_modules": top_modules,
        "top_owners": top_owners,
        "typical_issues": slim_issues(typical_issues),
        "open_reopen_high_risk": slim_issues(open_reopen_high_risk),
        "open_reopen_high_risk_total": len(open_reopen_high_risk),
        "open_reopen_issues": slim_issues(open_reopen_all),
        "open_reopen_issues_total": len(open_reopen_all),
        "open_reopen_high_count": open_reopen_high_count,
        "open_reopen_avg_aging": open_reopen_avg_aging,
        "submitted_issues": slim_issues([i for i in submitted_modifying_issues if i.get("status") == "Submitted"]),
        "submitted_count": len(submitted_issues),
        "modifying_issues": slim_issues([i for i in submitted_modifying_issues if i.get("status") == "Modifying"]),
        "modifying_count": len(modifying_issues),
        "submitted_modifying_issues": slim_issues(submitted_modifying_issues),
        "submitted_modifying_total": len(submitted_modifying_issues),
        "must_fix_issues": slim_issues(sorted([i for i in must_fix_unresolved if (i.get("risk_score") or 0) > 50], key=lambda x: x.get("risk_score") or 0, reverse=True)),
        "must_fix_issues_total": len([i for i in must_fix_unresolved if (i.get("risk_score") or 0) > 50]),
    }

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO analysis_snapshot (
        version_id, version_name, str_stage,
        period_start, period_end,
        metrics_json, risks_json, suggestions_json,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        version_id,
        version["version_name"],
        stage,
        None,
        None,
        json.dumps(metrics, ensure_ascii=False),
        json.dumps(risks, ensure_ascii=False),
        "[]",
        now_iso()
    ))
    conn.commit()
    conn.close()

    return {
        "metrics": metrics,
        "risks": risks,
    }


@app.get("/api/versions/{version_id}/analysis")
def get_analysis(version_id: int, stage: str = Query("STR1")):
    issues = load_issues(version_id, stage)
    if not issues:
        return build_analysis(version_id, stage)
    return build_analysis(version_id, stage)


# ==============================
# 稳定性专项数据 CRUD
# ==============================

class StabilityDeviceData(BaseModel):
    device_name: str
    rom_version: Optional[str] = ""
    sys_apr_value: Optional[str] = ""
    sys_apr_threshold: Optional[str] = ""
    sys_apr_duration: Optional[str] = ""
    app_apr_value: Optional[str] = ""
    app_apr_threshold: Optional[str] = ""
    app_apr_duration: Optional[str] = ""
    subsys_apr_value: Optional[str] = ""
    subsys_apr_threshold: Optional[str] = ""
    subsys_apr_duration: Optional[str] = ""
    third_apr_value: Optional[str] = ""
    third_apr_threshold: Optional[str] = ""
    third_apr_duration: Optional[str] = ""
    jira_keys: Optional[str] = ""
    remark: Optional[str] = ""


@app.get("/api/versions/{version_id}/stability")
def get_stability_data(version_id: int):
    """获取该版本所有机型的稳定性数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stability_data WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"devices": rows}


@app.post("/api/versions/{version_id}/stability")
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


@app.post("/api/versions/{version_id}/stability/init")
def init_stability_devices(version_id: int, device_names: Optional[List[str]] = Body(None, embed=False)):
    """根据机型信息初始化稳定性数据（不覆盖已有数据）。
    如果前端传了 device_names 则直接使用，否则从飞书管理书读取。"""
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
                                    if raw_values:
                                        values = [[feishu_cell_to_str(cell) for cell in (row or [])] for row in raw_values]
                                        CATEGORY_KEYWORDS = {"首发", "衍生", "存量SR适配"}
                                        def read_devices_downward(start_row, col):
                                            devs = []
                                            for r in range(start_row, len(values)):
                                                row = values[r]
                                                if col >= len(row):
                                                    break
                                                val = row[col].strip()
                                                if not val:
                                                    break
                                                if val in CATEGORY_KEYWORDS:
                                                    break
                                                devs.append(val)
                                            return devs
                                        for ri, row in enumerate(values):
                                            for ci, cell in enumerate(row):
                                                if cell.strip() in CATEGORY_KEYWORDS:
                                                    devs = read_devices_downward(ri + 1, ci)
                                                    devices.extend(devs)
                                        devices = list(dict.fromkeys(devices))  # 去重保序
            except Exception as e:
                print(f"[stability/init] 从飞书读取机型失败: {e}")

        # 回退：从 device_list 字段读取
        if not devices:
            device_list_str = version.get("device_list", "")
            devices = [d.strip() for d in device_list_str.split(",") if d.strip()]

    if not devices:
        return {"message": "未找到机型信息（请先配置飞书管理书或手动添加机型）", "added": 0}

    conn = get_conn()
    cur = conn.cursor()
    added = 0
    for device in devices:
        try:
            cur.execute("""
                INSERT INTO stability_data (version_id, device_name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(version_id, device_name) DO NOTHING
            """, (version_id, device, now_iso()))
            if cur.rowcount > 0:
                added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return {"message": f"已初始化 {added} 个机型（来源：{'飞书管理书' if feishu_url else 'device_list'}）", "added": added, "source": "feishu" if feishu_url else "device_list"}


@app.delete("/api/versions/{version_id}/stability/{device_name:path}")
def delete_stability_device(version_id: int, device_name: str):
    """删除单个机型的稳定性数据（device_name 支持含斜杠等特殊字符）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM stability_data WHERE version_id = ? AND device_name = ?", (version_id, device_name))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"已删除 {device_name}", "deleted": deleted}


# ==============================
# 测试计划 CRUD（性能/续航等专项的用户手动计划）
# ==============================

class TestPlanData(BaseModel):
    device_name: str
    test_items: Optional[str] = ""
    plan_status: Optional[str] = "planned"
    plan_start_date: Optional[str] = ""
    plan_end_date: Optional[str] = ""
    responsible_person: Optional[str] = ""
    remark: Optional[str] = ""


@app.get("/api/versions/{version_id}/test-plans/{plan_type}")
def get_test_plans(version_id: int, plan_type: str):
    """获取该版本指定类型的测试计划列表"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM test_plans WHERE version_id = ? AND plan_type = ? ORDER BY id", (version_id, plan_type))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"plans": rows}


@app.post("/api/versions/{version_id}/test-plans/{plan_type}")
def save_test_plan(version_id: int, plan_type: str, req: TestPlanData):
    """保存/更新单个测试计划"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO test_plans (
            version_id, plan_type, device_name, test_items, plan_status,
            plan_start_date, plan_end_date, responsible_person, remark, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, plan_type, device_name) DO UPDATE SET
            test_items = excluded.test_items,
            plan_status = excluded.plan_status,
            plan_start_date = excluded.plan_start_date,
            plan_end_date = excluded.plan_end_date,
            responsible_person = excluded.responsible_person,
            remark = excluded.remark,
            updated_at = excluded.updated_at
    """, (
        version_id, plan_type, req.device_name, req.test_items, req.plan_status,
        req.plan_start_date, req.plan_end_date, req.responsible_person, req.remark, now_iso(),
    ))
    conn.commit()
    conn.close()
    return {"message": "测试计划已保存"}


@app.delete("/api/versions/{version_id}/test-plans/{plan_type}/{device_name}")
def delete_test_plan(version_id: int, plan_type: str, device_name: str):
    """删除单个测试计划"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM test_plans WHERE version_id = ? AND plan_type = ? AND device_name = ?",
                (version_id, plan_type, device_name))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"已删除计划: {device_name}", "deleted": deleted}


# ==============================
# 价值点验收 CRUD（手动输入 IR 验收结论）
# ==============================

class ValuePointData(BaseModel):
    value_name: str
    ir_conclusion: Optional[str] = "PASS"
    fail_reason: Optional[str] = ""
    test_owner: Optional[str] = ""


@app.get("/api/versions/{version_id}/value-points")
def get_value_points(version_id: int):
    """获取该版本所有价值点数据"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM value_points WHERE version_id = ? ORDER BY id", (version_id,))
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    # 计算统计
    total = len(rows)
    pass_count = sum(1 for r in rows if r.get("ir_conclusion") == "PASS")
    fail_count = sum(1 for r in rows if r.get("ir_conclusion") == "FAIL")
    fail_items = [r for r in rows if r.get("ir_conclusion") == "FAIL"]
    return {
        "items": rows,
        "stats": {
            "total": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round(pass_count / total * 100, 1) if total > 0 else 0,
            "fail_items": fail_items,
        }
    }


@app.post("/api/versions/{version_id}/value-points")
def save_value_point(version_id: int, req: ValuePointData):
    """保存/更新单个价值点"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO value_points (
            version_id, value_name, ir_conclusion, fail_reason, test_owner, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id, value_name) DO UPDATE SET
            ir_conclusion = excluded.ir_conclusion,
            fail_reason = excluded.fail_reason,
            test_owner = excluded.test_owner,
            updated_at = excluded.updated_at
    """, (
        version_id, req.value_name, req.ir_conclusion,
        req.fail_reason, req.test_owner, now_iso(),
    ))
    conn.commit()
    conn.close()
    return {"message": "价值点已保存"}


@app.delete("/api/versions/{version_id}/value-points/{value_id}")
def delete_value_point(version_id: int, value_id: int):
    """删除单个价值点"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM value_points WHERE version_id = ? AND id = ?", (version_id, value_id))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": "已删除价值点", "deleted": deleted}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "db": str(DB_PATH),
        "time": now_iso()
    }


@app.get("/api/config/defaults")
def get_defaults():
    """获取默认配置信息"""
    return {
        "jira_base_url": DEFAULT_JIRA_BASE_URL,
        "jira_project": "TOS",
        "all_status": sorted(list(ALL_KNOWN_STATUS)),
        "closed_status": sorted(list(CLOSED_STATUS))
    }


@app.post("/api/admin/reset-db")
def reset_database():
    """重置数据库（谨慎使用）"""
    import os
    if DB_PATH.exists():
        os.remove(DB_PATH)
    if KEY_PATH.exists():
        os.remove(KEY_PATH)
    init_db()
    return {"message": "数据库已重置", "db_path": str(DB_PATH)}


@app.get("/api/jira/global-credential")
def get_global_credential_status():
    cred = get_global_credential()
    if not cred or not cred["username"]:
        return {"configured": False, "username": "", "jira_base_url": DEFAULT_JIRA_BASE_URL}
    return {"configured": True, "username": cred["username"], "jira_base_url": cred["jira_base_url"]}


class GlobalCredentialSave(BaseModel):
    jira_base_url: str = DEFAULT_JIRA_BASE_URL
    username: str
    password: str


@app.post("/api/jira/global-credential")
def save_global_credential(req: GlobalCredentialSave):
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    set_global_credential(req.username, req.password, req.jira_base_url)
    return {"message": "全局 Jira 账号已保存"}


@app.get("/api/sync-progress")
def get_sync_progress():
    """查询当前同步进度"""
    return sync_progress


# ==============================
# 按周趋势分析
# ==============================
@app.get("/api/versions/{version_id}/trends")
def get_weekly_trends(version_id: int, stage: str = Query("ALL")):
    """按周聚合 issue 数据，返回每周的新增/关闭/净增/未关闭等趋势"""
    issues = load_issues(version_id, stage)
    if not issues:
        return {"weeks": [], "summary": {}}

    # 按周聚合
    from collections import defaultdict
    weekly = defaultdict(lambda: {"created": 0, "closed": 0, "high_created": 0, "high_closed": 0, "must_fix_open": 0})

    for i in issues:
        created = i.get("created_time")
        resolved = i.get("resolved_time")
        is_closed = i.get("status") in CLOSED_STATUS or bool(resolved)
        is_high = i.get("priority") in HIGH_PRIORITY

        if created:
            try:
                dt = parser.parse(created)
                week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                weekly[week_key]["created"] += 1
                if is_high:
                    weekly[week_key]["high_created"] += 1
            except Exception:
                pass

        if resolved:
            try:
                dt = parser.parse(resolved)
                week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                weekly[week_key]["closed"] += 1
                if is_high:
                    weekly[week_key]["high_closed"] += 1
            except Exception:
                pass

    # 排序并计算累计未关闭
    sorted_weeks = sorted(weekly.keys())
    result = []
    cumulative_open = 0
    for wk in sorted_weeks:
        d = weekly[wk]
        cumulative_open += d["created"] - d["closed"]
        result.append({
            "week": wk,
            "created": d["created"],
            "closed": d["closed"],
            "net": d["created"] - d["closed"],
            "cumulative_open": max(cumulative_open, 0),
            "high_created": d["high_created"],
            "high_closed": d["high_closed"],
        })

    # 总体汇总
    total_created = sum(w["created"] for w in result)
    total_closed = sum(w["closed"] for w in result)
    total_high = sum(1 for i in issues if i.get("priority") in HIGH_PRIORITY)
    total_must_fix = sum(1 for i in issues if i.get("must_fix_flag") == 1)

    return {
        "weeks": result,
        "summary": {
            "total": len(issues),
            "total_created": total_created,
            "total_closed": total_closed,
            "close_ratio": round(total_closed / total_created * 100, 1) if total_created else 0,
            "total_high": total_high,
            "total_must_fix": total_must_fix,
        }
    }


# ==============================
# AI 配置管理
# ==============================
class AIConfigSave(BaseModel):
    api_base: str = "https://hk-intra-paas.transsion.com/tranai-proxy/v1"
    api_key: Optional[str] = None
    model: str = "gpt-5.2-chat"
    user_no: Optional[str] = ""
    user_name: Optional[str] = ""
    user_dept: Optional[str] = ""
    sr_ai_prompt: Optional[str] = None


@app.get("/api/ai/config")
def get_ai_config():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_config WHERE id = 1")
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row:
        return {"api_base": "https://hk-intra-paas.transsion.com/tranai-proxy/v1", "api_key": "", "model": "gpt-5.2-chat",
                "user_no": "", "user_name": "", "user_dept": "", "sr_ai_prompt": ""}
    key = row.get("api_key", "")
    masked = (key[:8] + "***") if len(key) > 8 else ("***" if key else "")
    return {"api_base": row["api_base"], "api_key_masked": masked, "model": row["model"],
            "user_no": row.get("user_no", ""), "user_name": row.get("user_name", ""),
            "user_dept": row.get("user_dept", "AI创新部"),
            "sr_ai_prompt": row.get("sr_ai_prompt", "")}


@app.post("/api/ai/config")
def save_ai_config(req: AIConfigSave):
    conn = get_conn()
    cur = conn.cursor()
    encrypted_key = encrypt_text(req.api_key) if req.api_key else ""
    updates = ["api_base = ?", "model = ?", "user_no = ?", "user_name = ?", "user_dept = ?", "updated_at = ?"]
    vals = [req.api_base.rstrip("/"), req.model, req.user_no or "", req.user_name or "", req.user_dept or "", now_iso()]
    if req.api_key:
        updates.insert(1, "api_key = ?")
        vals.insert(1, encrypted_key)
    if req.sr_ai_prompt is not None:
        updates.append("sr_ai_prompt = ?")
        vals.append(req.sr_ai_prompt)
    vals.append(1)  # WHERE id = 1
    cur.execute(f"UPDATE ai_config SET {', '.join(updates)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    return {"message": "AI 配置已保存"}


def get_ai_config_decrypted():
    """获取解密后的 AI 配置"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_config WHERE id = 1")
    row = row_to_dict(cur.fetchone())
    conn.close()
    if not row or not row.get("api_key"):
        raise HTTPException(status_code=400, detail="请先配置 AI API Key")
    return {
        "api_base": row["api_base"],
        "api_key": decrypt_text(row["api_key"]),
        "model": row["model"],
        "user_no": row.get("user_no", ""),
        "user_name": row.get("user_name", ""),
        "user_dept": row.get("user_dept", "AI创新部"),
    }


def build_ai_context(version_id: int, stage: str) -> dict:
    """构建压缩的 AI 上下文数据"""
    version = get_version(version_id)
    issues = load_issues(version_id, stage)

    total = len(issues)
    closed = [i for i in issues if i["status"] in CLOSED_STATUS or i.get("resolved_time")]
    unresolved = [i for i in issues if i["status"] not in CLOSED_STATUS and not i.get("resolved_time")]
    high = [i for i in unresolved if i["priority"] in HIGH_PRIORITY]
    must_fix = [i for i in issues if i.get("must_fix_flag") == 1]
    must_fix_open = [i for i in must_fix if i["status"] not in CLOSED_STATUS]
    over14 = [i for i in unresolved if (i.get("aging_days") or 0) >= 14]
    over30 = [i for i in unresolved if (i.get("aging_days") or 0) >= 30]
    reopen = [i for i in issues if i["status"] in {"Reopened", "Reopen", "重新打开"}]

    # 模块风险
    module_map = {}
    for i in issues:
        m = i.get("module_name") or "未归类"
        module_map.setdefault(m, {"open": 0, "high": 0, "risk": 0})
        if i["status"] not in CLOSED_STATUS:
            module_map[m]["open"] += 1
        if i.get("priority") in HIGH_PRIORITY:
            module_map[m]["high"] += 1
        module_map[m]["risk"] = module_map[m]["high"] * 3 + module_map[m]["open"]
    top_modules = sorted(module_map.items(), key=lambda x: x[1]["risk"], reverse=True)[:5]

    # 负责人风险
    owner_map = {}
    for i in unresolved:
        a = i.get("assignee") or "未分配"
        owner_map.setdefault(a, {"open": 0, "a_grade": 0, "avg_aging": []})
        owner_map[a]["open"] += 1
        if i.get("grade") == "A":
            owner_map[a]["a_grade"] += 1
        if i.get("aging_days"):
            owner_map[a]["avg_aging"].append(i["aging_days"])
    top_owners = sorted(owner_map.items(), key=lambda x: x[1]["a_grade"] * 10 + x[1]["open"], reverse=True)[:5]

    # 高风险 issue（前10）
    high_risk = sorted(unresolved, key=lambda x: x.get("risk_score") or 0, reverse=True)[:10]

    return {
        "version": version["version_name"],
        "stage": stage,
        "metrics": {
            "total": total,
            "open": len(unresolved),
            "closed": len(closed),
            "a_grade": sum(1 for i in issues if i.get("grade") == "A"),
            "b_grade": sum(1 for i in issues if i.get("grade") == "B"),
            "must_fix_open": len(must_fix_open),
            "reopen": len(reopen),
            "over_14_days": len(over14),
            "over_30_days": len(over30),
            "close_ratio": round(len(closed) / total * 100, 1) if total else 0,
        },
        "top_modules": [{"module": m, **d} for m, d in top_modules],
        "top_owners": [{"owner": o, "open": d["open"], "a_grade": d["a_grade"],
                        "avg_aging": round(sum(d["avg_aging"]) / len(d["avg_aging"])) if d["avg_aging"] else 0}
                       for o, d in top_owners],
        "high_risk_issues": [
            {"key": i["issue_key"], "summary": i["summary"][:80], "status": i["status"],
             "priority": i["priority"], "grade": i.get("grade", ""), "aging_days": i.get("aging_days", 0),
             "risk_score": i.get("risk_score", 0)}
            for i in high_risk
        ],
    }


def call_ai(system_prompt: str, user_prompt: str) -> str:
    """调用 TranAI / OpenAI 兼容 API"""
    cfg = get_ai_config_decrypted()
    url = f"{cfg['api_base']}/chat/completions"

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
                "x-user-no": cfg.get("user_no", ""),
                "x-user-name": quote(cfg.get("user_name", "")),
                "x-user-dept-name": quote(cfg.get("user_dept", "")),
            },
            timeout=120,
        )
        if resp.status_code != 200:
            # 尝试从返回体提取错误信息（兼容非 UTF-8 响应）
            try:
                err_body = resp.json()
                err_msg = err_body.get("error", {}).get("message", "") or err_body.get("detail", "") or str(err_body)[:300]
            except Exception:
                try:
                    err_msg = resp.content.decode("utf-8", errors="replace")[:300]
                except Exception:
                    err_msg = f"(无法读取响应体，状态码 {resp.status_code})"
            raise HTTPException(status_code=502, detail=f"AI API 错误 ({resp.status_code}): {err_msg}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="AI API 请求超时（120秒）")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="无法连接 AI API 服务器")
    except HTTPException:
        raise
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"AI API 返回格式异常: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用异常: {str(e)[:200]}")


@app.post("/api/versions/{version_id}/ai/summary")
def ai_quality_summary(version_id: int, stage: str = Query("ALL")):
    """AI 质量报告总结"""
    ctx = build_ai_context(version_id, stage)
    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = """你是一位资深的软件测试质量分析专家。根据提供的 Jira Issue 数据，生成一份简洁、专业的质量总结报告。
要求：
1. 用中文回答
2. 结构清晰，使用编号列表
3. 重点关注风险、趋势、闭环效率
4. 给出具体可执行的建议
5. 控制在 500 字以内"""

    user_prompt = f"以下是当前版本/阶段的 Jira 质量数据：\n```json\n{ctx_json}\n```\n\n请生成质量总结报告。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx}


@app.post("/api/versions/{version_id}/ai/risk")
def ai_risk_analysis(version_id: int, stage: str = Query("ALL")):
    """AI 风险解读与行动建议"""
    ctx = build_ai_context(version_id, stage)
    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = """你是一位资深的软件测试质量分析专家。根据提供的 Jira Issue 数据，进行深度风险解读并给出行动建议。
输出格式要求：
一、主要风险（列出 3-5 个核心风险点）
二、建议优先级（P0/P1/P2 分级，给出具体 issue 编号和动作）
三、准出判断（当前阶段是否建议进入下一阶段，需要满足什么条件）
要求：用中文回答，具体到 issue 编号、负责人、天数，不要泛泛而谈。"""

    user_prompt = f"以下是当前版本/阶段的 Jira 质量数据：\n```json\n{ctx_json}\n```\n\n请进行风险解读并给出行动建议。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx}


@app.post("/api/versions/{version_id}/ai/weekly")
def ai_weekly_report(version_id: int, stage: str = Query("ALL")):
    """AI 周报生成"""
    ctx = build_ai_context(version_id, stage)
    week_info = {
        "year": datetime.now().isocalendar()[0],
        "week": datetime.now().isocalendar()[1],
    }

    ctx_json = json.dumps(ctx, ensure_ascii=False, indent=2)

    system_prompt = "你是一位专业的测试项目经理，负责撰写每周测试质量周报。根据提供的数据生成结构化周报，包含：1.本周概况 2.关键数据 3.风险预警 4.下周计划。用中文，800字以内。"

    user_prompt = f"当前是{week_info['year']}年第{week_info['week']}周。\n\nJira质量数据：\n{ctx_json}\n\n请生成本周质量周报。"

    result = call_ai(system_prompt, user_prompt)
    return {"summary": result, "context": ctx, "week": week_info}


@app.post("/api/admin/clear-cache")
def clear_cache():
    """清空 Jira 缓存数据和过期凭据（保留版本配置和阶段时间）"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM jira_issue_cache")
    cache_count = cur.fetchone()["c"]

    cur.execute("DELETE FROM jira_issue_cache")
    cur.execute("DELETE FROM analysis_snapshot")
    # 清除过期的凭据
    cur.execute(f"DELETE FROM jira_credential WHERE expire_at < '{now_iso()}'")

    conn.commit()
    conn.close()

    return {"message": f"已清空 {cache_count} 条缓存数据和过期凭据"}


# ==============================
# [13] 每日 SR 风险总结报告
# ==============================

OUTPUT_DIR = Path.home() / ".tos_quality_workbench" / "output"


def ensure_output_dir():
    """确保输出目录存在"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def collect_sr_risk_data(version_id: int) -> dict:
    """
    收集指定版本的 SR 风险相关数据，用于生成每日报告。
    返回结构化数据字典。
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. 版本信息
    cur.execute("SELECT * FROM version_config WHERE id = ?", (version_id,))
    version = row_to_dict(cur.fetchone())
    if not version:
        conn.close()
        return {"error": "版本不存在"}

    version_name = version.get("version_name", "")

    # 2. 当前阶段
    cur.execute("SELECT * FROM str_stage_config WHERE version_id = ? AND current_flag = 1", (version_id,))
    stage = row_to_dict(cur.fetchone())
    stage_name = stage.get("stage_name", "未设置") if stage else "未设置"

    # 3. SR 需求详情（来自 ALM）
    cur.execute("SELECT * FROM sr_detail_cache WHERE version_id = ? AND is_other_version = 0 ORDER BY issue_count DESC", (version_id,))
    sr_details = [row_to_dict(r) for r in cur.fetchall()]

    # 4. SR 遗留问题（来自 Jira 缓存）
    cur.execute("SELECT * FROM sr_issue_cache WHERE version_id = ? ORDER BY aging_days DESC", (version_id,))
    sr_issues = [row_to_dict(r) for r in cur.fetchall()]

    # 5. SR AI 风险等级分析
    cur.execute("SELECT * FROM sr_ai_priority WHERE version_id = ?", (version_id,))
    sr_ai_results = {}
    for r in cur.fetchall():
        rd = dict(r)
        sr_ai_results[rd["sr_coding"]] = {
            "risk_level": rd.get("risk_level", ""),
            "analysis": rd.get("analysis", ""),
            "issue_count": rd.get("issue_count", 0),
        }

    # 6. Jira Issue 缓存（用于统计）
    cur.execute("SELECT * FROM jira_issue_cache WHERE version_id = ?", (version_id,))
    all_issues = [row_to_dict(r) for r in cur.fetchall()]

    conn.close()

    # ---- 统计汇总 ----
    total_issues = len(all_issues)
    unresolved = [i for i in all_issues if i.get("status") not in CLOSED_STATUS]
    high_priority = [i for i in unresolved if i.get("priority") in HIGH_PRIORITY]
    must_fix = [i for i in unresolved if i.get("must_fix_flag")]

    # SR 维度统计
    total_sr = len(sr_details)
    high_risk_sr = [s for s in sr_details if sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level") == "high"]
    medium_risk_sr = [s for s in sr_details if sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level") == "medium"]
    low_risk_sr = [s for s in sr_details if s not in high_risk_sr and s not in medium_risk_sr]

    # SR 遗留问题统计
    sr_issue_total = len(sr_issues)
    sr_blocker = [i for i in sr_issues if i.get("priority") == "Blocker"]
    sr_critical = [i for i in sr_issues if i.get("priority") == "Critical"]
    sr_major = [i for i in sr_issues if i.get("priority") == "Major"]

    # 超龄 SR 问题（>14天）
    sr_over_14 = [i for i in sr_issues if (i.get("aging_days") or 0) > 14]
    sr_over_30 = [i for i in sr_issues if (i.get("aging_days") or 0) > 30]

    # 负责人维度统计
    owner_map = {}
    for issue in sr_issues:
        owner = issue.get("assignee") or "未分配"
        if owner not in owner_map:
            owner_map[owner] = {"total": 0, "blocker": 0, "critical": 0, "max_aging": 0}
        owner_map[owner]["total"] += 1
        if issue.get("priority") == "Blocker":
            owner_map[owner]["blocker"] += 1
        if issue.get("priority") == "Critical":
            owner_map[owner]["critical"] += 1
        owner_map[owner]["max_aging"] = max(owner_map[owner]["max_aging"], issue.get("aging_days") or 0)

    top_owners = sorted(owner_map.items(), key=lambda x: (-x[1]["blocker"], -x[1]["critical"], -x[1]["total"]))[:10]

    return {
        "version_name": version_name,
        "stage_name": stage_name,
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_sr": total_sr,
            "high_risk_sr_count": len(high_risk_sr),
            "medium_risk_sr_count": len(medium_risk_sr),
            "low_risk_sr_count": len(low_risk_sr),
            "sr_issue_total": sr_issue_total,
            "sr_blocker_count": len(sr_blocker),
            "sr_critical_count": len(sr_critical),
            "sr_major_count": len(sr_major),
            "sr_over_14_days": len(sr_over_14),
            "sr_over_30_days": len(sr_over_30),
            "total_issues": total_issues,
            "unresolved_count": len(unresolved),
            "high_priority_count": len(high_priority),
            "must_fix_count": len(must_fix),
        },
        "high_risk_sr": [
            {
                "coding": s.get("sr_coding", ""),
                "name": s.get("sr_name", ""),
                "status": s.get("sr_status", ""),
                "issue_count": s.get("issue_count", 0),
                "ai_risk_level": sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level", ""),
                "ai_analysis": sr_ai_results.get(s.get("sr_coding", ""), {}).get("analysis", ""),
            }
            for s in high_risk_sr
        ],
        "medium_risk_sr": [
            {
                "coding": s.get("sr_coding", ""),
                "name": s.get("sr_name", ""),
                "status": s.get("sr_status", ""),
                "issue_count": s.get("issue_count", 0),
                "ai_risk_level": sr_ai_results.get(s.get("sr_coding", ""), {}).get("risk_level", ""),
                "ai_analysis": sr_ai_results.get(s.get("sr_coding", ""), {}).get("analysis", ""),
            }
            for s in medium_risk_sr
        ],
        "sr_blocker_issues": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": i.get("summary", "")[:80],
                "status": i.get("status", ""),
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_blocker
        ],
        "sr_critical_issues": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": i.get("summary", "")[:80],
                "status": i.get("status", ""),
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_critical[:20]
        ],
        "sr_over_30_days": [
            {
                "issue_key": i.get("issue_key", ""),
                "summary": i.get("summary", "")[:80],
                "priority": i.get("priority", ""),
                "assignee": i.get("assignee", ""),
                "aging_days": i.get("aging_days", 0),
            }
            for i in sr_over_30[:20]
        ],
        "top_owners": [
            {"owner": o, **d}
            for o, d in top_owners
        ],
    }


def generate_sr_risk_report_text(data: dict) -> str:
    """将 SR 风险数据格式化为可读的 Markdown 报告文本"""
    s = data.get("summary", {})
    lines = []
    lines.append(f"# {data.get('version_name', '')} 每日 SR 风险总结报告")
    lines.append(f"")
    lines.append(f"**报告时间：** {data.get('report_time', '')}")
    lines.append(f"**当前阶段：** {data.get('stage_name', '')}")
    lines.append(f"")

    # ---- 整体概览 ----
    lines.append(f"## 一、整体概览")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| SR 需求总数 | {s.get('total_sr', 0)} |")
    lines.append(f"| 高风险 SR | {s.get('high_risk_sr_count', 0)} |")
    lines.append(f"| 中风险 SR | {s.get('medium_risk_sr_count', 0)} |")
    lines.append(f"| 低风险 SR | {s.get('low_risk_sr_count', 0)} |")
    lines.append(f"| SR 遗留问题总数 | {s.get('sr_issue_total', 0)} |")
    lines.append(f"| 其中 Blocker | {s.get('sr_blocker_count', 0)} |")
    lines.append(f"| 其中 Critical | {s.get('sr_critical_count', 0)} |")
    lines.append(f"| 其中 Major | {s.get('sr_major_count', 0)} |")
    lines.append(f"| 超龄 >14 天 | {s.get('sr_over_14_days', 0)} |")
    lines.append(f"| 超龄 >30 天 | {s.get('sr_over_30_days', 0)} |")
    lines.append(f"| Jira 总 Issue | {s.get('total_issues', 0)} |")
    lines.append(f"| 未关闭 Issue | {s.get('unresolved_count', 0)} |")
    lines.append(f"| 高优 Issue | {s.get('high_priority_count', 0)} |")
    lines.append(f"| 必解 Issue | {s.get('must_fix_count', 0)} |")
    lines.append(f"")

    # ---- 高风险 SR ----
    high_risk = data.get("high_risk_sr", [])
    if high_risk:
        lines.append(f"## 二、高风险 SR（{len(high_risk)} 个）")
        lines.append(f"")
        lines.append(f"| SR 编号 | SR 名称 | 状态 | 关联 Issue 数 | AI 分析 |")
        lines.append(f"|---------|---------|------|---------------|---------|")
        for sr in high_risk:
            analysis = (sr.get("ai_analysis") or "")[:60].replace("\n", " ")
            lines.append(f"| {sr.get('coding', '')} | {sr.get('name', '')[:30]} | {sr.get('status', '')} | {sr.get('issue_count', 0)} | {analysis} |")
        lines.append(f"")

    # ---- 中风险 SR ----
    medium_risk = data.get("medium_risk_sr", [])
    if medium_risk:
        lines.append(f"## 三、中风险 SR（{len(medium_risk)} 个）")
        lines.append(f"")
        lines.append(f"| SR 编号 | SR 名称 | 状态 | 关联 Issue 数 | AI 分析 |")
        lines.append(f"|---------|---------|------|---------------|---------|")
        for sr in medium_risk[:15]:
            analysis = (sr.get("ai_analysis") or "")[:60].replace("\n", " ")
            lines.append(f"| {sr.get('coding', '')} | {sr.get('name', '')[:30]} | {sr.get('status', '')} | {sr.get('issue_count', 0)} | {analysis} |")
        if len(medium_risk) > 15:
            lines.append(f"| ... | 共 {len(medium_risk)} 个，此处显示前 15 个 | | | |")
        lines.append(f"")

    # ---- Blocker 问题 ----
    blockers = data.get("sr_blocker_issues", [])
    if blockers:
        lines.append(f"## 四、Blocker 级 SR 遗留问题（{len(blockers)} 条）")
        lines.append(f"")
        lines.append(f"| Issue Key | 描述 | 状态 | 负责人 | 遗留天数 |")
        lines.append(f"|-----------|------|------|--------|----------|")
        for i in blockers:
            lines.append(f"| {i.get('issue_key', '')} | {i.get('summary', '')} | {i.get('status', '')} | {i.get('assignee', '')} | {i.get('aging_days', 0)} |")
        lines.append(f"")

    # ---- Critical 问题（Top） ----
    criticals = data.get("sr_critical_issues", [])
    if criticals:
        lines.append(f"## 五、Critical 级 SR 遗留问题（Top {len(criticals)} 条）")
        lines.append(f"")
        lines.append(f"| Issue Key | 描述 | 状态 | 负责人 | 遗留天数 |")
        lines.append(f"|-----------|------|------|--------|----------|")
        for i in criticals:
            lines.append(f"| {i.get('issue_key', '')} | {i.get('summary', '')} | {i.get('status', '')} | {i.get('assignee', '')} | {i.get('aging_days', 0)} |")
        lines.append(f"")

    # ---- 超龄问题 ----
    over30 = data.get("sr_over_30_days", [])
    if over30:
        lines.append(f"## 六、超龄 >30 天 SR 遗留问题（Top {len(over30)} 条）")
        lines.append(f"")
        lines.append(f"| Issue Key | 描述 | 优先级 | 负责人 | 遗留天数 |")
        lines.append(f"|-----------|------|--------|--------|----------|")
        for i in over30:
            lines.append(f"| {i.get('issue_key', '')} | {i.get('summary', '')} | {i.get('priority', '')} | {i.get('assignee', '')} | {i.get('aging_days', 0)} |")
        lines.append(f"")

    # ---- 负责人 Top ----
    owners = data.get("top_owners", [])
    if owners:
        lines.append(f"## 七、SR 遗留问题负责人 Top 10")
        lines.append(f"")
        lines.append(f"| 负责人 | 总数 | Blocker | Critical | 最长遗留天数 |")
        lines.append(f"|--------|------|---------|----------|-------------|")
        for o in owners:
            lines.append(f"| {o.get('owner', '')} | {o.get('total', 0)} | {o.get('blocker', 0)} | {o.get('critical', 0)} | {o.get('max_aging', 0)} |")
        lines.append(f"")

    return "\n".join(lines)


@app.get("/api/versions/{version_id}/sr-daily-risk-report")
def generate_sr_daily_risk_report(version_id: int, include_ai: bool = Query(True)):
    """
    生成每日 SR 风险总结报告。
    - 收集 SR 需求、遗留问题、AI 风险等级等数据
    - 生成结构化 Markdown 报告
    - 可选调用 AI 生成整体分析
    - 保存到 output 目录
    """
    # 收集数据
    data = collect_sr_risk_data(version_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])

    version_name = data.get("version_name", "unknown")
    report_date = datetime.now().strftime("%Y%m%d")
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 生成报告文本
    report_text = generate_sr_risk_report_text(data)

    # AI 整体分析
    ai_analysis = ""
    if include_ai:
        try:
            cfg = get_ai_config_decrypted()
            if cfg and cfg.get("api_key"):
                summary = data.get("summary", {})
                sr_data_brief = {
                    "version": version_name,
                    "stage": data.get("stage_name", ""),
                    "total_sr": summary.get("total_sr", 0),
                    "high_risk_sr": summary.get("high_risk_sr_count", 0),
                    "medium_risk_sr": summary.get("medium_risk_sr_count", 0),
                    "sr_issues_total": summary.get("sr_issue_total", 0),
                    "blocker": summary.get("sr_blocker_count", 0),
                    "critical": summary.get("sr_critical_count", 0),
                    "over_30_days": summary.get("sr_over_30_days", 0),
                    "high_risk_sr_details": data.get("high_risk_sr", []),
                    "blocker_issues": data.get("sr_blocker_issues", []),
                    "top_owners": data.get("top_owners", [])[:5],
                }

                system_prompt = """你是软件测试质量分析专家。根据提供的 SR 需求风险数据，输出一份简要的 AI 分析报告。
要求：
1. 用中文回答
2. 重点关注：高风险 SR 的影响面、Blocker 问题的紧急程度、超龄问题的根因
3. 给出 3-5 条具体可执行的行动建议
4. 给出整体风险评级（高/中/低）和判断依据
5. 控制在 500 字以内"""

                user_prompt = f"以下是 {version_name} 版本 {data.get('stage_name', '')} 阶段的 SR 风险数据：\n```json\n{json.dumps(sr_data_brief, ensure_ascii=False, indent=2)}\n```\n\n请生成 SR 风险 AI 分析报告。"

                ai_analysis = call_ai(system_prompt, user_prompt)
        except Exception as e:
            ai_analysis = f"（AI 分析生成失败：{str(e)[:100]}）"

    # 拼接完整报告
    full_report = report_text
    if ai_analysis:
        full_report += f"\n\n## 八、AI 整体风险分析\n\n{ai_analysis}\n"

    # 保存到文件
    ensure_output_dir()
    safe_version = re.sub(r'[^\w\-.]', '_', version_name)
    filename = f"sr_daily_risk_report_{safe_version}_{report_date}.md"
    json_filename = f"sr_daily_risk_report_{safe_version}_{report_date}.json"
    filepath = OUTPUT_DIR / filename
    json_filepath = OUTPUT_DIR / json_filename
    filepath.write_text(full_report, encoding="utf-8")

    # 同时保存结构化 JSON，方便前端直接加载今天的报告（无需重新生成）
    json_payload = {
        "report": full_report,
        "ai_analysis": ai_analysis,
        "data": data,
        "saved_to": str(filepath),
        "filename": filename,
        "generated_at": report_time,
    }
    json_filepath.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return json_payload


@app.get("/api/versions/{version_id}/sr-daily-risk-report/today")
def load_today_sr_daily_risk_report(version_id: int):
    """
    加载今天已生成的 SR 风险总结报告（从 JSON 缓存读取）。
    如果今天没有生成过，返回 404。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT version_name FROM version_config WHERE id = ?", (version_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")

    version_name = row["version_name"]
    safe_version = re.sub(r'[^\w\-.]', '_', version_name)
    report_date = datetime.now().strftime("%Y%m%d")
    json_filename = f"sr_daily_risk_report_{safe_version}_{report_date}.json"
    json_filepath = OUTPUT_DIR / json_filename

    if not json_filepath.exists():
        raise HTTPException(status_code=404, detail="今天尚未生成报告")

    try:
        payload = json.loads(json_filepath.read_text(encoding="utf-8"))
        payload["from_cache"] = True
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取报告缓存失败: {str(e)[:80]}")


@app.get("/api/output/reports")
def list_output_reports():
    """列出 output 目录中的所有报告文件"""
    ensure_output_dir()
    files = []
    for f in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"reports": files}


@app.get("/api/output/reports/{filename}")
def get_output_report(filename: str):
    """读取指定的报告文件内容"""
    filepath = OUTPUT_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    # 安全检查：只允许读取 output 目录下的文件
    try:
        filepath.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="禁止访问")
    content = filepath.read_text(encoding="utf-8")
    return {"filename": filename, "content": content}