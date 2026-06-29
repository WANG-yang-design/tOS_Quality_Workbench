# 前端代码重构方案

## 一、现状分析

### 1.1 核心问题
- **App.tsx** 单文件 **5920 行**，包含所有组件、业务逻辑、类型定义
- 前次重构的 `components/`、`sections/`、`hooks/` 等目录使用了**完全不同的 CSS 类名和 HTML 结构**，无法替换现有 UI
- 所有 API 调用直接硬编码在组件内部，无统一管理层

### 1.2 前次重构失败原因
| 问题 | 说明 |
|------|------|
| CSS 类名不一致 | 重构版用 `metric-card`，原版用 `metricCard`；重构版用 `top-header`，原版用 `topHeader` |
| Props 接口完全不同 | 重构版 MetricCard 有 `suffix/icon/trend`，原版有 `label/value/note/danger` |
| HTML 结构差异 | 重构版用 `<select>` 做版本选择，原版用 `<button>` 版本药丸 |
| 丢失业务逻辑 | 原版的 SR 风险分析、AI 分析、UTP 报告等复杂逻辑未迁移 |

---

## 二、重构原则

> **零样式变更**：所有 CSS 类名、inline style、HTML 结构 100% 保持原样，仅做文件拆分和代码组织优化。

1. **复制粘贴式迁移**：从 App.tsx 中剪切组件代码，原封不动放入新文件
2. **保持所有 CSS 类名**：`metricCard`、`topHeader`、`floatingVersions` 等全部保留
3. **保持所有 inline style**：`style={{fontSize:13,color:"var(--text2)"}}` 等全部保留
4. **保持所有 HTML 结构**：DOM 层级、元素顺序不变
5. **API 接口暂不改动**：当前 `/api/*` 路径保持不变，重构只涉及前端文件组织

---

## 三、目标目录结构

