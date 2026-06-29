# tOS Quality Workbench

> tOS 系统测试项目跟踪与管理工作台 — 一站式测试质量管理平台

## 项目简介

tOS Quality Workbench 是一款面向 tOS 系统测试团队的本地化质量管理工具，集成 Jira 数据同步、ALM SR 管理、UTP 测试平台、飞书智能体对话、AI 智能分析等功能。支持同时管理多个 tOS 版本，每个版本独立配置阶段时间表，自动识别当前阶段并生成对应的质量报告。

## 项目进展文档

本项目进展记录、需求说明、部署说明等内容详见飞书文档：

- 进展文档：https://transsioner.feishu.cn/wiki/XcbgwSqEyi0xbZk9Tk5cvrCInMe
---

## 核心功能

### 1. 多版本多阶段管理
- 同时管理 tOS16.2 / tOS16.3 / tOS17.0 等多个系统版本
- 每个版本配置 8 个阶段：概念启动、STR1-STR5、STR4A、1+N版本火车
- 自动识别当前阶段，支持阶段倒计时显示
- 版本切换时主题色联动

### 2. Jira 数据同步与分析
- 全量/增量同步 Jira Issue 数据
- 多维度分析：模块分布、优先级分布、状态分布、负责人分布
- 周趋势分析：新增/关闭/净增/累计未关闭
- Jira 趋势分析：新老项目同期对比，AI 趋势预测

### 3. SR 需求管理（ALM 集成）
- ALM 加锁 SR 统计与状态分布
- SR 测试进度跟踪（UTP 集成）
- SR 风险等级 AI 分析
- 每日 SR 风险报告生成

### 4. UTP 测试平台集成
- UTP Weekly 测试报告查看
- UTP 测试计划进度跟踪
- 待验证问题分析（按部门分布）
- A/B 类缺陷详情

### 5. 飞书智能体集成（稳定性测试专家）
- 内嵌式对话窗口，随时向稳定性测试专家提问
- 对话历史按版本隔离保存
- 对话数据用于 AI 风险分析
- 自动复用 ALM 配置的用户凭据

### 6. AI 智能分析
- **第二章 AI 综合分析**：综合 SR、Jira、测试活动、稳定性数据的风险总结
- **Bug 修复效能分析**：CycleTime 模块对比，异常模块识别
- **健康地图**：模块风险等级评估
- **趋势预测**：收敛性分析与风险预警
- **周报生成**：一键生成包含全部数据的周报

### 7. 重点测试活动管理
- 按阶段配置测试活动
- 活动状态跟踪（Pass/Fail/未确认）
- AI 风险分析

### 8. 工时管理
- 工时数据导入（JSON/CSV/TSV）
- 工时分布统计
- AI 工时分析建议

### 9. 专项测试数据
- **稳定性专项**：APR 数据录入 + 飞书智能体对话
- **性能专项**：飞书表格数据读取
- **续航温升**：飞书表格数据读取
- **价值点验收**：IR 结论跟踪

### 10. 数据导出
- 所有表格和弹窗支持导出 Excel
- Issue 链接可跳转 Jira
- SR 列表按 AI 风险等级排序导出

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite |
| 后端 | FastAPI + Python 3.10+ |
| 数据库 | SQLite3 |
| AI | TranAI 代理（OpenAI 兼容） |
| 飞书 | 飞书开放平台 API + OAuth |
| ALM | ALM REST API（RSA 鉴权） |
| UTP | UTP REST API |
| 智能体 | 飞书/传音智库 WebSocket API |

---

## 项目结构

