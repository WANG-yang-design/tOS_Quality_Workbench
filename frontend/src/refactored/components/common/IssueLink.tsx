import React from "react";
import { JIRA_BROWSE } from "../../constants";

// IssueLink - Jira 问题链接组件（从 App.tsx 使用推断）
export function IssueLink({ issueKey }: { issueKey: string }) {
  if (!issueKey) return <span style={{color:"var(--text3)"}}>-</span>;
  return <a className="issueId" href={JIRA_BROWSE + issueKey} target="_blank" rel="noreferrer">{issueKey}</a>;
}