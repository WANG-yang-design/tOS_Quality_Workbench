// 从 App.tsx 提取的阶段工具函数 - 原样复制

export function detectCurrentStageFromSchedule(schedule: any[]): string {
  // 优先从数据库 current_flag 判断（用户手动设置或飞书导入时标记的）
  const dbCurrent = schedule.find((s: any) => s.current_flag === 1);
  if (dbCurrent) return dbCurrent.stage_name;

  // 兜底：根据日期自动判断
  const today = new Date().toISOString().slice(0, 10);
  const order = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"];
  const deadlines: Record<string, string> = {};
  const startDates: Record<string, string> = {};

  schedule.forEach((s: any) => {
    if (s.end_date) deadlines[s.stage_name] = s.end_date;
    if (s.start_date) startDates[s.stage_name] = s.start_date;
  });

  for (let i = 0; i < order.length; i++) {
    const stageName = order[i];
    const end = deadlines[stageName];
    if (!end) continue;

    const start = startDates[stageName] || (i > 0 && deadlines[order[i - 1]]
      ? new Date(new Date(deadlines[order[i - 1]]).getTime() + 86400000).toISOString().slice(0, 10)
      : "0000-00-00");

    if (start <= today && today <= end) return stageName;
  }

  // 如果当前日期过了最后一个有截止日期的阶段
  for (let i = order.length - 1; i >= 0; i--) {
    if (deadlines[order[i]] && today > deadlines[order[i]]) return order[i];
  }

  return "";
}

/**
 * 格式化阶段名称用于显示
 */
export function formatStageDisplayName(stageName: string): string {
  const map: Record<string, string> = {
    "概念启动": "概念启动",
    "STR1": "STR1",
    "STR2": "STR2",
    "STR3": "STR3",
    "STR4": "STR4",
    "STR4A": "STR4A",
    "STR5": "STR5",
    "1+N版本火车": "1+N版本火车",
  };
  return map[stageName] || stageName;
}