`
tos-quality-workbench/
├── start.bat                          # 一键启动
├── stop.bat                           # 一键停止
├── README.md                          # 本文档
├── backend/
│   ├── app.py                         # FastAPI 应用入口
│   ├── database.py                    # 数据库初始化
│   ├── config.py                      # 配置常量
│   ├── encryption.py                  # 加密工具
│   ├── utils.py                       # 工具函数
│   ├── run.py                         # 启动脚本
│   ├── requirements.txt               # Python 依赖
│   ├── routers/                       # API 路由
│   │   ├── versions.py                # 版本管理
│   │   ├── stages.py                  # 阶段管理
│   │   ├── jira.py                    # Jira 同步
│   │   ├── analysis.py                # 数据分析
│   │   ├── alm_locked_sr.py           # ALM SR 管理
│   │   ├── sr_progress.py             # SR 测试进度
│   │   ├── utp_weekly.py              # UTP Weekly
│   │   ├── utp_plan_progress.py       # UTP 测试计划
│   │   ├── trend_analysis.py          # Jira 趋势分析
│   │   ├── test_activities.py         # 测试活动
│   │   ├── custom_risks.py            # 自定义风险 + AI 综合分析
│   │   ├── agent.py                   # AI 助手
│   │   ├── feishu_agent.py            # 飞书智能体
│   │   └── ...
│   ├── services/
│   │   ├── jira_service.py            # Jira API 服务
│   │   ├── alm_service.py             # ALM API 服务
│   │   ├── utp_service.py             # UTP API 服务
│   │   ├── ai_service.py              # AI API 服务
│   │   ├── feishu_agent_service.py    # 飞书智能体服务
│   │   ├── trend_analysis_service.py  # 趋势分析服务
│   │   ├── agent_engine.py            # AI 助手引擎
│   │   ├── agent_tools.py             # AI 助手工具集
│   │   └── ...
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── refactored/                # 重构版前端
│   │   │   ├── AppRefactored.tsx      # 主应用
│   │   │   ├── sections/              # 页面板块
│   │   │   │   ├── StabilitySpecial.tsx   # 稳定性专项（含飞书智能体）
│   │   │   │   ├── JiraTrendAnalysis.tsx  # Jira 趋势分析
│   │   │   │   ├── risk/              # 风险分析板块
│   │   │   │   └── ...
│   │   │   ├── components/            # 通用组件
│   │   │   └── utils/                 # 工具函数
│   │   └── components/
│   │       └── agent/                 # AI 助手组件
│   └── package.json
└── docs/                              # 文档目录
`

---

## 快速启动

### 方式一：一键启动（推荐）
`cmd
start.bat
`

### 方式二：手动启动

**后端：**
`cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
`

**前端：**
`cmd
cd frontend
npm install
npm run dev
`

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

---

## 配置说明

### 1. Jira 配置
- 顶栏 ⚙️ 设置 → Jira Tab
- 配置全局 Jira 账号密码（一次配置，所有版本通用）

### 2. ALM 配置
- 顶栏 ⚙️ 设置 → ALM Tab
- 配置用户中心网关、App ID、工号、密码
- 每个版本独立配置 SPACE_BID 和 APP_BID

### 3. AI 配置
- 顶栏 ⚙️ 设置 → AI Tab
- 配置 TranAI API 地址和 Key
- 支持自定义 SR 风险分析 Prompt 模板

### 4. 飞书配置
- 顶栏 ⚙️ 设置 → 飞书 Tab
- 配置飞书应用 App ID 和 Secret
- 配置各版本的管理书/性能表/续航表 URL

---

## 数据存储

所有数据存储在用户目录下：
`
%USERPROFILE%/.tos_quality_workbench/
├── tos_quality.db           # SQLite 数据库
├── secret.key               # 加密密钥
└── feishu_agent_token_cache.json  # 飞书智能体 token 缓存
`

---

## 主要 API 接口

### 版本管理
- GET /api/versions - 获取版本列表
- POST /api/versions - 创建版本

### 数据同步
- POST /api/auto-refresh - 全量刷新数据
- GET /api/auto-refresh/status - 刷新状态

### AI 分析
- POST /api/versions/{id}/chapter2-ai-summary - 第二章 AI 综合分析
- GET /api/versions/{id}/ai/cycle-time - Bug 修复效能分析
- GET /api/versions/{id}/ai/health-map - 健康地图

