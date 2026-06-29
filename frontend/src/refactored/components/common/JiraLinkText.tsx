import React from "react";
import { JIRA_BROWSE } from "../../constants";

// 从 App.tsx 第4516行原样提取 - 渲染文本中的 Jira 编号为可跳转链接
export function JiraLinkText({ text }: { text: string }) {
  if (!text) return <>-</>;
  const parts = text.split(/(\b[A-Z][A-Z0-9]+-\d+\b)/g);
  return <>{parts.map((part, i) => {
    if (/^[A-Z][A-Z0-9]+-\d+$/.test(part)) {
      return <a key={i} className="issueId" href={JIRA_BROWSE + part} target="_blank" rel="noreferrer" title="在 Jira 中打开">{part}</a>;
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  })}</>;
}