import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";
import { exportSrList } from "../../utils/export";

// DI值计算函数
function calcDI(severityCount: any): number {
  if (!severityCount) return 0;
  return (
    (severityCount.blocker || 0) * 10 +
    (severityCount.critical || 0) * 3 +
    (severityCount.major || 0) * 1 +
    (severityCount.other || 0) * 0.1
  );
}

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

// 从 App.tsx 第5651行原样提取 - SR 需求详情弹窗
export function SRDetailListModal({ title, srList, srAiAnalyses, srAiPriority, sortMode, srAiLoadingSingle, setSrAiAnalyses, setSrAiLoadingSingle, activeVersion, setShowIssuePopup, onClose }: any) {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(srList.length / PAGE_SIZE));
  const startIdx = (page - 1) * PAGE_SIZE;
  const pageItems = srList.slice(startIdx, startIdx + PAGE_SIZE);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal modalWide" onClick={e => e.stopPropagation()}
        onWheel={e => e.stopPropagation()}>
        <div className="modalHeader">
          <h2>{title}</h2>
          <span className="modalCount">{srList.length} 个 · 第 {page}/{totalPages} 页</span>
        </div>
        <div className="modalTableWrap" style={{overflowX:"auto"}}>
          <table className="dataTable" style={{minWidth:900}}>
            <thead><tr>
              <th style={{whiteSpace:"nowrap",width:130}}>SR 编号</th>
              <th style={{whiteSpace:"nowrap",minWidth:150}}>需求名称</th>
              <th style={{whiteSpace:"nowrap",width:90,textAlign:"center"}}>A/B/C类</th>
              <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>DI值</th>
              <th style={{whiteSpace:"nowrap",width:80,textAlign:"center"}}>{sortMode === "acceptance" ? "紧迫度" : "风险等级"}</th>
              <th style={{whiteSpace:"nowrap",minWidth:150}}>测试模块主责人</th>
              <th style={{whiteSpace:"nowrap",width:90}}>计划验收</th>
              <th style={{minWidth:250}}>AI 风险分析</th>
            </tr></thead>
            <tbody>
              {pageItems.map((sr: any) => {
                const ai = srAiAnalyses[sr.coding];
                const singleLoading = srAiLoadingSingle[sr.coding];
                const sevCount = sr.issue_severity_count || {};
                const sevKeys = sr.issue_severity_keys || {};
                const diScore = calcDI(sevCount);
                const diRisk = diScore >= 30 ? "高" : diScore >= 10 ? "中" : "低";
                const diColor = diScore >= 30 ? "#dc2626" : diScore >= 10 ? "#ea580c" : "#16a34a";
                // 计算距离评审节点的天数
                const daysUntil = getDaysUntilAcceptance(sr);
                const daysText = daysUntil === null ? "" : daysUntil < 0 ? `已逾期${Math.abs(daysUntil)}天` : daysUntil === 0 ? "今天到期" : `还有${daysUntil}天`;
                const daysColor = daysUntil === null ? "var(--text3)" : daysUntil < 0 ? "#dc2626" : daysUntil <= 7 ? "#ea580c" : daysUntil <= 14 ? "#ca8a04" : "#16a34a";
                return (
                  <tr key={sr.coding}>
                    <td style={{whiteSpace:"nowrap"}}>
                      <a className="issueId" href={`https://alm.transsion.com/#/space/${activeVersion?.alm_space_bid || ""}/${activeVersion?.alm_app_bid || ""}?viewMode=tableView&appTypeCode=&appType=OBJECT`} target="_blank" rel="noreferrer"
                        style={{fontSize:12,fontWeight:600}} title="在 ALM 中打开">{sr.coding}</a>
                    </td>
                    <td style={{maxWidth:180,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={sr.name}>{sr.name || "-"}</td>
                    <td style={{textAlign:"center",whiteSpace:"nowrap"}}>
                      <span style={{color:"#dc2626",cursor:sevCount.blocker > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.blocker > 0 ? "1px dashed #dc2626" : "none"}}
                        onClick={() => sevCount.blocker > 0 && setShowIssuePopup && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.blocker || [], title: "A类(Blocker)" })}>
                        {sevCount.blocker || 0}
                      </span>
                      <span style={{color:"var(--text3)",margin:"0 2px"}}>/</span>
                      <span style={{color:"#ea580c",cursor:sevCount.critical > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.critical > 0 ? "1px dashed #ea580c" : "none"}}
                        onClick={() => sevCount.critical > 0 && setShowIssuePopup && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.critical || [], title: "B类(Critical)" })}>
                        {sevCount.critical || 0}
                      </span>
                      <span style={{color:"var(--text3)",margin:"0 2px"}}>/</span>
                      <span style={{color:"#ca8a04",cursor:sevCount.major > 0 ? "pointer" : "default",fontWeight:600,borderBottom:sevCount.major > 0 ? "1px dashed #ca8a04" : "none"}}
                        onClick={() => sevCount.major > 0 && setShowIssuePopup && setShowIssuePopup({ srCoding: sr.coding, issueKeys: sevKeys.major || [], title: "C类(Major)" })}>
                        {sevCount.major || 0}
                      </span>
                    </td>
                    <td style={{textAlign:"center"}}>
                      <span style={{color:diColor,fontWeight:700,fontSize:13}}>{diScore.toFixed(1)}</span>
                      <span style={{color:diColor,fontSize:10,marginLeft:2}}>({diRisk})</span>
                    </td>
                    <td style={{textAlign:"center"}}>
                      {sortMode === "acceptance" ? (
                        // 计划验收紧迫度模式：按时间划分
                        daysUntil !== null ? (
                          <span className={"badge " + (daysUntil < 0 ? "badgeRisk" : daysUntil <= 7 ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px"}}>
                            {daysUntil < 0 ? "已逾期" : daysUntil <= 7 ? "即将到期" : "正常"}
                          </span>
                        ) : <span style={{fontSize:11,color:"var(--text3)"}}>-</span>
                      ) : srAiPriority?.[sr.coding] ? (
                        <span className={"badge " + (srAiPriority[sr.coding].risk_level === "high" ? "badgeRisk" : srAiPriority[sr.coding].risk_level === "medium" ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px"}}>
                          {srAiPriority[sr.coding].risk_level === "high" ? "高风险" : srAiPriority[sr.coding].risk_level === "medium" ? "中风险" : "低风险"}
                        </span>
                      ) : (
                        // AI未分析时，用DI值作为参考风险等级
                        <span className={"badge " + (diScore >= 30 ? "badgeRisk" : diScore >= 10 ? "badgeWarn" : "badgeInfo")} style={{fontSize:10,padding:"1px 6px",opacity:0.7}} title="基于DI值估算，未经AI分析">
                          {diScore >= 30 ? "高(估)" : diScore >= 10 ? "中(估)" : "低(估)"}
                        </span>
                      )}
                    </td>
                    <td style={{whiteSpace:"normal",wordBreak:"break-word",lineHeight:1.6,fontSize:12}}>{sr.test_module_owners_display || "-"}</td>
                    <td style={{whiteSpace:"nowrap",fontSize:12}}>
                      <div>{sr.planned_acceptance ? sr.planned_acceptance.slice(0, 10) : "-"}</div>
                      {daysText && <div style={{color:daysColor,fontSize:10,marginTop:2}}>{daysText}</div>}
                    </td>
                    <td>
                      {ai ? (
                        <div style={{fontSize:12,lineHeight:1.5,color:"var(--text2)"}}>
                          <div style={{wordBreak:"break-word",whiteSpace:"normal"}} title={ai.analysis}>{ai.analysis}</div>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:4,gap:4}}>
                            <span style={{fontSize:10,color:"var(--text3)",whiteSpace:"nowrap",flexShrink:0}}>{ai.analyzed_at?.slice(0, 16).replace("T", " ")}</span>
                            <button className="smallBtn"
                              style={{padding:"2px 6px",fontSize:10,whiteSpace:"nowrap",borderRadius:4,color:"var(--danger)",border:"1px solid #fecaca",background:"transparent",flexShrink:0}}
                              title="删除此分析结果"
                              onClick={async () => {
                                setSrAiAnalyses((prev: any) => { const next = { ...prev }; delete next[sr.coding]; return next; });
                                try { await fetch(API_BASE + `/api/versions/${activeVersion?.id}/sr-ai-analysis?sr_coding=${encodeURIComponent(sr.coding)}`, { method: "DELETE" }); } catch { /* ignore */ }
                              }}>
                              🗑
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button className="smallBtn" disabled={singleLoading}
                          style={{padding:"3px 10px",fontSize:11,whiteSpace:"nowrap",background:singleLoading?"var(--accent-soft)":"transparent",color:singleLoading?"var(--accent)":"var(--text2)",border:"1px solid var(--card-border)",borderRadius:6,cursor:singleLoading?"wait":"pointer"}}
                          onClick={async () => {
                            setSrAiLoadingSingle((prev: any) => ({ ...prev, [sr.coding]: true }));
                            try {
                              const res = await fetch(API_BASE + `/api/versions/${activeVersion?.id}/sr-ai-analysis?sr_coding=${encodeURIComponent(sr.coding)}`, { method: "POST" });
                              const data = await res.json();
                              setSrAiAnalyses((prev: any) => ({ ...prev, ...data.analyses }));
                            } catch { alert("AI 分析失败"); }
                            finally { setSrAiLoadingSingle((prev: any) => ({ ...prev, [sr.coding]: false })); }
                          }}>
                          {singleLoading ? "🤖 分析中..." : "🤖 单独分析"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {pageItems.length === 0 && <tr><td colSpan={8} style={{textAlign:"center",color:"var(--text3)",padding:20}}>暂无数据</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="modalFooter">
          <div className="pagination">
            <button className="smallBtn" disabled={page <= 1} onClick={() => setPage(1)}>« 首页</button>
            <button className="smallBtn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ 上一页</button>
            <span className="pageInfo">第 {page} / {totalPages} 页</span>
            <button className="smallBtn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页 ›</button>
            <button className="smallBtn" disabled={page >= totalPages} onClick={() => setPage(totalPages)}>末页 »</button>
          </div>
          <button className="smallBtn" onClick={() => exportSrList(title, srList, activeVersion?.alm_space_bid, activeVersion?.alm_app_bid)} style={{padding:"5px 12px",fontSize:12}}>📥 导出 Excel</button>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}