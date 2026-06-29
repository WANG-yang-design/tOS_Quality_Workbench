import { DEFAULT_JIRA_URL } from "../constants";
import type { VersionItem } from "../types";

/**
 * 获取主项目（第一个项目）。
 * tOS17.0 的 jira_project 为 "TOS170,LK7KOS17,X6878OS17"，
 * 但大部分 JQL 只需要主项目 TOS170。
 */
export function getPrimaryProject(jiraProject: string): string {
  return jiraProject.split(",")[0]?.trim() || jiraProject;
}

/** 将 jira_project 的主项目转为 JQL 的 project 条件（用于大部分查询） */
export function buildProjectJql(jiraProject: string): string {
  const primary = getPrimaryProject(jiraProject);
  return `project = ${primary}`;
}

/**
 * 构建 SR 遗留问题专用的 JQL project 条件。
 * tOS17.0 需要包含所有关联项目：project in (TOS170, LK7KOS17, X6878OS17)
 */
export function buildSrProjectJql(jiraProject: string): string {
  const projects = jiraProject.split(",").map(p => p.trim()).filter(Boolean);
  if (projects.length > 1) return `project in (${projects.join(",")})`;
  return `project = ${projects[0] || jiraProject}`;
}

/**
 * 在前端构建与后端 build_jql() 一致的 JQL（不含增量同步条件）。
 * 用于生成 Jira 看板链接，方便用户验证数据量。
 */
export function buildJiraJqlUrl(
  version: VersionItem | null,
  activeStage: string,
  stageSchedule: any[]
): string {
  if (!version) return "#";
  const parts: string[] = [`project = ${getPrimaryProject(version.jira_project)}`];

  if (activeStage && activeStage !== "ALL") {
    const stage = stageSchedule.find((s: any) => s.stage_name === activeStage);
    if (stage) {
      const startDate = (stage.start_date || "").trim();
      const endDate = (stage.end_date || "").trim();

      if (activeStage === "STA5") {
        if (startDate) parts.push(`created >= "${startDate}"`);
      } else if (startDate && endDate) {
        parts.push(`created >= "${startDate}"`);
        parts.push(`created <= "${endDate}"`);
      } else if (startDate) {
        parts.push(`created >= "${startDate}"`);
      } else if (endDate) {
        parts.push(`created <= "${endDate}"`);
      }
    }
  }

  const jql = parts.join(" AND ") + " ORDER BY created DESC";
  return `${DEFAULT_JIRA_URL}/issues/?jql=${encodeURIComponent(jql)}`;
}