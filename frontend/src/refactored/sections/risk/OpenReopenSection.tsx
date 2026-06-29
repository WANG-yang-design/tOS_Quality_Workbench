import React, { useState, useEffect } from "react";
import { API_BASE, JIRA_BROWSE } from "../../constants";
import { MetricCard } from "../../components/common/MetricCard";
import { IssueLink } from "../../components/common/IssueLink";
import { IssueListModal } from "../../components/modals/IssueListModal";
import { exportIssueList } from "../../utils/export";

// 从 App.tsx 第4531行原样提取 - Open/Reopened 分析组件
export function OpenReopenSection({ activeVersion, activeStage, onDataUpdate, jiraSyncVersion }: any) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [showAllModal, setShowAllModal] = useState(false);
  const cols = [
    { key: "issue_key", label: "问题ID" },
    { key: "summary", label: "问题描述" },
    { key: "status", label: "状态" },
    { key: "priority", label: "优先级" },
    { key: "assignee", label: "负责人" },
    { key: "aging_days", label: "遗留天数", render: (i: any) => (i.aging_days ?? "-") + "天" },
  ];

  async function loadData(manual = false) {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/jira-issues/open_reopen?stage=${activeStage || "ALL"}&use_cache=${manual ? "false" : "true"}`);
      const d = await res.json();
      setData(d);
      if (onDataUpdate) onDataUpdate(d);
    } catch { const e = { total: 0, issues: [], error: "请求失败" }; setData(e); if (onDataUpdate) onDataUpdate(e); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadData(false); }, [activeVersion?.id, activeStage, jiraSyncVersion]);

  const issues = data?.issues || [];
  const total = data?.total ?? 0;
  const highCount = issues.filter((i: any) => ["Blocker", "Critical"].includes(i.priority)).length;
  const avgAging = issues.length > 0 ? Math.round(issues.reduce((s: number, i: any) => s + (i.aging_days || 0), 0) / issues.length) : 0;
  const openCount = issues.filter((i: any) => i.status === "Open").length;
  const reopenedCount = issues.filter((i: any) => ["Reopened", "Reopen", "重新打开"].includes(i.status)).length;

  return (
    <div className="card">
      <div className="grid4">
        <MetricCard label="Open/Reopened 总数" value={loading ? "..." : total} note="遗留问题" danger={total > 0} />
        <MetricCard label="高优 (Blocker/Critical)" value={loading ? "..." : highCount} note="需重点关注" danger={highCount > 0} />
        <MetricCard label="平均遗留天数" value={loading ? "..." : avgAging + "天"} note="越久风险越高" danger={avgAging > 14} />
        <div style={{display:"flex",flexDirection:"column",gap:4,justifyContent:"center"}}>
          <div style={{display:"flex",gap:8,alignItems:"center"}}><span style={{fontSize:12,color:"var(--text3)"}}>Open:</span><span className="badge badgeOpen">{openCount}</span></div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}><span style={{fontSize:12,color:"var(--text3)"}}>Reopened:</span><span className="badge badgeWarn">{reopenedCount}</span></div>
        </div>
      </div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:10,paddingTop:8,borderTop:"1px dashed var(--card-border)"}}>
        <span style={{fontSize:13,color:"var(--text2)",fontWeight:500}}>{data?.error ? <span style={{color:"var(--danger)"}}>⚠ {data.error}</span> : `最近查询：${data?.synced_at ? data.synced_at.slice(5, 16).replace("T", " ") : "暂无"}`}</span>
        <div style={{display:"flex",gap:8}}>
          <button className="primaryBtn" onClick={() => loadData(true)} disabled={loading} style={{padding:"4px 14px",fontSize:12}}>{loading ? "查询中..." : "🔄 刷新"}</button>
          {issues.length > 0 && <button className="smallBtn" onClick={() => exportIssueList("Open_Reopened遗留问题", issues, JIRA_BROWSE)} style={{padding:"4px 10px",fontSize:11}}>📥 导出</button>}
          {data?.jira_url && <a className="sectionJiraLink" href={data.jira_url} target="_blank" rel="noreferrer">🔗 Jira</a>}
        </div>
      </div>
      {issues.length > 0 ? (
        <div className="subCard mt12" style={{padding:0}}>
          <div className="cardTitle" style={{cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px"}} onClick={() => setShowTable(!showTable)}>
            <span>问题明细 <span style={{fontWeight:400,color:"var(--text3)",fontSize:12}}>（共 {total} 条）</span></span>
            <span style={{fontSize:12,color:"var(--text3)"}}>{showTable ? "▲ 收起" : "▼ 展开"}</span>
          </div>
          {showTable && (
            <>
              <div style={{overflowX:"auto"}}><table className="dataTable" style={{margin:0}}><thead><tr><th>问题 ID</th><th>问题描述</th><th>状态</th><th>优先级</th><th>负责人</th><th>遗留天数</th></tr></thead><tbody>
                {issues.slice(0, 10).map((i: any) => (
                  <tr key={i.issue_key}><td><IssueLink issueKey={i.issue_key} /></td><td style={{maxWidth:360,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td><td><span className="badge badgeOpen">{i.status}</span></td><td><span className={"badge " + (["Blocker","Critical"].includes(i.priority) ? "badgeRisk" : i.priority === "Major" ? "badgeWarn" : "badgeInfo")}>{i.priority}</span></td><td>{i.assignee || "未分配"}</td><td><span className={"badge " + ((i.aging_days ?? 0) > 14 ? "badgeRisk" : (i.aging_days ?? 0) > 7 ? "badgeWarn" : "badgeInfo")}>{i.aging_days ?? "-"}天</span></td></tr>
                ))}
              </tbody></table></div>
              {total > 10 && <button className="viewMoreBtn" onClick={() => setShowAllModal(true)}>查看更多（{total} 条）→</button>}
            </>
          )}
        </div>
      ) : !loading && (
        <p style={{color:"var(--text3)",textAlign:"center",padding:16,fontSize:13,marginTop:12}}>{total === 0 ? "✅ 当前无 Open/Reopened 状态的遗留问题" : "暂无数据"}</p>
      )}
      {showAllModal && <IssueListModal title="Open/Reopened 遗留问题" issues={issues} columns={cols} onClose={() => setShowAllModal(false)} />}
    </div>
  );
}