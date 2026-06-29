import React from "react";

// 从 App.tsx 第809行原样提取 - 机型横向Tab切换选择器
export function DeviceTabSelector({ devices, activeDevice, onSelect }: { devices: string[]; activeDevice: string; onSelect: (d: string) => void }) {
  if (devices.length <= 1) return null;
  return (
    <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:14}}>
      {devices.map(d => (
        <button key={d}
          onClick={() => onSelect(d)}
          style={{
            padding:"6px 16px",fontSize:13,fontWeight:activeDevice===d?600:400,
            background:activeDevice===d?"var(--accent)":"var(--surface)",
            color:activeDevice===d?"#fff":"var(--text2)",
            border:activeDevice===d?"1px solid var(--accent)":"1px solid var(--card-border)",
            borderRadius:8,cursor:"pointer",transition:"all .2s",whiteSpace:"nowrap",
          }}>
          {d}
        </button>
      ))}
    </div>
  );
}