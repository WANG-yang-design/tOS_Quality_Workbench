import React from "react";

// 从 App.tsx 第618行原样提取 - 不改任何样式
export function MetricCard({ label, value, note, danger }: any) {
  return <div className={"metricCard " + (danger ? "danger" : "")}><div className="metricLabel">{label}</div><div className="metricValue">{value}</div><div className="metricNote">{note}</div></div>;
}