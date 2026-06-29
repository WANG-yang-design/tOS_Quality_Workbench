import React, { useEffect, useMemo, useRef, useState } from "react";
import { AgentChat } from "../components/agent/AgentChat";

// 从 constants 导入
import { API_BASE, DEFAULT_JIRA_URL, JIRA_BROWSE, UTP_WEB_URL, STAGES, REPORT_SECTIONS } from "./constants";

// 从 types 导入
import type { VersionItem, CredentialStatus, Analysis, StabilityDevice, ValuePoint, TestPlan } from "./types";
import { EMPTY_DEVICE, EMPTY_PLAN } from "./types";

// 从 utils 导入
import { getISOWeek, getCurrentWeekInfo, formatStageName } from "./utils/date";
import { buildProjectJql, buildJiraJqlUrl } from "./utils/jira";
import { getVersionTheme, getGanttUrl } from "./utils/theme";
import { detectCurrentStageFromSchedule } from "./utils/stage";

// 从 components 导入
import { MetricCard } from "./components/common/MetricCard";
import { SectionHeader } from "./components/common/SectionHeader";
import { MajorSectionDivider } from "./components/common/MajorSectionDivider";
import { InfoRow } from "./components/common/InfoRow";
import { ResourceCard } from "./components/common/ResourceCard";
import { GoGrNgChips } from "./components/common/GoGrNgChips";
import { JiraLinkText } from "./components/common/JiraLinkText";
import { IssueLink } from "./components/common/IssueLink";
import { DeviceTabSelector } from "./components/common/DeviceTabSelector";
import { StageCountdown } from "./components/common/StageCountdown";

// 从 sections 导入
import { TestActivitySection } from "./sections/TestActivity";
import { BasicExperienceSection } from "./sections/BasicExperience";
import { WorkloadSection } from "./sections/Workload";
import { ProjectOverviewSection } from "./sections/ProjectOverview";
import { Chapter2AiCard } from "./sections/Chapter2AiCard";
import { StabilitySpecialSection } from "./sections/StabilitySpecial";
import { PerformanceSpecialSection } from "./sections/PerformanceSpecial";
import { BatterySpecialSection } from "./sections/BatterySpecial";
import { ValuePointSection } from "./sections/ValuePoint";
import { JiraTrendAnalysisSection } from "./sections/JiraTrendAnalysis";
import { AIDataAnalysisSection } from "./sections/AIDataAnalysis";

// 从 modals 导入
import { AddVersionModal } from "./components/modals/AddVersionModal";
import { StageScheduleEditor } from "./components/modals/StageScheduleEditor";
import { UnifiedSettingsModal } from "./components/modals/UnifiedSettingsModal";
import { VersionSettingsModal } from "./components/modals/VersionSettingsModal";
import { IssueListModal } from "./components/modals/IssueListModal";
import { GlobalCredModal } from "./components/modals/GlobalCredModal";
import { AISettingsModal } from "./components/modals/AISettingsModal";
import { ALMSettingsModal } from "./components/modals/ALMSettingsModal";
import { CredentialModal } from "./components/modals/CredentialModal";

// 从 sections/risk 导入
import { RiskSummarySection } from "./sections/risk/RiskSummarySection";

