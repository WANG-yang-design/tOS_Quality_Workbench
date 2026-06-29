import React, { useState, useEffect, useRef } from "react";
import { API_BASE, JIRA_BROWSE, DEFAULT_JIRA_URL } from "../../constants";
import { SectionHeader } from "../../components/common/SectionHeader";
import { MetricCard } from "../../components/common/MetricCard";
import { IssueLink } from "../../components/common/IssueLink";
import { IssueListModal } from "../../components/modals/IssueListModal";
import { SRDetailListModal } from "../../components/modals/SRDetailListModal";
import { JiraFilterEditor } from "../../components/common/JiraFilterEditor";
import { OpenReopenSection } from "./OpenReopenSection";
import { SubmittedModifyingSection } from "./SubmittedModifyingSection";
import { PendingVerificationSection } from "./PendingVerificationSection";
import { JiraTrendAnalysisSection } from "../JiraTrendAnalysis";
import { AIDataAnalysisSection } from "../AIDataAnalysis";
import { ValuePointSection } from "../ValuePoint";
import { StabilitySpecialSection } from "../StabilitySpecial";
import { PerformanceSpecialSection } from "../PerformanceSpecial";
import { BatterySpecialSection } from "../BatterySpecial";
import { exportIssueList, exportLockedSrList, exportUtpIssues, exportSrList } from "../../utils/export";
import { SrTestProgress } from "./SrTestProgress";
import { UtpPlanProgress } from "./UtpPlanProgress";

// DI值计算函数：DI = A类×10 + B类×3 + C类×1 + 其他×0.1
function calcDI(severityCount: any): number {
  if (!severityCount) return 0;
  return (
    (severityCount.blocker || 0) * 10 +
    (severityCount.critical || 0) * 3 +
    (severityCount.major || 0) * 1 +
    (severityCount.other || 0) * 0.1
  );
}

// UtpOwnerCodesSetting - 从 App.tsx 第4328行原样提取
function UtpOwnerCodesSetting({ activeVersion, onUpdate }: { activeVersion: any; onUpdate?: () => void }) {
  const [editing, setEditing] = useState(false);
  const [codes, setCodes] = useState(activeVersion?.utp_owner_codes || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setCodes(activeVersion?.utp_owner_codes || ""); }, [activeVersion?.utp_owner_codes]);
  async function handleSave() {
    if (!activeVersion?.id) return;
    setSaving(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ utp_owner_codes: codes.trim() }),
      });
      if (res.ok) { setEditing(false); if (onUpdate) onUpdate(); }
      else { alert("保存失败"); }
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }
  if (!editing) {
    return (
      <span style={{fontSize:11,color:"var(--text3)",cursor:"pointer",borderBottom:"1px dashed var(--card-border)"}} onClick={() => setEditing(true)} title="点击修改 UTP 创建人工号">
        创建人：{codes || "未配置"} ✏️
      </span>
    );
  }
  return (
    <span style={{display:"inline-flex",alignItems:"center",gap:4}}>
      <input value={codes} onChange={e => setCodes(e.target.value)} placeholder="如 18620222" style={{width:100,padding:"2px 6px",fontSize:11,borderRadius:4,border:"1px solid var(--card-border)",background:"var(--surface)"}} />
      <button className="primaryBtn" onClick={handleSave} disabled={saving} style={{padding:"2px 8px",fontSize:11}}>{saving ? "..." : "✓"}</button>
      <button className="secondaryBtn" onClick={() => { setEditing(false); setCodes(activeVersion?.utp_owner_codes || ""); }} style={{padding:"2px 8px",fontSize:11}}>✕</button>
    </span>
  );
}

