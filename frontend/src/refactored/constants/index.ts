// 从 App.tsx 提取的常量
// 开发模式下 API_BASE 为空（由 vite proxy 转发）
// 生产模式下如需直连后端，设置 VITE_API_BASE 环境变量

export const API_BASE = import.meta.env.VITE_API_BASE || "";
export const DEFAULT_JIRA_URL = "http://jira.transsion.com";
export const JIRA_BROWSE = DEFAULT_JIRA_URL + "/browse/";
export const UTP_WEB_URL = "https://utp.transsion.com/utpweb";

export const STAGES = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车", "ALL"];

export const STAGE_DISPLAY_NAMES: Record<string, string> = {
  "概念启动": "概念启动",
  "STR1": "STR1",
  "STR2": "STR2",
  "STR3": "STR3",
  "STR4": "STR4",
  "STR4A": "STR4A",
  "STR5": "STR5",
  "1+N版本火车": "1+N版本火车",
  "ALL": "全部",
};

export const REPORT_SECTIONS = [
  { key: "overview", icon: "📊", title: "项目概况" },
  { key: "risk", icon: "⚡", title: "风险和问题总结",
    children: [
      { key: "sec-ch2-overview", label: "一、质量风险总结" },
      { key: "sec-ch2-1-1", label: "  └ 1.1 SR 需求相关风险" },
      { key: "sec-ch2-1-2", label: "  └ 1.2 基础体验相关风险" },
      { key: "sec-ch2-1-3", label: "  └ 1.3 基础公共相关风险" },
      { key: "sec-ch2-1-4", label: "  └ 1.4 价值点相关风险" },
      { key: "sec-ch2-jira",    label: "二、Jira 风险" },
      { key: "sec-ch2-1",    label: "  └ 2.1 Jira 数据概览" },
      { key: "sec-ch2-trend",   label: "  └ 2.2 Jira 趋势分析" },
      { key: "sec-open-reopen", label: "  └ 2.3 Open/Reopened" },
      { key: "sec-submitted-modifying", label: "  └ 2.4 Submitted/Modifying" },
      { key: "sec-pending-verification", label: "  └ 2.5 待验证问题" },
      { key: "sec-ch2-3", label: "三、进度风险" },
      { key: "sec-ch2-4", label: "四、其他风险" },
    ]
  },
  { key: "key-test-activity", icon: "🎯", title: "重点测试活动" },
  { key: "workload", icon: "⏱️", title: "工时情况" }
];