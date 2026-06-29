import React, { useState, useEffect, useRef } from "react";
import { API_BASE } from "../constants";
import { TrendChart } from "../components/charts/TrendChart";
import { MetricCard } from "../components/common/MetricCard";

// 从 App.tsx 第3839行原样提取 - Jira 趋势分析
export function JiraTrendAnalysisSection({ activeVersion, activeStage, jiraSyncVersion, refreshCount }: any) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [refreshingAi, setRefreshingAi] = useState(false);
  const [activeTab, setActiveTab] = useState<"overall" | "submit" | "resolve">("overall");
  const [showDebugJql, setShowDebugJql] = useState(false);
  const [showAiModal, setShowAiModal] = useState<"overall" | "submit" | "resolve" | null>(null);
  const versionRef = useRef<number | null>(null);

  async function loadAnalysis(forceAi = false, force = false) {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const useRefresh = forceAi || force;
      const url = useRefresh
        ? `${API_BASE}/api/versions/${activeVersion.id}/jira-trend-analysis/refresh-ai?stage=${activeStage}`
        : `${API_BASE}/api/versions/${activeVersion.id}/jira-trend-analysis?stage=${activeStage}`;
      const method = useRefresh ? "POST" : "GET";
      const res = await fetch(url, { method });
      const d = await res.json();
      setData(d);
    } catch { setData({ error: "请求失败" }); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!activeVersion?.id) return;
    if (versionRef.current !== activeVersion.id) { setData(null); versionRef.current = activeVersion.id; }
    if (refreshCount > 0) { loadAnalysis(true); } else { loadAnalysis(); }
  }, [activeVersion?.id, activeStage, refreshCount]);

  async function handleRefreshAi() {
    if (!activeVersion?.id) return;
    setRefreshingAi(true);
    try { await loadAnalysis(true); } finally { setRefreshingAi(false); }
  }

  if (!activeVersion) return null;

  if (loading && !data) {
    return <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text3)" }}>
      <div className="dataLoadingSpinner" style={{ margin: "0 auto 12px" }} />
      正在加载趋势分析数据...
    </div>;
  }

  if (data?.error && !data?.current_version) {
    return <div className="card" style={{ textAlign: "center", padding: 24, color: "var(--text3)" }}>
      <p>{data.error || "暂无数据"}</p>
      <button className="primaryBtn" onClick={() => loadAnalysis()} style={{ marginTop: 12, fontSize: 13 }}>🔄 重新加载</button>
    </div>;
  }

  const overall = data?.overall || {};
  const curM = overall.current || {};
  const predM = overall.predecessor;
  const convergence = overall.convergence || {};

  const tabs = [
    { key: "overall" as const, label: "📊 整体趋势", desc: "新老项目同期对比" },
    { key: "submit" as const, label: "📤 提交板块", desc: "模块趋势与收敛性" },
    { key: "resolve" as const, label: "✅ 解决板块", desc: "解决效率与AI建议" },
  ];

  function renderMarkdown(text: string) {
    if (!text) return null;
    return text.split("\n").map((line: string, i: number) => {
      if (/^\d+\.\s/.test(line)) return <h4 key={i} style={{ margin: "12px 0 4px", fontSize: 14, fontWeight: 700 }}>{line}</h4>;
      if (line.startsWith("- ")) return <p key={i} style={{ margin: "2px 0 2px 14px", lineHeight: 1.7, fontSize: 13 }}>{line}</p>;
      if (line.startsWith("**") && line.endsWith("**")) return <p key={i} style={{ margin: "6px 0 3px", fontWeight: 700, fontSize: 13 }}>{line.replace(/\*\*/g, "")}</p>;
      if (!line.trim()) return <div key={i} style={{ height: 6 }} />;
      return <p key={i} style={{ margin: "2px 0", lineHeight: 1.7, fontSize: 13 }}>{line}</p>;
    });
  }

  function deltaTag(val: number, suffix = "") {
    if (val > 0) return <span style={{ color: "#ef4444", fontWeight: 600, fontSize: 12 }}>▲ +{val}{suffix}</span>;
    if (val < 0) return <span style={{ color: "#10b981", fontWeight: 600, fontSize: 12 }}>▼ {val}{suffix}</span>;
    return <span style={{ color: "var(--text3)", fontSize: 12 }}>—</span>;
  }

  function convergenceBadge(trend: string) {
    const colors: Record<string, { bg: string; fg: string }> = {
      "收敛": { bg: "#ecfdf5", fg: "#059669" },
      "趋于收敛": { bg: "#ecfdf5", fg: "#059669" },
      "发散": { bg: "#fef2f2", fg: "#dc2626" },
      "发散（需关注）": { bg: "#fef2f2", fg: "#dc2626" },
      "波动": { bg: "#fffbeb", fg: "#d97706" },
    };
    const c = colors[trend] || { bg: "#f3f4f6", fg: "#6b7280" };
    return <span style={{ background: c.bg, color: c.fg, padding: "2px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600 }}>{trend || "未知"}</span>;
  }

  return (
    <div className="reportSection">
      <div className="card" style={{ padding: "12px 18px", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 14, flexWrap: "wrap" }}>
            <span><strong>{data?.current_version || "?"}</strong>（当前 · {activeStage} 阶段）</span>
            <span style={{ color: "var(--text3)" }}>vs</span>
            <span><strong>{data?.predecessor_version || "无历史版本"}</strong></span>
            <span style={{ fontSize: 11, color: "var(--text3)" }}>
              {data?.pred_cutoff_date ? `口径：上一代截止 ${data.pred_cutoff_date} 前的 Issue` : "口径：双方全量 Issue"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="smallBtn" onClick={() => loadAnalysis(false, true)} disabled={loading} style={{ padding: "3px 12px", fontSize: 11 }}>
              {loading ? "加载中..." : "🔄 刷新"}
            </button>
            <button className="primaryBtn" onClick={handleRefreshAi} disabled={refreshingAi || loading} style={{ padding: "3px 14px", fontSize: 11 }}>
              {refreshingAi ? "AI 分析中..." : "🤖 重新AI分析"}
            </button>
            {data?.debug_jql && (
              <button className="smallBtn" onClick={() => setShowDebugJql(!showDebugJql)} style={{ padding: "3px 10px", fontSize: 11 }}>
                {showDebugJql ? "隐藏JQL" : "🔍 查看JQL"}
              </button>
            )}
          </div>
        </div>
        {data?.pred_schedule_warning && (
          <div style={{ marginTop: 8, padding: "6px 12px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, fontSize: 12, color: "#92400e", lineHeight: 1.6 }}>
            ⚠️ {data.pred_schedule_warning}
          </div>
        )}
        {data?.cached && data?.generated_at && (
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6 }}>
            缓存数据 · 生成于 {data.generated_at.replace("T", " ").slice(0, 16)}
          </div>
        )}
        {data?.pred_data_source && (
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4 }}>
            📦 上版本数据来源：{data.pred_data_source}
          </div>
        )}
        {data?.generated_at && !data?.cached && (
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4 }}>
            🕐 数据更新时间：{data.generated_at.replace("T", " ").slice(0, 16)}
          </div>
        )}
        {showDebugJql && data?.debug_jql && (
          <div style={{ marginTop: 8, padding: "10px 14px", background: "var(--surface)", border: "1px solid var(--card-border)", borderRadius: 8, fontSize: 11, lineHeight: 1.8 }}>
            <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>📋 数据来源与 JQL</div>
            <div><strong>当前版本数据源：</strong>{data.debug_jql.current_source}（{data.debug_jql.current_issue_count} 条）</div>
            <div><strong>上版本项目：</strong>{data.debug_jql.pred_project || "无"}</div>
            <div><strong>上版本 JQL：</strong><code style={{ background: "var(--bg2)", padding: "2px 6px", borderRadius: 4, wordBreak: "break-all" }}>{data.debug_jql.pred_jql}</code></div>
            <div><strong>上版本 Issue 数：</strong>{data.debug_jql.pred_issue_count} 条</div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            style={{ padding: "8px 20px", fontSize: 13, fontWeight: activeTab === t.key ? 700 : 400, background: activeTab === t.key ? "var(--accent)" : "var(--surface)", color: activeTab === t.key ? "#fff" : "var(--text2)", border: activeTab === t.key ? "1px solid var(--accent)" : "1px solid var(--card-border)", borderRadius: 8, cursor: "pointer", transition: "all .2s" }}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "overall" && (
        <>
          {data?.ai_overall && (
            <div style={{textAlign:"right",marginBottom:8}}>
              <button className="smallBtn" onClick={() => setShowAiModal("overall")} style={{padding:"4px 12px",fontSize:12,background:"var(--accent)",color:"#fff",border:"1px solid var(--accent)",borderRadius:6,cursor:"pointer"}}>🤖 查看 AI 整体趋势分析</button>
            </div>
          )}
          <div className="grid2" style={{ marginBottom: 14 }}>
            <div className="card">
              <div className="cardTitle" style={{ marginBottom: 8 }}>关键指标对比</div>
              <table className="dataTable" style={{ fontSize: 12 }}>
                <thead><tr><th>指标</th><th>当前</th><th>历史</th><th>差值</th></tr></thead>
                <tbody>
                  <tr><td>问题总数</td><td>{curM.total ?? 0}</td><td>{predM?.total ?? 0}</td><td>{deltaTag((curM.total ?? 0) - (predM?.total ?? 0))}</td></tr>
                  <tr><td>未关闭</td><td>{curM.open ?? 0}</td><td>{predM?.open ?? 0}</td><td>{deltaTag((curM.open ?? 0) - (predM?.open ?? 0))}</td></tr>
                  <tr><td>高优</td><td>{curM.high ?? 0}</td><td>{predM?.high ?? 0}</td><td>{deltaTag((curM.high ?? 0) - (predM?.high ?? 0))}</td></tr>
                  <tr><td>已关闭</td><td>{curM.closed ?? 0}</td><td>{predM?.closed ?? 0}</td><td>{deltaTag((curM.closed ?? 0) - (predM?.closed ?? 0))}</td></tr>
                </tbody>
              </table>
            </div>
            <div className="card">
              <div className="cardTitle" style={{ marginBottom: 8 }}>收敛性分析</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 13, color: "var(--text2)" }}>趋势：</span>
                {convergenceBadge(convergence.trend || "")}
                <span style={{ fontSize: 11, color: "var(--text3)" }}>（累计未关闭 {convergence.cumulative_open ?? 0}）</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, color: "var(--text2)" }}>风险偏离度：</span>
                {deltaTag(convergence.deviation || 0)}
              </div>
              {convergence.detail && <p style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.7, marginTop: 8 }}>{convergence.detail}</p>}
            </div>
          </div>

          {data?.overall?.weeks && data.overall.weeks.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="cardTitle" style={{ marginBottom: 10 }}>趋势图</div>
              <TrendChart
                data={data.overall.weeks}
                series={[
                  { key: "cur_created", color: "#3b82f6", label: `${data?.current_version || "当前"} 新增` },
                  { key: "cur_closed", color: "#10b981", label: `${data?.current_version || "当前"} 关闭` },
                  { key: "pred_created", color: "#f59e0b", label: `${data?.predecessor_version || "历史"} 新增` },
                  { key: "pred_closed", color: "#94a3b8", label: `${data?.predecessor_version || "历史"} 关闭` },
                ]}
              />
            </div>
          )}
        </>
      )}

      {activeTab === "submit" && (
        <>
          {data?.ai_submit ? (
            <div style={{textAlign:"right",marginBottom:8}}>
              <button className="smallBtn" onClick={() => setShowAiModal("submit")} style={{padding:"4px 12px",fontSize:12,background:"var(--accent)",color:"#fff",border:"1px solid var(--accent)",borderRadius:6,cursor:"pointer"}}>🤖 查看 AI 模块趋势分析</button>
            </div>
          ) : (
            <div style={{textAlign:"right",marginBottom:8}}>
              <span style={{fontSize:12,color:"var(--text3)"}}>点击「🤖 重新AI分析」生成模块趋势分析</span>
            </div>
          )}
          {/* 重点模块对比表格 */}
          {data?.submit?.modules && data.submit.modules.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="cardTitle" style={{ marginBottom: 10 }}>重点模块提交问题数量（当前 vs 历史同期）</div>
              <div style={{ overflowX: "auto" }}>
                <table className="dataTable" style={{ fontSize: 12, minWidth: 700 }}>
                  <thead><tr>
                    <th>模块</th><th>当前总数</th><th>当前未关闭</th><th>当前高优</th><th>历史总数</th><th>历史未关闭</th><th>历史高优</th><th>总数差值</th><th>风险等级</th>
                  </tr></thead>
                  <tbody>
                    {data.submit.modules.map((m: any) => {
                      const riskColors: Record<string, string> = { "高": "#ef4444", "中": "#f59e0b", "低": "#10b981" };
                      return (
                        <tr key={m.module}>
                          <td><strong>{m.module}</strong></td>
                          <td>{m.total}</td>
                          <td>{m.open}</td>
                          <td style={{ color: m.high > 0 ? "#ef4444" : undefined, fontWeight: m.high > 0 ? 600 : 400 }}>{m.high}</td>
                          <td style={{ color: "var(--text3)" }}>{m.pred_total}</td>
                          <td style={{ color: "var(--text3)" }}>{m.pred_open}</td>
                          <td style={{ color: "var(--text3)" }}>{m.pred_high}</td>
                          <td>{deltaTag(m.delta_total)}</td>
                          <td><span style={{ color: riskColors[m.risk_level] || "#888", fontWeight: 600, fontSize: 12 }}>{m.risk_level}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 提交趋势对比图 */}
          {data?.submit?.chart_data?.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="cardTitle" style={{ marginBottom: 10 }}>提交趋势对比（每周新增 · 阶段对齐）</div>
              <TrendChart
                data={data.submit.chart_data}
                series={[
                  { key: "cur_created", color: "#3b82f6", label: `${data?.current_version || "当前"} 新增` },
                  { key: "pred_created", color: "#94a3b8", label: `${data?.predecessor_version || "历史"} 新增` },
                ]}
              />
            </div>
          )}

          {/* 收敛性评估 */}
          {data?.submit?.convergence && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="cardTitle" style={{ marginBottom: 10 }}>收敛性评估</div>
              <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13, color: "var(--text2)" }}>趋势：</span>
                  {convergenceBadge(data.submit.convergence.trend || "—")}
                </div>
                <span style={{ fontSize: 13, color: "var(--text2)" }}>新增斜率：<strong>{data.submit.convergence.slope ?? "-"}</strong>（近3周）</span>
                <span style={{ fontSize: 13, color: "var(--text2)" }}>关闭率：<strong>{data.submit.convergence.close_ratio ?? "-"}%</strong>（近3周）</span>
              </div>
              {data.submit.convergence.detail && <p style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.7 }}>{data.submit.convergence.detail}</p>}
            </div>
          )}

        </>
      )}

      {activeTab === "resolve" && (
        <>
          {data?.ai_resolve ? (
            <div style={{textAlign:"right",marginBottom:8}}>
              <button className="smallBtn" onClick={() => setShowAiModal("resolve")} style={{padding:"4px 12px",fontSize:12,background:"var(--accent)",color:"#fff",border:"1px solid var(--accent)",borderRadius:6,cursor:"pointer"}}>🤖 查看 AI 解决效率分析</button>
            </div>
          ) : (
            <div style={{textAlign:"right",marginBottom:8}}>
              <span style={{fontSize:12,color:"var(--text3)"}}>点击「🤖 重新AI分析」生成解决效率分析</span>
            </div>
          )}
          {/* 解决效率对比 */}
          <div className="grid3" style={{ marginBottom: 14 }}>
            <MetricCard label="当前关闭率" value={`${curM.close_rate ?? "-"}%`} note={predM ? `历史 ${predM.close_rate}%` : ""} />
            <MetricCard label="当前平均遗留" value={`${curM.avg_aging ?? "-"}天`} note={predM ? `历史 ${predM.avg_aging}天` : ""} danger={(curM.avg_aging ?? 0) > (predM?.avg_aging ?? 999)} />
            <MetricCard label="Reopen数" value={curM.reopen ?? 0} note={predM ? `历史 ${predM.reopen}` : ""} />
          </div>
          <div className="grid2" style={{ marginBottom: 14 }}>
            <MetricCard label="超14天未关闭" value={curM.over14 ?? 0} note={predM ? `历史 ${predM.over14}` : ""} danger={(curM.over14 ?? 0) > (predM?.over14 ?? 999)} />
            <MetricCard label="超30天未关闭" value={curM.over30 ?? 0} note={predM ? `历史 ${predM.over30}` : ""} danger={(curM.over30 ?? 0) > 0} />
          </div>

          {/* 解决趋势对比图 */}
          {data?.resolve?.chart_data?.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="cardTitle" style={{ marginBottom: 10 }}>解决趋势对比（每周关闭 · 阶段对齐）</div>
              <TrendChart
                data={data.resolve.chart_data}
                series={[
                  { key: "cur_closed", color: "#10b981", label: `${data?.current_version || "当前"} 关闭` },
                  { key: "pred_closed", color: "#94a3b8", label: `${data?.predecessor_version || "历史"} 关闭` },
                ]}
              />
            </div>
          )}

        </>
      )}

      {/* AI 分析弹窗 */}
      {showAiModal && (() => {
        const titles: Record<string, string> = { overall: "🤖 AI 整体趋势分析", submit: "🤖 AI 模块趋势分析", resolve: "🤖 AI 解决效率分析与建议" };
        const content: Record<string, string> = { overall: data?.ai_overall, submit: data?.ai_submit, resolve: data?.ai_resolve };
        return (
          <div className="modalMask" onClick={() => setShowAiModal(null)}>
            <div className="modal" style={{maxWidth:750,maxHeight:"75vh",padding:0}} onClick={e => e.stopPropagation()}>
              <div style={{padding:"16px 20px",borderBottom:"1px solid var(--card-border)"}}>
                <h2 style={{fontSize:15,margin:0}}>{titles[showAiModal]}</h2>
                {data?.generated_at && <span style={{fontSize:11,color:"var(--text3)",marginTop:2,display:"inline-block"}}>分析时间：{data.generated_at.replace("T"," ").slice(0,19)}</span>}
              </div>
              <div className="modalScrollBody" style={{padding:"16px 20px"}}>
                <div className="aiResult">{renderMarkdown(content[showAiModal] || "暂无分析结果")}</div>
              </div>
              <div style={{padding:"10px 20px",borderTop:"1px solid var(--card-border)",textAlign:"right"}}>
                <button className="secondaryBtn" onClick={() => setShowAiModal(null)}>关闭</button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}