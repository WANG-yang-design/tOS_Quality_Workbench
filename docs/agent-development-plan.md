# tOS Quality Workbench — Agent 开发计划

> 版本：v1.0 | 日期：2026-06-18 | 状态：规划中

---

## 一、背景与目标

### 1.1 现状

tOS Quality Workbench 当前的 AI 使用方式是 **"一问一答"（one-shot）**：

```
用户点击按钮 → 后端构造 prompt → 调用 LLM → 返回文本 → 前端展示
```

这种方式存在以下局限：
- AI 无法主动感知数据变化，全靠人工触发
- AI 只能输出文本，无法执行操作（如同步数据、创建风险项）
- 每次调用独立，无跨会话记忆
- 无法处理多步骤的复杂任务

### 1.2 目标

引入 **Agent（智能体）** 架构，使 AI 具备：

| 能力 | 描述 | 当前状态 | 目标状态 |
|------|------|----------|----------|
| 感知（Perceive） | 持续观察数据源变化 | ❌ 手动刷新 | ✅ 自动监控 |
| 推理（Reason） | 根据数据做判断 | ⚠️ 一次性分析 | ✅ 多轮推理 |
| 行动（Act） | 调用工具/API 执行操作 | ❌ 只输出文本 | ✅ 可操作数据 |
| 记忆（Remember） | 跨会话保持上下文 | ❌ 无记忆 | ✅ 持久化记忆 |
| 规划（Plan） | 将复杂任务分解为多步 | ❌ 无 | ✅ 自动分解 |
| 自主循环（Loop） | 无需人工干预持续运行 | ❌ 无 | ✅ 定时/事件触发 |

### 1.3 Agent 定义

```
Agent = LLM（大脑） + Tools（手脚） + Memory（记忆） + Loop（循环）

在 tOS Quality Workbench 中：
  LLM    = TranAI Proxy（GPT-5.2 / DeepSeek / Gemini）
  Tools  = Jira / ALM / UTP / 飞书 API（已有 50+ 个端点）
  Memory = SQLite 数据库（已有完整数据模型）
  Loop   = 需新增的编排层（agent_engine.py）
```

---

## 二、平台已有基础设施分析

### 2.1 数据层（已具备）

| 数据源 | 数据内容 | 接口 |
|--------|----------|------|
| Jira | Issue 全量/增量数据、自定义字段、状态/优先级/模块/负责人 | `jira_service.py` → `jira_issue_cache` 表 |
| ALM | SR 需求详情、加锁 SR、测试主责人、三级部门 | `alm_service.py` → `sr_detail_cache` / `alm_locked_sr_cache` 表 |
| UTP | 待验证缺陷、Weekly 测试报告、A/B 类缺陷 | `utp_service.py` → `utp_pending_cache` / `utp_weekly_cache` 表 |
| 飞书 | STR 时间表、机型信息、性能/续航数据、OAuth | `feishu_service.py` |
| 本地 | 稳定性数据、价值点、自定义风险、AI 分析缓存 | SQLite 各业务表 |

### 2.2 工具层（已具备，但未被 Agent 调用）

平台已有 50+ 个 API 端点，覆盖：

**查询类**：
- `GET /jira-issues/{filter_key}` — 按 filter 查询 Jira 问题
- `GET /sr-detail-cached` — SR 需求详情
- `GET /alm-locked-srs` — ALM 加锁 SR
- `GET /stability` — 稳定性数据
- `GET /utp/weekly-reports` — UTP Weekly 报告
- `GET /analysis` — 风险分析报告
- `GET /trends` — 周趋势数据
- `GET /custom-risks` — 自定义风险项
- `GET /performance` / `/battery` — 性能/续航数据

**操作类**：
- `POST /sync` — 触发 Jira 同步
- `POST /custom-risks` — 添加风险项
- `DELETE /custom-risks/{id}` — 删除风险项
- `POST /sr-ai-priority` — AI 风险等级分析
- `POST /chapter2-ai-summary` — AI 综合分析

### 2.3 LLM 层（已具备）

- `call_ai(system_prompt, user_prompt)` — 单次调用
- 支持 GPT-5.2-chat、DeepSeek、Gemini 等多模型
- TranAI 代理统一鉴权（工号/姓名/部门）

### 2.4 缺失：Agent 编排层

需要新增的核心模块：

