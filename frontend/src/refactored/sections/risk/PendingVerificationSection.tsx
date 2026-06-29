import React, { useState, useEffect } from "react";
import { API_BASE, JIRA_BROWSE } from "../../constants";
import { MetricCard } from "../../components/common/MetricCard";
import { IssueLink } from "../../components/common/IssueLink";
import { IssueListModal } from "../../components/modals/IssueListModal";
import { exportIssueList, exportToExcel } from "../../utils/export";

// 从 App.tsx 第4720行原样提取 - 待验证问题分析组件
export function PendingVerificationSection({ activeVersion, activeStage, onDataUpdate, jiraSyncVersion }: any) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [showAllModal, setShowAllModal] = useState(false);
  const [showDeptStats, setShowDeptStats] = useState(false);
  const [selectedDept, setSelectedDept] = useState<string | null>(null);
  const cols = [
    { key: "issue_key", label: "问题ID" },
    { key: "summary", label: "问题描述" },
    { key: "status", label: "状态" },
    { key: "priority", label: "优先级" },
    { key: "assignee", label: "负责人" },
    { key: "assignee_third_dept_classified", label: "归类部门" },
    { key: "aging_days", label: "遗留天数", render: (i: any) => (i.aging_days ?? "-") + "天" },
  ];

  async function loadData() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/utp/pending-verification?stage=${activeStage || "ALL"}`);
      const d = await res.json();
      setData(d);
      if (onDataUpdate) onDataUpdate(d);
    } catch { const e = { total: 0, issues: [], error: "请求失败" }; setData(e); if (onDataUpdate) onDataUpdate(e); }
    finally { setLoading(false); }
  }

  async function refreshFromUTP() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/utp/pending-verification/refresh`, { method: "POST" });
      const d = await res.json();
      setData(d);
      if (onDataUpdate) onDataUpdate(d);
    } catch { alert("UTP 刷新失败"); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, [activeVersion?.id, activeStage, jiraSyncVersion]);

  const issues = data?.issues || [];
  const total = data?.total ?? 0;
  const resolvedCount = issues.filter((i: any) => i.status === "Resolved").length;
  const verifiedCount = issues.filter((i: any) => i.status === "Verified").length;
  const deptStats = data?.dept_stats || [];

  return (
    <div className="card">
      <div className="grid3">
        <MetricCard label="待验证问题总数" value={loading ? "..." : total} note="Resolved/Verified" danger={total > 0} />
        <MetricCard label="Resolved" value={loading ? "..." : resolvedCount} note="已解决待验" />
        <MetricCard label="Verified" value={loading ? "..." : verifiedCount} note="已验证待关" />
      </div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:10,paddingTop:8,borderTop:"1px dashed var(--card-border)"}}>
        <span style={{fontSize:13,color:"var(--text2)",fontWeight:500}}>
          {data?.error ? <span style={{color:"var(--danger)"}}>⚠ {data.error}</span> : <>
            {data?.source && <span className="badge badgeInfo" style={{marginRight:6}}>数据来源: {data.source}</span>}
            最近查询：{data?.synced_at ? data.synced_at.slice(5, 16).replace("T", " ") : "暂无"}
          </>}
        </span>
        <div style={{display:"flex",gap:8}}>
          <button className="primaryBtn" onClick={refreshFromUTP} disabled={loading} style={{padding:"4px 14px",fontSize:12}}>{loading ? "刷新中..." : "🔄 从 UTP 刷新"}</button>
          {issues.length > 0 && <button className="smallBtn" onClick={() => exportIssueList("待验证问题", issues, JIRA_BROWSE)} style={{padding:"4px 10px",fontSize:11}}>📥 导出</button>}
          <a className="sectionJiraLink" href="https://utp.transsion.com/utpweb/ProjectManage/defectAnalysis" target="_blank" rel="noreferrer">🔗 UTP 验证</a>
        </div>
      </div>

      {/* 部门分布统计 */}
      {deptStats.length > 0 && (
        <div className="subCard mt12">
          <div className="cardTitle" style={{cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between"}} onClick={() => setShowDeptStats(!showDeptStats)}>
            <span>📊 三级部门分布（归类后）</span>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <button className="smallBtn" onClick={(e) => {
                e.stopPropagation();
                // 导出部门分布（包含每个部门的issue单号）
                const exportData = deptStats.map((d: any) => {
                  const deptIssues = issues.filter((i: any) => (i.assignee_third_dept_classified || "未分类") === d.name);
                  return {
                    "归类部门": d.name,
                    "总数": d.count,
                    "Resolved": d.resolved,
                    "Verified": d.verified,
                    "占比": total > 0 ? (d.count / total * 100).toFixed(1) + "%" : "0%",
                    "Issue单号": deptIssues.map((i: any) => i.issue_key).join(", ")
                  };
                });
                exportToExcel("待验证问题_部门分布", [
                  { header: "归类部门", key: "归类部门" },
                  { header: "总数", key: "总数" },
                  { header: "Resolved", key: "Resolved" },
                  { header: "Verified", key: "Verified" },
                  { header: "占比", key: "占比" },
                  { header: "Issue单号", key: "Issue单号" },
                ], exportData);
              }} style={{padding:"3px 10px",fontSize:11}}>📥 导出部门分布</button>
              <span style={{fontSize:12,color:"var(--text3)"}}>{showDeptStats ? "▲ 收起" : "▼ 展开"}</span>
            </div>
          </div>
          {showDeptStats && (
            <table className="dataTable" style={{fontSize:12}}>
              <thead><tr><th>归类部门</th><th>总数</th><th>Resolved</th><th>Verified</th><th>占比</th><th>Issue单号</th></tr></thead>
              <tbody>{deptStats.map((d: any) => {
                const deptIssues = issues.filter((i: any) => (i.assignee_third_dept_classified || "未分类") === d.name);
                return (
                  <tr key={d.name} style={{cursor:"pointer",transition:"background .15s"}} onClick={() => setSelectedDept(d.name)}
                    onMouseEnter={e => e.currentTarget.style.background="var(--accent-soft)"}
                    onMouseLeave={e => e.currentTarget.style.background=""}>
                    <td style={{fontWeight:600}}>{d.name}</td>
                    <td style={{fontWeight:600,color:"var(--accent)"}}>{d.count}</td>
                    <td>{d.resolved}</td>
                    <td>{d.verified}</td>
                    <td style={{color:"var(--text3)"}}>{total > 0 ? (d.count / total * 100).toFixed(1) : 0}%</td>
                    <td style={{fontSize:11,maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={deptIssues.map((i: any) => i.issue_key).join(", ")}>
                      {deptIssues.slice(0, 3).map((i: any) => (
                        <a key={i.issue_key} href={`${JIRA_BROWSE}${i.issue_key}`} target="_blank" rel="noreferrer"
                          style={{color:"var(--accent)",textDecoration:"underline",marginRight:4,fontSize:11}}
                          onClick={e => e.stopPropagation()}>
                          {i.issue_key}
                        </a>
                      ))}
                      {deptIssues.length > 3 && <span style={{color:"var(--text3)",fontSize:11}}>+{deptIssues.length - 3}</span>}
                    </td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
        </div>
      )}
      {issues.length > 0 ? (
        <div className="subCard mt12" style={{padding:0}}>
          <div className="cardTitle" style={{cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px"}} onClick={() => setShowTable(!showTable)}>
            <span>待验证问题明细 <span style={{fontWeight:400,color:"var(--text3)",fontSize:12}}>（共 {total} 条）</span></span>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <button className="smallBtn" onClick={(e) => {
                e.stopPropagation();
                exportIssueList("待验证问题明细", issues, JIRA_BROWSE);
              }} style={{padding:"3px 10px",fontSize:11}}>📥 导出明细</button>
              <span style={{fontSize:12,color:"var(--text3)"}}>{showTable ? "▲ 收起" : "▼ 展开"}</span>
            </div>
          </div>
          {showTable && (
            <>
              <div style={{overflowX:"auto"}}><table className="dataTable" style={{margin:0}}><thead><tr><th>问题 ID</th><th>问题描述</th><th>状态</th><th>优先级</th><th>负责人</th><th>归类部门</th><th>遗留天数</th></tr></thead><tbody>
                {issues.slice(0, 10).map((i: any) => (
                  <tr key={i.issue_key}><td><IssueLink issueKey={i.issue_key} /></td><td style={{maxWidth:300,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td><td><span className={"badge " + (i.status === "Resolved" ? "badgeInfo" : "badgeWarn")}>{i.status}</span></td><td><span className={"badge " + (["Blocker","Critical"].includes(i.priority) ? "badgeRisk" : i.priority === "Major" ? "badgeWarn" : "badgeInfo")}>{i.priority}</span></td><td>{i.assignee || "未分配"}</td><td style={{fontSize:11,color:"var(--text2)"}}>{i.assignee_third_dept_classified || "-"}</td><td><span className={"badge " + ((i.aging_days ?? 0) > 14 ? "badgeRisk" : (i.aging_days ?? 0) > 7 ? "badgeWarn" : "badgeInfo")}>{i.aging_days ?? "-"}天</span></td></tr>
                ))}
              </tbody></table></div>
              {total > 10 && <button className="viewMoreBtn" onClick={() => setShowAllModal(true)}>查看更多（{total} 条）→</button>}
            </>
          )}
        </div>
      ) : !loading && (
        <p style={{color:"var(--text3)",textAlign:"center",padding:16,fontSize:13,marginTop:12}}>{total === 0 ? "✅ 当前无待验证问题" : "暂无数据"}</p>
      )}
      {showAllModal && <IssueListModal title="待验证问题" issues={issues} columns={cols} onClose={() => setShowAllModal(false)} />}
      {selectedDept && (() => {
        const deptIssues = issues.filter((i: any) => (i.assignee_third_dept_classified || "未分类") === selectedDept);
        return (
          <div className="modalMask" onClick={() => setSelectedDept(null)}>
            <div className="modal modalWide" onClick={e => e.stopPropagation()}>
              <div className="modalHeader">
                <h2>📋 {selectedDept}（{deptIssues.length} 条）</h2>
              </div>
              <div className="modalTableWrap">
                <table className="dataTable" style={{fontSize:12}}>
                  <thead><tr><th>问题 ID</th><th>问题描述</th><th>状态</th><th>优先级</th><th>负责人</th><th>遗留天数</th></tr></thead>
                  <tbody>{deptIssues.map((i: any) => (
                    <tr key={i.issue_key}>
                      <td><IssueLink issueKey={i.issue_key} /></td>
                      <td style={{maxWidth:300,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={i.summary}>{i.summary}</td>
                      <td><span className="badge badgeInfo">{i.status}</span></td>
                      <td><span className={"badge " + (["Blocker","Critical"].includes(i.priority) ? "badgeRisk" : "badgeWarn")}>{i.priority}</span></td>
                      <td>{i.assignee || "未分配"}</td>
                      <td>{i.aging_days ?? "-"}天</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <div className="modalActions">
                <button className="secondaryBtn" onClick={() => setSelectedDept(null)}>关闭</button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}