### 飞书智能体
- POST /api/feishu-agent/ask - 向稳定性测试专家提问
- GET /api/feishu-agent/history - 获取对话历史

### AI 助手
- POST /api/agent/chat - AI 助手对话
- POST /api/agent/weekly-report - 生成周报

---

## 环境要求

- Python 3.10+
- Node.js 18+
- 网络：需能访问 Jira、ALM、UTP、飞书等平台

---

## 更新日志

### 2026-06-26

#### Jira Filter 系统重构

**核心改动：**
- 彻底重构 JQL 逻辑，删除所有动态修改 JQL 的代码
- Filter JQL 在创建版本时一次性生成完整值（替换占位符），保存到数据库
- 前端修改 Filter 后直接保存到数据库，后端直接使用数据库中的 JQL
- 修改 Filter 后自动清除所有相关缓存，确保下次查询使用新 JQL
- 支持"还原默认"功能，恢复系统生成的完整 JQL

**修复问题：**
- 修复 Filter 修改后刷新页面 JQL 变回原值的问题
- 修复后端查询时未使用用户自定义 JQL 的问题
- 修复缓存未清除导致数据不更新的问题

#### SR 需求详情增强

**新增功能：**
- 每个 SR 显示 A/B/C 类 issue 数量（Blocker/Critical/Major）
- 点击 A/B/C 数字可查看对应等级的具体 issue 列表
- 从 Jira 批量查询 issue 的 severity 信息
- 后端返回 `issue_severity_count` 和 `issue_severity_keys` 字段

**排序优化：**
- 保留 AI 风险等级和计划验收紧迫度两种排序方式
- 删除 DI 风险值和 issue 数量排序
- 计划验收紧迫度显示距离评审节点的倒计时（已逾期X天/还有X天/今天到期）

#### 测试计划进度优化

- 修复"待下发"数量统计错误（排除失效状态的计划）
- 新增"失效"状态统计显示
- 添加同步时间戳显示

#### 界面优化

- 删除重点测试活动和工时情况的独立 AI 分析模块
- 删除"四、其他风险"自定义风险模块
- 删除重点测试活动的操作人功能（姓名/工号输入框）
- 添加响应式布局支持（平板/手机适配）

#### 代码清理

- 删除重构前的旧代码文件（App.tsx、App.tsx.bak 等）
- 删除旧的 sections/hooks/utils/types/constants 目录
- 删除旧的 components/charts/common/layout/modals 目录
- 删除 index-refactored.html、main-refactored.tsx、vite.refactored.config.ts

#### Git 仓库初始化

- 安装 Git 2.54.0
- 初始化本地仓库，创建 `main` 和 `dev` 分支
- 推送到远程仓库：`ssh://git@gitlab.transsion.com:29418/AI_Tree/tos_test_workbench.git`

---

### 2026-06-25

#### 飞书智能体集成（稳定性测试专家）

**核心功能：**
- 新增稳定性测试专家对话模块，内嵌在稳定性专项下方
- 自动复用 ALM 配置的用户凭据，无需额外配置
- 对话历史按版本隔离保存，切换版本自动清空当前对话
- 对话数据用于第二章 AI 综合分析
- 数据库新增 `feishu_agent_conversations` 表

**交互优化：**
- 新增「✚ 新建对话」按钮，可随时开始新对话
- 历史记录支持单条删除和一键清空
- 自动清理超过 2 周的历史数据
- 相同问题重复提问时，自动更新回答（不重复保存）
- 修复滚动穿透问题，聊天区域滚动不会影响页面滚动

#### AI 助手功能增强

**新增能力（25 项）：**
- 数据查询（14 项）：Jira 问题、SR 详情、UTP 报告、测试活动、工时数据等
- 数据刷新（4 项）：刷新 Jira/SR/UTP/全部数据
- 数据导出（4 项）：导出问题列表、SR 列表、周报、**自定义导出**
- 数据操作（3 项）：添加/删除风险项、更新测试活动状态

