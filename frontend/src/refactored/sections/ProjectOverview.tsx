import React, { useState, useEffect } from "react";
import { API_BASE, DEFAULT_JIRA_URL } from "../constants";
import { buildProjectJql } from "../utils/jira";
import { formatStageName } from "../utils/date";
import { getGanttUrl } from "../utils/theme";
import { SectionHeader } from "../components/common/SectionHeader";
import { ResourceCard } from "../components/common/ResourceCard";

// 从 AppRefactored.tsx 内联提取 - 基础信息 & 关键资源
export function ProjectOverviewSection({ activeVersion, metrics, risks, trends, activeStage, stageSchedule, onSyncJira, loading, onUpdateVersion }: any) {
  const [editing, setEditing] = useState(false);
  const [ownerName, setOwnerName] = useState(activeVersion?.owner_name || "");
  const [editingUrl, setEditingUrl] = useState(false);
  const [customUrl, setCustomUrl] = useState(activeVersion?.feishu_sheet_url || "");
  const [deviceInfo, setDeviceInfo] = useState<any>(null);
  const [deviceLoading, setDeviceLoading] = useState(false);
  const prevVersionIdRef = React.useRef<number | null>(null);
  const [contactMapUrl, setContactMapUrl] = useState<string>("");
  const [contactMapLoading, setContactMapLoading] = useState(false);

  useEffect(() => {
    if (activeVersion) {
      if (prevVersionIdRef.current !== activeVersion.id) {
        setDeviceInfo(null);
        setContactMapUrl("");
        prevVersionIdRef.current = activeVersion.id;
      }
      setOwnerName(activeVersion.owner_name || "");
      setCustomUrl(activeVersion.feishu_sheet_url || "");
    }
  }, [activeVersion]);

  async function loadDeviceInfo() {
    if (!activeVersion?.id) return;
    setDeviceLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/device-info");
      const data = await res.json();
      setDeviceInfo(data);
    } catch { setDeviceInfo({ categories: {}, text: "", message: "读取失败" }); }
    finally { setDeviceLoading(false); }
  }

  useEffect(() => {
    if (activeVersion?.id && activeVersion?.feishu_sheet_url) {
      loadDeviceInfo();
      loadContactMapUrl();
    }
  }, [activeVersion?.id, activeVersion?.feishu_sheet_url]);

  async function loadContactMapUrl() {
    if (!activeVersion?.id) return;
    setContactMapLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/contact-map-url");
      const data = await res.json();
      setContactMapUrl(data.url || "");
    } catch { setContactMapUrl(""); }
    finally { setContactMapLoading(false); }
  }

  async function handleSave() {
    if (!activeVersion?.id) return;
    const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_name: ownerName })
    });
    if (res.ok) { setEditing(false); if (onUpdateVersion) onUpdateVersion(); }
  }

  async function handleSaveUrl() {
    if (!activeVersion?.id) return;
    const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feishu_sheet_url: customUrl.trim() })
    });
    if (res.ok) { setEditingUrl(false); if (onUpdateVersion) onUpdateVersion(); }
  }

  const feishuUrl = activeVersion?.feishu_sheet_url || "";
  const jiraUrl = activeVersion ? `${DEFAULT_JIRA_URL}/issues/?jql=${encodeURIComponent(buildProjectJql(activeVersion.jira_project) + " ORDER BY created DESC")}` : "";

  return (
    <div className="reportSection">
      <SectionHeader title="基础信息 & 关键资源" />
      <div className="card" style={{marginBottom:14,padding:"14px 22px"}}>
        <div style={{display:"flex",alignItems:"center",gap:20,flexWrap:"wrap"}}>
          <div style={{display:"flex",alignItems:"center",gap:6}}><span style={{color:"var(--text3)",fontSize:12,fontWeight:600}}>项目</span><span style={{fontSize:14,fontWeight:600,color:"var(--text)"}}>{(activeVersion?.version_name || "-") + " 系统测试"}</span></div>
          <span style={{color:"var(--card-border)"}}>│</span>
          <div style={{display:"flex",alignItems:"center",gap:6}}><span style={{color:"var(--text3)",fontSize:12,fontWeight:600}}>阶段</span><span className="badge badgeInfo">{formatStageName(activeStage || "ALL")}</span></div>
          <span style={{color:"var(--card-border)"}}>│</span>
          <div style={{display:"flex",alignItems:"center",gap:6}}>
            <span style={{color:"var(--text3)",fontSize:12,fontWeight:600}}>负责人</span>
            {!editing ? (
              <span style={{fontSize:14,color:"var(--text)",cursor:"pointer",borderBottom:"1px dashed var(--card-border)"}} onClick={() => setEditing(true)} title="点击编辑">{ownerName || "未配置"}</span>
            ) : (
              <span style={{display:"inline-flex",alignItems:"center",gap:4}}>
                <input value={ownerName} onChange={e => setOwnerName(e.target.value)} placeholder="姓名" style={{width:80,padding:"3px 8px",fontSize:13,borderRadius:6,border:"1px solid var(--card-border)",background:"var(--surface)"}} />
                <button className="primaryBtn" onClick={handleSave} style={{padding:"3px 10px",fontSize:12}}>✓</button>
                <button className="secondaryBtn" onClick={() => { setEditing(false); setOwnerName(activeVersion?.owner_name || ""); }} style={{padding:"3px 10px",fontSize:12}}>✕</button>
              </span>
            )}
          </div>
        </div>
        <div style={{display:"flex",alignItems:"flex-start",gap:6,marginTop:10,paddingTop:10,borderTop:"1px dashed var(--card-border)"}}>
          <span style={{color:"var(--text3)",fontSize:12,fontWeight:600,marginTop:2,minWidth:32}}>机型</span>
          {deviceLoading ? (
            <span style={{fontSize:12,color:"var(--text3)"}}>读取中...</span>
          ) : deviceInfo?.categories && Object.keys(deviceInfo.categories).length > 0 ? (
            <span style={{fontSize:13,lineHeight:1.8,color:"var(--text2)",display:"flex",flexDirection:"column",gap:2}}>
              {["存量SR适配", "首发", "衍生"].map((cat: string) => {
                const devices = deviceInfo.categories[cat];
                if (!devices || devices.length === 0) return null;
                const seen = new Set<string>();
                const unique = devices.filter((d: string) => { if (seen.has(d)) return false; seen.add(d); return true; });
                return <span key={cat} style={{display:"block"}}><span style={{color:"var(--text3)",fontSize:12,fontWeight:600}}>{cat}：</span>{unique.join("、")}</span>;
              })}
            </span>
          ) : deviceInfo?.text ? (
            <span style={{fontSize:13,lineHeight:1.7,color:"var(--text2)"}}>{deviceInfo.text}</span>
          ) : deviceInfo?.message && deviceInfo.message !== "ok" ? (
            <span style={{fontSize:12,color:"var(--text3)"}}>
              {deviceInfo.message === "未配置管理书地址" ? "请先配置管理书地址 →" : deviceInfo.message}
              <button className="smallBtn" onClick={loadDeviceInfo} style={{padding:"2px 8px",fontSize:11,marginLeft:4}}>刷新</button>
            </span>
          ) : (
            <span style={{fontSize:12,color:"var(--text3)"}}>
              {(activeVersion?.device_list || "未配置").split(",").map((d: string) => d.trim()).filter(Boolean).map((d: string) => <span className="badge badgeInfo" key={d} style={{padding:"1px 6px",fontSize:11,marginRight:4}}>{d}</span>)}
            </span>
          )}
          <button className="smallBtn" onClick={loadDeviceInfo} disabled={deviceLoading || !activeVersion?.feishu_sheet_url} style={{padding:"2px 6px",fontSize:11,marginLeft:4,marginTop:2}} title="从管理书刷新机型">🔄</button>
        </div>
      </div>
      <div style={{display:"flex",gap:14,marginBottom:16}}>
        <div className="subCard" style={{flex:1,display:"flex",alignItems:"center",gap:10,padding:"10px 16px"}}>
          <div>
            <div className="subCardTitle" style={{marginBottom:2}}>测试项目管理书</div>
            <div className="smallMuted">tOS 测试管理文档</div>
          </div>
          {feishuUrl && !editingUrl ? (
            <a href={feishuUrl} className="textLink" style={{marginLeft:"auto",whiteSpace:"nowrap"}} target="_blank" rel="noreferrer">打开 →</a>
          ) : editingUrl ? (
            <span style={{display:"inline-flex",alignItems:"center",gap:4,marginLeft:"auto"}}>
              <input value={customUrl} onChange={e => setCustomUrl(e.target.value)} placeholder="粘贴飞书表格URL" style={{width:220,padding:"3px 8px",fontSize:12,borderRadius:6,border:"1px solid var(--card-border)",background:"var(--surface)"}} />
              <button className="primaryBtn" onClick={handleSaveUrl} style={{padding:"3px 8px",fontSize:11}}>✓</button>
              <button className="secondaryBtn" onClick={() => { setEditingUrl(false); setCustomUrl(feishuUrl); }} style={{padding:"3px 8px",fontSize:11}}>✕</button>
            </span>
          ) : (
            <button className="textLink" style={{marginLeft:"auto",whiteSpace:"nowrap",background:"none",border:"none",cursor:"pointer",color:"var(--accent)"}} onClick={() => setEditingUrl(true)}>配置 URL</button>
          )}
        </div>
        <ResourceCard title="Jira 看板" desc="Bug 追踪 · 需求管理" href={jiraUrl} />
        {(() => {
          const ganttUrl = getGanttUrl(activeVersion?.version_name);
          return ganttUrl ? <ResourceCard title="📊 版本计划甘特图" desc={`${activeVersion?.version_name || ""} 开发计划`} href={ganttUrl} /> : null;
        })()}
        <ResourceCard title="🗺️ 沟通地图" desc={contactMapUrl ? "测试接口人 · 点击打开" : contactMapLoading ? "加载中..." : "未配置管理书"} href={contactMapUrl} />
      </div>
    </div>
  );
}