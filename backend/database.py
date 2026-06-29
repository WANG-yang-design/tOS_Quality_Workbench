import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, date

# 支持直接运行和作为包导入两种方式
try:
    from .config import APP_DIR, DB_PATH
except ImportError:
    from config import APP_DIR, DB_PATH

def ensure_app_dir():
    """确保应用目录存在"""
    APP_DIR.mkdir(parents=True, exist_ok=True)

def get_conn():
    """获取数据库连接"""
    ensure_app_dir()
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def init_db():
    """初始化数据库表结构"""
    conn = get_conn()
    cur = conn.cursor()

    # 创建版本配置表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS version_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_name TEXT NOT NULL UNIQUE,
        jira_project TEXT,
        jira_fix_version TEXT,
        owner_name TEXT,
        is_train_version INTEGER DEFAULT 0,
        created_at TEXT,
        baseline_date TEXT,
        branch_name TEXT,
        device_count INTEGER DEFAULT 0,
        device_list TEXT,
        coverage_scope TEXT,
        project_status TEXT DEFAULT '进行中'
    )
    """)

    # 创建阶段配置表
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

    # 创建Jira凭据表
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

    # 创建Jira问题缓存表
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
        must_fix TEXT,
        severity TEXT,
        model TEXT,
        issue_category TEXT,
        frequency TEXT,
        module_category TEXT,
        project_code TEXT,
        os_version TEXT,
        android_version TEXT,
        grade TEXT,
        must_fix_flag INTEGER DEFAULT 0,
        aging_days INTEGER,
        stale_days INTEGER,
        risk_score INTEGER DEFAULT 0,
        UNIQUE(version_id, str_stage, issue_key)
    )
    """)

    # 创建分析快照表
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

    # 创建飞书配置表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feishu_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        app_id TEXT NOT NULL DEFAULT '',
        app_secret TEXT NOT NULL DEFAULT '',
        updated_at TEXT
    )
    """)
    cur.execute("INSERT OR IGNORE INTO feishu_config (id, app_id, app_secret, updated_at) VALUES (1, '', '', '')")

    # 创建AI配置表
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

    # 兼容旧表：补充缺失的列
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

    # 迁移：ai_config 新增 sr_ai_prompt 列
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

    # SR 需求详情缓存表
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
        issue_severity_count TEXT DEFAULT '{}',
        issue_severity_keys TEXT DEFAULT '{}',
        is_other_version INTEGER DEFAULT 0,
        other_version_reason TEXT,
        bid TEXT,
        third_dept TEXT,
        synced_at TEXT,
        UNIQUE(version_id, sr_coding)
    )
    """)

    # 兼容旧数据库：添加新字段
    try:
        cur.execute("ALTER TABLE sr_detail_cache ADD COLUMN issue_severity_count TEXT DEFAULT '{}'")
        conn.commit()
    except Exception:
        pass  # 字段已存在
    try:
        cur.execute("ALTER TABLE sr_detail_cache ADD COLUMN issue_severity_keys TEXT DEFAULT '{}'")
        conn.commit()
    except Exception:
        pass  # 字段已存在

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

    # 稳定性专项数据表
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
    cur.execute("SELECT uac_username FROM alm_config WHERE id = 1")
    alm_row = cur.fetchone()
    if alm_row:
        alm_username = (alm_row["uac_username"] or "").strip()
        if alm_username and not alm_username.isdigit():
            print(f"[迁移] ALM uac_username '{alm_username}' 是 Jira 域账号，不是 ALM 工号")
            print(f"[迁移] 清除无效的 ALM 凭据，请重新配置正确的工号")
            cur.execute("UPDATE alm_config SET uac_username='', encrypted_password='' WHERE id=1")
            # 同时清除可能存在的无效 token 缓存
            ALM_TOKEN_CACHE_PATH = APP_DIR / "alm_token_cache.json"
            if ALM_TOKEN_CACHE_PATH.exists():
                try:
                    ALM_TOKEN_CACHE_PATH.unlink()
                    print("[迁移] 已清除无效的 ALM token 缓存")
                except Exception:
                    pass

    # 测试计划表
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

    # 价值点验收表
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

    # Jira Filter Presets 表
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

    # UTP 待验证问题缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS utp_pending_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        issue_key TEXT NOT NULL,
        jira_url TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        status TEXT DEFAULT '',
        priority TEXT DEFAULT '',
        resolution TEXT DEFAULT '',
        assignee TEXT DEFAULT '',
        assignee_third_dept TEXT DEFAULT '',
        assignee_third_dept_classified TEXT DEFAULT '',
        assignee_second_dept TEXT DEFAULT '',
        reporter TEXT DEFAULT '',
        components TEXT DEFAULT '',
        affect_project TEXT DEFAULT '',
        aging_days INTEGER,
        created_time TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, issue_key)
    )
    """)

    # UTP Weekly 报告缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS utp_weekly_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        data_json TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, platform)
    )
    """)

    # Jira API 结果缓存表（避免每次切换版本都重新查询 Jira）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_issue_api_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        cache_key TEXT NOT NULL,
        data_json TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, cache_key)
    )
    """)

    # ALM 加锁 SR 数据缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alm_locked_sr_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        sr_coding TEXT NOT NULL,
        sr_name TEXT DEFAULT '',
        life_cycle_code TEXT DEFAULT '',
        life_cycle_name TEXT DEFAULT '',
        priority TEXT DEFAULT '',
        lock_flag TEXT DEFAULT '',
        space_bid TEXT DEFAULT '',
        test_representative TEXT DEFAULT '',
        person_responsible TEXT DEFAULT '',
        development_representative TEXT DEFAULT '',
        planned_transfer_test_time TEXT DEFAULT '',
        planned_acceptance_start_time TEXT DEFAULT '',
        actual_development_completion_time TEXT DEFAULT '',
        belong_domain TEXT DEFAULT '',
        tag TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, sr_coding)
    )
    """)
    # 迁移：确保 tag 列存在
    try:
        cur.execute("ALTER TABLE alm_locked_sr_cache ADD COLUMN tag TEXT DEFAULT ''")
    except Exception:
        pass

    # ALM 加锁 SR 统计快照表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alm_locked_sr_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        total_count INTEGER DEFAULT 0,
        status_json TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id)
    )
    """)

    # ALM 加锁 SR 每日快照表（用于跟踪每日新增/减少 SR 数量）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alm_locked_sr_daily_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        snapshot_date TEXT NOT NULL,
        total_count INTEGER DEFAULT 0,
        sr_codings_json TEXT DEFAULT '[]',
        created_at TEXT,
        UNIQUE(version_id, snapshot_date)
    )
    """)

    # 用户自定义风险项表（四、其他风险）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS custom_risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'medium',
        title TEXT NOT NULL DEFAULT '',
        description TEXT DEFAULT '',
        impact_scope TEXT DEFAULT '',
        owner TEXT DEFAULT '',
        plan_close_date TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 第二章 AI 综合总结缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chapter2_ai_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL DEFAULT '',
        summary_text TEXT DEFAULT '',
        generated_at TEXT,
        UNIQUE(version_id, stage_name)
    )
    """)

    # Agent 对话历史表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_conversations (
        id TEXT PRIMARY KEY,
        version_id INTEGER NOT NULL,
        title TEXT DEFAULT '',
        messages_json TEXT DEFAULT '[]',
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # Agent 任务执行记录表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT DEFAULT '',
        version_id INTEGER NOT NULL,
        user_message TEXT DEFAULT '',
        reply TEXT DEFAULT '',
        tool_calls_json TEXT DEFAULT '[]',
        steps INTEGER DEFAULT 0,
        status TEXT DEFAULT 'completed',
        created_at TEXT
    )
    """)

    # AI 数据分析缓存表（CycleTime + 健康地图 + AI 建议）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_analysis_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        analysis_type TEXT NOT NULL,
        data_json TEXT DEFAULT '',
        ai_suggestion TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, analysis_type)
    )
    """)

    # 全平台刷新配置表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS refresh_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER NOT NULL DEFAULT 1,
        interval_minutes INTEGER NOT NULL DEFAULT 30,
        work_start TEXT NOT NULL DEFAULT '09:30',
        work_end TEXT NOT NULL DEFAULT '18:30',
        weekdays TEXT NOT NULL DEFAULT '0,1,2,3,4',
        version_ids TEXT NOT NULL DEFAULT '',
        updated_at TEXT
    )
    """)
    cur.execute("INSERT OR IGNORE INTO refresh_config (id) VALUES (1)")

    # Jira 趋势分析缓存表（新老项目同期对比）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_trend_analysis_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        data_json TEXT DEFAULT '',
        ai_overall TEXT DEFAULT '',
        ai_submit TEXT DEFAULT '',
        ai_resolve TEXT DEFAULT '',
        generated_at TEXT,
        UNIQUE(version_id, stage_name)
    )
    """)

    # Jira 趋势分析 - 上一代版本统计数据缓存表（只存数量，不存完整 issue）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jira_trend_predecessor_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        cutoff_date TEXT,
        total_count INTEGER DEFAULT 0,
        closed_count INTEGER DEFAULT 0,
        open_count INTEGER DEFAULT 0,
        unresolved_count INTEGER DEFAULT 0,
        high_priority_count INTEGER DEFAULT 0,
        high_unresolved_count INTEGER DEFAULT 0,
        blocker_count INTEGER DEFAULT 0,
        must_fix_count INTEGER DEFAULT 0,
        must_fix_open_count INTEGER DEFAULT 0,
        avg_aging_days REAL DEFAULT 0,
        over14_count INTEGER DEFAULT 0,
        over30_count INTEGER DEFAULT 0,
        reopen_count INTEGER DEFAULT 0,
        close_rate REAL DEFAULT 0,
        module_stats_json TEXT DEFAULT '{}',
        severity_stats_json TEXT DEFAULT '{}',
        category_stats_json TEXT DEFAULT '{}',
        weekly_trends_json TEXT DEFAULT '[]',
        synced_at TEXT,
        UNIQUE(version_id, stage_name)
    )
    """)

    # 飞书智能体对话历史表（稳定性测试专家）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feishu_agent_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT DEFAULT '',
        agent_name TEXT DEFAULT '稳定性测试专家',
        created_at TEXT,
        version_id INTEGER
    )
    """)

    # 重点测试活动表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        activity_index INTEGER NOT NULL DEFAULT 0,
        activity_name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'unconfirmed',
        operator TEXT DEFAULT '',
        employee_id TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        updated_at TEXT,
        UNIQUE(version_id, stage_name, activity_index)
    )
    """)

    # 工时数据表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS work_hours (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        data_json TEXT DEFAULT '[]',
        ai_analysis TEXT DEFAULT '',
        imported_at TEXT,
        analyzed_at TEXT,
        UNIQUE(version_id)
    )
    """)

    # 重点测试活动 AI 风险分析缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_activity_ai_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        analysis_text TEXT DEFAULT '',
        generated_at TEXT,
        UNIQUE(version_id, stage_name)
    )
    """)

    # UTP SR 测试进度缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS utp_sr_progress_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        plan_name TEXT DEFAULT '',
        plan_code TEXT DEFAULT '',
        plan_status TEXT DEFAULT '',
        execute_schedule INTEGER DEFAULT 0,
        strategy_schedule INTEGER DEFAULT 0,
        sr_coding TEXT DEFAULT '',
        sr_name TEXT DEFAULT '',
        group_name TEXT DEFAULT '',
        owner_name TEXT DEFAULT '',
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, plan_id, sr_coding)
    )
    """)

    # UTP 测试计划进度缓存表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS utp_plan_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        plan_name TEXT DEFAULT '',
        plan_code TEXT DEFAULT '',
        plan_type TEXT DEFAULT '',
        plan_status TEXT DEFAULT '',
        test_stage TEXT DEFAULT '',
        level TEXT DEFAULT '',
        execute_schedule INTEGER DEFAULT 0,
        strategy_schedule INTEGER DEFAULT 0,
        cases_num INTEGER DEFAULT 0,
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        created_by_name TEXT DEFAULT '',
        created_by TEXT DEFAULT '',
        updated_by_name TEXT DEFAULT '',
        updated_time TEXT DEFAULT '',
        warning_status TEXT DEFAULT '',
        board_status TEXT DEFAULT '',
        synced_at TEXT,
        UNIQUE(version_id, plan_id)
    )
    """)

    # 迁移：version_config 新增 owner_code 列（负责人工号）
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN owner_code TEXT DEFAULT ''")
    except Exception:
        pass

    # 迁移：test_activities 新增 employee_id 列
    try:
        cur.execute("ALTER TABLE test_activities ADD COLUMN employee_id TEXT DEFAULT ''")
    except Exception:
        pass

    # 迁移：STA5 → 1+N版本火车（幂等：只有还存在 STA5 记录时才执行）
    cur.execute("SELECT COUNT(*) AS c FROM str_stage_config WHERE stage_name = 'STA5'")
    if cur.fetchone()["c"] > 0:
        # 先删已存在的空占位 1+N版本火车（避免 UNIQUE 冲突）
        cur.execute("""DELETE FROM str_stage_config
                       WHERE stage_name = '1+N版本火车'
                         AND (start_date = '' OR start_date IS NULL)
                         AND (end_date = '' OR end_date IS NULL)""")
        # 再改名
        cur.execute("UPDATE str_stage_config SET stage_name = '1+N版本火车' WHERE stage_name = 'STA5'")
        print(f"[迁移] 已将 {cur.rowcount} 条 STA5 阶段重命名为 1+N版本火车")
        cur.execute("UPDATE test_activities SET stage_name = '1+N版本火车' WHERE stage_name = 'STA5'")
        if cur.rowcount > 0:
            print(f"[迁移] 已将 {cur.rowcount} 条 STA5 活动重命名为 1+N版本火车")

    # 迁移：为已有版本补充缺失的阶段（概念启动、STR4A、1+N版本火车）
    cur.execute("SELECT id FROM version_config")
    all_version_ids = [r["id"] for r in cur.fetchall()]
    required_stages = ["概念启动", "STR4A", "1+N版本火车"]
    for vid in all_version_ids:
        for stage_name in required_stages:
            cur.execute(
                "SELECT id FROM str_stage_config WHERE version_id = ? AND stage_name = ?",
                (vid, stage_name),
            )
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO str_stage_config (version_id, stage_name, start_date, end_date, current_flag)
                       VALUES (?, ?, '', '', 0)""",
                    (vid, stage_name),
                )
                print(f"[迁移] 为版本 {vid} 补充阶段: {stage_name}")

    conn.commit()

    # 迁移：给 version_config 添加 ALM space/app bid 列
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
        # 版本配置种子数据
        seed_versions = [
            ("tOS16.2", "OS162", "OS162", "未配置", 0),
            ("tOS16.3", "TOS163", "TOS163", "未配置", 0),
            ("tOS17.0", "TOS170, LK7KOS17, X6878OS17", "TOS170", "未配置", 0),
        ]

        for v in seed_versions:
            cur.execute("""
            INSERT INTO version_config (
                version_name, jira_project, jira_fix_version, owner_name, is_train_version, created_at,
                baseline_date, branch_name, device_count, device_list, coverage_scope, project_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (*v, datetime.now().isoformat(timespec="seconds"), "", f"{v[0]}_release", 6, "", "手机+PAD", "进行中"))
            version_id = cur.lastrowid

            # 创建阶段：概念启动 + STR1-4 + STR4A + STR5 + 1+N版本火车
            today = date.today()
            stage_names = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"]
            for i, stage_name in enumerate(stage_names):
                start = today - timedelta(days=(len(stage_names) - 1 - i) * 7)
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
                    1 if stage_name == "STR3" else 0  # 默认选中STR3
                ))

    # 为所有版本播种默认 Jira Filter Presets（不覆盖用户自定义的 JQL）
    _seed_filter_presets(cur, force_update=False)

    # 迁移：version_config 新增 is_pad 列（PAD 版本需在 JQL 中加 summary ~ "PAD" 条件）
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN is_pad INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass

    # 迁移：version_config 新增 utp_owner_codes 列（UTP Weekly 报告创建人工号）
    try:
        cur.execute("ALTER TABLE version_config ADD COLUMN utp_owner_codes TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    conn.commit()

    # ---- 数据迁移：修正已有数据库中 16.3 / 17.0 的 Jira project key ----
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

    # 修正 tOS17.0 多项目配置
    cur.execute("""
        UPDATE version_config
        SET jira_project = 'TOS170, LK7KOS17, X6878OS17'
        WHERE version_name LIKE '%17%' AND jira_project = 'TOS170'
    """)
    if cur.rowcount > 0:
        print(f"[迁移] 已将 tOS17.0 jira_project 修正为多项目配置")

    conn.commit()
    conn.close()

# Jira Filter Presets 默认定义模板
# {project} = 完整的 jira_project（如 "TOS170, LK7KOS17, X6878OS17"）
# {primary_project} = 第一个项目（如 "TOS170"）
DEFAULT_JIRA_FILTERS = [
    {
        "filter_key": "main_sync",
        "label": "主数据同步 JQL",
        "description": "从 Jira 同步 issue 到本地数据库",
        "default_jql": 'project = {primary_project} AND issuetype in (Bug) ORDER BY updated DESC',
    },
    {
        "filter_key": "sr_backlog",
        "label": "SR 遗留问题 JQL",
        "description": "查询 SR 相关的高优遗留问题",
        "default_jql": 'project in ({project}) AND (summary ~ "SR*" or SR编号 is not empty) AND status not in (Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished) AND priority in (Blocker, Critical, Major) ORDER BY priority ASC, created DESC',
    },
    {
        "filter_key": "sr_blocking_test",
        "label": "SR 阻塞测试 JQL",
        "description": "查询 SR 遗留问题中阻塞测试的问题（labels=阻塞测试）",
        "default_jql": 'project in ({project}) AND (summary ~ "SR*" or SR编号 is not empty) AND status not in (Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished) AND priority in (Blocker, Critical, Major) AND labels = 阻塞测试 ORDER BY priority ASC, created DESC',
    },
    {
        "filter_key": "sr_blocker",
        "label": "SR Blocker JQL",
        "description": "查询 SR 遗留问题中 Blocker 级别的问题",
        "default_jql": 'project in ({project}) AND (summary ~ "SR*" or SR编号 is not empty) AND status not in (Closed, Resolved, Verified, Abandoned, Done, Fixed, Duplicated, Approved, Finished) AND priority = Blocker ORDER BY created DESC',
    },
    {
        "filter_key": "open_reopen",
        "label": "遗留问题 Open/Reopened JQL",
        "description": "查询 Open 和 Reopened 状态的遗留问题",
        "default_jql": 'project = {primary_project} AND status in (Open, Reopened) ORDER BY priority ASC, created DESC',
    },
    {
        "filter_key": "submitted_modifying",
        "label": "积压问题 Submitted/Modifying JQL",
        "description": "查询 Submitted 和 Modifying 状态的积压问题",
        "default_jql": 'project = {primary_project} AND status in (Submitted, Modifying) ORDER BY created ASC',
    },
    {
        "filter_key": "pending_verification",
        "label": "待验证问题 JQL",
        "description": "查询已解决/已验证但待最终确认的问题",
        "default_jql": 'project = {primary_project} AND issuetype in (Bug) AND status in (Resolved, Verified) AND (DupIssueStatus ~ Verified OR DupIssueStatus ~ resolved OR DupIssueStatus ~ closed or DupIssueStatus is EMPTY) ORDER BY updated DESC',
    },
]


def _resolve_jql_template(jql_template: str, jira_project: str) -> str:
    """将 JQL 模板中的占位符替换为实际值"""
    primary_project = jira_project.split(",")[0].strip() if jira_project else jira_project
    return jql_template.replace("{project}", jira_project).replace("{primary_project}", primary_project)


def _seed_filter_presets(cur, force_update: bool = False):
    """播种默认 Jira Filter Presets（使用完整的 JQL，不再需要动态替换）"""
    cur.execute("SELECT id, jira_project FROM version_config")
    versions = [(row["id"], row["jira_project"]) for row in cur.fetchall()]
    from .utils import now_iso
    for vid, jira_project in versions:
        for f in DEFAULT_JIRA_FILTERS:
            # 生成完整的默认 JQL（替换占位符）
            resolved_jql = _resolve_jql_template(f["default_jql"], jira_project or "")
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
                """, (vid, f["filter_key"], f["label"], f["description"], resolved_jql, now_iso()))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO jira_filter_preset
                        (version_id, filter_key, label, description, default_jql, custom_jql, updated_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                """, (vid, f["filter_key"], f["label"], f["description"], resolved_jql, now_iso()))