**自定义导出功能（新增）：**
- 新增 `export_custom_data` 工具，支持导出任意筛选后的数据
- 使用流程：查询数据 → 筛选 → 调用工具导出
- 支持场景：导出中风险SR、导出超龄问题、导出特定模块问题等
- 导出文件自动下载，同时在聊天窗口显示下载按钮

**导出功能优化：**
- 修复导出文件无法下载的问题，新增 `/api/agent/export/{filename}` 下载接口
- 导出后自动触发文件下载
- 聊天消息中的链接自动渲染为可点击的超链接

**查询限制优化：**
- 查询工具返回数量限制增加：Jira 问题 200 条、SR 详情 200 条、UTP 计划 100 条
- 工具结果截断限制增加：查询类工具 15000 字符（原 4000）
- 更新系统提示词，明确自定义导出的正确流程

#### Jira 趋势分析优化
- 上一代版本统计数据缓存到数据库，加快加载速度
- 显示数据更新时间和数据来源
- 数据库新增 `jira_trend_predecessor_stats` 表

#### 测试计划进度优化
- 显示刷新时间

#### 待验证问题分析优化
- 新增部门分布导出按钮
- 新增问题明细导出按钮
- 部门分布表格显示可跳转的 Issue 单号

#### 第二章 AI 综合分析增强
- 新增稳定性测试专家对话数据作为输入
- 新增 Blocker/Critical 问题统计
- 新增超龄问题统计
- 新增测试活动数据
- AI 提示词优化，增加稳定性数据分析要求

#### Git 部署支持（新增）
- 新增 `.gitignore` 文件，排除敏感文件和依赖
- 新增 `docs/DEPLOYMENT.md` 部署指南
- 更新 README.md，精简文档结构

#### 数据库自动初始化
- 首次启动自动创建数据库目录和文件
- 自动创建所有数据表（20+ 张表）
- 用户配置自动保存到服务器数据库

---

### 2026-06-24

#### 阶段体系扩展：新增「概念启动」和「STR4A」

- 阶段顺序变更为：`概念启动 → STR1 → STR2 → STR3 → STR4 → STR4A → STR5 → 1+N版本火车`
- `STA5` 全量更名为 `1+N版本火车`（数据库迁移自动执行）
- 新建版本自动创建全部 8 个阶段
- 已有版本启动时自动补充缺失的阶段记录

#### 重点测试活动（全新实现）

- **后端** `routers/test_activities.py`：按阶段定义活动配置，CRUD 接口 + AI 风险分析
- **前端** `TestActivity.tsx`：默认只读展示，点击「✏ 修改」按钮展开编辑行
- **数据库**：新增 `test_activities` 表、`test_activity_ai_analysis` 表

#### 工时管理（全新实现）

- **后端**：支持 JSON/CSV/TSV 导入 + AI 工时分析
- **前端** `Workload.tsx`：文件上传/粘贴导入、统计卡片、AI 分析区域
- **数据库**：新增 `work_hours` 表

#### SR 测试进度（UTP，新增）

- 从 UTP 拉取需求任务计划，提取 SR 编号，与本地"测试中"SR 匹配展示进度
- **前端** `SrTestProgress.tsx`：默认展示 10 条 + 查看全部弹窗

#### 三、进度风险（UTP 测试计划，全新实现）

- 从 UTP `queryPlanList` 接口按版本名搜索
- **前端** `UtpPlanProgress.tsx`：统计卡片、计划表格、进度条
- **数据库**：新增 `utp_plan_cache` 表

#### Jira 趋势分析修复

- 对齐方式改为阶段开始日期对齐
- Tooltip 改用 SVG `foreignObject`
- 图表放大：viewBox 900×340

---

### 2026-06-23

#### 前端代码重构（模块化拆分）

**目标**：将 `App.tsx`（5920 行单文件）拆分为模块化结构，零样式变更、零功能变更。

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| 主文件 | `App.tsx` 5920 行 | `AppRefactored.tsx` 391 行（缩减 93%） |
| 文件总数 | 1 个主文件 | 47 个模块文件 |

