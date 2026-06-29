import React from "react";

// 从 App.tsx 第4884行原样提取 - 简易饼状图（SVG）
export function PieChart({ data, size = 120 }: { data: { label: string; value: number; color: string }[]; size?: number }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return null;
  const r = size / 2 - 4;
  const cx = size / 2, cy = size / 2;

  let acc = 0;
  const slices = data.map(d => {
    const startAngle = (acc / total) * 2 * Math.PI - Math.PI / 2;
    acc += d.value;
    const endAngle = (acc / total) * 2 * Math.PI - Math.PI / 2;
    const largeArc = d.value / total > 0.5 ? 1 : 0;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const pct = ((d.value / total) * 100).toFixed(0);
    return { ...d, path: `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc},1 ${x2},${y2} Z`, pct };
  });

  return (
    <div style={{display:"flex",alignItems:"center",gap:12}}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {slices.map(s => <path key={s.label} d={s.path} fill={s.color} stroke="var(--surface)" strokeWidth={1.5} />)}
      </svg>
      <div style={{display:"flex",flexDirection:"column",gap:5}}>
        {slices.map(s => (
          <div key={s.label} style={{display:"flex",alignItems:"center",gap:6,fontSize:12}}>
            <span style={{width:10,height:10,borderRadius:2,background:s.color,flexShrink:0}} />
            <span style={{color:"var(--text2)"}}>{s.label}</span>
            <span style={{fontWeight:600,color:"var(--text)"}}>{s.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}