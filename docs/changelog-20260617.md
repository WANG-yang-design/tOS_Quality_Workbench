# Changelog - 2026-06-17

## 一、SR 需求详情（ALM）

- **移除"其他版本 SR"**：不再展示其他版本的 SR 数据，只关注当前版本
- 移除了"其他版本 SR"、"其他版本 Issue"两张 MetricCard
- 移除了"其他版本 SR"可展开/收起的表格区块
- 板块标题改为"SR 需求详情（ALM）- 当前版本"

## 二、SR 数量展示（新板块）

在"SR 需求相关风险"中新增"SR 数量展示（ALM 加锁 SR）"板块：

- **数据来源**：从 ALM 平台查询 `lockFlag=YES_LOCK` 的加锁 SR，参考 `alm_locked_sr_status_reader.py`
- **总计 SR 数量**：显示加锁 SR 总数
- **三个关键比率**（分母排除"不涉及测试"的 SR）：
  - 转测率 = (测试中 + 验收 + 完成) / 涉及测试 SR
  - 测试中占比 = 测试中 / 涉及测试 SR
  - 验收通过率 = 完成 / 涉及测试 SR
- **六种状态进度条**：初始、设计、开发、测试、验收、完成，可点击查看明细
- **今日/本周新增**：标签嵌入总计卡片，点击弹出明细 + 各阶段新增数量
- **SR 明细弹窗**：每个 SR 编号可点击跳转 ALM 并自动复制到剪贴板
- **"不涉及测试"过滤**：识别 ALM `tag` 字段含"不涉及测试"的 SR，从比率分母中排除

### 新增后端文件

| 文件 | 说明 |
|------|------|
| `backend/routers/alm_locked_sr.py` | 加锁 SR 路由（GET 缓存 / POST 刷新 / GET 今日新增） |
| `backend/routers/utp_weekly.py` | UTP Weekly 报告路由（GET 缓存 / POST 刷新 / POST AI 分析） |

### 新增数据库表

| 表名 | 说明 |
|------|------|
| `alm_locked_sr_cache` | 加锁 SR 明细缓存（含 `tag` 字段） |
| `alm_locked_sr_snapshot` | 加锁 SR 统计快照（含 delta 追踪） |
| `jira_issue_api_cache` | Jira 查询结果缓存（30 分钟 TTL，使用 Unix 时间戳） |
| `utp_weekly_cache` | UTP Weekly 报告缓存 |

### 新增数据库列

| 表 | 新增列 | 说明 |
|------|--------|------|
| `version_config` | `is_pad` | 是否为 PAD 版本 |
| `version_config` | `utp_owner_codes` | UTP 创建人工号 |
| `alm_locked_sr_cache` | `tag` | ALM SR 标签（如"不涉及测试"） |

## 三、AI 每日风险报告修复

- **报告持久化**：`/sr-daily-risk-report/today` 端点现在会查找最近 7 天内的报告（之前只查当天）
- **AI 数据增强**：AI prompt 从简略摘要扩展为完整数据（高/中风险 SR 详情、Blocker/Critical 遗留问题、超龄问题、负责人 Top 10），字数上限从 500 提升至 800 字
- **前端提示**：加载非当天报告时显示"⚠ 非当天报告，请重新生成"

## 四、板块合并：测试活动 + 重点任务 → 重点测试活动

- `REPORT_SECTIONS` 数组合并 `activity` + `tasks` 为 `key-test-activity`
- 侧边栏导航从 5 项减少到 4 项
- 主内容区两个组件共用一个"🎯 重点测试活动"板块分隔线

## 五、Jira 数据缓存（解决切换版本慢的问题）

- **`jira-issues/{filter_key}` 端点**：新增 `use_cache` 参数，默认 30 分钟内返回缓存
- **`analysis` 端点**：同样加 30 分钟缓存
- **`sr-issues-refresh` 端点**：新增 `force` 参数，默认使用 30 分钟缓存
- **缓存存储**：使用 Unix 时间戳（`time.time()`）而非 ISO datetime，避免格式解析问题
- **前端**：`OpenReopenSection`、`SubmittedModifyingSection` 自动加载用缓存，手动刷新才查 Jira；`loadSrIssues` 同理
- **日志**：后端打印 `[CACHE-HIT]`、`[CACHE-SAVE]`、`[CACHE-ERROR]` 便于排查

