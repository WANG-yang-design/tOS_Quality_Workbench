/**
 * 导出表格数据为 Excel 文件（HTML Table 格式，Excel 可直接打开）
 * 支持超链接（如 Jira Issue 链接）
 *
 * @param title - 文件名标题（中文）
 * @param columns - 列定义 [{ header, key, render?, linkBase? }]
 * @param rows - 数据行
 */
export function exportToExcel(
  title: string,
  columns: { header: string; key: string; render?: (row: any) => string; linkBase?: string }[],
  rows: any[]
) {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const filename = `${title}_${today}.xls`;

  let html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>${title}</x:Name></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]--></head>
<body><table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px;">
<thead><tr style="background:#f0f0f0;font-weight:bold;">`;

  for (const col of columns) {
    html += `<th>${escapeHtml(col.header)}</th>`;
  }
  html += `</tr></thead><tbody>`;

  for (const row of rows) {
    html += `<tr>`;
    for (const col of columns) {
      let cellValue = "";
      let cellLink = "";

      if (col.render) {
        cellValue = col.render(row);
      } else {
        cellValue = row[col.key] != null ? String(row[col.key]) : "";
      }

      // 如果有 linkBase，生成超链接
      if (col.linkBase && row[col.key]) {
        cellLink = col.linkBase + encodeURIComponent(row[col.key]);
      }

      if (cellLink) {
        html += `<td><a href="${escapeHtml(cellLink)}" target="_blank" style="color:#1890ff;text-decoration:underline;">${escapeHtml(cellValue)}</a></td>`;
      } else {
        html += `<td>${escapeHtml(cellValue)}</td>`;
      }
    }
    html += `</tr>`;
  }

  html += `</tbody></table></body></html>`;

  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** 导出 SR 需求列表（保留调用方排序，支持 AI 风险等级 / 计划验收紧迫度两种模式） */
export function exportSrList(
  title: string,
  srList: any[],
  almSpaceBid?: string,
  almAppBid?: string,
  srAiPriority?: Record<string, { risk_level: string; analysis: string }>,
  sortMode?: "ai_priority" | "acceptance"
) {
  const almBase = `https://alm.transsion.com/#/space/${almSpaceBid || ""}/${almAppBid || ""}?viewMode=tableView&appTypeCode=&appType=OBJECT`;
  const jiraBrowse = "http://jira.transsion.com/browse/";

  const riskLabel = (level?: string) => {
    if (level === "high") return "🔴 高风险";
    if (level === "medium") return "🟡 中风险";
    if (level === "low") return "🟢 低风险";
    return "-";
  };

  // 计划验收紧迫度模式：按时间计算紧迫度
  const urgencyLabel = (sr: any) => {
    if (!sr.planned_acceptance) return "-";
    try {
      const acceptDate = new Date(sr.planned_acceptance);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      acceptDate.setHours(0, 0, 0, 0);
      const days = Math.ceil((acceptDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
      if (days < 0) return `🔴 已逾期${Math.abs(days)}天`;
      if (days <= 7) return `🟡 ${days}天后到期`;
      return `🟢 还有${days}天`;
    } catch { return "-"; }
  };

  const riskHeader = sortMode === "acceptance" ? "紧迫度" : "风险等级";

  exportToExcel(title, [
    { header: riskHeader, key: "_risk", render: (r) => sortMode === "acceptance" ? urgencyLabel(r) : riskLabel(srAiPriority?.[r.coding]?.risk_level) },
    { header: "SR 编号", key: "coding", linkBase: almBase },
    { header: "需求名称", key: "name" },
    { header: "A类(Blocker)", key: "_a", render: (r) => String((r.issue_severity_count?.blocker || 0)) },
    { header: "B类(Critical)", key: "_b", render: (r) => String((r.issue_severity_count?.critical || 0)) },
    { header: "C类(Major)", key: "_c", render: (r) => String((r.issue_severity_count?.major || 0)) },
    { header: "DI值", key: "_di", render: (r) => { const sc = r.issue_severity_count || {}; return ((sc.blocker||0)*10 + (sc.critical||0)*3 + (sc.major||0)*1 + (sc.other||0)*0.1).toFixed(1); } },
    { header: "关联 Issue 数", key: "issue_count" },
    { header: "关联 Issue（可跳转）", key: "_issues", render: (r) => (r.issue_keys || []).join(", "), linkBase: jiraBrowse },
    { header: "测试模块主责人", key: "test_module_owners_display" },
    { header: "计划验收", key: "planned_acceptance", render: (r) => r.planned_acceptance ? r.planned_acceptance.slice(0, 10) : "" },
    { header: "状态", key: "status" },
    { header: "AI 风险分析", key: "_ai", render: (r) => srAiPriority?.[r.coding]?.analysis || "" },
  ], srList);
}

/** 导出 Issue 列表（带 Jira 链接） */
export function exportIssueList(title: string, issues: any[], jiraBrowseBase: string = "http://jira.transsion.com/browse/") {
  exportToExcel(title, [
    { header: "问题 ID", key: "issue_key", linkBase: jiraBrowseBase },
    { header: "问题描述", key: "summary" },
    { header: "状态", key: "status" },
    { header: "优先级", key: "priority" },
    { header: "负责人", key: "assignee" },
    { header: "遗留天数", key: "aging_days", render: (r) => (r.aging_days ?? "") + "天" },
    { header: "机型", key: "model" },
    { header: "归类部门", key: "assignee_third_dept_classified" },
  ], issues);
}

/** 导出 UTP 缺陷列表 */
export function exportUtpIssues(title: string, issues: any[]) {
  exportToExcel(title, [
    { header: "问题编号", key: "jiraKey", linkBase: "http://jira.transsion.com/browse/" },
    { header: "问题描述", key: "summary" },
    { header: "优先级", key: "bugClass" },
    { header: "状态", key: "fixStatus" },
    { header: "解决方式", key: "resolution" },
    { header: "负责人", key: "assignee" },
    { header: "报告人", key: "reporter" },
    { header: "创建时间", key: "createTime", render: (r) => r.createTime ? r.createTime.slice(0, 10) : "" },
  ], issues);
}

/** 导出加锁 SR 列表 */
export function exportLockedSrList(title: string, srList: any[], almSpaceBid?: string, almAppBid?: string) {
  const almBase = `https://alm.transsion.com/#/space/${almSpaceBid || ""}/${almAppBid || ""}?viewMode=tableView&appTypeCode=&appType=OBJECT`;
  exportToExcel(title, [
    { header: "SR 编号", key: "sr_coding", linkBase: almBase },
    { header: "需求名称", key: "sr_name" },
    { header: "状态", key: "life_cycle_name" },
    { header: "优先级", key: "priority" },
    { header: "测试主责人", key: "test_representative" },
  ], srList);
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br>");
}