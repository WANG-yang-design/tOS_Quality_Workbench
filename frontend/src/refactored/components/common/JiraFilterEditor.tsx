import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第4371行原样提取 - Jira Filter Editor 组件
export function JiraFilterEditor({ versionId, filterKey, activeStage }: { versionId: number; filterKey: string; activeStage?: string }) {
  const [filter, setFilter] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [editJql, setEditJql] = useState("");
  const [saving, setSaving] = useState(false);
  const [resolved, setResolved] = useState<any>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!versionId) return;
    fetch(API_BASE + `/api/versions/${versionId}/filters`)
      .then(r => r.json())
      .then(data => {
        const f = (data.filters || []).find((x: any) => x.filter_key === filterKey);
        setFilter(f);
      })
      .catch(() => {});
  }, [versionId, filterKey]);

  useEffect(() => {
    if (!versionId || !filterKey) return;
    const stageParam = activeStage ? `?stage=${activeStage}` : "";
    fetch(API_BASE + `/api/versions/${versionId}/jql/${filterKey}${stageParam}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setResolved(data); })
      .catch(() => {});
  }, [versionId, filterKey, activeStage, filter]);

  async function handleSave() {
    if (!versionId || !filterKey) return;
    setSaving(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${versionId}/filters/${filterKey}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_jql: editJql }),
      });
      if (res.ok) {
        const data = await res.json();
        // 使用后端返回的完整 filter 数据更新状态
        if (data.filter) {
          setFilter(data.filter);
        } else {
          setFilter({ ...filter, custom_jql: editJql, updated_at: new Date().toISOString() });
        }
        setEditing(false);
        // Re-resolve JQL
        const stageParam = activeStage ? `?stage=${activeStage}` : "";
        const rRes = await fetch(API_BASE + `/api/versions/${versionId}/jql/${filterKey}${stageParam}`);
        if (rRes.ok) setResolved(await rRes.json());
      }
    } catch { /* ignore */ }
    finally { setSaving(false); }
  }

  async function handleReset() {
    if (!versionId || !filterKey) return;
    setSaving(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${versionId}/filters/${filterKey}/reset`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        // 使用后端返回的完整 filter 数据更新状态
        if (data.filter) {
          setFilter(data.filter);
        } else {
          setFilter({ ...filter, custom_jql: null, updated_at: new Date().toISOString() });
        }
        setEditing(false);
        const stageParam = activeStage ? `?stage=${activeStage}` : "";
        const rRes = await fetch(API_BASE + `/api/versions/${versionId}/jql/${filterKey}${stageParam}`);
        if (rRes.ok) setResolved(await rRes.json());
      }
    } catch { /* ignore */ }
    finally { setSaving(false); }
  }

  if (!filter) return null;

  const isCustom = !!filter.custom_jql;
  const displayJql = resolved?.jql_resolved || "";

  return (
    <div style={{marginBottom:8}}>
      <div style={{display:"flex",alignItems:"center",gap:6,flexWrap:"wrap"}}>
        {resolved?.jira_url && (
          <a className="sectionJiraLink" href={resolved.jira_url} target="_blank" rel="noreferrer" title={"JQL: " + displayJql}>
            🔗 Jira 验证
          </a>
        )}
        <button
          onClick={() => { setExpanded(!expanded); if (!expanded && !editing) setEditJql(displayJql || filter.custom_jql || filter.default_jql); }}
          style={{padding:"2px 8px",fontSize:11,borderRadius:5,cursor:"pointer",background:isCustom ? "var(--accent-soft)" : "var(--surface)",color:isCustom ? "var(--accent)" : "var(--text3)",border:"1px solid " + (isCustom ? "var(--accent)" : "var(--card-border)"),transition:"all .15s"}}
          title={isCustom ? "此 Filter 已自定义，点击编辑" : "点击编辑此 Filter"}
        >
          {isCustom ? "✏️ 已自定义" : "⚙️ Filter"}
        </button>
        {isCustom && (
          <button onClick={handleReset} disabled={saving}
            style={{padding:"2px 8px",fontSize:11,borderRadius:5,cursor:"pointer",background:"transparent",color:"var(--danger)",border:"1px solid #fecaca"}}
            title="还原为初始默认设定">
            🔄 还原默认
          </button>
        )}
        {isCustom && (
          <span style={{fontSize:11,color:"var(--warn)",alignSelf:"center"}}>
            ⚠️ 已使用自定义 JQL，如不确定请点击「还原默认」
          </span>
        )}
      </div>
      {expanded && (
        <div style={{marginTop:6,padding:"10px 12px",background:"var(--surface)",border:"1px solid var(--card-border)",borderRadius:8,fontSize:12}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
            <span style={{fontWeight:600,color:"var(--text)"}}>{filter.label}</span>
            <div style={{display:"flex",gap:8,alignItems:"center"}}>
              {filter.description && <span style={{color:"var(--text3)",fontSize:11}}>{filter.description}</span>}
              {!editing && (
                <button onClick={() => { setEditing(true); setEditJql(filter.custom_jql || filter.default_jql); }}
                  style={{padding:"3px 10px",fontSize:11,borderRadius:5,cursor:"pointer",background:"var(--accent)",color:"#fff",border:"1px solid var(--accent)"}}>
                  ✏️ 编辑
                </button>
              )}
            </div>
          </div>
          {editing ? (
            <>
              <textarea
                value={editJql}
                onChange={e => setEditJql(e.target.value)}
                style={{width:"100%",minHeight:60,fontFamily:"monospace",fontSize:12,padding:8,borderRadius:6,border:"1px solid var(--card-border)",background:"var(--bg)",color:"var(--text)",resize:"vertical",boxSizing:"border-box"}}
                placeholder="输入 JQL 模板..."
              />
              <div style={{display:"flex",gap:6,marginTop:6,alignItems:"center"}}>
                <button className="primaryBtn" onClick={handleSave} disabled={saving} style={{padding:"4px 14px",fontSize:12}}>
                  {saving ? "保存中..." : "💾 保存"}
                </button>
                <button className="secondaryBtn" onClick={() => setEditing(false)} style={{padding:"4px 14px",fontSize:12}}>取消</button>
                <button onClick={handleReset} disabled={saving}
                  style={{padding:"4px 14px",fontSize:12,borderRadius:6,cursor:"pointer",background:"transparent",color:"var(--danger)",border:"1px solid #fecaca",marginLeft:"auto"}}>
                  🔄 还原默认
                </button>
              </div>
            </>
          ) : (
            <div style={{fontFamily:"monospace",fontSize:11,color:"var(--text2)",whiteSpace:"pre-wrap",wordBreak:"break-all",lineHeight:1.6}}>
              {displayJql || "（未配置）"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}