```
frontend/src/
├── main.tsx                          # 入口（保持不变）
├── styles.css                        # 全局样式（保持不变）
├── App.tsx                           # 精简后的主组件（仅保留布局骨架 + 状态管理）
│
├── constants/
│   └── index.ts                      # API_BASE, JIRA_URL, STAGES, REPORT_SECTIONS 等常量
│
├── types/
│   └── index.ts                      # VersionItem, CredentialStatus, Analysis, StabilityDevice 等类型
│
├── utils/
│   ├── date.ts                       # getISOWeek, getCurrentWeekInfo, formatStageName
│   ├── jira.ts                       # buildProjectJql, buildJiraJqlUrl, JiraLinkText
│   ├── theme.ts                      # getVersionTheme, getGanttUrl
│   └── stage.ts                      # detectCurrentStageFromSchedule
│
├── hooks/
│   ├── useVersions.ts                # 版本列表加载 + 切换逻辑
│   ├── useStageSchedule.ts           # 阶段时间表加载逻辑
│   ├── useAnalysis.ts                # analysis + trends 加载逻辑
│   ├── useCredential.ts              # 凭证状态加载逻辑
│   ├── useFullRefresh.ts             # 全平台刷新逻辑（含轮询状态）
│   └── useScrollSpy.ts              # 滚动监听 + 高亮当前板块
│
├── api/
│   └── client.ts                     # 保持现有 ApiClient（暂不改动）
│
├── components/
│   ├── common/
│   │   ├── MetricCard.tsx            # 从 App.tsx 第618行剪切
│   │   ├── SectionHeader.tsx         # 从 App.tsx 第573行剪切
│   │   ├── MajorSectionDivider.tsx   # 从 App.tsx 第577行剪切
│   │   ├── InfoRow.tsx               # 从 App.tsx 第586行剪切
│   │   ├── ResourceCard.tsx          # 从 App.tsx 第590行剪切
│   │   ├── GoGrNgChips.tsx          # 从 App.tsx 第598行剪切
│   │   ├── JiraLinkText.tsx          # 从 App.tsx 第4516行剪切
│   │   ├── IssueLink.tsx             # 通用 Issue 链接组件
│   │   └── DeviceTabSelector.tsx     # 从 App.tsx 第809行剪切
│   │
│   ├── layout/
│   │   ├── TopHeader.tsx             # 从 App.tsx 第393行剪切（顶部栏）
│   │   ├── FloatingVersions.tsx      # 从 App.tsx 第459行剪切（版本选择器）
│   │   ├── FloatingSidebar.tsx       # 从 App.tsx 第481行剪切（侧边导航）
│   │   ├── DataLoadingOverlay.tsx    # 从 App.tsx 第513行剪切（加载遮罩）
│   │   ├── RefreshBanner.tsx         # 从 App.tsx 第423行剪切（刷新状态横幅）
│   │   └── ScrollFloatButtons.tsx    # 从 App.tsx 第561行剪切（滚动按钮）
│   │
│   ├── charts/
│   │   ├── PieChart.tsx              # 保持现有
│   │   └── TrendChart.tsx            # 保持现有
│   │
│   ├── modals/
│   │   ├── AddVersionModal.tsx       # 从 App.tsx 第5818行剪切
│   │   ├── VersionSettingsModal.tsx  # 从 App.tsx 第5862行剪切
│   │   ├── UnifiedSettingsModal.tsx  # 从 App.tsx 剪切（已有，需按原版重写）
│   │   ├── CredentialModal.tsx       # 从 App.tsx 剪切（已有，需按原版重写）
│   │   ├── StageScheduleEditor.tsx   # 从 App.tsx 剪切（已有，需按原版重写）
│   │   ├── IssueListModal.tsx        # 从 App.tsx 第5760行剪切
│   │   ├── ValuePointModal.tsx       # 从 App.tsx 第1621行剪切
│   │   ├── TestPlanModal.tsx         # 从 App.tsx 第1777行剪切
│   │   ├── SRDetailListModal.tsx     # 从 App.tsx 剪切（已有，需按原版重写）
│   │   ├── DailyReportModal.tsx      # 每日 SR 风险报告弹窗
│   │   ├── CycleTimeModal.tsx        # Bug 修复效能全量弹窗
│   │   ├── HealthMapModal.tsx         # 健康地图全量弹窗
│   │   ├── ModuleIssuesModal.tsx     # 模块问题单弹窗
│   │   ├── BlockingIssuesModal.tsx   # 阻塞测试问题弹窗
│   │   ├── BlockerIssuesModal.tsx    # Blocker 问题弹窗
│   │   ├── LowRiskSrModal.tsx        # 低风险 SR 弹窗
│   │   ├── AllSrModal.tsx            # 全部 SR 弹窗
│   │   ├── UtpJiraModal.tsx          # UTP Jira 缺陷弹窗
│   │   ├── LockedSrDetailModal.tsx   # ALM 加锁 SR 明细弹窗
│   │   ├── GlobalCredModal.tsx       # 全局凭证弹窗
│   │   ├── AISettingsModal.tsx       # AI 设置弹窗
│   │   └── ALMSettingsModal.tsx      # ALM 设置弹窗
│   │
│   └── agent/
│       └── AgentChat.tsx             # 保持现有
│
└── sections/
    ├── ProjectOverview.tsx           # 从 App.tsx 第636行剪切（基础信息 & 关键资源）
    ├── RiskSummary.tsx               # 从 App.tsx 第2280行剪切（风险和问题总结 - 超大组件）
    │   ├── 内含子组件：
    │   │   ├── SR风险卡片
    │   │   ├── OpenReopenSection
    │   │   ├── SubmittedModifyingSection
    │   │   ├── PendingVerificationSection
    │   │   ├── ALMLockedSrSection
    │   │   ├── UtpWeeklySection
    │   │   ├── CustomRisksSection
    │   │   └── AIDataAnalysisSection
    ├── StabilitySpecial.tsx          # 从 App.tsx 第853行剪切
    ├── PerformanceSpecial.tsx        # 从 App.tsx 第1105行剪切
    ├── BatterySpecial.tsx            # 从 App.tsx 第1209行剪切
    ├── ValuePoint.tsx                # 从 App.tsx 第1481行剪切
    ├── TestActivity.tsx              # 从 App.tsx 第529行组合
    ├── BasicExperience.tsx           # 从 App.tsx 组合
    ├── Workload.tsx                  # 从 App.tsx 剪切
    └── Chapter2AiCard.tsx            # 从 App.tsx 第2214行剪切
```