```
backend/
├── services/
│   ├── agent_engine.py      # Agent 核心循环（感知→推理→工具调用→回答）
│   ├── agent_tools.py       # 工具定义与执行器
│   └── agent_memory.py      # 记忆管理（短期/长期）
├── routers/
│   └── agent.py             # Agent API 端点
└── database.py              # 新增 agent_tasks / agent_memory 表
```

---

## 三、实施路线

### 第一阶段：对话式 Agent（预计 1-2 周）

**目标**：用户通过自然语言与 Agent 对话，Agent 能调用平台 API 获取数据并回答。

#### 3.1.1 后端：Agent 引擎

**新增文件**：`backend/services/agent_engine.py`

**核心逻辑**：

```python
def agent_chat(user_message: str, version_id: int, stage: str, 
               conversation_id: str = None) -> dict:
    """
    Agent 对话入口。
    
    流程：
    1. 加载对话历史（短期记忆）
    2. 构造 system prompt（含工具定义 + 平台上下文）
    3. 调用 LLM（function calling 模式）
    4. 如果 LLM 返回 tool_call → 执行工具 → 将结果加入对话 → 回到步骤 3
    5. 如果 LLM 返回文本 → 保存对话历史 → 返回给用户
    
    参数：
      user_message: 用户输入
      version_id: 当前版本 ID
      stage: 当前阶段（STR1-5 / STA5 / ALL）
      conversation_id: 对话 ID（用于多轮对话）
    
    返回：
      {
        "reply": "Agent 的回答文本",
        "conversation_id": "conv_xxx",
        "tool_calls": [{"tool": "...", "args": {...}, "result": "..."}],
        "steps": 3  # 推理步数
      }
    """
```

**Agent 循环实现**：

```python
MAX_STEPS = 8  # 防止死循环

def agent_run(messages: list, tools: list, version_id: int, stage: str) -> str:
    for step in range(MAX_STEPS):
        response = call_llm_with_tools(messages, tools)
        
        if not response.tool_calls:
            return response.content  # 最终回答
        
        for tc in response.tool_calls:
            result = execute_tool(tc.name, tc.arguments, version_id, stage)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False)
            })
    
    return "抱歉，分析步骤过多，请尝试更具体的问题。"
```

#### 3.1.2 后端：工具定义

**新增文件**：`backend/services/agent_tools.py`

每个工具定义为 JSON Schema，供 LLM 的 function calling 使用：

```python
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_jira_issues",
            "description": "查询当前版本/阶段的 Jira 问题列表。支持按状态、优先级、模块筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_key": {
                        "type": "string",
                        "enum": ["open_reopen", "submitted_modifying", "pending_verification", "main_sync"],
                        "description": "查询类型"
                    },
                    "status": {
                        "type": "string",
                        "description": "状态筛选，如 'Open', 'Blocker'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，默认 20"
                    }
                },
                "required": ["filter_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sr_details",
            "description": "获取 SR 需求详情列表，包含关联 Issue 数、测试主责人、计划验收时间等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low", "all"],
                        "description": "按风险等级筛选"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_locked_srs",
            "description": "获取 ALM 加锁 SR 统计和列表，包含各状态数量、今日/本周新增。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_risk_summary",
            "description": "获取综合风险分析报告，包含指标、风险模块、风险负责人等。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend_data",
            "description": "获取按周趋势数据，包含每周新增/关闭/净增/累计未关闭。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_utp_weekly",
            "description": "获取 UTP Weekly 测试报告，包含子领域 PASS/FAIL 统计、用例通过率。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["MTK", "Q", "展锐"],
                        "description": "平台筛选"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_custom_risks",
            "description": "获取用户自定义的风险项列表。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_custom_risk",
            "description": "添加一条自定义风险项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_level": {"type": "string", "enum": ["high", "medium", "low"]},
                    "title": {"type": "string", "description": "风险标题"},
                    "description": {"type": "string", "description": "风险描述"},
                    "owner": {"type": "string", "description": "负责人"},
                    "plan_close_date": {"type": "string", "description": "计划关闭日期 YYYY-MM-DD"}
                },
                "required": ["risk_level", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_jira_data",
            "description": "触发 Jira 数据同步（增量）。在数据可能过时时使用。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stability_data",
            "description": "获取稳定性专项数据（各机型 APR 指标）。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_performance_data",
            "description": "获取性能专项数据。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]
```

**工具执行器**：

