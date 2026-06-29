import React, { useState, useRef, useCallback } from "react";

const VW = 900, VH = 340, PL = 55, PR = 25, PT = 35, PB = 55;

export function TrendChart({ data, series }: any) {
  if (!data || data.length === 0) return <div style={{ color: "var(--text3)", padding: 24, textAlign: "center", fontSize: 14 }}>暂无趋势数据</div>;

  const cW = VW - PL - PR, cH = VH - PT - PB;
  const allVals = series.flatMap((s: any) => data.map((d: any) => d[s.key] || 0));
  const maxVal = Math.max(...allVals, 1);
  const niceMax = Math.ceil(maxVal * 1.1);
  const anchorIdx = data.findIndex((d: any) => d.week_idx === 0);
  const svgRef = useRef<SVGSVGElement>(null);

  function svgPt(i: number, v: number) {
    return { x: PL + (i / Math.max(data.length - 1, 1)) * cW, y: PT + cH - (v / niceMax) * cH };
  }
  function linePath(key: string) {
    return data.map((_: any, i: number) => { const p = svgPt(i, data[i][key] || 0); return (i === 0 ? "M" : "L") + p.x + "," + p.y; }).join(" ");
  }
  function areaPath(key: string) {
    const lp = linePath(key); const last = svgPt(data.length - 1, 0); const first = svgPt(0, 0);
    return lp + " L" + last.x + "," + (PT + cH) + " L" + first.x + "," + (PT + cH) + " Z";
  }

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    // 鼠标在 SVG 渲染区域中的像素 → 映射到 viewBox 坐标
    const svgX = ((e.clientX - rect.left) / rect.width) * VW;
    let closest = 0, minDist = Infinity;
    for (let i = 0; i < data.length; i++) {
      const dist = Math.abs(svgPt(i, 0).x - svgX);
      if (dist < minDist) { minDist = dist; closest = i; }
    }
    setHoverIdx(closest);
  }, [data]);

  const handleMouseLeave = useCallback(() => setHoverIdx(null), []);

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} viewBox={`0 0 ${VW} ${VH}`}
        style={{ width: "100%", height: 340, display: "block" }}
        onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
        <defs>{series.map((s: any) => (
          <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={s.color} stopOpacity={0.18} />
            <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
          </linearGradient>
        ))}</defs>
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = PT + cH * (1 - pct);
          return <g key={pct}>
            <line x1={PL} y1={y} x2={VW - PR} y2={y} stroke="#e5e7eb" strokeWidth={0.5} />
            <text x={PL - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#9ca3af">{Math.round(niceMax * pct)}</text>
          </g>;
        })}
        {anchorIdx >= 0 && (() => {
          const p = svgPt(anchorIdx, 0);
          return <g>
            <line x1={p.x} y1={PT} x2={p.x} y2={PT + cH} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="6,3" />
            <text x={p.x} y={PT + cH + 32} textAnchor="middle" fontSize={10} fill="#f59e0b" fontWeight={700}>▼ 阶段开始</text>
          </g>;
        })()}
        {series.map((s: any) => (
          <g key={s.key}>
            <path d={areaPath(s.key)} fill={`url(#g-${s.key})`} />
            <path d={linePath(s.key)} fill="none" stroke={s.color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
          </g>
        ))}
        {series.map((s: any) =>
          data.map((d: any, i: number) => {
            const p = svgPt(i, d[s.key] || 0);
            return <circle key={`${s.key}-${i}`} cx={p.x} cy={p.y} r={hoverIdx === i ? 5 : 3} fill={s.color} stroke="#fff" strokeWidth={hoverIdx === i ? 2 : 1} />;
          })
        )}
        {data.map((d: any, i: number) => {
          const step = Math.max(1, Math.floor(data.length / 12));
          if (i % step !== 0 && i !== data.length - 1 && d.week_idx !== 0) return null;
          const p = svgPt(i, 0);
          const isA = d.week_idx === 0;
          return <text key={i} x={p.x} y={PT + cH + 18} textAnchor="middle" fontSize={isA ? 10 : 9} fontWeight={isA ? 700 : 400} fill={isA ? "#f59e0b" : "#9ca3af"}>{d.label || ""}</text>;
        })}
        {series.map((s: any, i: number) => (
          <g key={s.key} transform={`translate(${PL + i * 220}, ${PT - 14})`}>
            <rect x={0} y={0} width={12} height={12} rx={3} fill={s.color} />
            <text x={16} y={10} fontSize={11} fill="var(--text2)">{s.label}</text>
          </g>
        ))}
        {hoverIdx !== null && (() => {
          const x = svgPt(hoverIdx, 0).x;
          return <line x1={x} y1={PT} x2={x} y2={PT + cH} stroke="#9ca3af" strokeWidth={1} strokeDasharray="4,3" />;
        })()}
        {/* Tooltip: foreignObject 直接在 SVG 坐标系中定位，零转换误差 */}
        {hoverIdx !== null && (() => {
          const d = data[hoverIdx];
          const tipX = svgPt(hoverIdx, 0).x;
          const tipW = 180;
          // 边界检测：防止 tooltip 超出 SVG 左右边界
          const clampedX = Math.max(2, Math.min(tipX - tipW / 2, VW - tipW - 2));
          return (
            <foreignObject x={clampedX} y={2} width={tipW} height={120} style={{ pointerEvents: "none", overflow: "visible" }}>
              <div style={{
                background: "rgba(255,255,255,0.97)", border: "1px solid #e5e7eb",
                borderRadius: 8, padding: "8px 12px", fontSize: 11, lineHeight: 1.6,
                boxShadow: "0 4px 14px rgba(0,0,0,0.1)", whiteSpace: "nowrap",
                fontFamily: "inherit",
              }}>
                <div style={{ fontWeight: 700, marginBottom: 4, color: "#111827", borderBottom: "1px solid #f3f4f6", paddingBottom: 3 }}>
                  {d.label}{d.cur_week ? ` (${d.cur_week})` : ""}
                </div>
                {series.map((s: any) => (
                  <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: s.color, flexShrink: 0 }} />
                    <span style={{ color: "#6b7280" }}>{s.label}：</span>
                    <strong style={{ color: s.color }}>{d[s.key] ?? 0}</strong>
                  </div>
                ))}
              </div>
            </foreignObject>
          );
        })()}
      </svg>
    </div>
  );
}