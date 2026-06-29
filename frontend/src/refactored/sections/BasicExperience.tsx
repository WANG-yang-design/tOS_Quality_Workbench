import React, { useState } from "react";
import { SectionHeader } from "../components/common/SectionHeader";
import { MetricCard } from "../components/common/MetricCard";
import { IssueLink } from "../components/common/IssueLink";
import { IssueListModal } from "../components/modals/IssueListModal";

// 从 App.tsx 第4264行区域原样提取
export function BasicExperienceSection({ metrics, risks }: any) {
  const [showAllMustFix, setShowAllMustFix] = useState(false);
  const mustFixCols = [
    { key: "issue_key", label: "问题ID" },
    { key: "summary", label: "问题描述" },
    { key: "model", label: "机型" },
    { key: "must_fix", label: "必解原因" },
    { key: "status", label: "状态" },
    { key: "aging_days", label: "时效", render: (i: any) => (i.aging_days ?? "-") + "天" },
  ];
  return (
    <div className="reportSection">
      <SectionHeader title="必解问题跟踪（AI 自动化计算）" />
      <div className="card"><div className="grid2"><div className="subCard"><div className="subCardTitle">待验证问题</div><div className="grid2"><MetricCard label="待验证总数" value={metrics.must_fix_pending_count ?? "__"} note="待验证" /><MetricCard label="超时未验" value={metrics.must_fix_timeout_count ?? "__"} note="> 3天" danger /></div></div><div className="subCard"><div className="subCardTitle">必解问题验证情况</div><div className="grid2"><MetricCard label="必解总数" value={metrics.must_fix_total_count ?? "__"} note="必解问题" /><MetricCard label="已验证通过" value={metrics.must_fix_pass_count ?? "__"} note="已通过" /></div></div></div><div className="subCard mt12"><div className="subCardTitle">必解问题明细 <span style={{fontWeight:400,color:"var(--text3)",fontSize:12}}>（{(risks.must_fix_issues || []).length} 条）</span></div><table className="dataTable"><thead><tr><th>问题 ID</th><th>问题描述</th><th>机型</th><th>必解原因</th><th>状态</th><th>时效</th></tr></thead><tbody>{(risks.must_fix_issues || []).slice(0, 8).map((i: any) => <tr key={i.issue_key}><td><IssueLink issueKey={i.issue_key} /></td><td>{i.summary}</td><td>{i.model || "-"}</td><td>{i.must_fix || "高优/版本阻塞"}</td><td><span className="badge badgeOpen">{i.status}</span></td><td>{i.aging_days ?? "-"}天</td></tr>)}</tbody></table>{(risks.must_fix_issues || []).length > 8 && <button className="viewMoreBtn" onClick={() => setShowAllMustFix(true)}>查看更多（{risks.must_fix_issues.length} 条）→</button>}</div>{showAllMustFix && <IssueListModal title="必解问题明细" issues={risks.must_fix_issues || []} columns={mustFixCols} onClose={() => setShowAllMustFix(false)} />}</div>
    </div>
  );
}