```python
def execute_tool(name: str, args: dict, version_id: int, stage: str) -> dict:
    """根据工具名调用对应的平台 API（内部调用，不走 HTTP）"""
    if name == "query_jira_issues":
        filter_key = args.get("filter_key", "open_reopen")
        # 内部调用已有逻辑
        from ..routers.jira import get_jira_issues_by_filter
        return get_jira_issues_by_filter(version_id, filter_key, stage, limit=args.get("limit", 20))
    
    elif name == "get_sr_details":
        from ..routers.sr import load_sr_details_from_cache
        return load_sr_details_from_cache(version_id)
    
    elif name == "get_locked_srs":
        from ..routers.alm_locked_sr import _load_locked_srs_from_db
        return _load_locked_srs_from_db(version_id)
    
    # ... 其他工具
    
    return {"error": f"Unknown tool: {name}"}
```

#### 3.1.3 后端：记忆管理

**新增文件**：`backend/services/agent_memory.py`

```python
# 短期记忆：对话历史（保存最近 N 轮）
def load_conversation(conversation_id: str) -> list:
    """从数据库加载对话历史"""

def save_conversation(conversation_id: str, messages: list):
    """保存对话历史到数据库"""

# 长期记忆：关键事实（跨对话持久化）
def recall_facts(version_id: int) -> str:
    """召回与当前版本相关的关键事实"""

def save_fact(version_id: int, fact: str, source: str):
    """保存一条关键事实"""
```

**数据库新增表**：

```sql
-- 对话历史
CREATE TABLE agent_conversations (
    id TEXT PRIMARY KEY,           -- conversation_id (UUID)
    version_id INTEGER NOT NULL,
    messages_json TEXT DEFAULT '[]',  -- 完整消息历史 (JSON)
    created_at TEXT,
    updated_at TEXT
);

-- Agent 任务执行记录
CREATE TABLE agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,        -- 'chat' / 'scheduled' / 'alert'
    input TEXT DEFAULT '',
    output TEXT DEFAULT '',
    tool_calls_json TEXT DEFAULT '[]',
    steps INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed', -- 'running' / 'completed' / 'failed'
    created_at TEXT,
    completed_at TEXT
);

-- 长期记忆
CREATE TABLE agent_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    fact TEXT NOT NULL,              -- 关键事实描述
    source TEXT DEFAULT '',          -- 来源（如 'user_chat' / 'auto_analysis'）
    importance INTEGER DEFAULT 1,    -- 重要性 1-5
    created_at TEXT,
    expires_at TEXT                  -- 过期时间（可选）
);
```

#### 3.1.4 后端：API 端点

**新增文件**：`backend/routers/agent.py`

```python
@router.post("/api/agent/chat")
def agent_chat(req: AgentChatRequest):
    """
    Agent 对话入口。
    
    请求体：
    {
        "message": "当前有哪些 Blocker 没关闭？",
        "version_id": 3,
        "stage": "STR3",
        "conversation_id": "conv_xxx"  // 可选，续接对话
    }
    
    响应：
    {
        "reply": "当前有 5 个 Blocker 未关闭...",
        "conversation_id": "conv_xxx",
        "tool_calls": [...],
        "steps": 2
    }
    """

@router.get("/api/agent/conversations")
def list_conversations(version_id: int):
    """获取对话列表"""

@router.get("/api/agent/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """获取对话详情"""

@router.delete("/api/agent/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """删除对话"""
```

#### 3.1.5 前端：对话 UI

**新增组件**：`frontend/src/components/agent/AgentChat.tsx`

UI 方案：
- 页面右下角悬浮聊天按钮（与滚动按钮并列）
- 点击展开聊天面板（右侧抽屉或浮动窗口）
- 支持多轮对话，显示工具调用过程
- 对话历史列表（可切换/新建/删除）

```
┌─────────────────────────────┐
│ 🤖 tOS 智能助手        ─ ✕  │
├─────────────────────────────┤
│                             │
│ 👤 当前有哪些 Blocker？     │
│                             │
│ 🤖 正在查询 Jira 数据...    │
│    ⚙ 调用: query_jira_issues│
│                             │
│ 🤖 当前有 5 个 Blocker 未   │
│ 关闭：                      │
│ 1. TOS170-2954 性能问题     │
│ 2. LK7KOS17-60 续航功耗     │
│ ...                        │
│ 建议优先处理 TOS170-2954，   │
│ 该问题已遗留 10 天。         │
│                             │
├─────────────────────────────┤
│ [输入消息...]        [发送]  │
└─────────────────────────────┘
```

