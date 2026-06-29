import React from "react";

// 从 App.tsx 第586行原样提取
export function InfoRow({ label, value }: any) {
  return <div className="infoRow"><span className="infoLabel">{label}</span><span className="infoValue">{value}</span></div>;
}