---

## 四、拆分策略（详细）

### 4.1 第一步：删除前次重构的无效文件

删除以下目录中**已被 App.tsx 内联定义覆盖**的文件：
- `components/common/` 下全部 → 用原版重写
- `components/layout/` 下全部 → 用原版重写
- `components/modals/` 下全部 → 用原版重写
- `sections/` 下全部 → 用原版重写
- `hooks/` 下全部 → 重新实现
- `types/index.ts` → 重新整理
- `utils/` 下全部 → 重新整理
- `constants/index.ts` → 重新整理
- `api/client.ts` → 保持不动

### 4.2 第二步：提取常量和类型

**`constants/index.ts`**
```typescript
// 从 App.tsx 第6-9行提取
export const API_BASE = "";
export const DEFAULT_JIRA_URL = "http://jira.transsion.com";
export const JIRA_BROWSE = DEFAULT_JIRA_URL + "/browse/";
export const UTP_WEB_URL = "https://utp.transsion.com/utpweb";

// 从 App.tsx 第50行提取
export const STAGES = ["STR1", "STR2", "STR3", "STR4", "STR5", "STA5", "ALL"];

// 从 App.tsx 第52-66行提取
export const REPORT_SECTIONS = [ ... ]; // 原样复制
```

**`types/index.ts`**
```typescript
// 从 App.tsx 第18-48行提取所有 type 定义
export type VersionItem = { ... };
export type CredentialStatus = { ... };
export type Analysis = { ... };
export type StabilityDevice = { ... };
export type ValuePoint = { ... };
export type TestPlan = { ... };
```

### 4.3 第三步：提取工具函数

**`utils/jira.ts`** - 从 App.tsx 第11-102行提取
- `buildProjectJql()`
- `buildJiraJqlUrl()`

**`utils/date.ts`** - 从 App.tsx 第136-157行提取
- `getISOWeek()`
- `getCurrentWeekInfo()`
- `formatStageName()`

**`utils/theme.ts`** - 从 App.tsx 第110-134行提取
- `getVersionTheme()`
- `getGanttUrl()`

**`utils/stage.ts`** - 从 App.tsx 第159-176行提取
- `detectCurrentStageFromSchedule()`

### 4.4 第四步：提取自定义 Hooks

**`hooks/useVersions.ts`**
```typescript
// 封装 App.tsx 中的：
// - loadVersions() (第307行)
// - switchVersion() (第382行)
// - versions, activeVersionId, activeVersion 状态
```

**`hooks/useStageSchedule.ts`**
```typescript
// 封装 App.tsx 中的：
// - loadStageSchedule() (第323行)
// - stageSchedule 状态
// - 自动识别当前阶段逻辑
```

**`hooks/useAnalysis.ts`**
```typescript
// 封装 App.tsx 中的：
// - loadAnalysis() (第332行)
// - loadTrends() (第337行)
// - analysis, trends 状态
```

**`hooks/useFullRefresh.ts`**
```typescript
// 封装 App.tsx 中的：
// - fullRefresh() (第348行)
// - fullRefreshing, fullRefreshStatus, fullRefreshDone 状态
// - 轮询逻辑
```

**`hooks/useScrollSpy.ts`**
```typescript
// 封装 App.tsx 中的：
// - IntersectionObserver 逻辑 (第211行)
// - 滚动按钮显示逻辑 (第246行)
// - activeSection, showScrollBtns 状态
```

### 4.5 第五步：逐组件拆分

**核心原则：从 App.tsx 中剪切 → 粘贴到新文件 → 添加 import → 在 App.tsx 中 import 使用**

