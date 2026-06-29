import React, { useState, useEffect, useRef } from "react";
import { API_BASE, JIRA_BROWSE } from "../constants";
import { IssueLink } from "../components/common/IssueLink";
import { AiCriteriaHint } from "../components/common/AiCriteriaHint";
import { exportToExcel } from "../utils/export";

// 从 App.tsx 第1946行原样提取 - AI 数据分析小模块
export function AIDataAnalysisSection({ activeVersion, activeStage, jiraSyncVersion }: any) {
  const [cycleTime, setCycleTime] = useState<any>(null);
  const [healthMap, setHealthMap] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showCycleModal, setShowCycleModal] = useState(false);
  const [showHealthModal, setShowHealthModal] = useState(false);
  const [moduleIssues, setModuleIssues] = useState<any[] | null>(null);
  const [moduleIssuesTitle, setModuleIssuesTitle] = useState("");
  const [moduleIssuesLoading, setModuleIssuesLoading] = useState(false);

  async function loadModuleIssues(moduleName: string) {
    if (!activeVersion?.id) return;
    setModuleIssuesLoading(true);
    setModuleIssuesTitle(moduleName);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/issues/by-module?module=${encodeURIComponent(moduleName)}&stage=${activeStage || "ALL"}`);
      const d = await res.json();
      setModuleIssues(d.issues || []);
    } catch { setModuleIssues([]); }
    finally { setModuleIssuesLoading(false); }
  }

  async function loadData(refresh = false) {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const r = refresh ? "&refresh=true" : "";
      const [ctRes, hmRes] = await Promise.all([
        fetch(API_BASE + `/api/versions/${activeVersion.id}/ai/cycle-time?stage=${activeStage || "ALL"}${r}`),
        fetch(API_BASE + `/api/versions/${activeVersion.id}/ai/health-map?stage=${activeStage || "ALL"}${r}`),
      ]);
      setCycleTime(await ctRes.json());
      setHealthMap(await hmRes.json());
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, [activeVersion?.id, activeStage, jiraSyncVersion]);

  const slowModules = (cycleTime?.modules || []).filter((m: any) => m.is_slow);
  const highRiskModules = (healthMap?.modules || []).filter((m: any) => m.risk === "high");
  const medRiskModules = (healthMap?.modules || []).filter((m: any) => m.risk === "medium");

  return (
    <div className="card mt12">
      <div className="cardTitle">
        <span>🤖 Jira数据AI分析</span>
        <div style={{display:"flex",gap:6}}>
          <button className="smallBtn" onClick={() => loadData(true)} disabled={loading} style={{padding:"3px 10px",fontSize:11}} title="重新计算并调用 AI 生成建议">
            {loading ? "分析中..." : "🤖 刷新并 AI 分析"}
          </button>
          <button className="smallBtn" onClick={() => loadData(false)} disabled={loading} style={{padding:"3px 10px",fontSize:11}}>
            {loading ? "..." : "🔄 刷新"}
          </button>
        </div>
      </div>
      <div className="grid2">
        <div className="subCard" style={{padding:"14px 18px"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
            <span style={{fontSize:14,fontWeight:600,color:"var(--text)",display:"flex",alignItems:"center",position:"relative"}}>🐛 Bug 修复效能分析
              <AiCriteriaHint title="Bug 修复效能" criteria={`判断标准：
1. 计算每个模块的平均 CycleTime（从创建到关闭的天数）
2. 与上个 tOS 版本同模块的平均 CycleTime 做对比
3. 若当前模块 > 上版本同模块 × 1.5 倍（且 ≥3 个 Issue），标记为「异常」
4. 若上版本无数据，退回使用当前版本整体平均值 × 1.5 倍作为基线
5. 数据来源：本阶段已关闭的 Jira Issue
6. AI 建议结合上版本对比数据、高优占比、必解占比等维度生成`} />
            </span>
            {cycleTime?.overall_avg > 0 && <span style={{fontSize:12,color:"var(--text3)"}}>平均 CycleTime: <strong>{cycleTime.overall_avg}</strong> 天</span>}
          </div>
          {loading ? (
            <p style={{color:"var(--text3)",textAlign:"center",padding:16}}>正在分析...</p>
          ) : slowModules.length > 0 ? (
            <>
              <p style={{fontSize:12,color:"var(--danger)",marginBottom:8}}>⚠ 以下模块修复周期明显高于平均值（&gt;1.5x），需关注：</p>
              {slowModules.slice(0, 5).map((m: any) => (
                <div key={m.module} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"6px 0",borderBottom:"1px solid #f3f4f6"}}>
                  <span style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{m.module}</span>
                  <span style={{display:"flex",gap:12,fontSize:12}}>
                    <span style={{color:"var(--danger)",fontWeight:600}}>{m.avg_cycle_time}天</span>
                    <span style={{color:"var(--text3)"}}>({m.ratio}x)</span>
                    <span style={{color:"var(--text3)"}}>{m.count}个</span>
                  </span>
                </div>
              ))}
              {slowModules.length > 5 && (
                <button className="viewMoreBtn" onClick={() => setShowCycleModal(true)} style={{marginTop:8}}>查看全部 {slowModules.length} 个异常模块 →</button>
              )}
              {slowModules.length > 0 && slowModules.length <= 5 && (cycleTime?.modules?.length || 0) > slowModules.length && (
                <button className="viewMoreBtn" onClick={() => setShowCycleModal(true)} style={{marginTop:8}}>查看全部 {(cycleTime?.modules?.length || 0)} 个模块 →</button>
              )}
              {cycleTime?.ai_suggestion && (
                <div style={{marginTop:10,padding:"10px 14px",background:"linear-gradient(135deg, var(--accent-soft), var(--bg2))",border:"1px solid var(--accent)",borderRadius:8}}>
                  <div style={{fontSize:12,fontWeight:600,color:"var(--accent)",marginBottom:4}}>🤖 AI 分析建议</div>
                  <div style={{fontSize:12,lineHeight:1.7,color:"var(--text2)",whiteSpace:"pre-wrap"}}>{cycleTime.ai_suggestion}</div>
                </div>
              )}
            </>
          ) : cycleTime?.modules?.length > 0 ? (
            <>
              <p style={{fontSize:13,color:"var(--ok)",textAlign:"center",padding:12}}>✅ 各模块修复效能正常，无明显异常</p>
              <button className="viewMoreBtn" onClick={() => setShowCycleModal(true)} style={{marginTop:4}}>查看全部 {(cycleTime?.modules?.length || 0)} 个模块 →</button>
            </>
          ) : (
            <p style={{fontSize:12,color:"var(--text3)",textAlign:"center",padding:16}}>暂无已解决 Issue 数据</p>
          )}
        </div>

        <div className="subCard" style={{padding:"14px 18px"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
            <span style={{fontSize:14,fontWeight:600,color:"var(--text)",display:"flex",alignItems:"center",position:"relative"}}>🗺️ 健康地图
              <AiCriteriaHint title="健康地图" criteria={`判断标准：
1. 按模块统计所有未关闭 Issue 的数量、优先级分布
2. 高风险：未关闭数 > 10 且（Blocker > 0 或 高优占比 > 30%）
3. 中风险：未关闭数 > 5 且 高优占比 > 15%
4. 低风险：其余模块
5. 超龄标准：Issue 创建超过 14 天未关闭
6. AI 建议基于模块风险等级、超龄占比、优先级分布等维度综合生成`} />
            </span>
            {healthMap?.total_issues > 0 && <span style={{fontSize:12,color:"var(--text3)"}}>共 {healthMap.total_issues} 个 Issue</span>}
          </div>
          {loading ? (
            <p style={{color:"var(--text3)",textAlign:"center",padding:16}}>正在分析...</p>
          ) : highRiskModules.length > 0 || medRiskModules.length > 0 ? (
            <>
              {highRiskModules.length > 0 && (
                <div style={{marginBottom:10}}>
                  <span style={{fontSize:12,fontWeight:600,color:"var(--danger)"}}>🔴 高风险模块（{highRiskModules.length}）</span>
                  {highRiskModules.slice(0, 4).map((m: any) => (
                    <div key={m.name} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #f3f4f6"}}>
                      <span style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{m.name}</span>
                      <span style={{display:"flex",gap:10,fontSize:11}}>
                        {m.blocker > 0 && <span className="badge badgeRisk">Blocker {m.blocker}</span>}
                        <span className="badge badgeWarn">高优 {m.high}</span>
                        <span style={{color:"var(--text3)"}}>未关 {m.unresolved}</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {medRiskModules.length > 0 && (
                <div>
                  <span style={{fontSize:12,fontWeight:600,color:"var(--warn)"}}>🟡 中风险模块（{medRiskModules.length}）</span>
                  {medRiskModules.slice(0, 3).map((m: any) => (
                    <div key={m.name} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #f3f4f6"}}>
                      <span style={{fontSize:13,color:"var(--text)"}}>{m.name}</span>
                      <span style={{display:"flex",gap:10,fontSize:11}}>
                        <span className="badge badgeWarn">高优 {m.high}</span>
                        <span style={{color:"var(--text3)"}}>未关 {m.unresolved}</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {(healthMap?.modules || []).length > (highRiskModules.length + medRiskModules.length) && (
                <button className="viewMoreBtn" onClick={() => setShowHealthModal(true)} style={{marginTop:8}}>查看全部模块 →</button>
              )}
              {healthMap?.ai_suggestion && (
                <div style={{marginTop:10,padding:"10px 14px",background:"linear-gradient(135deg, var(--accent-soft), var(--bg2))",border:"1px solid var(--accent)",borderRadius:8}}>
                  <div style={{fontSize:12,fontWeight:600,color:"var(--accent)",marginBottom:4}}>🤖 AI 分析建议</div>
                  <div style={{fontSize:12,lineHeight:1.7,color:"var(--text2)",whiteSpace:"pre-wrap"}}>{healthMap.ai_suggestion}</div>
                </div>
              )}
            </>
          ) : healthMap?.modules?.length > 0 ? (
            <p style={{fontSize:13,color:"var(--ok)",textAlign:"center",padding:12}}>✅ 各模块健康状态良好</p>
          ) : (
            <p style={{fontSize:12,color:"var(--text3)",textAlign:"center",padding:16}}>暂无 Issue 数据</p>
          )}
        </div>
      </div>

      {/* CycleTime 全量弹窗 */}
      {showCycleModal && cycleTime && <CycleTimeModal cycleTime={cycleTime} onClose={() => setShowCycleModal(false)} onModuleClick={loadModuleIssues} />}

      {/* 健康地图全量弹窗 */}
      {showHealthModal && healthMap && <HealthMapModal healthMap={healthMap} onClose={() => setShowHealthModal(false)} onModuleClick={loadModuleIssues} />}

      {/* 模块问题单弹窗 */}
      {moduleIssues !== null && (
        <div className="modalMask" onClick={() => setModuleIssues(null)}>
          <div className="modal modalWide" onClick={e => e.stopPropagation()}>
            <div className="modalHeader">
              <h2>📋 {moduleIssuesTitle}</h2>
              <span className="modalCount">{moduleIssues.length} 条</span>
            </div>
            <div className="modalTableWrap">
              {moduleIssuesLoading ? (
                <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>正在加载...</p>
              ) : moduleIssues.length === 0 ? (
                <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>暂无数据</p>
              ) : (
                <table className="dataTable" style={{fontSize:12}}>
                  <thead><tr><th>问题 ID</th><th>问题描述</th><th>状态</th><th>优先级</th><th>负责人</th><th>遗留天数</th></tr></thead>
                  <tbody>{moduleIssues.slice(0, 100).map((i: any) => (
                    <tr key={i.issue_key}>
                      <td><IssueLink issueKey={i.issue_key} /></td>
                      <td style={{maxWidth:360,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td>
                      <td><span className={"badge " + (["Closed","Done","Resolved","Verified"].includes(i.status) ? "badgeNormal" : "badgeOpen")}>{i.status}</span></td>
                      <td><span className={"badge " + (["Blocker","Critical"].includes(i.priority) ? "badgeRisk" : i.priority === "Major" ? "badgeWarn" : "badgeInfo")}>{i.priority}</span></td>
                      <td>{i.assignee || "未分配"}</td>
                      <td>{i.aging_days ?? "-"}天</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
            <div className="modalActions"><button className="secondaryBtn" onClick={() => setModuleIssues(null)}>关闭</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// 独立弹窗组件（不能用 useState in IIFE）
// ═══════════════════════════════════════

function CycleTimeModal({ cycleTime, onClose, onModuleClick }: any) {
  const [cycleTab, setCycleTab] = useState<"all"|"slow"|"normal">("all");
  const slowMods = (cycleTime.modules || []).filter((m: any) => m.is_slow);
  const normalMods = (cycleTime.modules || []).filter((m: any) => !m.is_slow);
  const displayMods = cycleTab === "slow" ? slowMods : cycleTab === "normal" ? normalMods : (cycleTime.modules || []);
  const predAvg = cycleTime.predecessor_overall_avg;

  const handleExport = () => {
    // 按异常/正常排序：异常在前
    const sorted = [...(cycleTime.modules || [])].sort((a: any, b: any) => {
      if (a.is_slow !== b.is_slow) return a.is_slow ? -1 : 1;
      return b.avg_cycle_time - a.avg_cycle_time;
    });
    exportToExcel("Bug修复效能分析", [
      { header: "模块", key: "module" },
      { header: "已解决数", key: "count" },
      { header: "平均天数", key: "avg_cycle_time" },
      { header: "上版本平均", key: "pred_avg", render: (r: any) => r.pred_avg != null ? String(r.pred_avg) : "-" },
      { header: "倍率", key: "ratio", render: (r: any) => r.ratio + "x" },
      { header: "高优", key: "high_count" },
      { header: "必解", key: "must_fix_count" },
      { header: "状态", key: "is_slow", render: (r: any) => r.is_slow ? "异常" : "正常" },
    ], sorted);
  };

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal modalWide" onClick={e => e.stopPropagation()}>
        <div className="modalHeader">
          <h2>🐛 Bug 修复效能分析（全量）</h2>
          <span className="modalCount">平均: {cycleTime.overall_avg} 天{predAvg != null ? ` · 上版本: ${predAvg} 天` : ""} · {cycleTime.total_resolved} 个已解决</span>
        </div>
        <div style={{display:"flex",gap:8,padding:"0 0 12px",borderBottom:"1px solid var(--card-border)"}}>
          {[{k:"all",l:`全部 (${(cycleTime.modules||[]).length})`},{k:"slow",l:`异常 (${slowMods.length})`},{k:"normal",l:`正常 (${normalMods.length})`}].map(t => (
            <button key={t.k} onClick={() => setCycleTab(t.k as any)}
              style={{padding:"6px 16px",fontSize:12,fontWeight:cycleTab===t.k?600:400,background:cycleTab===t.k?"var(--accent)":"var(--surface)",color:cycleTab===t.k?"#fff":"var(--text2)",border:cycleTab===t.k?"1px solid var(--accent)":"1px solid var(--card-border)",borderRadius:6,cursor:"pointer",transition:"all .15s"}}>
              {t.l}
            </button>
          ))}
        </div>
        <div className="modalTableWrap">
          <table className="dataTable" style={{fontSize:12}}>
            <thead><tr><th>模块</th><th>已解决数</th><th>平均天数</th><th>上版本</th><th>倍率</th><th>高优</th><th>必解</th><th>状态</th></tr></thead>
            <tbody>{displayMods.map((m: any) => (
              <tr key={m.module} style={{cursor:"pointer",...(m.is_slow ? {background:"var(--danger-bg)"} : {})}}
                onClick={() => onModuleClick(m.module)}
                onMouseEnter={e => e.currentTarget.style.background="var(--accent-soft)"}
                onMouseLeave={e => e.currentTarget.style.background=m.is_slow?"var(--danger-bg)":""}>
                <td style={{fontWeight:600}}>{m.module}</td>
                <td>{m.count}</td>
                <td style={{color: m.is_slow ? "var(--danger)" : "var(--text)", fontWeight: m.is_slow ? 600 : 400}}>{m.avg_cycle_time} 天</td>
                <td style={{color:"var(--text3)"}}>{m.pred_avg != null ? m.pred_avg + " 天" : "-"}</td>
                <td>{m.ratio}x</td>
                <td>{m.high_count}</td>
                <td>{m.must_fix_count}</td>
                <td>{m.is_slow ? <span className="badge badgeRisk">异常</span> : <span className="badge badgeNormal">正常</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="modalActions">
          <button className="smallBtn" onClick={handleExport} style={{padding:"5px 12px",fontSize:12}}>📥 导出 Excel</button>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

function HealthMapModal({ healthMap, onClose, onModuleClick }: any) {
  const [healthTab, setHealthTab] = useState<"all"|"high"|"medium"|"low">("all");
  const highMods = (healthMap.modules || []).filter((m: any) => m.risk === "high");
  const medMods = (healthMap.modules || []).filter((m: any) => m.risk === "medium");
  const lowMods = (healthMap.modules || []).filter((m: any) => m.risk === "low");
  const displayMods = healthTab === "high" ? highMods : healthTab === "medium" ? medMods : healthTab === "low" ? lowMods : (healthMap.modules || []);

  const handleExport = () => {
    // 按风险等级排序：高 → 中 → 低
    const riskOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
    const sorted = [...(healthMap.modules || [])].sort((a: any, b: any) => {
      const la = riskOrder[a.risk] ?? 3;
      const lb = riskOrder[b.risk] ?? 3;
      if (la !== lb) return la - lb;
      return (b.unresolved || 0) - (a.unresolved || 0);
    });
    exportToExcel("健康地图_模块分析", [
      { header: "模块", key: "name" },
      { header: "总数", key: "total" },
      { header: "未关闭", key: "unresolved" },
      { header: "高优", key: "high" },
      { header: "Blocker", key: "blocker" },
      { header: "必解", key: "must_fix" },
      { header: "超14天", key: "over14" },
      { header: "风险等级", key: "risk", render: (r: any) => r.risk === "high" ? "高" : r.risk === "medium" ? "中" : "低" },
    ], sorted);
  };

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal modalWide" onClick={e => e.stopPropagation()}>
        <div className="modalHeader">
          <h2>🗺️ 健康地图（全量）</h2>
          <span className="modalCount">{healthMap.total_issues} 个 Issue · {healthMap.modules?.length || 0} 个模块</span>
        </div>
        <div style={{display:"flex",gap:8,padding:"0 0 12px",borderBottom:"1px solid var(--card-border)"}}>
          {[{k:"all",l:`全部 (${(healthMap.modules||[]).length})`},{k:"high",l:`🔴 高风险 (${highMods.length})`},{k:"medium",l:`🟡 中风险 (${medMods.length})`},{k:"low",l:`🟢 低风险 (${lowMods.length})`}].map(t => (
            <button key={t.k} onClick={() => setHealthTab(t.k as any)}
              style={{padding:"6px 14px",fontSize:12,fontWeight:healthTab===t.k?600:400,background:healthTab===t.k?"var(--accent)":"var(--surface)",color:healthTab===t.k?"#fff":"var(--text2)",border:healthTab===t.k?"1px solid var(--accent)":"1px solid var(--card-border)",borderRadius:6,cursor:"pointer",transition:"all .15s"}}>
              {t.l}
            </button>
          ))}
        </div>
        <div className="modalTableWrap">
          <table className="dataTable" style={{fontSize:12}}>
            <thead><tr><th>模块</th><th>总数</th><th>未关闭</th><th>高优</th><th>Blocker</th><th>必解</th><th>超14天</th><th>风险</th></tr></thead>
            <tbody>{displayMods.map((m: any) => (
              <tr key={m.name} style={{cursor:"pointer"}}
                onClick={() => onModuleClick(m.name)}
                onMouseEnter={e => e.currentTarget.style.background="var(--accent-soft)"}
                onMouseLeave={e => e.currentTarget.style.background=""}>
                <td style={{fontWeight:600}}>{m.name}</td>
                <td>{m.total}</td>
                <td>{m.unresolved}</td>
                <td>{m.high}</td>
                <td>{m.blocker > 0 ? <span className="badge badgeRisk">{m.blocker}</span> : 0}</td>
                <td>{m.must_fix}</td>
                <td>{m.over14}</td>
                <td><span className={"badge " + (m.risk === "high" ? "badgeRisk" : m.risk === "medium" ? "badgeWarn" : "badgeNormal")}>{m.risk === "high" ? "高" : m.risk === "medium" ? "中" : "低"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="modalActions">
          <button className="smallBtn" onClick={handleExport} style={{padding:"5px 12px",fontSize:12}}>📥 导出 Excel</button>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}