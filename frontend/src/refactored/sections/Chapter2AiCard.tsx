import React, { useState, useEffect, useRef } from "react";
import { API_BASE } from "../constants";

// 从 AppRefactored.tsx 内联提取 - 第二章 AI 综合分析入口卡片
export function Chapter2AiCard({ activeVersion, activeStage, jiraSyncVersion }: any) {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const versionIdRef = useRef<number | null>(null);

  async function load() {
    if (!activeVersion?.id) { setSummary(null); setExpanded(false); return; }
    if (versionIdRef.current !== activeVersion.id) {
      setSummary(null); setExpanded(false); versionIdRef.current = activeVersion.id;
    }
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/chapter2-ai-summary?stage=${activeStage || "ALL"}`);
      const d = await res.json();
      if (d.cached) { setSummary(d); setExpanded(true); }
    } catch { /* ignore */ }
  }

  async function generate() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${activeVersion.id}/chapter2-ai-summary?stage=${activeStage || "ALL"}`, { method: "POST" });
      const d = await res.json();
      setSummary(d); setExpanded(true);
    } catch (e: any) { alert("AI 分析失败：" + (e.message || "未知错误")); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [activeVersion?.id, activeStage, jiraSyncVersion]);

  return (
    <div style={{margin:"12px 0 8px",padding:"12px 18px",borderRadius:10,background:"linear-gradient(135deg, var(--accent-soft), var(--bg2))",border:"1px solid var(--accent)"}}>
      <div style={{display:"flex",alignItems:"center",gap:14,flexWrap:"wrap"}}>
        <span style={{fontSize:24}}>🤖</span>
        <div style={{flex:1,minWidth:180}}>
          <div style={{fontSize:15,fontWeight:800,color:"var(--accent)"}}>第二章 AI 综合分析</div>
          <div style={{fontSize:11,color:"var(--text2)",marginTop:1}}>综合 SR 需求、Jira 数据、进度风险、自定义风险项，输出整体分析与建议</div>
        </div>
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          {summary?.generated_at && (
            <span style={{fontSize:11,color:"var(--text2)"}}>{summary.generated_at.slice(0, 16).replace("T", " ")}</span>
          )}
          <button className="primaryBtn" onClick={generate} disabled={loading} style={{padding:"6px 20px",fontSize:13,fontWeight:600}}>
            {loading ? "⏳ 分析中..." : "🤖 一键 AI 分析"}
          </button>
          {summary?.summary && (
            <button className="smallBtn" onClick={() => setExpanded(!expanded)} style={{padding:"5px 12px",fontSize:12}}>
              {expanded ? "收起 ▲" : "展开 ▼"}
            </button>
          )}
        </div>
      </div>
      {expanded && summary?.summary && (
        <div style={{marginTop:12,padding:14,background:"var(--surface)",border:"1px solid var(--card-border)",borderRadius:8,lineHeight:1.9,fontSize:13,whiteSpace:"pre-wrap",color:"var(--text)"}}>
          {summary.summary}
        </div>
      )}
    </div>
  );
}