#### 布局组件（直接剪切 JSX 部分）
| 组件 | App.tsx 行号 | 说明 |
|------|-------------|------|
| `TopHeader` | 393-420 | 顶部栏，含版本信息、链接、在线状态 |
| `FloatingVersions` | 459-478 | 版本药丸选择器 |
| `FloatingSidebar` | 481-509 | 侧边导航 |
| `DataLoadingOverlay` | 513-518 | 数据加载遮罩 |
| `RefreshBanner` | 423-456 | 全平台刷新状态横幅 |
| `ScrollFloatButtons` | 561-568 | 滚动按钮 |

#### 通用组件（直接剪切函数定义）
| 组件 | App.tsx 行号 | 说明 |
|------|-------------|------|
| `MetricCard` | 618-619 | 指标卡片 |
| `SectionHeader` | 573-575 | 区块标题 |
| `MajorSectionDivider` | 577-584 | 大板块分割符 |
| `InfoRow` | 586-588 | 信息行 |
| `ResourceCard` | 590-592 | 资源卡片 |
| `GoGrNgChips` | 598-600 | GO/GR/NG 标签 |
| `JiraLinkText` | 4516-4526 | Jira 链接文本 |
| `DeviceTabSelector` | 809-828 | 机型 Tab 切换 |

#### 页面板块（大组件，直接剪切整个函数）
| 组件 | App.tsx 行号 | 预估行数 | 说明 |
|------|-------------|---------|------|
| `ProjectOverview` | 636-804 | ~170行 | 基础信息 & 关键资源 |
| `StabilitySpecial` | 853-1100 | ~250行 | 稳定性专项 |
| `PerformanceSpecial` | 1105-1204 | ~100行 | 性能专项 |
| `BatterySpecial` | 1209-1313 | ~105行 | 续航温升 |
| `ValuePoint` | 1481-1616 | ~135行 | 价值点验收 |
| `Chapter2AiCard` | 2214-2278 | ~65行 | AI 综合分析卡片 |
| `RiskSummary` | 2280-4513 | ~2230行 | 风险和问题总结（最大板块） |
| `AIDataAnalysis` | 1946-2211 | ~265行 | AI 数据分析 |
| `OpenReopen` | 4531-4607 | ~75行 | Open/Reopened 分析 |
| `SubmittedModifying` | 4612-4700+ | ~90行 | 积压问题分析 |

#### 弹窗组件（直接剪切）
| 组件 | App.tsx 行号 | 说明 |
|------|-------------|------|
| `AddVersionModal` | 5818-5860 | 新增版本 |
| `VersionSettingsModal` | 5862-5920 | 版本设置 |
| `ValuePointModal` | 1621-1775 | 价值点录入 |
| `TestPlanModal` | 1777-1941 | 测试计划 |
| `IssueListModal` | 5760-5816 | Issue 列表通用弹窗 |
| 其他弹窗 | 各自位置 | 原样剪切 |

### 4.6 第六步：精简 App.tsx

重构后的 App.tsx 预计 **~150 行**，仅保留：
1. 状态声明（或调用 hooks）
2. useEffect 初始化
3. JSX 布局骨架（组合各组件）

```tsx
function App() {
  // 使用 hooks 管理状态
  const { versions, activeVersionId, activeVersion, switchVersion } = useVersions();
  const { stageSchedule } = useStageSchedule(activeVersionId);
  const { analysis, trends } = useAnalysis(activeVersionId, activeStage);
  const { fullRefreshing, fullRefreshDone, fullRefresh } = useFullRefresh(activeVersionId);
  const { activeSection, showScrollBtns } = useScrollSpy();
  // ...

  return (
    <div className={"page weekly-page " + theme.themeClass}>
      <TopHeader ... />
      <RefreshBanner ... />
      <FloatingVersions ... />
      <FloatingSidebar ... />
      <main className="mainScroll">
        <DataLoadingOverlay ... />
        <MajorSectionDivider icon="📊" title="项目概况" />
        <div id="sec-overview"><ProjectOverview ... /></div>
        <MajorSectionDivider icon="⚡" title="风险和问题总结" />
        <Chapter2AiCard ... />
        <div id="sec-risk"><RiskSummary ... /></div>
        <MajorSectionDivider icon="🎯" title="重点测试活动" />
        <div id="sec-key-test-activity">
          <TestActivity ... />
          <BasicExperience ... />
        </div>
        <MajorSectionDivider icon="⏱️" title="工时情况" />
        <div id="sec-workload"><Workload ... /></div>
      </main>
      {/* 弹窗层 */}
      {showUnifiedSettings && <UnifiedSettingsModal ... />}
      {/* ... */}
      <AgentChat ... />
      <ScrollFloatButtons ... />
    </div>
  );
}
```