## 六、多项目与 PAD 版本支持

### tOS17.0 多项目

- 种子数据 tOS17.0 的 `jira_project` 改为 `"TOS170, LK7KOS17, X6878OS17"`
- `_build_project_condition()` 重写：自动检测逗号分隔的多项目，选择 `project in (...)` 语法
- 移除了硬编码的 `SR_MULTI_PROJECT_MAP`

### PAD 版本

- 创建版本时可勾选"PAD 版本"
- PAD 版本的所有 Jira 查询自动附加 `AND summary ~ "PAD"` 条件
- 创建 PAD 版本时自动继承基础版本的 ALM `space_bid` 和 `app_bid`
- UTP 查询时自动去掉版本名中的"PAD"后缀
- 版本选择器显示蓝色 `PAD` 标签
- `VersionSettingsModal` 新增 PAD 复选框和 UTP 创建人工号输入框

## 七、版本管理修复

- **版本删除**：新增 `DELETE /api/versions/{version_id}` 端点，删除版本及其所有关联数据（20+ 张表）
- **新版本 Filter Presets**：创建版本时自动播种默认 Jira Filter Presets（之前只在数据库初始化时播种）

## 八、基础公共相关风险 - UTP Weekly 报告集成

- **数据来源**：UTP 平台 `/api/testPlan/queryPlanList` + `/api/report/getPlanReport`
- **每个芯片平台（MTK/Q）可折叠区块**：
  - 总体统计：用例总数、通过率、Fail 数、遗留缺陷
  - 测试进度表格：业务领域、子领域、子领域结果、测试进度、用例数、Blocked、通过率、NA 率、JIRA、风险、完成时间、负责人
  - 🤖 AI 分析按钮
- **UTP 创建人工号**：内联在 1.3 板块标题栏，点击编辑保存
- **修复的 bug**：
  - 报告接口应为 GET 请求（之前误用 POST 导致 500 错误）
  - `_utp_post`/`_utp_get` 新增业务状态检查（之前静默返回错误响应）
  - UTP App ID 优先使用 ALM 配置的 `alm_app_id`

## 九、文件变更清单

### 新增文件
- `backend/routers/alm_locked_sr.py`
- `backend/routers/utp_weekly.py`
- `docs/changelog-20260617.md`

### 修改文件（后端）
- `backend/app.py` — 注册新路由
- `backend/database.py` — 新增 4 张表 + 3 列迁移 + tOS17.0 多项目修正
- `backend/models/schemas.py` — `VersionCreate`/`VersionUpdate` 新增 `is_pad`、`utp_owner_codes`
- `backend/routers/analysis.py` — 30 分钟缓存
- `backend/routers/jira.py` — `use_cache` 参数 + PAD 条件注入 + 缓存
- `backend/routers/sr.py` — `sr-issues-refresh` 缓存 + PAD 条件 + 报告持久化 + AI 数据增强
- `backend/routers/versions.py` — 版本删除 + 创建时播种 Filter Presets + PAD 版本 ALM BID 继承
- `backend/services/alm_service.py` — 加锁 SR 查询/汇总/规范化 + `tag` 字段 + 用户姓名解析
- `backend/services/jira_service.py` — `build_sr_jql` 支持 `is_pad` + 多项目自动检测
- `backend/services/utp_service.py` — Weekly 报告获取 + GET 请求 + 错误检查

### 修改文件（前端）
- `frontend/src/App.tsx` — SR 数量展示 / UTP 板块 / 缓存逻辑 / 板块合并 / PAD 标签 / 版本设置 / 分数不约分
- `frontend/src/components/modals/AddVersionModal.tsx` — PAD 复选框
- `frontend/src/types/index.ts` — `VersionItem`/`VersionCreateRequest` 新增字段