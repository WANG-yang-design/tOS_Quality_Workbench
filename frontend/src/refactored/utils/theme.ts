// 从 App.tsx 提取的主题工具函数 - 原样复制

export function getVersionTheme(versionName?: string) {
  if (!versionName) {
    return { themeClass: "theme-162", accent: "#185FA5" };
  }
  if (versionName.includes("16.3")) {
    return { themeClass: "theme-163", accent: "#0F6E56" };
  }
  if (versionName.includes("17")) {
    return { themeClass: "theme-170", accent: "#534AB7" };
  }
  return { themeClass: "theme-162", accent: "#185FA5" };
}

export function getGanttUrl(versionName?: string): string | null {
  if (!versionName) return null;
  const m = versionName.match(/(\d+)\.(\d+)/);
  if (!m) return null;
  const major = m[1];
  const minor = m[2];
  const suffix = `${major}${minor}`;
  return `/gantt_tos${suffix}.html`;
}