---

## 五、实施计划

### 阶段一：准备工作（不改任何运行代码）
1. ✅ 备份当前 `App.tsx` 为 `App.tsx.bak`
2. ✅ 删除前次重构的无效文件（components/、sections/、hooks/、utils/、types/、constants/）
3. ✅ 确认 `npm run dev` 正常运行

### 阶段二：提取基础设施
1. 创建 `constants/index.ts` - 提取常量
2. 创建 `types/index.ts` - 提取类型定义
3. 创建 `utils/*.ts` - 提取工具函数
4. **验证**：`npm run dev` 正常，页面无变化

### 阶段三：提取 Hooks
1. 创建 `hooks/useVersions.ts`
2. 创建 `hooks/useStageSchedule.ts`
3. 创建 `hooks/useAnalysis.ts`
4. 创建 `hooks/useFullRefresh.ts`
5. 创建 `hooks/useScrollSpy.ts`
6. **验证**：`npm run dev` 正常，页面无变化

### 阶段四：提取通用组件
1. 创建 `components/common/*.tsx` - 逐个剪切
2. 创建 `components/layout/*.tsx` - 逐个剪切
3. 创建 `components/charts/*.tsx` - 保持现有
4. **验证**：`npm run dev` 正常，页面无变化

### 阶段五：提取页面板块
1. 创建 `sections/ProjectOverview.tsx`
2. 创建 `sections/StabilitySpecial.tsx`
3. 创建 `sections/PerformanceSpecial.tsx`
4. 创建 `sections/BatterySpecial.tsx`
5. 创建 `sections/ValuePoint.tsx`
6. 创建 `sections/Chapter2AiCard.tsx`
7. 创建 `sections/RiskSummary.tsx`（最大，需仔细）
8. **验证**：`npm run dev` 正常，页面无变化

### 阶段六：提取弹窗组件
1. 创建 `components/modals/*.tsx` - 逐个剪切
2. **验证**：`npm run dev` 正常，所有弹窗功能正常

### 阶段七：最终清理
1. 确认 App.tsx 精简到 ~150 行
2. 删除 `App.tsx.bak`
3. 全量功能测试
4. `npm run build` 验证生产构建

---

## 六、验证检查清单

- [ ] 页面首屏加载正常，样式无变化
- [ ] 版本切换正常，主题色切换正常
- [ ] 阶段切换正常，数据刷新正常
- [ ] 全平台刷新功能正常
- [ ] 所有弹窗打开/关闭正常
- [ ] AI 分析功能正常
- [ ] SR 需求相关功能正常
- [ ] 稳定性/性能/续航专项正常
- [ ] 价值点录入正常
- [ ] 侧边导航高亮正常
- [ ] 滚动按钮正常
- [ ] 响应式布局正常（900px 以下）
- [ ] `npm run build` 无报错

---

## 七、风险控制

1. **逐步验证**：每完成一个阶段就验证，发现问题立即回退
2. **不改 API**：所有 `/api/*` 路径保持不变
3. **不改样式**：`styles.css` 完全不动，所有 CSS 类名保持原样
4. **不改逻辑**：业务逻辑原样迁移，不优化、不重构业务代码
5. **备份机制**：保留 `App.tsx.bak` 直到全部验证通过

---

## 八、预期收益

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| App.tsx 行数 | 5920 行 | ~150 行 |
| 最大单文件行数 | 5920 行 | ~2230 行（RiskSummary） |
| 文件数量 | 1 个主文件 | ~40 个模块文件 |
| 可维护性 | 低（难以定位） | 高（按职责分离） |
| 样式变更 | 无 | 无 |
| 功能变更 | 无 | 无 |