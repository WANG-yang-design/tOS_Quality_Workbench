import React, { useState } from "react";

/**
 * AI 分析依据展示组件
 * 显示一个小 info 按钮，点击后展开 AI 的分析依据/prompt/判断标准
 */
export function AiCriteriaHint({ title, criteria }: { title: string; criteria: string | React.ReactNode }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <span style={{ display: "inline-flex", alignItems: "center", marginLeft: 6 }}>
      <button
        onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
        style={{
          width: 18, height: 18, borderRadius: "50%", border: "1px solid var(--card-border)",
          background: expanded ? "var(--accent-soft)" : "var(--surface)", color: expanded ? "var(--accent)" : "var(--text3)",
          fontSize: 11, fontWeight: 700, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center",
          transition: "all .15s", lineHeight: 1, padding: 0,
        }}
        title={`查看 ${title} 分析依据`}
      >i</button>
      {expanded && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 50,
          minWidth: 320, maxWidth: 480, padding: "12px 16px",
          background: "var(--surface)", border: "1px solid var(--card-border)", borderRadius: 10,
          boxShadow: "0 8px 24px rgba(0,0,0,0.12)", fontSize: 12, lineHeight: 1.8, color: "var(--text2)",
          whiteSpace: "pre-wrap",
        }}>
          <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6, fontSize: 13 }}>📋 {title} — 分析依据</div>
          {typeof criteria === "string" ? <div>{criteria}</div> : criteria}
        </div>
      )}
    </span>
  );
}