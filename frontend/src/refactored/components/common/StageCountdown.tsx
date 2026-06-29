import React, { useState, useEffect } from "react";
import { formatStageName } from "../../utils/date";

/**
 * 阶段倒计时组件
 * 显示当前阶段到下一个阶段截止日期的剩余时间
 */
export function StageCountdown({ stageSchedule, activeStage }: { stageSchedule: any[]; activeStage: string }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000); // 每分钟更新
    return () => clearInterval(timer);
  }, []);

  if (!stageSchedule || stageSchedule.length === 0 || !activeStage || activeStage === "ALL") return null;

  // 找到当前阶段和下一阶段
  const order = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"];
  const currentIdx = order.indexOf(activeStage);
  if (currentIdx < 0) return null;

  const currentStage = stageSchedule.find(s => s.stage_name === activeStage);
  const nextStage = currentIdx < order.length - 1 ? stageSchedule.find(s => s.stage_name === order[currentIdx + 1]) : null;

  // 目标日期：当前阶段的 end_date
  const targetDate = currentStage?.end_date;
  if (!targetDate) return null;

  const target = new Date(targetDate + "T23:59:59");
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 10px", borderRadius: 10,
        background: "#fef2f2", border: "1px solid #fca5a5",
        fontSize: 11, fontWeight: 600, color: "#dc2626",
      }}>
        ⏰ {formatStageName(activeStage)} 已到期
      </span>
    );
  }

  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);

  // 根据剩余时间变色
  let bgColor = "#ecfdf5", borderColor = "#86efac", textColor = "#059669";
  if (days <= 1) { bgColor = "#fef2f2"; borderColor = "#fca5a5"; textColor = "#dc2626"; }
  else if (days <= 3) { bgColor = "#fffbeb"; borderColor = "#fde68a"; textColor = "#d97706"; }

  const timeStr = days > 0 ? `${days}天${hours}时` : hours > 0 ? `${hours}时${minutes}分` : `${minutes}分`;

  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: 10,
      background: bgColor, border: `1px solid ${borderColor}`,
      fontSize: 11, fontWeight: 600, color: textColor,
      transition: "all .3s",
    }} title={`${formatStageName(activeStage)} 截止：${targetDate}${nextStage ? `\n下一阶段：${formatStageName(nextStage.stage_name)}` : ""}`}>
      ⏳ {formatStageName(activeStage)} 剩余 <strong>{timeStr}</strong>
    </span>
  );
}