#### 3.1.6 Agent System Prompt 设计

```python
AGENT_SYSTEM_PROMPT = """你是 tOS 测试项目管理平台的 AI 智能助手。

你的能力：
1. 查询 Jira 问题数据（按状态/优先级/模块/负责人筛选）
2. 查询 SR 需求详情（ALM 平台数据）
3. 查询 UTP 测试报告（Weekly 报告、缺陷分析）
4. 查询稳定性/性能/续航专项数据
5. 分析风险趋势、生成报告
6. 添加/管理自定义风险项
7. 触发数据同步

当前上下文：
- 版本：{version_name}
- 阶段：{stage}
- Jira 项目：{jira_project}

工作原则：
- 先用工具查询数据，再基于数据回答，不要凭空猜测
- 回答简洁、有数据支撑、给出可执行建议
- 涉及具体问题时附上 Jira 编号（可跳转）
- 如果数据可能过时，主动提示用户是否需要同步
- 中文回答
"""
```

---

### 第二阶段：定时任务 Agent（预计 2-3 周）

**目标**：Agent 作为后台服务持续运行，主动监控、分析、通知。

#### 3.2.1 调度器

使用 APScheduler 实现定时任务：

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# 每天 09:00 晨检
scheduler.add_job(morning_check, 'cron', hour=9, minute=0)

# 每周五 17:00 周报
scheduler.add_job(weekly_report, 'cron', day_of_week='fri', hour=17)

# 每 30 分钟监控告警
scheduler.add_job(alert_monitor, 'interval', minutes=30)
```

#### 3.2.2 晨检 Agent

```
触发：每天 09:00
流程：
  1. 自动同步 Jira 最新数据
  2. 对比昨日快照，识别变化：
     - 新增 Blocker/Critical
     - 必解问题状态变化
     - SR 超龄预警
  3. 生成晨检摘要（AI 分析）
  4. 推送飞书群通知
```

#### 3.2.3 周报 Agent

```
触发：每周五 17:00
流程：
  1. 汇总本周数据：
     - 本周新增/关闭/净增问题
     - SR 需求交付进度
     - 测试模块通过率
     - 风险项变化
  2. AI 生成周报草稿
  3. 发送给负责人审批
```

#### 3.2.4 告警 Agent

```
触发：每 30 分钟
流程：
  1. 检查告警条件：
     - 新增 Blocker → 立即通知
     - SR 超龄 > 30 天 → 升级告警
     - 必解问题临近 deadline → 提前提醒
     - 某模块问题数突增 → 异常告警
  2. 告警去重（同一问题 24h 内不重复通知）
  3. 推送飞书/钉钉通知
```

#### 3.2.5 数据库新增表

```sql
-- 定时任务定义
CREATE TABLE agent_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,        -- 'morning_check' / 'weekly_report' / 'alert'
    cron_expr TEXT DEFAULT '',       -- cron 表达式
    enabled INTEGER DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    config_json TEXT DEFAULT '{}',   -- 任务配置
    created_at TEXT
);

-- 告警规则
CREATE TABLE agent_alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    rule_type TEXT NOT NULL,         -- 'new_blocker' / 'sr_overdue' / 'must_fix_deadline'
    condition_json TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    last_triggered_at TEXT,
    cooldown_hours INTEGER DEFAULT 24,
    notify_channel TEXT DEFAULT 'feishu',  -- 'feishu' / 'email'
    created_at TEXT
);

-- 告警历史
CREATE TABLE agent_alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    rule_id INTEGER,
    alert_type TEXT NOT NULL,
    message TEXT DEFAULT '',
    notified INTEGER DEFAULT 0,
    created_at TEXT
);
```

---

### 第三阶段：多 Agent 协作（预计 4-6 周）

**目标**：多个专业化 Agent 协同工作，共享记忆。

#### 3.3.1 Agent 角色定义

| Agent 名称 | 职责 | 触发方式 |
|------------|------|----------|
| **QA Agent** | 对话式问答，处理用户自然语言请求 | 用户对话 |
| **Monitor Agent** | 监控数据变化，触发告警 | 定时/事件 |
| **Report Agent** | 生成各类报告（日报/周报/准出报告） | 定时/手动 |
| **SR Agent** | 专注 SR 需求跟踪，风险预警 | 定时 |
| **Judge Agent** | 综合所有数据做准出决策 | 手动触发 |

#### 3.3.2 共享记忆

```python
# agent_memory 表存储跨 Agent 共享的关键事实
# 例如：
# - "tOS17.0 STR3 阶段 Blocker 数量从 3 增长到 7（2026-06-15 ~ 06-18）"
# - "SR-202605-001234 已超龄 35 天，负责人张三未响应"
# - "MTK 平台稳定性子领域 FAIL，原因：GPU 压力测试 KE"
```

#### 3.3.3 Agent 间通信

```
Monitor Agent 检测到新增 Blocker
    → 写入 agent_memory（关键事实）
    → 触发 QA Agent 更新上下文
    → 触发 Report Agent 更新日报