#### 数据导出功能（新增）

所有弹窗和明细表格增加「📥 导出 Excel」按钮，Issue 链接可跳转 Jira。

#### Bug 修复效能分析优化

- 异常判定改为与上个 tOS 版本同模块对比（> 1.5x 且 ≥3 个 Issue）
- 弹窗新增全部/异常/正常 Tab 切换

#### 阶段倒计时（新增）

顶部栏显示当前阶段到截止日期的剩余时间。

---

### 2026-06-22

#### Jira 趋势分析 — 新老项目同期对比（新增）

- 自动找到上一代版本，排除 PAD 版本
- 上一代数据直接从 Jira 查询
- 三 Tab 切换：整体趋势 / 提交板块 / 解决板块
- AI 趋势分析（3 段独立分析）
- 数据库新增 `jira_trend_analysis_cache` 表

#### 全平台数据刷新系统（新增）

- 后台调度器，可配置工作时间/间隔/工作日
- 刷新内容：Jira + SR + UTP + ALM
- 数据库新增 `refresh_config` 表

---

### 2026-06-18

#### UTP Weekly A/B 类缺陷提取流程修复

修复使用错误 ID 查询的问题，正确流程：plan_id → report.id → 缺陷列表

#### SR 数量展示"今日新增"bug 修复

改用 UPSERT + 每日快照表精确计算新增数量。

---

### 2026-06-16

#### 后端模块化重构修复

- CSS 样式修复
- Jira Filter Presets 播种
- 全局 Jira 凭据修复
- SR 遗留问题/需求详情完整移植

#### UTP 平台集成（新增）

- UTP 待验证问题查询
- 部门归类规则
- 数据库新增 `utp_pending_cache` 表

#### AI 数据分析小模块（新增）

- Bug 修复效能分析（CycleTime）
- 健康地图
- 数据库新增 `ai_analysis_cache` 表

---

### 2026-06-15

#### Jira Filter 可编辑系统（新增）

- 数据库新增 `jira_filter_preset` 表
- 5 个默认 Filter：main_sync / sr_backlog / open_reopen / submitted_modifying / pending_verification

#### 遗留问题 Open/Reopened 分析

替换原占位，实现完整分析功能。

#### 积压问题 Submitted/Modifying 分析

替换原占位，实现完整分析功能。

---

### 2026-06-12

#### 机型信息读取逻辑重构

完全重写飞书管理书机型提取算法。

#### SR 需求详情交互增强

- SR 编号跳转 ALM
- Issue 数量弹窗

---

### 2026-06-11

#### SR 遗留问题主看板重构

3 个核心数据卡片：SR 遗留总数、阻塞测试、Blocker

#### SR 需求详情数据持久化

- 数据库新增 `sr_detail_cache` 表
- SR 需求详情排序切换（3 种模式）

---

### 2026-06-10

#### 续航温升板块（新增）

从飞书续航体验表格读取 GO/GR/NG 数据。

#### 性能专项增强

Fail 原因多来源合并，Jira 编号跳转链接。

---

### 2026-06-09

#### 统一设置中心

合并 5+ 个设置弹窗为 1 个，分 4 个 Tab：Jira / ALM / AI / 飞书

#### SR AI 风险分析

SR 需求详情新增 AI 风险等级分析。

---

### 2026-06-08

#### 增量同步优化

改用 Jira 真实更新时间，精确到分钟。

#### ALM 平台集成（新增）

- 数据库新增 `alm_config` 表
- SR 需求详情查询

---

### 2026-06-05

#### 飞书时间解析重构

年份推断引擎，多格式日期支持。

#### 周趋势分析修复

统一使用 ISO 8601 周编号。

---

### 2026-06-04

#### AI 接入修复

迁移到 TranAI 代理，新增用户身份请求头。

#### 局域网多人协同

Vite 配置 `host: 0.0.0.0`。

---

## 许可证

内部项目，仅供传音控股测试团队使用。
