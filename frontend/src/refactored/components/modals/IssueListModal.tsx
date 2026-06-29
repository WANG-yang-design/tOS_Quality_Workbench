import React, { useState, useEffect } from "react";
import { IssueLink } from "../common/IssueLink";
import { exportIssueList } from "../../utils/export";
import { JIRA_BROWSE } from "../../constants";

// 从 App.tsx 第5760行原样提取 - Issue 列表通用弹窗
export function IssueListModal({ title, issues, columns, onClose }: any) {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;
  const totalPages = Math.max(1, Math.ceil(issues.length / PAGE_SIZE));
  const startIdx = (page - 1) * PAGE_SIZE;
  const pageItems = issues.slice(startIdx, startIdx + PAGE_SIZE);

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
          <span className="modalCount">{issues.length} 条 · 第 {page}/{totalPages} 页</span>
        </div>
        <div className="modalTableWrap">
          <table className="dataTable">
            <thead><tr>{columns.map((c: any) => <th key={c.key}>{c.label}</th>)}</tr></thead>
            <tbody>
              {pageItems.map((i: any) => (
                <tr key={i.issue_key}>
                  {columns.map((c: any) => (
                    <td key={c.key}>
                      {c.key === "issue_key" ? <IssueLink issueKey={i.issue_key} />
                        : c.key === "status" ? <span className={"badge " + (["Closed","Done","Resolved","Verified","关闭","已解决","已验证"].includes(i.status) ? "badgeNormal" : "badgeOpen")}>{i.status}</span>
                        : c.key === "priority" ? <span className={"badge " + (["Blocker","Critical"].includes(i.priority) ? "badgeRisk" : "badgeWarn")}>{i.priority}</span>
                        : c.render ? c.render(i)
                        : (i[c.key] ?? "-")}
                    </td>
                  ))}
                </tr>
              ))}
              {pageItems.length === 0 && <tr><td colSpan={columns.length} style={{textAlign:"center",color:"var(--text3)",padding:20}}>暂无数据</td></tr>}
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
          <button className="smallBtn" onClick={() => exportIssueList(title, issues, JIRA_BROWSE)} style={{padding:"5px 12px",fontSize:12}}>📥 导出 Excel</button>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}