function AppRefactored() {
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [activeStage, setActiveStage] = useState("");
  const [credential, setCredential] = useState<CredentialStatus | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncProgress, setSyncProgress] = useState("");
  const [showAddVersion, setShowAddVersion] = useState(false);
  const [showCredential, setShowCredential] = useState(false);
  const [stageSchedule, setStageSchedule] = useState<any[]>([]);
  const [showStageEditor, setShowStageEditor] = useState(false);
  const [showUnifiedSettings, setShowUnifiedSettings] = useState(false);
  const [unifiedSettingsTab, setUnifiedSettingsTab] = useState("jira");
  const [showAISettings, setShowAISettings] = useState(false);
  const [showALMSettings, setShowALMSettings] = useState(false);
  const [showVersionSettings, setShowVersionSettings] = useState(false);
  const [showGlobalCred, setShowGlobalCred] = useState(false);
  const [globalCredStatus, setGlobalCredStatus] = useState<any>(null);
  const [trends, setTrends] = useState<any>(null);
  const [activeSection, setActiveSection] = useState("overview");
  const [dataLoading, setDataLoading] = useState(false);
  const [syncDone, setSyncDone] = useState<{ msg: string; time: string } | null>(null);
  const [feishuLoggedIn, setFeishuLoggedIn] = useState(false);
  const [jiraSyncVersion, setJiraSyncVersion] = useState(0);
  const [showScrollBtns, setShowScrollBtns] = useState(false);
  const [activeConns, setActiveConns] = useState<{total: number; clients: any[]}>({total: 0, clients: []});
  const [hoveredNav, setHoveredNav] = useState<string | null>(null);
  const [fullRefreshing, setFullRefreshing] = useState(false);
  const [fullRefreshStatus, setFullRefreshStatus] = useState<any>(null);
  const [fullRefreshDone, setFullRefreshDone] = useState<{msg: string; time: string; errors: string[]} | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  // 滚动监听：高亮当前板块
  useEffect(() => {
    const observers: IntersectionObserver[] = [];
    const sectionKeys = REPORT_SECTIONS.map(s => s.key);
    REPORT_SECTIONS.forEach(sec => {
      const el = document.getElementById("sec-" + sec.key);
      if (!el) return;
      const obs = new IntersectionObserver(
        ([entry]) => { if (entry.isIntersecting) setActiveSection(sec.key); },
        { rootMargin: "-20% 0px -65% 0px", threshold: 0 }
      );
      obs.observe(el);
      observers.push(obs);
    });
    const handleScroll = () => {
      const scrollBottom = window.innerHeight + window.scrollY;
      const docHeight = document.documentElement.scrollHeight;
      if (docHeight - scrollBottom < 100) {
        setActiveSection(sectionKeys[sectionKeys.length - 1]);
      }
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      observers.forEach(o => o.disconnect());
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  // 滚动按钮显示/隐藏
  useEffect(() => {
    const onScroll = () => { setShowScrollBtns(window.scrollY > 300); };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // 在线连接轮询
  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch(API_BASE + "/api/active-connections");
        setActiveConns(await res.json());
      } catch { /* ignore */ }
    }
    poll();
    const timer = setInterval(poll, 15000);
    return () => clearInterval(timer);
  }, []);

  // 自动刷新检测：每 2 分钟检查后端是否已完成自动刷新，若是则同步前端数据
  useEffect(() => {
    if (!activeVersionId) return;
    let lastKnownRefresh: string | null = null;

    async function checkAutoRefresh() {
      try {
        const res = await fetch(API_BASE + "/api/auto-refresh/status");
        const status = await res.json();
        const backendRefreshTime = status.last_refresh;
        if (backendRefreshTime && backendRefreshTime !== lastKnownRefresh) {
          if (lastKnownRefresh !== null) {
            // 后端有新数据，触发前端刷新
            console.log("[AutoSync] 检测到后端自动刷新完成，同步前端数据...");
            setRefreshCount(c => c + 1);
            setJiraSyncVersion(v => v + 1);
            if (activeVersionId) {
              loadAnalysis(activeVersionId, activeStage);
            }
          }
          lastKnownRefresh = backendRefreshTime;
        }
      } catch { /* ignore */ }
    }

    // 立即检查一次（获取当前状态作为基线）
    checkAutoRefresh();
    // 每 2 分钟检查一次
    const timer = setInterval(checkAutoRefresh, 2 * 60 * 1000);
    return () => clearInterval(timer);
  }, [activeVersionId, activeStage]);

  const activeVersion = useMemo(() => versions.find(v => v.id === activeVersionId) || null, [versions, activeVersionId]);
  const theme = getVersionTheme(activeVersion?.version_name);
  const weekInfo = getCurrentWeekInfo();

  useEffect(() => { loadVersions(); loadGlobalCredStatus(); checkFeishuToken(); }, []);

  async function loadGlobalCredStatus() {
    try {
      const res = await fetch(API_BASE + "/api/jira/global-credential");
      setGlobalCredStatus(await res.json());
    } catch { /* ignore */ }
  }

  async function checkFeishuToken() {
    try {
      const d = await (await fetch(API_BASE + "/api/feishu/token-status")).json();
      setFeishuLoggedIn(!!d.logged_in);
    } catch { setFeishuLoggedIn(false); }
  }

  function handleFeishuLogin() {
    const loginWin = window.open(API_BASE + "/api/feishu/login", "feishu_oauth", "width=600,height=700,scrollbars=yes");
    const poll = setInterval(() => {
      if (!loginWin || loginWin.closed) {
        clearInterval(poll);
        checkFeishuToken();
      }
    }, 1000);
  }

  useEffect(() => {
    if (activeVersionId) {
      setDataLoading(true);
      setSyncDone(null);
      Promise.all([
        loadCredentialStatus(activeVersionId),
        loadAnalysis(activeVersionId, activeStage),
        loadStageSchedule(activeVersionId),
        loadTrends(activeVersionId, activeStage),
      ]).finally(() => setDataLoading(false));
    }
  }, [activeVersionId, activeStage]);

  async function loadVersions() {
    const res = await fetch(API_BASE + "/api/versions");
    const data = await res.json();
    setVersions(data);
    if (data.length > 0) {
      const saved = Number(localStorage.getItem("tos_active_version_id"));
      const target = data.find((v: VersionItem) => v.id === saved) || data[1] || data[0];
      setActiveVersionId(target.id);
    }
  }

  async function loadCredentialStatus(versionId: number) {
    const res = await fetch(API_BASE + "/api/versions/" + versionId + "/credential/status");
    setCredential(await res.json());
  }

  async function loadStageSchedule(versionId: number) {
    const res = await fetch(API_BASE + "/api/versions/" + versionId + "/stages");
    const data = await res.json();
    setStageSchedule(data);
    const detected = detectCurrentStageFromSchedule(data);
    if (detected) setActiveStage(detected);
  }

  async function loadAnalysis(versionId: number, stage: string) {
    const res = await fetch(API_BASE + "/api/versions/" + versionId + "/analysis?stage=" + stage);
    setAnalysis(await res.json());
  }

  async function loadTrends(versionId: number, stage: string) {
    const res = await fetch(API_BASE + "/api/versions/" + versionId + "/trends?stage=" + stage);
    setTrends(await res.json());
  }

  async function syncJira() { await fullRefresh(); }

  async function fullRefresh() {
    if (fullRefreshing || !activeVersionId) return;
    setFullRefreshing(true);
    setFullRefreshDone(null);
    const poll = setInterval(async () => {
      try {
        const s = await (await fetch(API_BASE + "/api/auto-refresh/status")).json();
        setFullRefreshStatus(s);
        if (!s.is_refreshing && s.last_refresh) clearInterval(poll);
      } catch { /* ignore */ }
    }, 2000);
    try {
      const res = await fetch(API_BASE + `/api/auto-refresh?version_id=${activeVersionId}`, { method: "POST" });
      const data = await res.json();
      const errs = data.errors || [];
      setFullRefreshDone({
        msg: data.message || "刷新完成",
        time: new Date().toLocaleTimeString(),
        errors: errs,
      });
      setRefreshCount(c => c + 1);
      setJiraSyncVersion(v => v + 1);
      loadCredentialStatus(activeVersionId);
      loadAnalysis(activeVersionId, activeStage);
    } catch (e: any) {
      setFullRefreshDone({ msg: "❌ 刷新失败: " + (e.message || "未知错误"), time: new Date().toLocaleTimeString(), errors: [] });
    } finally {
      clearInterval(poll);
      setFullRefreshing(false);
      setFullRefreshStatus(null);
      setTimeout(() => setFullRefreshDone(null), 10000);
    }
  }

  function switchVersion(id: number) {
    setActiveVersionId(id);
    localStorage.setItem("tos_active_version_id", String(id));
  }

  const metrics = analysis?.metrics || {};
  const risks = analysis?.risks || {};

  // ═══════════════════════════════════════════════════
  // 以下组件暂时内联定义，后续逐步迁移到独立文件
  // 所有代码原样复制自 App.tsx，零修改
  // ═══════════════════════════════════════════════════

  // ... 内联组件定义将在后续步骤中添加
  // 目前先导入 App.tsx 的默认导出作为后备

  return (
    <div className={"page weekly-page " + theme.themeClass}>
      {/* 顶部栏 */}
      <header className="topHeader">
        <div className="topHeaderLeft">
          <span className="productTitle">◈ tOS 测试项目管理工作台</span>
          <span className="reportMeta">{weekInfo.year}年第{weekInfo.week}周（{weekInfo.start} — {weekInfo.end}）· {activeVersion?.owner_name || "未配置"}</span>
          <StageCountdown stageSchedule={stageSchedule} activeStage={activeStage} />
        </div>
        <div className="topHeaderRight">
          <a className="textLink" href={activeVersion?.feishu_sheet_url || "#"} target="_blank" rel="noreferrer">{activeVersion?.feishu_sheet_url ? "管理书" : "管理书 ⚠"}</a>
          <a className="textLink" href={activeVersion ? `${DEFAULT_JIRA_URL}/issues/?jql=${encodeURIComponent(buildProjectJql(activeVersion.jira_project) + " ORDER BY created DESC")}` : "#"} target="_blank" rel="noreferrer">Jira 看板</a>
          <a className="textLink" href={UTP_WEB_URL + "/ProjectManage/testPlan"} target="_blank" rel="noreferrer">UTP</a>
          <span className={"statusBadge " + (globalCredStatus?.configured ? "ok" : "warn")}>{globalCredStatus?.configured ? "Jira:" + globalCredStatus.username : "Jira未配置"}</span>
          <span className="statusBadge ok" style={{cursor:"default",position:"relative",userSelect:"none"}} title={activeConns.clients.map(c => `${c.ip}（${c.idle_seconds < 60 ? '刚刚' : Math.floor(c.idle_seconds/60) + '分钟前'}）`).join("\n") || "仅本机"}>
            🟢 {activeConns.total} 在线
          </span>
          <button className={feishuLoggedIn ? "statusBadge ok" : "statusBadge warn"} onClick={handleFeishuLogin} style={{cursor:"pointer",border:"none"}} title={feishuLoggedIn ? "飞书已授权，点击重新授权" : "点击完成飞书授权"}>
            {feishuLoggedIn ? "飞书✓" : "飞书⚠"}
          </button>
          <button className="primaryBtn syncBtn" onClick={fullRefresh} disabled={fullRefreshing || loading || !activeVersionId}
            title={`刷新 ${activeVersion?.version_name || "当前版本"} 的 Jira + UTP + ALM 数据（不含 SR 需求详情和 AI 分析）`}>
            {fullRefreshing ? "⏳ 刷新中..." : "🔄 刷新数据"}
          </button>
          {fullRefreshDone && !fullRefreshing && (
            <span className="syncDoneBadge" title={fullRefreshDone.msg}>
              ✅ 已刷新 · {fullRefreshDone.time}
            </span>
          )}
          <button className="smallBtn" onClick={() => { setShowUnifiedSettings(true); setUnifiedSettingsTab("jira"); }} title="设置">⚙️</button>
        </div>
      </header>

      {/* 全平台刷新状态横幅 */}
      {(fullRefreshing || fullRefreshDone) && (
        <div style={{
          position: "fixed", top: 52, left: 0, right: 0, zIndex: 300,
          padding: "8px 24px", fontSize: 13, fontWeight: 500, textAlign: "center",
          background: fullRefreshing ? "linear-gradient(90deg, #eff6ff, #dbeafe)" : (fullRefreshDone?.errors?.length ? "#fef3c7" : "#ecfdf5"),
          borderBottom: `2px solid ${fullRefreshing ? "#3b82f6" : (fullRefreshDone?.errors?.length ? "#f59e0b" : "#10b981")}`,
          display: "flex", alignItems: "center", justifyContent: "center", gap: 12,
          animation: "navSubFadeIn .2s ease",
        }}>
          {fullRefreshing ? (
            <>
              <div className="dataLoadingSpinner" style={{ width: 16, height: 16 }} />
              <span>{fullRefreshStatus?.progress || `正在刷新 ${activeVersion?.version_name || ""} 数据...`}</span>
              {fullRefreshStatus?.total_versions > 0 && (
                <span style={{ color: "var(--text3)" }}>({fullRefreshStatus.completed_versions}/{fullRefreshStatus.total_versions})</span>
              )}
            </>
          ) : fullRefreshDone && (
            <>
              <span>{fullRefreshDone.msg}</span>
              <span style={{ color: "var(--text3)", fontSize: 11 }}>{fullRefreshDone.time}</span>
              {fullRefreshDone.errors.length > 0 && (
                <span style={{ color: "#b45309", fontSize: 11 }}>⚠️ {fullRefreshDone.errors.length} 个版本有错误</span>
              )}
            </>
          )}
        </div>
      )}

      {/* 悬浮版本选择器 */}
      <nav className="floatingVersions">
        {versions.map(v => {
          const vt = getVersionTheme(v.version_name);
          const isActive = v.id === activeVersionId;
          const detected = isActive ? detectCurrentStageFromSchedule(stageSchedule) : "";
          return (
            <button key={v.id} className={"versionPill " + (isActive ? "active" : "")} onClick={() => switchVersion(v.id)}
              onContextMenu={(e) => { e.preventDefault(); setShowVersionSettings(true); }}>
              <span className="versionDot" style={{ background: vt.accent }} />
              {v.version_name}
              {isActive && detected && <span className="versionStageTag">{formatStageName(detected)}</span>}
              {v.is_train_version === 1 && <span className="versionTag">1+N</span>}
              {v.is_pad === 1 && <span className="versionTag" style={{background:"#dbeafe",color:"#2563eb"}}>PAD</span>}
              {isActive && <span className="versionSettingsBtn" onClick={(e) => { e.stopPropagation(); setShowVersionSettings(true); }} title="版本设置">⚙</span>}
            </button>
          );
        })}
        <button className="stageEditBtn" onClick={() => setShowStageEditor(true)} title="时间表">📅</button>
        <button className="addVersionNew" onClick={() => setShowAddVersion(true)}>+</button>
      </nav>

      {/* 悬浮侧边导航 */}
      <aside className="floatingSidebar">
        {REPORT_SECTIONS.map(item => (
          <div key={item.key}
            style={{ position: "relative" }}
            onMouseEnter={() => item.children && setHoveredNav(item.key)}
            onMouseLeave={() => setHoveredNav(prev => prev === item.key ? null : prev)}>
            <button
              className={"navIcon" + (activeSection === item.key ? " active" : "")}
              onClick={() => document.getElementById("sec-" + item.key)?.scrollIntoView({ behavior: "smooth" })}>
              <span className="navIconEmoji">{item.icon}</span>
              <span className="navIconLabel">{item.title}</span>
            </button>
            {item.children && hoveredNav === item.key && (
              <div className="navSubPopup">
                {item.children.map(child => (
                  <button key={child.key}
                    className={"navSubItem" + (child.label.startsWith("  └") ? " indent" : "")}
                    onClick={() => {
                      document.getElementById(child.key)?.scrollIntoView({ behavior: "smooth" });
                      setHoveredNav(null);
                    }}>
                    {child.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </aside>

      {/* 主内容 */}
      <main className="mainScroll">
        {dataLoading && (
          <div className="dataLoadingOverlay">
            <div className="dataLoadingSpinner" />
            <span>正在加载 {activeVersion?.version_name || ""} 数据...</span>
          </div>
        )}

        <MajorSectionDivider icon="📊" title="项目概况" />
        <div id="sec-overview">
          <ProjectOverviewSection activeVersion={activeVersion} metrics={metrics} risks={risks} trends={trends} activeStage={activeStage} stageSchedule={stageSchedule} onSyncJira={fullRefresh} loading={loading} onUpdateVersion={loadVersions} />
        </div>

        <MajorSectionDivider icon="⚡" title="风险和问题总结" />
        <Chapter2AiCard activeVersion={activeVersion} activeStage={activeStage} jiraSyncVersion={jiraSyncVersion} />
        <div id="sec-risk">
          <RiskSummarySection metrics={metrics} risks={risks} trends={trends} activeVersion={activeVersion} activeStage={activeStage} stageSchedule={stageSchedule} onSyncJira={fullRefresh} loading={loading} jiraSyncVersion={jiraSyncVersion} refreshCount={refreshCount} />
        </div>

        <MajorSectionDivider icon="🎯" title="重点测试活动" />
        <div id="sec-key-test-activity">
          <TestActivitySection activeVersion={activeVersion} stageSchedule={stageSchedule} />
        </div>

        <MajorSectionDivider icon="⏱️" title="工时情况" />
        <div id="sec-workload"><WorkloadSection activeVersion={activeVersion} /></div>
      </main>

      {/* 弹窗层 - 暂时留空，后续添加 */}
      {showAddVersion && <AddVersionModal onClose={() => setShowAddVersion(false)} onSuccess={() => { setShowAddVersion(false); loadVersions(); }} />}
      {showStageEditor && activeVersionId && <StageScheduleEditor versionId={activeVersionId} versionName={activeVersion?.version_name || ""} stages={stageSchedule} onClose={() => setShowStageEditor(false)} onSuccess={(updated: any[]) => { setShowStageEditor(false); setStageSchedule(updated); }} />}
      {showUnifiedSettings && activeVersion && <UnifiedSettingsModal version={activeVersion} defaultTab={unifiedSettingsTab} onClose={() => setShowUnifiedSettings(false)} onSaved={() => { loadVersions(); loadGlobalCredStatus(); if (activeVersionId) loadCredentialStatus(activeVersionId); }} />}
      {showVersionSettings && activeVersion && <VersionSettingsModal version={activeVersion} onClose={() => setShowVersionSettings(false)} onSuccess={() => { setShowVersionSettings(false); loadVersions(); }} />}

      {/* AI 智能助手 */}
      <AgentChat activeVersionId={activeVersionId} activeStage={activeStage} />

      {/* 悬浮滚动按钮 */}
      <div className={`scrollFloatWrap ${showScrollBtns ? "visible" : ""}`}>
        <button className="scrollFloatBtn topBtn" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} title="回到顶部">
          <svg viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15" /></svg>
        </button>
        <button className="scrollFloatBtn btmBtn" onClick={() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" })} title="跳到底部">
          <svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9" /></svg>
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// 内联组件 - 从 App.tsx 原样复制
// 后续将逐步迁移到独立文件
// ═══════════════════════════════════════════════════════

// 所有弹窗组件已迁移到 components/modals/ 目录

export default AppRefactored;