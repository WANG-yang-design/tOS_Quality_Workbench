// 从 App.tsx 提取的日期工具函数 - 原样复制

export function getISOWeek(date: Date): { year: number; week: number } {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return { year: d.getUTCFullYear(), week };
}

export function getCurrentWeekInfo() {
  const now = new Date();
  const iso = getISOWeek(now);
  const day = now.getDay() || 7;
  const monday = new Date(now);
  monday.setDate(now.getDate() - day + 1);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const fmt = (d: Date) => String(d.getMonth() + 1).padStart(2, "0") + "." + String(d.getDate()).padStart(2, "0");
  return { year: iso.year, week: iso.week, start: fmt(monday), end: fmt(sunday) };
}

export function formatStageName(stage: string) {
  if (stage === "ALL") return "全部阶段";
  if (stage === "概念启动") return "概念启动";
  if (stage === "STR4A") return "STR4A";
  if (stage === "1+N版本火车") return "1+N版本火车";
  return stage;
}