export function RiskSummarySection({ metrics, risks, trends, activeVersion, activeStage, stageSchedule, onSyncJira, loading, jiraSyncVersion, refreshCount }: any) {
  const status = metrics.status_distribution || {};
  const [showAllHighRisk, setShowAllHighRisk] = useState(false);
  const [showTrendTable, setShowTrendTable] = useState(false);
  const [srIssues, setSrIssues] = useState<{ total: number; issues: any[]; jql?: string; jira_url?: string; cached?: boolean; error?: string } | null>(null);
  const [srLoading, setSrLoading] = useState(false);
  const [showAllSr, setShowAllSr] = useState(false);
  const [showSrTable, setShowSrTable] = useState(false);
  const [srDetails, setSrDetails] = useState<{ sr_list: any[]; total_sr: number; total_issues: number; alm_page_url: string; error?: string; warning?: string; cached?: boolean } | null>(null);
  const [srDetailsLoading, setSrDetailsLoading] = useState(false);
  const [srAiAnalyses, setSrAiAnalyses] = useState<Record<string, { analysis: string; analyzed_at: string }>>({});
  const [srAiLoading, setSrAiLoading] = useState(false);
  const [srAiLoadingSingle, setSrAiLoadingSingle] = useState<Record<string, boolean>>({});
  const [expandedCurrentSR, setExpandedCurrentSR] = useState(false);
  const [showAllSRModal, setShowAllSRModal] = useState(false);
  // 阻塞测试 issues（从 filter JQL 端点加载）
  const [blockingIssues, setBlockingIssues] = useState<{ total: number; issues: any[]; error?: string } | null>(null);
  const [blockingLoading, setBlockingLoading] = useState(false);
  // Blocker issues（从 filter JQL 端点加载）
  const [blockerIssues, setBlockerIssues] = useState<{ total: number; issues: any[]; error?: string } | null>(null);
  const [blockerLoading, setBlockerLoading] = useState(false);
  // 弹窗状态
  const [showBlockingModal, setShowBlockingModal] = useState(false);
  const [showBlockerModal, setShowBlockerModal] = useState(false);
  // SR 排序模式
  const [srSortMode, setSrSortMode] = useState<"ai_priority"|"issue_count" | "acceptance" >("ai_priority");
  // SR Issue 弹窗
  const [showIssuePopup, setShowIssuePopup] = useState<{ srCoding: string; issueKeys: string[]; title?: string } | null>(null);
  const [srAiPriority, setSrAiPriority] = useState<Record<string, { risk_level: string; analysis: string; issue_count: number; analyzed_at: string }>>({});
  const [srAiPriorityLoading, setSrAiPriorityLoading] = useState(false);
  const [showLowRiskModal, setShowLowRiskModal] = useState(false);
  // 每日 SR 风险总结报告
  const [dailyReport, setDailyReport] = useState<any>(null);
  const [dailyReportLoading, setDailyReportLoading] = useState(false);
  const [showDailyReportModal, setShowDailyReportModal] = useState(false);
  // 各板块数据提升到父组件，用于概览卡片同步
  const [openReopenData, setOpenReopenData] = useState<any>(null);
  const [submittedModifyingData, setSubmittedModifyingData] = useState<any>(null);
  const [pendingVerificationData, setPendingVerificationData] = useState<any>(null);
  // UTP Weekly 报告数据
  const [utpData, setUtpData] = useState<any>(null);
  const [utpLoading, setUtpLoading] = useState(false);
  const [utpAiLoading, setUtpAiLoading] = useState<Record<string, boolean>>({});
  const [utpExpanded, setUtpExpanded] = useState<Record<string, boolean>>({});
  const [utpJiraModal, setUtpJiraModal] = useState<{ title: string; platform: string; priority: string } | null>(null);
  const [utpJiraIssues, setUtpJiraIssues] = useState<any[]>([]);
  const [utpJiraLoading, setUtpJiraLoading] = useState(false);
  // 用户自定义风险项
  const [customRisks, setCustomRisks] = useState<any[]>([]);
  const [showAddRisk, setShowAddRisk] = useState(false);
  const [newRisk, setNewRisk] = useState({ risk_level: "medium", title: "", description: "", impact_scope: "", owner: "", plan_close_date: "" });

  async function loadCustomRisks() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/custom-risks");
      const d = await res.json();
      setCustomRisks(d.risks || []);
    } catch { /* ignore */ }
  }
  async function addCustomRisk() {
    if (!activeVersion?.id || !newRisk.title.trim()) return;
    await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/custom-risks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newRisk),
    });
    setNewRisk({ risk_level: "medium", title: "", description: "", impact_scope: "", owner: "", plan_close_date: "" });
    setShowAddRisk(false);
    loadCustomRisks();
  }
  async function deleteCustomRisk(id: number) {
    if (!activeVersion?.id) return;
    await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/custom-risks/" + id, { method: "DELETE" });
    loadCustomRisks();
  }

  async function loadUtpData() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/utp/weekly-reports");
      const d = await res.json();
      if (d.platforms && d.platforms.length > 0) setUtpData(d);
    } catch { /* ignore */ }
  }

  async function refreshUtpData() {
    if (!activeVersion?.id) return;
    setUtpLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/utp/weekly-reports/refresh", { method: "POST" });
      const d = await res.json();
      setUtpData(d);
    } catch (e) { alert("UTP Weekly 报告获取失败：" + ((e as any).message || "未知错误")); }
    finally { setUtpLoading(false); }
  }

  async function runUtpAiAnalyze(platform: string) {
    if (!activeVersion?.id) return;
    setUtpAiLoading(prev => ({ ...prev, [platform]: true }));
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/utp/weekly-reports/ai-analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform }),
      });
      const d = await res.json();
      // Update local state
      setUtpData((prev: any) => {
        if (!prev) return prev;
        const platforms = (prev.platforms || []).map((p: any) =>
          p.platform === platform ? { ...p, ai_analysis: d.analysis } : p
        );
        return { ...prev, platforms };
      });
    } catch (e) { alert("AI 分析失败"); }
    finally { setUtpAiLoading(prev => ({ ...prev, [platform]: false })); }
  }

  async function fetchUtpJiraIssues(platform: string, priority: string, planId?: number) {
    if (!activeVersion?.id) return;
    setUtpJiraModal({ title: `${platform} 平台 ${priority} 类缺陷`, platform, priority });
    setUtpJiraLoading(true);
    setUtpJiraIssues([]);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/utp/weekly-reports/jira-issues", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, priority, plan_id: planId || null }),
      });
      const d = await res.json();
      setUtpJiraIssues(d.issues || []);
    } catch (e: any) {
      alert("获取缺陷列表失败：" + (e.message || "未知错误"));
      setUtpJiraModal(null);
    } finally {
      setUtpJiraLoading(false);
    }
  }

  // ALM 加锁 SR 数据
  const [lockedSrData, setLockedSrData] = useState<any>(null);
  const [lockedSrLoading, setLockedSrLoading] = useState(false);
  const [lockedSrDelta, setLockedSrDelta] = useState<any>(null);  // 上次刷新的 delta
  const [newSrData, setNewSrData] = useState<any>(null);  // 今日/本周新增
  // SR 明细弹窗
  const [lockedSrDetailModal, setLockedSrDetailModal] = useState<{ title: string; list: any[]; stageCounts?: Record<string, number>; stageOrder?: string[] } | null>(null);

  async function loadLockedSrData() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/alm-locked-srs");
      const data = await res.json();
      if (data.cached) setLockedSrData(data);
    } catch { /* ignore */ }
    // 同时加载今日/本周新增
    try {
      const r2 = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/alm-locked-srs/new-today");
      const d2 = await r2.json();
      setNewSrData(d2);
    } catch { /* ignore */ }
  }

  async function refreshLockedSrData() {
    if (!activeVersion?.id) return;
    setLockedSrLoading(true);
    setLockedSrDelta(null);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/alm-locked-srs/refresh", { method: "POST" });
      const data = await res.json();
      setLockedSrData(data);
      if (data.delta) setLockedSrDelta(data.delta);
      // 重新加载今日/本周新增
      const r2 = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/alm-locked-srs/new-today");
      const d2 = await r2.json();
      setNewSrData(d2);
    } catch (e) { alert("获取 ALM 加锁 SR 失败：" + ((e as any).message || "未知错误")); }
    finally { setLockedSrLoading(false); }
  }

  // 弹窗打开时锁定页面滚动
  useEffect(() => {
    if (!showDailyReportModal) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [showDailyReportModal]);

  // 切换版本或进入时自动加载最近的报告（优先今天的）
  useEffect(() => {
    if (!activeVersion?.id) return;
    setDailyReport(null);
    setShowDailyReportModal(false);
    fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-daily-risk-report/today")
      .then(r => { if (r.ok) return r.json(); throw new Error("no cache"); })
      .then(data => { if (data && data.data) setDailyReport(data); })
      .catch(() => { /* 尚未生成过报告，正常 */ });
  }, [activeVersion?.id]);

  async function loadSrIssues(manual = false) {
    if (!activeVersion?.id) return;
    setSrLoading(true);
    try {
      // 优先从缓存加载
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-issues-cached");
      const data = await res.json();
      if (data.cached && data.total > 0) {
        setSrIssues(data);
        if (!manual) { setSrLoading(false); return; } // 缓存命中且非手动刷新，不查 Jira
      }
      // 后台刷新（仅手动或缓存为空时触发）
      const forceParam = manual ? "?force=true" : "";
      const refreshRes = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-issues-refresh" + forceParam, { method: "POST" });
      const refreshData = await refreshRes.json();
      setSrIssues(refreshData);
    } catch (e) { setSrIssues({ total: 0, issues: [], error: "请求失败" }); }
    finally { setSrLoading(false); }
  }

  async function loadBlockingIssues() {
    if (!activeVersion?.id) return;
    setBlockingLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/jira-issues/sr_blocking_test?stage=${activeStage || "ALL"}&use_cache=false`);
      const data = await res.json();
      setBlockingIssues({ total: data.total || 0, issues: data.issues || [], error: data.error });
    } catch (e) { setBlockingIssues({ total: 0, issues: [], error: "请求失败" }); }
    finally { setBlockingLoading(false); }
  }

  async function loadBlockerIssues() {
    if (!activeVersion?.id) return;
    setBlockerLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/jira-issues/sr_blocker?stage=${activeStage || "ALL"}&use_cache=false`);
      const data = await res.json();
      setBlockerIssues({ total: data.total || 0, issues: data.issues || [], error: data.error });
    } catch (e) { setBlockerIssues({ total: 0, issues: [], error: "请求失败" }); }
    finally { setBlockerLoading(false); }
  }

  async function loadSrAiAnalyses() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-ai-analysis");
      const data = await res.json();
      setSrAiAnalyses(data.analyses || {});
    } catch (e) { /* ignore */ }
  }

  async function loadSrDetails() {
    if (!activeVersion?.id) return;
    setSrDetailsLoading(true);
    try {
      // 只从数据库缓存加载，不查询 ALM（秒级响应）
      const cachedRes = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-detail-cached");
      const cachedData = await cachedRes.json();
      setSrDetails(cachedData);
    } catch (e) { setSrDetails(null); }
    finally { setSrDetailsLoading(false); }
  }

  async function refreshSrDetails() {
    if (!activeVersion?.id) return;
    setSrDetailsLoading(true);
    try {
      // 从 Jira + ALM 刷新，结果会自动写入数据库缓存
      const refreshRes = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-detail-refresh", { method: "POST" });
      const refreshData = await refreshRes.json();
      setSrDetails(refreshData);
    } catch (e) { setSrDetails(null); }
    finally { setSrDetailsLoading(false); }
  }

  async function generateDailyReport() {
    if (!activeVersion?.id) return;
    setDailyReportLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-daily-risk-report?include_ai=true");
      const data = await res.json();
      setDailyReport(data);
      setShowDailyReportModal(true);
    } catch (e) { alert("生成每日报告失败: " + (e as any).message); }
    finally { setDailyReportLoading(false); }
  }

  async function loadSrAiPriority() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/sr-ai-priority");
      const data = await res.json();
      setSrAiPriority(data.results || {});
      // 如果没有缓存结果且有 SR 数据，自动触发 AI 分析
      if ((!data.results || Object.keys(data.results).length === 0) && srDetails?.sr_list?.length > 0) {
        runSrAiPriority(false);
      }
    } catch { /* ignore */ }
  }

  async function runSrAiPriority(force: boolean = false) {
    if (!activeVersion?.id) return;
    setSrAiPriorityLoading(true);
    // 重新分析时先清除之前的分析结果
    if (force) {
      setSrAiPriority({});
    }
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/sr-ai-priority?force=${force}`, { method: "POST" });
      const data = await res.json();
      if (data.results) setSrAiPriority(data.results);
      if (data.changed === 0 && !force) {
        // 无变化，不需要提示
      }
    } catch (e) { alert("AI 风险等级分析失败"); }
    finally { setSrAiPriorityLoading(false); }
  }

  useEffect(() => {
    if (activeVersion?.id) {
      setSrDetails(null);
      setOpenReopenData(null);
      setSubmittedModifyingData(null);
      setPendingVerificationData(null);
      setLockedSrData(null);
      setUtpData(null);
      setCustomRisks([]);

      // 使用 Promise.all 并行加载所有数据，提升性能
      Promise.all([
        loadSrIssues(),
        loadBlockingIssues(),
        loadBlockerIssues(),
        loadSrDetails(),
        loadSrAiAnalyses(),
        loadSrAiPriority(),
        loadLockedSrData(),
        loadUtpData(),
        loadCustomRisks(),
      ]).catch(err => {
        console.error("[RiskSummary] 并行加载部分失败:", err);
      });
    }
  }, [activeVersion?.id, refreshCount]);

  // Jira 同步后刷新自定义风险
  useEffect(() => {
    if (activeVersion?.id && jiraSyncVersion > 0) {
      loadCustomRisks();
    }
  }, [jiraSyncVersion]);
  const highRiskCols = [
    { key: "issue_key", label: "问题ID" },
    { key: "summary", label: "问题描述" },
    { key: "status", label: "状态" },
    { key: "priority", label: "优先级" },
    { key: "assignee", label: "负责人" },
    { key: "aging_days", label: "遗留天数", render: (i: any) => (i.aging_days ?? "-") + "天" },
  ];
  return (
    <div className="reportSection">
      {/* ═══════════ Part 1: 质量风险总结 ═══════════ */}
      <div className="majorPartHeader" id="sec-ch2-overview">
        <span className="mpIcon">📊</span>
        <div style={{flex:1}}><h2 className="mpTitle">一、质量风险总结</h2><div className="mpSub">SR 需求、基础体验、基础公共、价值点</div></div>
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          <button className="smallBtn" onClick={generateDailyReport} disabled={dailyReportLoading}
            style={{padding:"3px 10px",fontSize:11}} title="AI 综合分析 SR 风险（含每日报告）">
            {dailyReportLoading ? "🤖 分析中..." : "🤖 AI 分析"}
          </button>
          {dailyReport && (
            <button className="smallBtn" onClick={() => setShowDailyReportModal(true)}
              style={{padding:"3px 10px",fontSize:11}}>📋 查看报告</button>
          )}
        </div>
      </div>

      {/* 每日报告弹窗 */}
      {showDailyReportModal && dailyReport && dailyReport.data && (() => {
        const d = dailyReport.data;
        const s = d.summary || {};
        return (
          <div className="modalMask" onClick={() => setShowDailyReportModal(false)}>
            <div className="modal modalWide" onClick={e => e.stopPropagation()}
              onWheel={e => e.stopPropagation()}>
              <div className="modalHeader">
                <h2>📋 {d.version_name} 每日 SR 风险总结报告</h2>
                <span className="modalCount">{d.stage_name} · {dailyReport.generated_at}</span>
              </div>
              <div className="modalScrollBody">
                {/* ── 整体概览 ── */}
                <div className="grid4" style={{marginBottom:14}}>
                  <MetricCard label="SR 需求总数" value={s.total_sr ?? 0} note="当前版本" />
                  <MetricCard label="高风险 SR" value={s.high_risk_sr_count ?? 0} note="AI 判定" danger />
                  <MetricCard label="中风险 SR" value={s.medium_risk_sr_count ?? 0} note="AI 判定" />
                  <MetricCard label="低风险 SR" value={s.low_risk_sr_count ?? 0} note="AI 判定" />
                </div>
                <div className="grid4" style={{marginBottom:14}}>
                  <MetricCard label="SR 遗留问题" value={s.sr_issue_total ?? 0} note="高优未关闭" danger />
                  <MetricCard label="Blocker" value={s.sr_blocker_count ?? 0} note="需立即处理" danger />
                  <MetricCard label="Critical" value={s.sr_critical_count ?? 0} note="高优先级" />
                  <MetricCard label="超龄>30天" value={s.sr_over_30_days ?? 0} note="长期积压" danger />
                </div>

                {/* ── 高风险 SR ── */}
                {(d.high_risk_sr || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px",color:"var(--danger)"}}>🔴 高风险 SR（{d.high_risk_sr.length} 个）</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>SR 编号</th><th>SR 名称</th><th>状态</th><th>Issue 数</th><th>AI 分析</th></tr></thead>
                      <tbody>{d.high_risk_sr.map((sr: any) => (
                        <tr key={sr.coding}>
                          <td style={{fontWeight:600}}>{sr.coding}</td>
                          <td style={{maxWidth:180,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={sr.name}>{sr.name}</td>
                          <td><span className="badge badgeOpen">{sr.status}</span></td>
                          <td style={{textAlign:"center"}}>{sr.issue_count}</td>
                          <td style={{maxWidth:220,fontSize:12,color:"var(--text2)",whiteSpace:"normal"}}>{sr.ai_analysis || "-"}</td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── 中风险 SR ── */}
                {(d.medium_risk_sr || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px",color:"var(--warn)"}}>🟡 中风险 SR（{d.medium_risk_sr.length} 个）</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>SR 编号</th><th>SR 名称</th><th>状态</th><th>Issue 数</th><th>AI 分析</th></tr></thead>
                      <tbody>{d.medium_risk_sr.map((sr: any) => (
                        <tr key={sr.coding}>
                          <td style={{fontWeight:600}}>{sr.coding}</td>
                          <td style={{maxWidth:180,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={sr.name}>{sr.name}</td>
                          <td><span className="badge badgeWarn">{sr.status}</span></td>
                          <td style={{textAlign:"center"}}>{sr.issue_count}</td>
                          <td style={{maxWidth:220,fontSize:12,color:"var(--text2)",whiteSpace:"normal"}}>{sr.ai_analysis || "-"}</td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── Blocker 问题 ── */}
                {(d.sr_blocker_issues || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px",color:"var(--danger)"}}>🚫 Blocker 级遗留问题（{d.sr_blocker_issues.length} 条）</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>Issue Key</th><th>描述</th><th>状态</th><th>负责人</th><th>遗留</th></tr></thead>
                      <tbody>{d.sr_blocker_issues.map((i: any) => (
                        <tr key={i.issue_key}>
                          <td><IssueLink issueKey={i.issue_key} /></td>
                          <td style={{maxWidth:240,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td>
                          <td><span className="badge badgeOpen">{i.status}</span></td>
                          <td>{i.assignee}</td>
                          <td><span className="badge badgeRisk">{i.aging_days}天</span></td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── Critical 问题 ── */}
                {(d.sr_critical_issues || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px",color:"var(--warn)"}}>⚠️ Critical 级遗留问题（Top {d.sr_critical_issues.length} 条）</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>Issue Key</th><th>描述</th><th>状态</th><th>负责人</th><th>遗留</th></tr></thead>
                      <tbody>{d.sr_critical_issues.map((i: any) => (
                        <tr key={i.issue_key}>
                          <td><IssueLink issueKey={i.issue_key} /></td>
                          <td style={{maxWidth:240,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td>
                          <td><span className="badge badgeOpen">{i.status}</span></td>
                          <td>{i.assignee}</td>
                          <td>{i.aging_days}天</td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── 超龄问题 ── */}
                {(d.sr_over_30_days || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px"}}>⏰ 超龄 &gt;30 天遗留问题（Top {d.sr_over_30_days.length} 条）</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>Issue Key</th><th>描述</th><th>优先级</th><th>负责人</th><th>遗留</th></tr></thead>
                      <tbody>{d.sr_over_30_days.map((i: any) => (
                        <tr key={i.issue_key}>
                          <td><IssueLink issueKey={i.issue_key} /></td>
                          <td style={{maxWidth:240,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td>
                          <td><span className={"badge " + (i.priority === "Blocker" ? "badgeRisk" : i.priority === "Critical" ? "badgeWarn" : "badgeInfo")}>{i.priority}</span></td>
                          <td>{i.assignee}</td>
                          <td><span className="badge badgeRisk">{i.aging_days}天</span></td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── 负责人 Top ── */}
                {(d.top_owners || []).length > 0 && (
                  <div style={{marginBottom:14}}>
                    <h3 style={{fontSize:14,margin:"0 0 6px"}}>👤 负责人 Top 10</h3>
                    <div className="modalTableWrap"><table className="dataTable">
                      <thead><tr><th>负责人</th><th>总数</th><th>Blocker</th><th>Critical</th><th>最长遗留</th></tr></thead>
                      <tbody>{d.top_owners.map((o: any) => (
                        <tr key={o.owner}>
                          <td style={{fontWeight:600}}>{o.owner}</td>
                          <td>{o.total}</td>
                          <td>{o.blocker > 0 ? <span className="badge badgeRisk">{o.blocker}</span> : o.blocker}</td>
                          <td>{o.critical > 0 ? <span className="badge badgeWarn">{o.critical}</span> : o.critical}</td>
                          <td>{o.max_aging}天</td>
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </div>
                )}

                {/* ── AI 整体分析 ── */}
                {dailyReport.ai_analysis && (
                  <div style={{marginBottom:8,padding:14,background:"linear-gradient(135deg, var(--accent-soft), var(--bg2))",border:"1px solid var(--accent)",borderRadius:10}}>
                    <h3 style={{fontSize:14,margin:"0 0 8px",color:"var(--accent)"}}>🤖 AI 整体风险分析</h3>
                    <div style={{fontSize:13,lineHeight:1.8,whiteSpace:"pre-wrap",color:"var(--text)"}}>{dailyReport.ai_analysis}</div>
                  </div>
                )}
              </div>
              {/* 弹窗底部 */}
              <div className="modalFooter">
                <span style={{fontSize:11,color:"var(--text3)"}}>📄 已保存: {dailyReport.filename}</span>
                <div style={{display:"flex",gap:8}}>
                  <button className="smallBtn" onClick={() => {
                    const blob = new Blob([dailyReport.report], {type:"text/markdown"});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a"); a.href=url; a.download=dailyReport.filename||"report.md"; a.click(); URL.revokeObjectURL(url);
                  }}>📥 下载 .md</button>
                  <button className="secondaryBtn" onClick={() => setShowDailyReportModal(false)}>关闭</button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
      {/* SR 需求相关风险 */}
      <div id="sec-ch2-1-1"><SectionHeader title="1.1 SR 需求相关风险" /></div>
      {/* ═══════════ SR 数量展示（ALM 加锁 SR 统计） ═══════════ */}
      <div className="card mt12">
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div className="subCardTitle" style={{margin:0}}>📊 SR 数量展示（ALM 加锁 SR）</div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            {lockedSrData?.synced_at && (
              <span style={{fontSize:13,color:"var(--text2)",fontWeight:500}}>
                同步：{lockedSrData.synced_at.slice(0, 16).replace("T", " ")}
              </span>
            )}
            <button className="smallBtn" onClick={refreshLockedSrData} disabled={lockedSrLoading} style={{padding:"3px 10px",fontSize:12}}>
              {lockedSrLoading ? "查询中..." : "🔄 从 ALM 获取"}
            </button>
          </div>
        </div>
        {/* 今日/本周新增已被移入总计卡片内部（见下方） */}
        {!lockedSrData && !lockedSrLoading && (
          <p style={{color:"var(--text3)",textAlign:"center",padding:20,fontSize:13}}>
            点击「从 ALM 获取」查询当前版本加锁 SR 数据
          </p>
        )}
        {lockedSrLoading && (
          <p style={{color:"var(--text3)",textAlign:"center",padding:20,fontSize:13}}>
            ⏳ 正在从 ALM 平台查询加锁 SR 数据，可能需要 30-60 秒...
          </p>
        )}
        {lockedSrData && lockedSrData.total_count > 0 && (() => {
          const s = lockedSrData.status_summary || {};
          const total = lockedSrData.total_count || 0;
          // 计算"不涉及测试"的 SR 数量
          const skipTestCount = (lockedSrData.sr_list || []).filter((r: any) => (r.tag || "").includes("不涉及测试")).length;
          const effectiveTotal = total - skipTestCount;  // 有效总数 = 总数 - 不涉及测试

          // 重新统计"涉及测试"的 SR 的状态分布（排除不涉及测试的）
          const effectiveSrList = (lockedSrData.sr_list || []).filter((r: any) => !(r.tag || "").includes("不涉及测试"));
          const effectiveStatusSummary: Record<string, number> = {};
          effectiveSrList.forEach((r: any) => {
            const code = r.life_cycle_code || "";
            effectiveStatusSummary[code] = (effectiveStatusSummary[code] || 0) + 1;
          });

          const testing = effectiveStatusSummary["TESTING"] || 0;
          const uat = effectiveStatusSummary["UAT"] || 0;
          const completed = effectiveStatusSummary["COMPLETED"] || 0;
          const testingPlusUatPlusCompleted = testing + uat + completed;

          function FractionBadge({ label, value, num, den, color, icon }: { label: string; value: string; num: number; den: number; color: string; icon: string }) {
            return (
              <div style={{flex:1,minWidth:140,textAlign:"center",padding:"12px 8px",borderRadius:10,background:`${color}12`,border:`1px solid ${color}30`}}>
                <div style={{fontSize:22,fontWeight:700,color,marginBottom:4}}>{icon}</div>
                <div style={{fontSize:13,fontWeight:600,color:"var(--text)",marginBottom:4}}>{label}</div>
                <div style={{fontSize:20,fontWeight:800,color,marginBottom:4}}>{value}</div>
                <div style={{fontSize:12,color:"var(--text2)",display:"inline-flex",alignItems:"center",gap:2}}>
                  <span style={{display:"inline-flex",flexDirection:"column",alignItems:"center",lineHeight:1}}>
                    <span style={{fontSize:13,fontWeight:600}}>{num}</span>
                    <span style={{width:"100%",height:1,background:"var(--text2)",margin:"2px 0"}} />
                    <span style={{fontSize:13,fontWeight:600}}>{den}</span>
                  </span>
                </div>
              </div>
            );
          }

          return (
            <>
              {/* 总数大卡片（含今日/本周新增） */}
              <div style={{textAlign:"center",marginBottom:16,padding:"16px 0",background:"linear-gradient(135deg, var(--accent-soft), var(--bg2))",borderRadius:12,border:"1px solid var(--accent)"}}>
                <div style={{fontSize:11,color:"var(--text3)",marginBottom:2}}>ALM 加锁 SR 总计</div>
                <div style={{fontSize:36,fontWeight:800,color:"var(--accent)"}}>{total}</div>
                <div style={{fontSize:11,color:"var(--text3)",marginTop:2}}>
                  lockFlag=YES_LOCK · {activeVersion?.version_name || ""}
                  {skipTestCount > 0 && <span style={{color:"#faad14",marginLeft:8}}>（其中 {skipTestCount} 个不涉及测试）</span>}
                </div>
                {skipTestCount > 0 && <div style={{fontSize:11,color:"var(--text2)",marginTop:2}}>涉及测试 SR：{effectiveTotal} 个（以下比率以此为分母）</div>}
                {/* 今日/本周新增小标签 */}
                {/* 今日/本周新增小标签 */}
                {newSrData && (newSrData.today_count > 0 || newSrData.week_count > 0) && (
                  <div style={{display:"inline-flex",gap:8,flexWrap:"wrap",justifyContent:"center"}}>
                    {newSrData.today_count > 0 && (
                      <span onClick={(e) => {
                        e.stopPropagation();
                        const todayList = (lockedSrData?.sr_list || []).filter((r: any) => (newSrData.today_new || []).includes(r.sr_coding));
                        const ORDER = ["初始","设计","开发","测试","验收","完成"];
                        const sc: Record<string, number> = {}; ORDER.forEach(n => { sc[n] = 0; });
                        todayList.forEach((r: any) => { const k = r.life_cycle_name || ""; if (k in sc) sc[k]++; });
                        setLockedSrDetailModal({ title: `🆕 今日新增 SR（${todayList.length} 个）`, list: todayList, stageCounts: sc, stageOrder: ORDER });
                      }}
                        style={{display:"inline-flex",alignItems:"center",gap:4,padding:"3px 10px",borderRadius:12,background:"#dcfce7",border:"1px solid #86efac",cursor:"pointer",fontSize:12,fontWeight:600,color:"#16a34a",transition:"transform .15s"}}
                        onMouseEnter={(e) => { e.currentTarget.style.transform="scale(1.05)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.transform=""; }}>
                        🆕 今日 +{newSrData.today_count}
                      </span>
                    )}
                    {newSrData.week_count > 0 && (
                      <span onClick={(e) => {
                        e.stopPropagation();
                        const weekList = (lockedSrData?.sr_list || []).filter((r: any) => (newSrData.week_new || []).includes(r.sr_coding));
                        const ORDER = ["初始","设计","开发","测试","验收","完成"];
                        const sc: Record<string, number> = {}; ORDER.forEach(n => { sc[n] = 0; });
                        weekList.forEach((r: any) => { const k = r.life_cycle_name || ""; if (k in sc) sc[k]++; });
                        setLockedSrDetailModal({ title: `📅 本周新增 SR（${weekList.length} 个）`, list: weekList, stageCounts: sc, stageOrder: ORDER });
                      }}
                        style={{display:"inline-flex",alignItems:"center",gap:4,padding:"3px 10px",borderRadius:12,background:"#dbeafe",border:"1px solid #93c5fd",cursor:"pointer",fontSize:12,fontWeight:600,color:"#2563eb",transition:"transform .15s"}}
                        onMouseEnter={(e) => { e.currentTarget.style.transform="scale(1.05)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.transform=""; }}>
                        📅 本周 +{newSrData.week_count}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* 三个关键比率指标（分母排除不涉及测试的 SR） */}
              <div style={{display:"flex",gap:12,marginBottom:16}}>
                <FractionBadge
                  label="转测率"
                  value={`${(effectiveTotal > 0 ? (testingPlusUatPlusCompleted / effectiveTotal * 100) : 0).toFixed(1)}%`}
                  num={testingPlusUatPlusCompleted} den={effectiveTotal}
                  color="#1890ff" icon="🚀"
                />
                <FractionBadge
                  label="测试中占比"
                  value={`${(effectiveTotal > 0 ? (testing / effectiveTotal * 100) : 0).toFixed(1)}%`}
                  num={testing} den={effectiveTotal}
                  color="#faad14" icon="🧪"
                />
                <FractionBadge
                  label="验收通过率"
                  value={`${(effectiveTotal > 0 ? (completed / effectiveTotal * 100) : 0).toFixed(1)}%`}
                  num={completed} den={effectiveTotal}
                  color="#52c41a" icon="✅"
                />
              </div>

              {/* 各状态数量明细（可点击查看详情，已排除不涉及测试的 SR） */}
              <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:8}}>
                {["INITIALIZE", "DESIGNING", "DEVELOPING", "TESTING", "UAT", "COMPLETED"].map(code => {
                  const count = effectiveStatusSummary[code] || 0;
                  const statusName = s[code]?.statusName || code;
                  const pct = effectiveTotal > 0 ? (count / effectiveTotal * 100).toFixed(1) : "0.0";
                  const barColor = code === "COMPLETED" ? "#52c41a" : code === "TESTING" ? "#1890ff" : code === "UAT" ? "#faad14" : code === "DEVELOPING" ? "#13c2c2" : code === "DESIGNING" ? "#722ed1" : "#8c8c8c";
                  return (
                    <div key={code}
                      style={{flex:"1 1 130px",minWidth:120,padding:"8px 12px",borderRadius:8,border:"1px solid var(--card-border)",background:"var(--surface)",cursor:"pointer",transition:"transform .15s,box-shadow .15s"}}
                      onClick={() => {
                        // 只显示涉及测试的 SR
                        const list = effectiveSrList.filter((r: any) => r.life_cycle_code === code);
                        setLockedSrDetailModal({ title: `${statusName} SR（${list.length} 个）`, list, stageCounts: { [statusName]: list.length } });
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,0.08)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.transform=""; e.currentTarget.style.boxShadow=""; }}>
                      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
                        <span style={{fontSize:12,fontWeight:600,color:"var(--text)"}}>{statusName}</span>
                        <span style={{fontSize:14,fontWeight:700,color:barColor}}>{count}</span>
                      </div>
                      <div style={{width:"100%",height:4,background:"var(--bg2)",borderRadius:2,overflow:"hidden"}}>
                        <div style={{width:`${pct}%`,height:"100%",background:barColor,borderRadius:2,transition:"width .3s"}} />
                      </div>
                      <div style={{fontSize:10,color:"var(--text3)",marginTop:2,textAlign:"right"}}>{pct}% · 点击查看</div>
                    </div>
                  );
                })}
              </div>
            </>
          );
        })()}
        {lockedSrData && lockedSrData.total_count === 0 && (
          <p style={{color:"var(--text3)",textAlign:"center",padding:16,fontSize:13}}>当前版本未找到加锁 SR（请确认版本已配置正确的 ALM_SPACE_BID）</p>
        )}
        {/* SR 明细弹窗 */}
        {lockedSrDetailModal && (
          <div className="modalMask" onClick={() => setLockedSrDetailModal(null)}>
            <div className="modal modalWide" style={{maxWidth:800,maxHeight:"80vh",padding:0}} onClick={e => e.stopPropagation()}>
              <div style={{padding:"16px 20px",borderBottom:"1px solid var(--card-border)"}}>
                <h2 style={{fontSize:15,margin:0}}>{lockedSrDetailModal.title}</h2>
                <p style={{fontSize:11,color:"var(--text3)",margin:"4px 0 0"}}>共 {lockedSrDetailModal.list.length} 条记录</p>
                {/* 各阶段新增数量分布（按标准顺序展示） */}
                {lockedSrDetailModal.stageCounts && Object.keys(lockedSrDetailModal.stageCounts).length > 0 && (
                  <div style={{display:"flex",gap:6,flexWrap:"wrap",marginTop:8}}>
                    {(lockedSrDetailModal.stageOrder || Object.keys(lockedSrDetailModal.stageCounts)).map((stage: string) => {
                      const cnt = lockedSrDetailModal.stageCounts![stage] ?? 0;
                      const STAGE_COLORS: Record<string, string> = {"初始":"#8c8c8c","设计":"#722ed1","开发":"#13c2c2","测试":"#1890ff","验收":"#faad14","完成":"#52c41a"};
                      const color = STAGE_COLORS[stage] || "var(--accent)";
                      return (
                        <span key={stage} style={{display:"inline-flex",alignItems:"center",gap:3,padding:"2px 8px",borderRadius:10,background:`${color}15`,border:`1px solid ${color}40`,fontSize:11,fontWeight:600,color}}>
                          {stage}：<span style={{fontWeight:800}}>{cnt}</span>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="modalScrollBody" style={{padding:"12px 20px"}}>
                {lockedSrDetailModal.list.length > 0 ? (
                  <div style={{overflowX:"auto"}}>
                    <table className="dataTable" style={{margin:0,width:"100%"}}>
                      <thead><tr>
                        <th style={{whiteSpace:"nowrap",minWidth:140}}>SR 编号</th>
                        <th>需求名称</th>
                        <th style={{whiteSpace:"nowrap",width:70}}>状态</th>
                        <th style={{whiteSpace:"nowrap",width:70}}>优先级</th>
                        <th style={{whiteSpace:"nowrap",width:100}}>测试主责人</th>
                      </tr></thead>
                      <tbody>
                        {lockedSrDetailModal.list.map((sr: any) => {
                          const almUrl = `https://alm.transsion.com/#/space/${activeVersion?.alm_space_bid || ""}/${activeVersion?.alm_app_bid || ""}?viewMode=tableView&appTypeCode=&appType=OBJECT`;
                          return (
                            <tr key={sr.sr_coding}>
                              <td style={{whiteSpace:"nowrap"}}>
                                <a className="issueId" href={almUrl} target="_blank" rel="noreferrer"
                                  style={{cursor:"pointer",textDecoration:"underline",textDecorationStyle:"dotted",textUnderlineOffset:3,fontWeight:600,fontSize:12}}
                                  title="点击打开 ALM 并复制 SR 编号"
                                  onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(sr.sr_coding).catch(() => {}); }}>
                                  {sr.sr_coding}
                                </a>
                              </td>
                              <td style={{maxWidth:250,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",fontSize:12}} title={sr.sr_name}>{sr.sr_name || "-"}</td>
                              <td><span className="badge badgeInfo" style={{fontSize:10}}>{sr.life_cycle_name || sr.life_cycle_code}</span></td>
                              <td style={{fontSize:12}}>{sr.priority || "-"}</td>
                              <td style={{fontSize:11,color:"var(--text2)"}}>{sr.test_representative || sr.person_responsible || "-"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{color:"var(--text3)",textAlign:"center",padding:20}}>暂无数据</p>
                )}
              </div>
              <div style={{padding:"10px 20px",borderTop:"1px solid var(--card-border)",textAlign:"right"}}>
                <button className="smallBtn" onClick={() => exportLockedSrList(lockedSrDetailModal.title, lockedSrDetailModal.list, activeVersion?.alm_space_bid, activeVersion?.alm_app_bid)} style={{padding:"5px 12px",fontSize:12,marginRight:8}}>📥 导出 Excel</button>
                <button className="secondaryBtn" onClick={() => setLockedSrDetailModal(null)}>关闭</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* SR 测试进度（UTP）— 放在 SR 遗留问题前面 */}
      {activeVersion && <SrTestProgress activeVersion={activeVersion} lockedSrData={lockedSrData} />}

      {/* SR 遗留问题 */}
      <div className="sectionHeader">
        <span />
        <h2>SR 遗留问题</h2>
      </div>
      {/* 3个 JQL 编辑器统一展示 */}
      {activeVersion?.id && (
        <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:8}}>
          {[
            { key: "sr_backlog", label: "SR 遗留问题", color: "var(--accent)" },
            { key: "sr_blocking_test", label: "阻塞测试", color: "#ff4d4f" },
            { key: "sr_blocker", label: "Blocker", color: "#ff4d4f" },
          ].map(f => (
            <div key={f.key} style={{flex:"1 1 280px",minWidth:260,border:"1px solid var(--card-border)",borderRadius:8,padding:"6px 10px",background:"var(--surface)"}}>
              <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}>
                <span style={{width:8,height:8,borderRadius:"50%",background:f.color,flexShrink:0}} />
                <span style={{fontSize:12,fontWeight:600,color:"var(--text)"}}>{f.label}</span>
              </div>
              <JiraFilterEditor versionId={activeVersion.id} filterKey={f.key} activeStage={activeStage} />
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <div className="grid4">
          <MetricCard label="SR 遗留问题总数" value={srIssues?.total ?? (srLoading ? "..." : 0)} note="summary含SR · 高优 · 未关闭" danger />
          <div className={"metricCard danger"} style={{cursor:"pointer",transition:"transform .15s,box-shadow .15s"}} onClick={() => setShowBlockingModal(true)} onMouseEnter={(e) => { e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,0.1)"; }} onMouseLeave={(e) => { e.currentTarget.style.transform=""; e.currentTarget.style.boxShadow=""; }}>
            <div className="metricLabel">阻塞测试</div>
            <div className="metricValue">{blockingIssues?.total ?? (blockingLoading ? "..." : 0)}</div>
            <div className="metricNote">点击查看详情</div>
          </div>
          <div className={"metricCard danger"} style={{cursor:"pointer",transition:"transform .15s,box-shadow .15s"}} onClick={() => setShowBlockerModal(true)} onMouseEnter={(e) => { e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,0.1)"; }} onMouseLeave={(e) => { e.currentTarget.style.transform=""; e.currentTarget.style.boxShadow=""; }}>
            <div className="metricLabel">Blocker</div>
            <div className="metricValue">{blockerIssues?.total ?? (blockerLoading ? "..." : 0)}</div>
            <div className="metricNote">点击查看详情</div>
          </div>
          <MetricCard label="SR 数量" value={srDetails?.total_current_version ?? (srDetailsLoading ? "..." : 0)} note={`关联 ${srDetails?.current_version_issue_count ?? 0} 个 Issue`} />
        </div>
        {/* 阻塞测试弹窗 */}
        {showBlockingModal && blockingIssues && (
          <IssueListModal title="阻塞测试 SR 遗留问题" issues={blockingIssues.issues} columns={highRiskCols} onClose={() => setShowBlockingModal(false)} />
        )}
        {/* Blocker弹窗 */}
        {showBlockerModal && blockerIssues && (
          <IssueListModal title="Blocker SR 遗留问题" issues={blockerIssues.issues} columns={highRiskCols} onClose={() => setShowBlockerModal(false)} />
        )}
        {/* 底部操作栏 */}
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:10,paddingTop:8,borderTop:"1px dashed var(--card-border)"}}>
          <span style={{fontSize:11,color:"var(--text3)"}}>
            {srIssues?.synced_at ? `SR数据更新：${srIssues.synced_at.slice(5, 16).replace("T", " ")}` : ""}
          </span>
          <div style={{display:"flex",gap:8}}>
            <button className="smallBtn" onClick={() => { loadSrIssues(true); loadBlockingIssues(); loadBlockerIssues(); }} disabled={srLoading || blockingLoading || blockerLoading}
              style={{padding:"4px 12px",fontSize:12}}>
              {(srLoading || blockingLoading || blockerLoading) ? "刷新中..." : "🔄 刷新 SR"}
            </button>
            {srIssues && srIssues.issues && srIssues.issues.length > 0 && (
              <button className="smallBtn" onClick={() => exportIssueList("SR遗留问题明细", srIssues.issues, JIRA_BROWSE)} style={{padding:"4px 12px",fontSize:12}}>📥 导出SR遗留问题明细（{srIssues.total} 条）</button>
            )}
          </div>
        </div>
      </div>

      {/* SR 需求详情（来自 ALM） */}
      <div className="card mt12">
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div>
            <div className="subCardTitle" style={{margin:0}}>SR 需求详情（ALM）- {(activeVersion?.version_name || "-") + "版本"}</div>
            {(() => {
              // 取第一条 SR 的 synced_at 作为整体时间戳
              const ts = srDetails?.sr_list?.[0]?.synced_at;
              return ts ? (
                <span style={{fontSize:11,color:"var(--text2)",fontWeight:500,marginTop:2,display:"inline-block"}}>
                  📅 上次刷新：{ts.replace("T", " ").slice(0, 16)}
                </span>
              ) : (
                <span style={{fontSize:11,color:"var(--text3)",marginTop:2,display:"inline-block"}}>
                  尚未刷新（点击右侧按钮从 ALM 获取）
                </span>
              );
            })()}
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            {srDetails?.alm_page_url && (
              <a className="textLink" href={srDetails.alm_page_url} target="_blank" rel="noreferrer" style={{fontSize:12}}>🔗 打开 ALM 平台</a>
            )}
            <button className="smallBtn" onClick={refreshSrDetails} disabled={srDetailsLoading} style={{padding:"3px 10px",fontSize:12}}>
              {srDetailsLoading ? "刷新中..." : "🔄 刷新 ALM"}
            </button>
          </div>
        </div>
        {srDetails?.error ? (
          <p style={{color:"#dc2626",textAlign:"center",padding:16}}>⚠ {srDetails.error}</p>
        ) : srDetailsLoading ? (
          <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>正在从 ALM 查询 SR 详情，请稍候...</p>
        ) : srDetails && srDetails.sr_list && srDetails.sr_list.length > 0 ? (
          <>
            {srDetails.warning && (
              <p style={{color:"#d97706",fontSize:12,margin:"0 0 8px 0",padding:"6px 10px",background:"#fffbeb",borderRadius:4,border:"1px solid #fde68a"}}>⚠ {srDetails.warning}</p>
            )}
            {(() => {
              const currentSRs = srDetails.sr_list.filter((s: any) => !s.is_other_version);
              const otherSRs = srDetails.sr_list.filter((s: any) => s.is_other_version);

              // 计算距离评审节点的天数
              function getDaysUntilAcceptance(sr: any): number | null {
                if (!sr.planned_acceptance) return null;
                try {
                  const acceptDate = new Date(sr.planned_acceptance);
                  const today = new Date();
                  today.setHours(0, 0, 0, 0);
                  acceptDate.setHours(0, 0, 0, 0);
                  return Math.ceil((acceptDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
                } catch {
                  return null;
                }
              }

              // 排序
              let sortedCurrentSRs = [...currentSRs];
              if (srSortMode === "ai_priority") {
                sortedCurrentSRs.sort((a: any, b: any) => {
                  const la = (srAiPriority[a.coding]?.risk_level === "high") ? 0 : (srAiPriority[a.coding]?.risk_level === "medium") ? 1 : 2;
                  const lb = (srAiPriority[b.coding]?.risk_level === "high") ? 0 : (srAiPriority[b.coding]?.risk_level === "medium") ? 1 : 2;
                  if (la !== lb) return la - lb;
                  return (b.issue_count ?? 0) - (a.issue_count ?? 0);
                });
              } else if (srSortMode === "acceptance") {
                sortedCurrentSRs.sort((a: any, b: any) => {
                  const da = getDaysUntilAcceptance(a);
                  const db = getDaysUntilAcceptance(b);
                  // 没有日期的排最后
                  if (da === null && db === null) return 0;
                  if (da === null) return 1;
                  if (db === null) return -1;
                  // 距离越近（天数越小）排越前面
                  return da - db;
                });
              }
              const top10SRs = sortedCurrentSRs.slice(0, 10);
              const restSRs = sortedCurrentSRs.slice(10);

              const SORT_OPTIONS = [
                { key: "ai_priority", label: "🤖 AI 风险等级" },
                { key: "acceptance", label: "📅 计划验收紧迫度" },
              ];

              // AI 模式分组
              const highRiskSRs = srSortMode === "ai_priority" ? sortedCurrentSRs.filter((s: any) => srAiPriority[s.coding]?.risk_level === "high") : [];
              const mediumRiskSRs = srSortMode === "ai_priority" ? sortedCurrentSRs.filter((s: any) => srAiPriority[s.coding]?.risk_level === "medium") : [];
              const lowRiskSRs = srSortMode === "ai_priority" ? sortedCurrentSRs.filter((s: any) => !srAiPriority[s.coding] || srAiPriority[s.coding]?.risk_level === "low") : [];
              const aiDisplaySRs = [...highRiskSRs, ...mediumRiskSRs];

              // SR 行渲染
              function renderSRRow(sr: any, showRiskBadge?: boolean) {
                const ai = srAiAnalyses[sr.coding];
                const aiPri = srAiPriority[sr.coding];
                const singleLoading = srAiLoadingSingle[sr.coding];
                // 构建 ALM SR 详情链接（打开 ALM 空间，用户可粘贴 SR 编号搜索）
                const almSpaceUrl = `https://alm.transsion.com/#/space/${activeVersion?.alm_space_bid || ""}/${activeVersion?.alm_app_bid || ""}?viewMode=tableView&appTypeCode=&appType=OBJECT`;
                // 获取严重等级分布
                const sevCount = sr.issue_severity_count || {};
                const sevKeys = sr.issue_severity_keys || {};
                // 计算距离评审节点的天数
                const daysUntil = getDaysUntilAcceptance(sr);
                const daysText = daysUntil === null ? "" : daysUntil < 0 ? `已逾期${Math.abs(daysUntil)}天` : daysUntil === 0 ? "今天到期" : `还有${daysUntil}天`;
                const daysColor = daysUntil === null ? "var(--text3)" : daysUntil < 0 ? "#dc2626" : daysUntil <= 7 ? "#ea580c" : daysUntil <= 14 ? "#ca8a04" : "#16a34a";
                const diScore = calcDI(sevCount);
                const diRisk = diScore >= 30 ? "高" : diScore >= 10 ? "中" : "低";
                const diColor = diScore >= 30 ? "#dc2626" : diScore >= 10 ? "#ea580c" : "#16a34a";
                return (
                  <tr key={sr.coding}>
                    <td style={{whiteSpace:"nowrap"}}>
                      <a className="issueId" href={almSpaceUrl} target="_blank" rel="noreferrer"
                        style={{cursor:"pointer",textDecoration:"underline",textDecorationStyle:"dotted",textUnderlineOffset:3}}
                        title="点击打开 ALM 并复制 SR 编号"
                        onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(sr.coding).catch(() => {}); }}>{sr.coding}</a>
                    </td>
                    <td style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={sr.name}>{sr.name || "-"}</td>
                    <td style={{textAlign:"center",whiteSpace:"nowrap"}}>
                      {/* A/B/C 类合并显示 */}
                      <span style={{color:"#dc2626",cursor:sevCount.blocker > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.blocker > 0 ? "1px dashed #dc2626" : "none"}}
                        onClick={() => sevCount.blocker > 0 && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.blocker || [], title: "A类(Blocker)" })}>
                        {sevCount.blocker || 0}
                      </span>
                      <span style={{color:"var(--text3)",margin:"0 2px"}}>/</span>
                      <span style={{color:"#ea580c",cursor:sevCount.critical > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.critical > 0 ? "1px dashed #ea580c" : "none"}}
                        onClick={() => sevCount.critical > 0 && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.critical || [], title: "B类(Critical)" })}>
                        {sevCount.critical || 0}
                      </span>
                      <span style={{color:"var(--text3)",margin:"0 2px"}}>/</span>
                      <span style={{color:"#ca8a04",cursor:sevCount.major > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.major > 0 ? "1px dashed #ca8a04" : "none"}}
                        onClick={() => sevCount.major > 0 && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.major || [], title: "C类(Major)" })}>
                        {sevCount.major || 0}
                      </span>
                    </td>
                    <td style={{textAlign:"center",whiteSpace:"nowrap"}}>
                      <span style={{color:diColor,fontWeight:700,fontSize:13}}>{diScore.toFixed(1)}</span>
                      <span style={{color:diColor,fontSize:10,marginLeft:2}}>({diRisk})</span>
                    </td>
                    <td style={{textAlign:"center",whiteSpace:"nowrap"}}>
                      {srSortMode === "acceptance" ? (
                        // 计划验收紧迫度模式：按时间划分风险等级
                        daysUntil !== null ? (
                          <span className={"badge " + (daysUntil < 0 ? "badgeRisk" : daysUntil <= 7 ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px"}}>
                            {daysUntil < 0 ? "已逾期" : daysUntil <= 7 ? "即将到期" : "正常"}
                          </span>
                        ) : <span style={{fontSize:11,color:"var(--text3)"}}>-</span>
                      ) : (
                        // AI 风险等级模式：使用 AI 分析结果
                        aiPri ? (
                          <span className={"badge " + (aiPri.risk_level === "high" ? "badgeRisk" : aiPri.risk_level === "medium" ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px"}}>
                            {aiPri.risk_level === "high" ? "高风险" : aiPri.risk_level === "medium" ? "中风险" : "低风险"}
                          </span>
                        ) : (
                          // AI未分析时，用DI值作为参考风险等级
                          <span className={"badge " + (diScore >= 30 ? "badgeRisk" : diScore >= 10 ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px",opacity:0.7}} title="基于DI值估算，未经AI分析">
                            {diScore >= 30 ? "高(估)" : diScore >= 10 ? "中(估)" : "低(估)"}
                          </span>
                        )
                      )}
                    </td>
                    <td style={{whiteSpace:"normal",wordBreak:"break-word",lineHeight:1.6,fontSize:12}}>{sr.test_module_owners_display || "-"}</td>
                    <td style={{whiteSpace:"nowrap",fontSize:12}}>
                      <div>{sr.planned_acceptance ? sr.planned_acceptance.slice(0, 10) : "-"}</div>
                      {daysText && <div style={{color:daysColor,fontSize:10,marginTop:2}}>{daysText}</div>}
                    </td>
                    <td style={{maxWidth:200,overflow:"hidden"}}>
                      {aiPri?.analysis ? (
                        <div style={{fontSize:12,lineHeight:1.5,color:"var(--text2)"}}>
                          <div style={{maxHeight:60,overflow:"auto",wordBreak:"break-word",whiteSpace:"normal"}} title={aiPri.analysis}>{aiPri.analysis}</div>
                          <div style={{fontSize:10,color:"var(--text3)",marginTop:2,whiteSpace:"nowrap"}}>{aiPri.analyzed_at?.slice(0, 16).replace("T", " ")}</div>
                        </div>
                      ) : ai ? (
                        <div style={{fontSize:12,lineHeight:1.5,color:"var(--text2)"}}>
                          <div style={{maxHeight:60,overflow:"auto",wordBreak:"break-word",whiteSpace:"normal"}} title={ai.analysis}>{ai.analysis}</div>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:4,gap:4}}>
                            <span style={{fontSize:10,color:"var(--text3)",whiteSpace:"nowrap",flexShrink:0}}>{ai.analyzed_at?.slice(0, 16).replace("T", " ")}</span>
                            <button className="smallBtn" style={{padding:"2px 6px",fontSize:10,borderRadius:4,color:"var(--danger)",border:"1px solid #fecaca",background:"transparent",flexShrink:0}}
                              onClick={async (e) => { e.stopPropagation(); setSrAiAnalyses(prev => { const n = { ...prev }; delete n[sr.coding]; return n; }); try { await fetch(API_BASE + `/api/versions/${activeVersion?.id}/sr-ai-analysis?sr_coding=${encodeURIComponent(sr.coding)}`, { method: "DELETE" }); } catch {} }}>🗑</button>
                          </div>
                        </div>
                      ) : (
                        <button className="smallBtn" disabled={singleLoading || srAiLoading}
                          style={{padding:"3px 10px",fontSize:11,whiteSpace:"nowrap",background:singleLoading?"var(--accent-soft)":"transparent",color:singleLoading?"var(--accent)":"var(--text2)",border:"1px solid var(--card-border)",borderRadius:6,cursor:singleLoading?"wait":"pointer"}}
                          onClick={async (e) => {
                            e.stopPropagation();
                            setSrAiLoadingSingle(prev => ({ ...prev, [sr.coding]: true }));
                            // 先清除这个SR的旧分析结果
                            setSrAiAnalyses(prev => { const n = { ...prev }; delete n[sr.coding]; return n; });
                            setSrAiPriority(prev => { const n = { ...prev }; delete n[sr.coding]; return n; });
                            try {
                              const res = await fetch(API_BASE + `/api/versions/${activeVersion?.id}/sr-ai-analysis?sr_coding=${encodeURIComponent(sr.coding)}`, { method: "POST" });
                              const data = await res.json();
                              setSrAiAnalyses(prev => ({ ...prev, ...data.analyses }));
                            } catch { alert("AI 分析失败"); }
                            finally { setSrAiLoadingSingle(prev => ({ ...prev, [sr.coding]: false })); }
                          }}>
                          {singleLoading ? "🤖 分析中..." : "🤖 单独分析"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              }
              return (
                <>
                  {/* SR 表格（可展开/收起） */}
                  {currentSRs.length > 0 && (
                    <div className="subCard" style={{padding: 0}}>
                      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px",cursor:"pointer",borderRadius: expandedCurrentSR ? "8px 8px 0 0" : 8,background: expandedCurrentSR ? "var(--accent-soft)" : "transparent"}} onClick={() => setExpandedCurrentSR(!expandedCurrentSR)}>
                        <div className="subCardTitle" style={{margin:0,display:"flex",alignItems:"center",gap:8}}>
                          <span style={{fontSize:12,color:"var(--text3)",transition:"transform .2s",display:"inline-block",transform: expandedCurrentSR ? "rotate(90deg)" : "rotate(0deg)"}}>▶</span>
                          ✅{currentSRs.length} 个 SR，关联 {srDetails.current_version_issue_count ?? 0} 个 Issue
                        </div>
                        <span style={{fontSize:12,color:"var(--text3)"}}>{expandedCurrentSR ? "▲ 收起" : "▼ 展开"}</span>
                      </div>
                      {expandedCurrentSR && (
                        <>
                          {/* 排序切换 + 操作按钮 */}
                          <div style={{padding:"8px 16px",display:"flex",alignItems:"center",justifyContent:"space-between",borderBottom:"1px dashed var(--card-border)"}}>
                            <div style={{display:"flex",gap:4}}>
                              {SORT_OPTIONS.map(opt => (
                                <button key={opt.key} onClick={(e) => { e.stopPropagation(); setSrSortMode(opt.key as any); }}
                                  style={{
                                    padding:"4px 12px",fontSize:11,fontWeight:srSortMode===opt.key?600:400,borderRadius:6,cursor:"pointer",transition:"all .15s",
                                    background:srSortMode===opt.key?"var(--accent)":"var(--surface)",
                                    color:srSortMode===opt.key?"#fff":"var(--text2)",
                                    border:srSortMode===opt.key?"1px solid var(--accent)":"1px solid var(--card-border)",
                                  }}>
                                  {opt.label}
                                </button>
                              ))}
                            </div>
                            <div style={{display:"flex",gap:6}}>
                              <button className="smallBtn" disabled={srSortMode === "ai_priority" ? srAiPriorityLoading : srAiLoading} style={{padding:"3px 10px",fontSize:11}}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (srSortMode === "ai_priority") {
                                    runSrAiPriority(true);
                                  } else {
                                    // 批量分析 Top 10
                                    setSrAiLoading(true);
                                    const list = top10SRs;
                                    setSrAiAnalyses(prev => { const next = { ...prev }; list.forEach((s: any) => { delete next[s.coding]; }); return next; });
                                    const codings = list.map((s: any) => `sr_coding=${encodeURIComponent(s.coding)}`).join("&");
                                    fetch(API_BASE + `/api/versions/${activeVersion?.id}/sr-ai-analysis?${codings}`, { method: "POST" })
                                      .then(r => r.json()).then(data => { setSrAiAnalyses(prev => ({ ...prev, ...data.analyses })); })
                                      .catch(() => { alert("AI 分析失败"); })
                                      .finally(() => { setSrAiLoading(false); });
                                  }
                                }}>
                                {(srSortMode === "ai_priority" ? srAiPriorityLoading : srAiLoading) ? "🤖 分析中..." : "🤖 重新分析"}
                              </button>
                            </div>
                          </div>

                          {/* AI 风险等级模式 */}
                          {srSortMode === "ai_priority" ? (
                            srAiPriorityLoading ? (
                              <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>🤖 AI 正在综合分析所有 SR 风险等级，请稍候...</p>
                            ) : Object.keys(srAiPriority).length === 0 ? (
                              <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>暂无 AI 分析结果，点击「🤖 重新分析」开始</p>
                            ) : (
                              <>
                                <div style={{overflowX:"auto",maxHeight:480,overflowY:"auto"}}>
                                  <table className="dataTable" style={{tableLayout:"fixed",margin:0,width:"100%"}}>
                                    <thead style={{position:"sticky",top:0,zIndex:1,background:"var(--surface)"}}><tr>
                                      <th style={{whiteSpace:"nowrap",width:160}}>SR 编号</th>
                                      <th style={{width:"18%"}}>需求名称</th>
                                      <th style={{whiteSpace:"nowrap",width:90,textAlign:"center"}}>A/B/C类</th>
                                      <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>DI值</th>
                                      <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>{srSortMode === "acceptance" ? "紧迫度" : "风险等级"}</th>
                                      <th style={{width:160}}>测试模块主责人</th>
                                      <th style={{whiteSpace:"nowrap",width:120}}>计划验收</th>
                                      <th>AI 风险分析</th>
                                    </tr></thead>
                                    <tbody>
                                      {aiDisplaySRs.map((sr: any) => renderSRRow(sr, true))}
                                      {aiDisplaySRs.length === 0 && <tr><td colSpan={8} style={{textAlign:"center",color:"var(--text3)",padding:20}}>无高/中风险 SR</td></tr>}
                                    </tbody>
                                  </table>
                                </div>
                                {lowRiskSRs.length > 0 && (
                                  <div style={{padding:"8px 16px",textAlign:"center",borderTop:"1px dashed var(--card-border)"}}>
                                    <button className="viewMoreBtn" onClick={(e) => { e.stopPropagation(); setShowLowRiskModal(true); }}>
                                      查看低风险 SR（{lowRiskSRs.length} 个）→
                                    </button>
                                  </div>
                                )}
                                <div style={{padding:"6px 16px",textAlign:"right",borderTop:"1px dashed var(--card-border)"}}>
                                  <button className="smallBtn" onClick={(e) => { e.stopPropagation(); exportSrList("SR需求详情_AI风险等级排序", sortedCurrentSRs, activeVersion?.alm_space_bid, activeVersion?.alm_app_bid, srAiPriority, "ai_priority"); }} style={{padding:"4px 12px",fontSize:12}}>📥 导出AI风险等级排序（{sortedCurrentSRs.length} 个）</button>
                                </div>
                              </>
                            )
                          ) : (
                            <>
                              <div style={{overflowX:"auto"}}>
                                <table className="dataTable" style={{tableLayout:"fixed",margin:0,width:"100%"}}>
                                  <thead><tr>
                                    <th style={{whiteSpace:"nowrap",width:160}}>SR 编号</th>
                                    <th style={{width:"18%"}}>需求名称</th>
                                    <th style={{whiteSpace:"nowrap",width:90,textAlign:"center"}}>A/B/C类</th>
                                    <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>DI值</th>
                                    <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>{srSortMode === "acceptance" ? "紧迫度" : "风险等级"}</th>
                                    <th style={{width:160}}>测试模块主责人</th>
                                    <th style={{whiteSpace:"nowrap",width:120}}>计划验收</th>
                                    <th>AI 风险分析</th>
                                  </tr></thead>
                                  <tbody>
                                    {top10SRs.map((sr: any) => renderSRRow(sr, false))}
                                  </tbody>
                                </table>
                              </div>
                              {restSRs.length > 0 && (
                                <div style={{padding:"8px 16px",textAlign:"center",borderTop:"1px dashed var(--card-border)"}}>
                                  <button className="viewMoreBtn" onClick={(e) => { e.stopPropagation(); setShowAllSRModal(true); }}>
                                    查看更多（{restSRs.length} 个 SR）→
                                  </button>
                                  <div style={{fontSize:11,color:"var(--text3)",marginTop:4}}>其余 SR 可单独点击「🤖 单独分析」</div>
                                </div>
                              )}
                              <div style={{padding:"6px 16px",textAlign:"right",borderTop:"1px dashed var(--card-border)"}}>
                                <button className="smallBtn" onClick={(e) => { e.stopPropagation(); exportSrList("SR需求详情_计划验收紧迫度排序", sortedCurrentSRs, activeVersion?.alm_space_bid, activeVersion?.alm_app_bid, srAiPriority, "acceptance"); }} style={{padding:"4px 12px",fontSize:12}}>📥 导出计划验收紧迫度排序（{sortedCurrentSRs.length} 个）</button>
                              </div>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {/* 低风险 SR 弹窗 */}
                  {showLowRiskModal && lowRiskSRs.length > 0 && (
                    <SRDetailListModal
                      title={`低风险 SR（${lowRiskSRs.length} 个）`}
                      srList={lowRiskSRs}
                      srAiAnalyses={srAiAnalyses}
                      srAiPriority={srAiPriority}
                      sortMode={srSortMode}
                      srAiLoadingSingle={srAiLoadingSingle}
                      setSrAiAnalyses={setSrAiAnalyses}
                      setSrAiLoadingSingle={setSrAiLoadingSingle}
                      activeVersion={activeVersion}
                      setShowIssuePopup={setShowIssuePopup}
                      onClose={() => setShowLowRiskModal(false)}
                    />
                  )}

                  {/* 查看更多 SR 弹窗 */}
                  {showAllSRModal && restSRs.length > 0 && (
                    <SRDetailListModal
                      title={`其余当前版本 SR（${restSRs.length} 个）`}
                      srList={restSRs}
                      srAiAnalyses={srAiAnalyses}
                      srAiPriority={srAiPriority}
                      sortMode={srSortMode}
                      srAiLoadingSingle={srAiLoadingSingle}
                      setSrAiAnalyses={setSrAiAnalyses}
                      setSrAiLoadingSingle={setSrAiLoadingSingle}
                      activeVersion={activeVersion}
                      setShowIssuePopup={setShowIssuePopup}
                      onClose={() => setShowAllSRModal(false)}
                    />
                  )}
                </>
              );
            })()}
          </>
        ) : srDetails ? (
          <p style={{color:"var(--text3)",textAlign:"center",padding:16}}>暂无 SR 需求数据（请先点击「查询 ALM」）</p>
        ) : (
          <p style={{color:"var(--text3)",textAlign:"center",padding:16}}>点击「查询 ALM」从 ALM 平台获取 SR 需求详情</p>
        )}
      </div>

      {/* SR Issue 弹窗 */}
      {showIssuePopup && (
        <div className="modalMask" onClick={() => setShowIssuePopup(null)}>
          <div className="modal modalWide" style={{width:480,maxWidth:"90vw",maxHeight:"70vh",padding:0}} onClick={e => e.stopPropagation()}>
            {/* 固定头部 */}
            <div style={{padding:"20px 24px 12px",borderBottom:"1px solid var(--card-border)"}}>
              <h2 style={{fontSize:16,margin:0}}>📋 {showIssuePopup.srCoding} 关联 Issue {showIssuePopup.title ? `(${showIssuePopup.title})` : ""}</h2>
              <p style={{fontSize:12,color:"var(--text3)",margin:"4px 0 0"}}>共 {showIssuePopup.issueKeys.length} 个 Issue，点击跳转 Jira</p>
            </div>
            {/* 可滚动内容区 */}
            <div className="modalScrollBody" style={{padding:"12px 24px"}}>
              <div style={{display:"flex",flexDirection:"column",gap:6}}>
                {showIssuePopup.issueKeys.map((key: string) => (
                  <a key={key} href={`${JIRA_BROWSE}${key}`} target="_blank" rel="noreferrer"
                    style={{fontSize:13,color:"var(--accent)",textDecoration:"underline",padding:"6px 10px",borderRadius:6,background:"var(--surface)",display:"block"}}>
                    {key}
                  </a>
                ))}
              </div>
            </div>
            {/* 固定底部 */}
            <div style={{padding:"12px 24px",borderTop:"1px solid var(--card-border)",textAlign:"right"}}>
              <button className="secondaryBtn" onClick={() => setShowIssuePopup(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 基础体验相关风险 */}
      <div id="sec-ch2-1-2"><SectionHeader title="1.2 基础体验相关风险" /></div>
      <div className="sectionHeader"><span /><h2>稳定性专项</h2><span style={{fontSize:11,color:"var(--text3)",background:"var(--bg2)",padding:"3px 8px",borderRadius:6,marginLeft:8}}>🔒</span></div>
      <StabilitySpecialSection activeVersion={activeVersion} />
      <div className="sectionHeader"><span /><h2>性能专项</h2><span style={{fontSize:11,color:"var(--text3)",background:"var(--bg2)",padding:"3px 8px",borderRadius:6,marginLeft:8}}>⚡</span></div>
      <PerformanceSpecialSection activeVersion={activeVersion} />
      <div className="sectionHeader"><span /><h2>续航温升</h2><span style={{fontSize:11,color:"var(--text3)",background:"var(--bg2)",padding:"3px 8px",borderRadius:6,marginLeft:8}}>🔋</span></div>
      <BatterySpecialSection activeVersion={activeVersion} />

      {/* 基础公共相关风险 - UTP Weekly 测试报告 */}
      <div id="sec-ch2-1-3"><SectionHeader title="1.3 基础公共相关风险（UTP Weekly 报告）" /></div>
      <div className="card">
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div className="subCardTitle" style={{margin:0}}>UTP Weekly 测试报告</div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <UtpOwnerCodesSetting activeVersion={activeVersion} />
            <button className="smallBtn" onClick={refreshUtpData} disabled={utpLoading} style={{padding:"3px 10px",fontSize:12}}>
              {utpLoading ? "获取中..." : "🔄 从 UTP 获取"}
            </button>
          </div>
        </div>
        {!utpData && !utpLoading && (
          <p style={{color:"var(--text3)",textAlign:"center",padding:20,fontSize:13}}>点击「从 UTP 获取」拉取 Weekly 测试报告数据</p>
        )}
        {utpLoading && (
          <p style={{color:"var(--text3)",textAlign:"center",padding:20,fontSize:13}}>⏳ 正在从 UTP 获取 Weekly 报告...</p>
        )}
        {utpData && utpData.platforms && utpData.platforms.map((pf: any) => {
          if (pf.error && !pf.group_tasks) {
            return <div key={pf.platform} className="subCard" style={{marginBottom:12,padding:12}}><span style={{color:"var(--danger)"}}>⚠ {pf.platform}: {pf.error}</span></div>;
          }
          const cc = pf.case_count || {};
          const jc = pf.jira_count || {};
          const tasks = pf.group_tasks || [];
          const pfKey = `pf_${pf.platform}`;
          const pfExpanded = utpExpanded[pfKey] === true;
          // 按业务领域(group_name)合并
          const domainGroupMap: Record<string, any[]> = {};
          tasks.forEach((t: any) => {
            const gn = t.group_name || "-";
            if (!domainGroupMap[gn]) domainGroupMap[gn] = [];
            domainGroupMap[gn].push(t);
          });
          const domainEntries = Object.entries(domainGroupMap).sort((a, b) => {
            const aFail = a[1].filter((t: any) => { const r = (t.sub_result || "").toUpperCase(); return r === "FAIL" || r === "NG"; }).length;
            const bFail = b[1].filter((t: any) => { const r = (t.sub_result || "").toUpperCase(); return r === "FAIL" || r === "NG"; }).length;
            if (bFail !== aFail) return bFail - aFail;
            return b[1].length - a[1].length;
          });
          return (
            <div key={pf.platform} className="subCard" style={{marginBottom:12,padding:0}}>
              {/* AI 分析弹窗（放在最外层，不依赖展开状态） */}
              {utpExpanded[`ai_${pf.platform}`] && pf.ai_analysis && (
                <div className="modalMask" onClick={() => setUtpExpanded(prev => { const n = {...prev}; delete n[`ai_${pf.platform}`]; return n; })}>
                  <div className="modal" style={{maxWidth:700,maxHeight:"70vh",padding:0}} onClick={e => e.stopPropagation()}>
                    <div style={{padding:"16px 20px",borderBottom:"1px solid var(--card-border)"}}>
                      <h2 style={{fontSize:15,margin:0}}>🤖 {pf.platform} 平台 AI 分析报告</h2>
                      {pf.ai_analyzed_at && <span style={{fontSize:11,color:"var(--text3)",marginTop:2,display:"inline-block"}}>分析时间：{pf.ai_analyzed_at.replace("T"," ").slice(0,19)}</span>}
                    </div>
                    <div className="modalScrollBody" style={{padding:"16px 20px"}}>
                      <div style={{fontSize:13,lineHeight:1.8,whiteSpace:"pre-wrap",color:"var(--text)"}}>{pf.ai_analysis}</div>
                    </div>
                    <div style={{padding:"10px 20px",borderTop:"1px solid var(--card-border)",textAlign:"right"}}>
                      <button className="secondaryBtn" onClick={() => setUtpExpanded(prev => { const n = {...prev}; delete n[`ai_${pf.platform}`]; return n; })}>关闭</button>
                    </div>
                  </div>
                </div>
              )}
              {/* 平台标题栏 + 指标 */}
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px",cursor:"pointer",background:pfExpanded?"var(--accent-soft)":"transparent",borderRadius:pfExpanded?"8px 8px 0 0":8}} onClick={() => setUtpExpanded(prev => ({...prev, [pfKey]: !pfExpanded}))}>
                <div style={{display:"flex",alignItems:"center",gap:10}}>
                  <span style={{fontSize:12,color:"var(--text3)",display:"inline-block",transform:pfExpanded?"rotate(90deg)":"rotate(0deg)",transition:"transform .2s"}}>▶</span>
                  <span style={{fontWeight:700,fontSize:14}}>{pf.platform} 平台</span>
                  {pf.report_result && <span className={"badge " + (pf.report_result === "PASS" ? "badgeGo" : pf.report_result === "FAIL" ? "badgeRisk" : "badgeWarn")}>{pf.report_result}</span>}
                  <span style={{fontSize:12,color:"var(--text3)"}}>{domainEntries.length} 个业务领域 · {tasks.length} 项</span>
                  <button className="smallBtn" disabled={utpAiLoading[pf.platform]} onClick={(e) => { e.stopPropagation(); runUtpAiAnalyze(pf.platform); }} style={{padding:"2px 8px",fontSize:11,borderRadius:4,background:pf.ai_analysis ? "var(--accent)" : "var(--surface)",color:pf.ai_analysis ? "#fff" : "var(--text2)",border:`1px solid ${pf.ai_analysis ? "var(--accent)" : "var(--card-border)"}`}}>
                    {utpAiLoading[pf.platform] ? "⏳ 分析中..." : pf.ai_analysis ? "🤖 AI 已分析" : "🤖 AI 分析"}
                  </button>
                  {pf.ai_analysis && <span style={{fontSize:11,color:"var(--accent)",cursor:"pointer",textDecoration:"underline"}} onClick={(e) => { e.stopPropagation(); setUtpExpanded(prev => ({...prev, [`ai_${pf.platform}`]: true})); }}>查看报告</span>}
                </div>
                <div style={{display:"flex",gap:12,alignItems:"center",fontSize:12}}>
                  {cc.rate && <span style={{color:"var(--text2)"}}>用例 {cc.rate}</span>}
                  {(jc.leave || 0) > 0 && <span style={{color:"#ff4d4f",fontWeight:600}}>遗留 {jc.leave}</span>}
                  {pf.plan_finish_time && <span style={{color:"var(--text3)"}}>{pf.plan_finish_time.slice(0,10)}</span>}
                </div>
              </div>
              {pfExpanded && (
                <div style={{padding:"10px 16px"}}>
                  {/* 遗留缺陷快捷入口 */}
                  {(jc.leave || 0) > 0 && (
                    <div style={{display:"flex",gap:10,marginBottom:10,fontSize:12}}>
                      <span style={{color:"var(--text3)"}}>遗留缺陷：</span>
                      <span style={{color:"#1890ff",cursor:"pointer",borderBottom:"1px dashed #1890ff",fontWeight:600}} onClick={(e) => { e.stopPropagation(); fetchUtpJiraIssues(pf.platform, "A", pf.plan_id); }}>A类:{jc.a||0}</span>
                      <span style={{color:"#1890ff",cursor:"pointer",borderBottom:"1px dashed #1890ff",fontWeight:600}} onClick={(e) => { e.stopPropagation(); fetchUtpJiraIssues(pf.platform, "B", pf.plan_id); }}>B类:{jc.b||0}</span>
                    </div>
                  )}
                  {/* 业务领域列表（平台内按 group_name 合并） */}
                  {domainEntries.map(([domainName, domainTasks]) => {
                    const dKey = `${pf.platform}_${domainName}`;
                    const dExpanded = utpExpanded[dKey] === true;
                    const dPass = domainTasks.filter((t: any) => (t.sub_result || "").toUpperCase() === "PASS").length;
                    const dFail = domainTasks.filter((t: any) => { const r = (t.sub_result || "").toUpperCase(); return r === "FAIL" || r === "NG"; }).length;
                    const dJiraTotal = domainTasks.reduce((s: number, t: any) => s + (t.jira_count || 0), 0);
                    const dJiraIds = domainTasks.flatMap((t: any) => (t.jira_ids || "").split(",").filter(Boolean));
                    return (
                      <div key={dKey} style={{marginBottom:6,border:"1px solid var(--card-border)",borderRadius:6,overflow:"hidden"}}>
                        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"6px 12px",cursor:"pointer",background:dExpanded?"var(--surface)":"transparent"}} onClick={() => setUtpExpanded(prev => ({...prev, [dKey]: !dExpanded}))}>
                          <div style={{display:"flex",alignItems:"center",gap:6}}>
                            <span style={{fontSize:10,color:"var(--text3)",display:"inline-block",transform:dExpanded?"rotate(90deg)":"rotate(0deg)",transition:"transform .2s"}}>▶</span>
                            <span style={{fontWeight:600,fontSize:12}}>{domainName}</span>
                            <span style={{fontSize:11,color:"var(--text3)"}}>({domainTasks.length})</span>
                          </div>
                          <div style={{display:"flex",gap:8,fontSize:11,alignItems:"center"}}>
                            {dPass > 0 && <span style={{color:"#52c41a",fontWeight:600}}>✓{dPass}</span>}
                            {dFail > 0 && <span style={{color:"#ff4d4f",fontWeight:600}}>✗{dFail}</span>}
                            {dJiraTotal > 0 && (
                              <span style={{color:"#1890ff",cursor:"pointer",borderBottom:"1px dashed #1890ff",fontWeight:600}} title="点击查看缺陷列表" onClick={(e) => { e.stopPropagation(); setUtpJiraModal({ title: `${pf.platform} / ${domainName} 缺陷列表`, issueKeys: dJiraIds }); }}>🐛{dJiraTotal}</span>
                            )}
                          </div>
                        </div>
                        {dExpanded && (
                          <div style={{overflowX:"auto",borderTop:"1px solid var(--card-border)"}}>
                            <table style={{margin:0,width:"100%",fontSize:12,borderCollapse:"collapse"}}>
                              <thead><tr>
                                <th style={{textAlign:"left",padding:"4px 8px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)",whiteSpace:"nowrap"}}>子领域</th>
                                <th style={{textAlign:"center",padding:"4px 6px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>结果</th>
                                <th style={{textAlign:"center",padding:"4px 6px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>进度</th>
                                <th style={{textAlign:"center",padding:"4px 6px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>用例</th>
                                <th style={{textAlign:"center",padding:"4px 6px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>通过率</th>
                                <th style={{textAlign:"center",padding:"4px 6px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>缺陷</th>
                                <th style={{textAlign:"left",padding:"4px 8px",fontSize:11,fontWeight:600,color:"var(--text2)",borderBottom:"1px solid var(--card-border)"}}>负责人</th>
                              </tr></thead>
                              <tbody>
                                {domainTasks.map((t: any, idx: number) => {
                                  const subRes = (t.sub_result || "").toUpperCase();
                                  const resColor = subRes === "PASS" ? "#52c41a" : subRes === "FAIL" || subRes === "NG" ? "#ff4d4f" : subRes === "GR" ? "#faad14" : "var(--text3)";
                                  return (
                                    <tr key={idx}>
                                      <td style={{padding:"4px 8px",fontSize:11,borderBottom:"1px solid var(--card-border)",maxWidth:160,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={t.sub_group_name}>{t.sub_group_name || "-"}</td>
                                      <td style={{padding:"4px 6px",textAlign:"center",borderBottom:"1px solid var(--card-border)"}}><span style={{color:resColor,fontWeight:700,fontSize:11}}>{t.sub_result || "-"}</span></td>
                                      <td style={{padding:"4px 6px",textAlign:"center",fontSize:11,borderBottom:"1px solid var(--card-border)"}}>{t.progress || "-"}</td>
                                      <td style={{padding:"4px 6px",textAlign:"center",fontSize:11,borderBottom:"1px solid var(--card-border)"}}>{t.case_count || 0}</td>
                                      <td style={{padding:"4px 6px",textAlign:"center",fontSize:11,borderBottom:"1px solid var(--card-border)"}}>{t.pass_rate || "-"}</td>
                                      <td style={{padding:"4px 6px",textAlign:"center",borderBottom:"1px solid var(--card-border)"}}>
                                        {(t.jira_count || 0) > 0 && t.jira_ids ? (
                                          <span style={{color:"#1890ff",fontWeight:600,cursor:"pointer",borderBottom:"1px dashed #1890ff",fontSize:12}}
                                            onClick={(e) => { e.stopPropagation(); const ids = (t.jira_ids || "").split(",").filter(Boolean); setUtpJiraModal({ title: `${pf.platform} / ${domainName} / ${t.sub_group_name || ""} 关联缺陷`, issueKeys: ids }); }}
                                            title="点击查看缺陷列表">
                                            {t.jira_count}
                                          </span>
                                        ) : <span style={{color:"var(--text3)",fontSize:11}}>{t.jira_count || 0}</span>}
                                      </td>
                                      <td style={{padding:"4px 8px",fontSize:11,color:"var(--text2)",borderBottom:"1px solid var(--card-border)",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis",maxWidth:100}} title={t.owner_name || t.executor}>{t.owner_name || t.executor || "-"}</td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* UTP Weekly 缺陷详情弹窗（支持两种模式：issueKeys 直接显示 / platform+priority 从 API 查询） */}
      {utpJiraModal && (() => {
        const hasIssueKeys = utpJiraModal.issueKeys && utpJiraModal.issueKeys.length > 0;
        const currentPf = (utpData?.platforms || []).find((p: any) => p.platform === utpJiraModal.platform);
        const switchPriority = (p: string) => {
          if (utpJiraModal.platform) fetchUtpJiraIssues(utpJiraModal.platform, p, currentPf?.plan_id);
        };
        return (
        <div className="modalMask" onClick={() => setUtpJiraModal(null)}>
          <div className="modal modalWide" style={{width: hasIssueKeys ? 480 : "90vw", maxWidth: hasIssueKeys ? "90vw" : 1100, maxHeight:"80vh",padding:0}} onClick={e => e.stopPropagation()}>
            <div style={{padding:"20px 24px 12px",borderBottom:"1px solid var(--card-border)"}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                <h2 style={{fontSize:16,margin:0}}>🐛 {utpJiraModal.title || "缺陷详情"}</h2>
                {!hasIssueKeys && (
                  <div style={{display:"flex",gap:6}}>
                    <button className={utpJiraModal.priority === "A" ? "primaryBtn" : "smallBtn"} onClick={() => switchPriority("A")} style={{padding:"4px 14px",fontSize:12}}>A 类</button>
                    <button className={utpJiraModal.priority === "B" ? "primaryBtn" : "smallBtn"} onClick={() => switchPriority("B")} style={{padding:"4px 14px",fontSize:12}}>B 类</button>
                  </div>
                )}
              </div>
              <p style={{fontSize:12,color:"var(--text3)",margin:"4px 0 0"}}>
                {hasIssueKeys ? `共 ${utpJiraModal.issueKeys.length} 个关联缺陷，点击跳转 Jira` : (utpJiraLoading ? "正在加载..." : `共 ${utpJiraIssues.length} 个 ${utpJiraModal.priority || ""} 类缺陷`)}
              </p>
            </div>
            <div className="modalScrollBody" style={{padding:"12px 24px"}}>
              {hasIssueKeys ? (
                <div style={{display:"flex",flexDirection:"column",gap:6}}>
                  {utpJiraModal.issueKeys.map((key: string) => (
                    <a key={key} href={`${JIRA_BROWSE}${key}`} target="_blank" rel="noreferrer"
                      style={{fontSize:13,color:"var(--accent)",textDecoration:"underline",padding:"6px 10px",borderRadius:6,background:"var(--surface)",display:"block"}}>
                      {key}
                    </a>
                  ))}
                </div>
              ) : utpJiraLoading ? (
                <p style={{textAlign:"center",color:"var(--text3)",padding:30}}>⏳ 正在从 UTP 拉取数据...</p>
              ) : utpJiraIssues.length === 0 ? (
                <p style={{textAlign:"center",color:"var(--text3)",padding:30}}>✅ 暂无 {utpJiraModal.priority} 类缺陷</p>
              ) : (
                <div style={{overflowX:"auto"}}>
                  <table className="dataTable" style={{margin:0,width:"100%",fontSize:12}}>
                    <thead><tr>
                      <th style={{minWidth:130}}>问题编号</th>
                      <th>问题描述</th>
                      <th style={{width:70}}>优先级</th>
                      <th style={{width:80}}>状态</th>
                      <th style={{width:70}}>解决方式</th>
                      <th style={{width:100}}>负责人</th>
                      <th style={{width:100}}>报告人</th>
                      <th style={{width:90}}>创建时间</th>
                    </tr></thead>
                    <tbody>
                      {utpJiraIssues.map((iss: any) => (
                        <tr key={iss.jiraKey}>
                          <td><IssueLink issueKey={iss.jiraKey} /></td>
                          <td style={{maxWidth:300,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={iss.summary}>{iss.summary || "-"}</td>
                          <td><span className={"badge " + (iss.bugClass === "Blocker" ? "badgeRisk" : iss.bugClass === "Critical" ? "badgeWarn" : "badgeInfo")}>{iss.bugClass || "-"}</span></td>
                          <td><span className={"badge " + (["Closed","Resolved","Verified","Fixed"].includes(iss.fixStatus) ? "badgeNormal" : "badgeOpen")}>{iss.fixStatus || "-"}</span></td>
                          <td style={{fontSize:11,color:"var(--text2)"}}>{iss.resolution || "-"}</td>
                          <td style={{fontSize:11}}>{iss.assignee || "-"}</td>
                          <td style={{fontSize:11,color:"var(--text2)"}}>{iss.reporter || "-"}</td>
                          <td style={{fontSize:11,color:"var(--text3)",whiteSpace:"nowrap"}}>{iss.createTime ? iss.createTime.slice(0,10) : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div style={{padding:"12px 24px",borderTop:"1px solid var(--card-border)",textAlign:"right"}}>
              {!hasIssueKeys && utpJiraIssues.length > 0 && (
                <button className="smallBtn" onClick={() => exportUtpIssues(utpJiraModal.title || "UTP缺陷", utpJiraIssues)} style={{padding:"5px 12px",fontSize:12,marginRight:8}}>📥 导出 Excel</button>
              )}
              <button className="secondaryBtn" onClick={() => setUtpJiraModal(null)}>关闭</button>
            </div>
          </div>
        </div>
        );
      })()}

      {/* 价值点相关风险 */}
      <div id="sec-ch2-1-4"><SectionHeader title="1.4 价值点相关风险" /></div>
      <ValuePointSection activeVersion={activeVersion} />

      {/* ═══════════ Part 2: Jira 风险 ═══════════ */}
      <div className="majorPartHeader" id="sec-ch2-jira">
        <span className="mpIcon">🐛</span>
        <div><h2 className="mpTitle">二、Jira 风险</h2><div className="mpSub">问题状态、积压、趋势分析</div></div>
      </div>

      {/* Jira 数据概览 */}
      <div id="sec-ch2-1"><div className="sectionHeader"><div><h2 className="spTitle">2.1 Jira 数据概览</h2></div></div></div>
      {activeVersion?.id && <JiraFilterEditor versionId={activeVersion.id} filterKey="main_sync" activeStage={activeStage} />}
      <div className="card">
        <div className="grid4">
          <MetricCard label="问题总数" value={metrics.cache_count ?? 0} note="本阶段缓存" />
          <div className={"metricCard " + ((openReopenData?.total ?? 0) > 0 ? "danger" : "")} style={{cursor:"pointer",transition:"transform .15s,box-shadow .15s"}} onClick={() => { const el = document.getElementById("sec-open-reopen"); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
            <div className="metricLabel">遗留问题</div>
            <div className="metricValue">{openReopenData?.total ?? 0}</div>
            <div className="metricNote">Open/Reopened · 点击查看</div>
          </div>
          <div className={"metricCard " + ((submittedModifyingData?.total ?? 0) > 0 ? "danger" : "")} style={{cursor:"pointer",transition:"transform .15s,box-shadow .15s"}} onClick={() => { const el = document.getElementById("sec-submitted-modifying"); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
            <div className="metricLabel">待处理问题</div>
            <div className="metricValue">{submittedModifyingData?.total ?? 0}</div>
            <div className="metricNote">Submitted/Modifying · 点击查看</div>
          </div>
          <div className={"metricCard " + ((pendingVerificationData?.total ?? 0) > 0 ? "danger" : "")} style={{cursor:"pointer",transition:"transform .15s,box-shadow .15s"}} onClick={() => { const el = document.getElementById("sec-pending-verification"); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
            <div className="metricLabel">待验证问题</div>
            <div className="metricValue">{pendingVerificationData?.total ?? 0}</div>
            <div className="metricNote">Resolved/Verified · 点击查看</div>
          </div>
        </div>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:12,paddingTop:10,borderTop:"1px dashed var(--card-border)"}}>
          <span style={{fontSize:11,color:"var(--text3)"}}>💡 卡片数据来自下方各模块，点击卡片可跳转查看详情</span>
          <span style={{fontSize:13,color:"var(--text2)",fontWeight:500}}>最近同步：{metrics.last_sync ? metrics.last_sync.slice(5, 16).replace("T", " ") : "暂无"}</span>
        </div>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:12,paddingTop:10,borderTop:"1px dashed var(--card-border)"}}>
          <span style={{fontSize:13,color:"var(--text2)",fontWeight:500}}>最近同步：{metrics.last_sync ? metrics.last_sync.slice(5, 16).replace("T", " ") : "暂无"}</span>
          <button className="primaryBtn" onClick={onSyncJira} disabled={loading} style={{padding:"5px 16px",fontSize:12}}>
            {loading ? "同步中..." : "🔄 刷新数据"}
          </button>
        </div>
      </div>

      {/* AI 数据分析小模块 */}
      <AIDataAnalysisSection activeVersion={activeVersion} activeStage={activeStage} jiraSyncVersion={jiraSyncVersion} />

      {/* Jira 趋势分析 */}
      <div id="sec-ch2-trend"><div className="subPartHeader"><div><h2 className="spTitle">2.2 Jira 趋势分析</h2></div></div></div>
      
      <JiraTrendAnalysisSection activeVersion={activeVersion} activeStage={activeStage} jiraSyncVersion={jiraSyncVersion} refreshCount={refreshCount} />

      {/* 遗留问题 Open/Reopened 分析 */}
      <div id="sec-open-reopen"><div className="subPartHeader"><div><h2 className="spTitle">2.3 遗留问题 Open/Reopened 分析</h2></div></div></div>
      {activeVersion?.id && <JiraFilterEditor versionId={activeVersion.id} filterKey="open_reopen" activeStage={activeStage} />}
      <OpenReopenSection activeVersion={activeVersion} activeStage={activeStage} onDataUpdate={setOpenReopenData} jiraSyncVersion={jiraSyncVersion} />

      {/* 积压问题 Submitted/Modifying 分析 */}
      <div id="sec-submitted-modifying">
        <div className="subPartHeader"><div><h2 className="spTitle">2.4 积压问题 Submitted/Modifying 分析</h2></div></div>
      </div>
      {activeVersion?.id && <JiraFilterEditor versionId={activeVersion.id} filterKey="submitted_modifying" activeStage={activeStage} />}
      <SubmittedModifyingSection activeVersion={activeVersion} activeStage={activeStage} onDataUpdate={setSubmittedModifyingData} jiraSyncVersion={jiraSyncVersion} />

      {/* 待验证问题分析 */}
      <div id="sec-pending-verification">
        <div className="subPartHeader"><div><h2 className="spTitle">2.5 待验证问题分析</h2></div></div>
      </div>
      {activeVersion?.id && <JiraFilterEditor versionId={activeVersion.id} filterKey="pending_verification" activeStage={activeStage} />}
      <PendingVerificationSection activeVersion={activeVersion} activeStage={activeStage} onDataUpdate={setPendingVerificationData} jiraSyncVersion={jiraSyncVersion} />

      

      {/* ═══════════ Part 3: 进度风险 ═══════════ */}
      <div className="majorPartHeader" id="sec-ch2-3">
        <span className="mpIcon">📅</span>
        <div><h2 className="mpTitle">三、进度风险</h2><div className="mpSub">UTP 测试计划执行进度与风险评估</div></div>
      </div>
      {activeVersion && <UtpPlanProgress activeVersion={activeVersion} />}

    </div>
  );
}