SR Agent 检测到 SR 超龄
    → 写入 agent_memory
    → 触发告警通知
    → Judge Agent 在准出评估时参考此事实
```

---

## 四、技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| LLM | TranAI Proxy (OpenAI 兼容) | 已有接入，支持 function calling |
| Function Calling | OpenAI tool_calls 协议 | 行业标准，TranAI 兼容 |
| 定时调度 | APScheduler | 轻量，与 FastAPI 集成好 |
| 对话存储 | SQLite（复用现有数据库） | 零运维，与平台一致 |
| 前端聊天 UI | 自定义 React 组件 | 与平台风格统一 |
| 飞书通知 | 飞书机器人 Webhook | 已有飞书 OAuth 集成 |

---

## 五、文件结构规划

```
backend/
├── services/
│   ├── ai_service.py          # 已有：基础 LLM 调用
│   ├── agent_engine.py        # 新增：Agent 核心循环
│   ├── agent_tools.py         # 新增：工具定义与执行器
│   └── agent_memory.py        # 新增：记忆管理
├── routers/
│   ├── ai.py                  # 已有：基础 AI 端点
│   └── agent.py               # 新增：Agent 端点
└── database.py                # 修改：新增 agent_* 表

frontend/src/
├── components/
│   └── agent/
│       ├── AgentChat.tsx       # 新增：对话面板
│       ├── AgentMessage.tsx    # 新增：消息气泡（含工具调用展示）
│       └── AgentHistory.tsx    # 新增：对话历史列表
└── App.tsx                     # 修改：集成 Agent 入口
```

---

## 六、验收标准

### 第一阶段验收

- [ ] 用户可在前端聊天面板输入自然语言问题
- [ ] Agent 能调用至少 5 种工具查询平台数据
- [ ] Agent 回答有数据支撑，附 Jira 编号可跳转
- [ ] 支持多轮对话（上下文保持）
- [ ] 工具调用过程可视化展示
- [ ] 对话历史可查看/删除

### 第二阶段验收

- [ ] 晨检 Agent 每日自动执行，生成摘要
- [ ] 告警 Agent 在新增 Blocker 时推送飞书通知
- [ ] 周报 Agent 每周五自动生成草稿
- [ ] 定时任务可在前端配置开关

### 第三阶段验收

- [ ] 至少 3 个专业化 Agent 协同工作
- [ ] Agent 间共享记忆，信息不丢失
- [ ] 准出判断 Agent 综合所有数据给出决策建议

---

## 七、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| LLM function calling 不稳定 | Agent 可能误调工具 | 添加工具调用校验 + 重试机制 |
| API 调用频率限制 | Agent 循环调用过多 | 设置 MAX_STEPS 上限 + 工具调用冷却 |
| 数据量大导致 token 超限 | 对话历史过长 | 自动压缩旧对话 + 摘要替代 |
| TranAI 代理不稳定 | Agent 不可用 | 本地缓存 + 降级为普通 AI 模式 |
| 定时任务占用资源 | 影响平台响应 | 后台线程 + 任务队列 |

---

## 八、里程碑

| 里程碑 | 内容 | 预计时间 |
|--------|------|----------|
| M1 | 对话式 Agent 后端（engine + tools + memory） | 第 1 周 |
| M2 | 对话式 Agent 前端（聊天 UI） | 第 2 周 |
| M3 | 定时任务调度器 + 晨检 Agent | 第 3 周 |
| M4 | 告警 Agent + 飞书通知 | 第 4 周 |
| M5 | 周报 Agent | 第 5 周 |
| M6 | 多 Agent 协作框架 | 第 6-8 周 |