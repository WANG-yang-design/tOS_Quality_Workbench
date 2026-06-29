import React, { useState, useEffect, useRef } from "react";
import { API_BASE, JIRA_BROWSE } from "../constants";
import type { StabilityDevice } from "../types";
import { EMPTY_DEVICE } from "../types";

// 飞书智能体对话模块组件（内嵌式）
function FeishuAgentChat({ activeVersion }: { activeVersion: any }) {
  const [messages, setMessages] = useState<{role: "user"|"assistant"; content: string; time?: string}[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const historyScrollRef = useRef<HTMLDivElement>(null);
  const versionIdRef = useRef<number | null>(null);

  async function loadHistory() {
    if (!activeVersion?.id) return;
    try {
      const res = await fetch(API_BASE + `/api/feishu-agent/history?version_id=${activeVersion.id}&limit=50`);
      const data = await res.json();
      setHistory(data.history || []);
    } catch {}
  }

  async function deleteHistoryItem(id: number) {
    try {
      await fetch(API_BASE + `/api/feishu-agent/history/${id}`, { method: "DELETE" });
      loadHistory();
    } catch {}
  }

  async function clearHistory() {
    if (!activeVersion?.id) return;
    if (!confirm("确定清空当前版本的所有历史对话？")) return;
    try {
      await fetch(API_BASE + `/api/feishu-agent/history?version_id=${activeVersion.id}`, { method: "DELETE" });
      setHistory([]);
    } catch {}
  }

  function startNewChat() {
    setMessages([]);
  }

  // 阻止滚动穿透
  function handleScroll(e: React.UIEvent) {
    const target = e.currentTarget;
    const { scrollTop, scrollHeight, clientHeight } = target;
    const isAtTop = scrollTop === 0;
    const isAtBottom = scrollTop + clientHeight >= scrollHeight - 1;

    // 只有在滚动到顶部或底部时才允许页面滚动
    if ((isAtTop && e.nativeEvent.deltaY < 0) || (isAtBottom && e.nativeEvent.deltaY > 0)) {
      return; // 允许默认行为（页面滚动）
    }
    e.stopPropagation(); // 阻止事件冒泡
  }

  async function sendMessage() {
    const q = input.trim();
    if (!q || loading) return;
    if (!activeVersion?.id) {
      setMessages(prev => [...prev, { role: "assistant", content: "请先选择一个版本", time: new Date().toLocaleTimeString() }]);
      return;
    }
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: q, time: new Date().toLocaleTimeString() }]);
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/feishu-agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, version_id: activeVersion.id })
      });
      const data = await res.json();
      if (data.success) {
        setMessages(prev => [...prev, { role: "assistant", content: data.answer, time: new Date().toLocaleTimeString() }]);
      } else {
        setMessages(prev => [...prev, { role: "assistant", content: `错误: ${data.error || data.detail || "请求失败"}`, time: new Date().toLocaleTimeString() }]);
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { role: "assistant", content: `请求失败: ${e.message}`, time: new Date().toLocaleTimeString() }]);
    } finally {
      setLoading(false);
      loadHistory();
    }
  }

  // 切换版本时清空当前对话并重新加载历史
  useEffect(() => {
    if (activeVersion?.id !== versionIdRef.current) {
      versionIdRef.current = activeVersion?.id || null;
      setMessages([]);
      setShowHistory(false);
      loadHistory();
    }
  }, [activeVersion?.id]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const quickQuestions = [
    "查询当前版本的稳定性数据",
    "分析 Crash 问题趋势",
    "生成稳定性测试报告",
    "对比上个版本的 APR 数据",
    "查询各机型的系统APR",
  ];

  return (
    <div style={{marginTop: 16, border: "1px solid var(--card-border)", borderRadius: 12, overflow: "hidden", background: "var(--surface)"}}>
      {/* 模块标题 */}
      <div style={{
        padding: "12px 16px", display: "flex", alignItems: "center", gap: 10,
        background: "linear-gradient(135deg, #4f46e5, #7c3aed)", color: "#fff",
      }}>
        <span style={{ fontSize: 20 }}>🤖</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>稳定性测试专家</div>
          <div style={{ fontSize: 10, opacity: 0.8 }}>
            {activeVersion?.version_name || "未选择版本"} · {messages.length > 0 ? `${messages.length} 条对话中` : `${history.length} 条历史`}
          </div>
        </div>
        <button onClick={startNewChat} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 12 }} title="新建对话">
          ✚ 新建
        </button>
        <button onClick={() => setShowHistory(!showHistory)} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>
          {showHistory ? "隐藏历史" : "📋 历史"}
        </button>
      </div>

      {/* 快捷问题 */}
      {messages.length === 0 && !showHistory && (
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--card-border)" }}>
          <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 8 }}>💡 快捷问题：</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {quickQuestions.map(q => (
              <button key={q} onClick={() => { setInput(q); }}
                style={{ padding: "6px 12px", fontSize: 12, background: "rgba(79,70,229,0.06)", border: "1px solid #e0e7ff", borderRadius: 8, cursor: "pointer", color: "#4f46e5", transition: "all .15s" }}
                onMouseEnter={e => { e.currentTarget.style.background = "rgba(79,70,229,0.12)"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "rgba(79,70,229,0.06)"; }}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 历史记录 */}
      {showHistory && (
        <div style={{ maxHeight: 300, overflowY: "auto", borderBottom: "1px solid var(--card-border)" }}
          onWheel={handleScroll}>
          <div style={{ padding: "8px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--card-border)", position: "sticky", top: 0, background: "var(--surface)", zIndex: 1 }}>
            <span style={{ fontSize: 11, color: "var(--text3)" }}>最近 2 周的历史对话</span>
            {history.length > 0 && (
              <button onClick={clearHistory} style={{ fontSize: 11, color: "var(--danger)", background: "none", border: "none", cursor: "pointer" }}>🗑 清空</button>
            )}
          </div>
          {history.length === 0 ? (
            <p style={{ padding: 20, textAlign: "center", color: "var(--text3)", fontSize: 13 }}>暂无历史对话</p>
          ) : (
            history.map((h) => (
              <div key={h.id} style={{ padding: "10px 16px", borderBottom: "1px dashed var(--card-border)", display: "flex", alignItems: "flex-start", gap: 8 }}
                onMouseEnter={e => { e.currentTarget.style.background = "var(--accent-soft)"; }}
                onMouseLeave={e => { e.currentTarget.style.background = ""; }}>
                <div style={{ flex: 1, cursor: "pointer" }}
                  onClick={() => { setMessages([{ role: "user", content: h.question, time: h.created_at?.slice(11, 16) }, { role: "assistant", content: h.answer, time: h.created_at?.slice(11, 16) }]); setShowHistory(false); }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>{h.question.slice(0, 80)}{h.question.length > 80 ? "..." : ""}</div>
                  <div style={{ fontSize: 11, color: "var(--text3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.answer.slice(0, 100)}...</div>
                  <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 4 }}>{h.created_at?.replace("T", " ").slice(0, 16)}</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); deleteHistoryItem(h.id); }}
                  style={{ background: "none", border: "none", color: "var(--text3)", cursor: "pointer", padding: "4px", fontSize: 14, marginTop: 2 }}
                  title="删除此条">🗑</button>
              </div>
            ))
          )}
        </div>
      )}

      {/* 消息列表 */}
      <div ref={scrollRef} onWheel={handleScroll} style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10, minHeight: 200, maxHeight: 400, overflowY: "auto" }}>
        {messages.length === 0 && !showHistory && (
          <div style={{ textAlign: "center", color: "var(--text3)", padding: "30px 0", fontSize: 13 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🤖</div>
            <div>向稳定性测试专家提问，获取专业的稳定性分析</div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{
              maxWidth: "85%", padding: "10px 14px", borderRadius: 12, fontSize: 13, lineHeight: 1.7, whiteSpace: "pre-wrap",
              background: m.role === "user" ? "#4f46e5" : "var(--bg2, #f3f4f6)",
              color: m.role === "user" ? "#fff" : "var(--text)",
              borderBottomRightRadius: m.role === "user" ? 4 : 12,
              borderBottomLeftRadius: m.role === "assistant" ? 4 : 12,
            }}>
              {m.content}
              {m.time && <div style={{ fontSize: 10, opacity: 0.6, marginTop: 4, textAlign: "right" }}>{m.time}</div>}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div style={{ padding: "10px 14px", borderRadius: 12, fontSize: 13, background: "var(--bg2)", color: "var(--text3)", borderBottomLeftRadius: 4 }}>
              🤔 稳定性测试专家思考中...
            </div>
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div style={{ padding: "10px 16px", borderTop: "1px solid var(--card-border)", display: "flex", gap: 8, alignItems: "flex-end" }}>
        <textarea value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="向稳定性测试专家提问..." rows={1}
          style={{ flex: 1, padding: "8px 12px", borderRadius: 10, border: "1px solid var(--card-border)", background: "var(--surface)", color: "var(--text)", fontSize: 13, resize: "none", outline: "none", lineHeight: 1.5, maxHeight: 80 }} />
        <button onClick={sendMessage} disabled={!input.trim() || loading}
          style={{ width: 38, height: 38, borderRadius: 10, border: "none", cursor: loading ? "wait" : "pointer", background: input.trim() ? "#4f46e5" : "var(--bg2)", color: input.trim() ? "#fff" : "var(--text3)", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>➤</button>
      </div>
    </div>
  );
}

// 从 App.tsx 第853行原样提取 - 稳定性专项
export function StabilitySpecialSection({ activeVersion }: any) {
  const [devices, setDevices] = useState<StabilityDevice[]>([]);
  const [activeDevice, setActiveDevice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [editData, setEditData] = useState<StabilityDevice>({ ...EMPTY_DEVICE });

  async function loadStability() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/stability");
      const data = await res.json();
      const list: StabilityDevice[] = data.devices || [];
      setDevices(list);
      if (list.length > 0 && !list.find(d => d.device_name === activeDevice)) {
        setActiveDevice(list[0].device_name);
        setEditData(list[0]);
      } else if (list.length > 0) {
        const found = list.find(d => d.device_name === activeDevice);
        if (found) setEditData(found);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function initDevices() {
    if (!activeVersion?.id) return;
    setSyncing(true);
    try {
      let deviceNames: string[] = [];
      let infoError = "";
      try {
        const infoRes = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/device-info");
        const infoData = await infoRes.json();
        if (infoData.error) { infoError = infoData.error; }
        else {
          const cats = infoData.categories || {};
          for (const cat of ["存量SR适配", "首发", "衍生"]) {
            for (const d of (cats[cat] || [])) {
              const name = (d || "").trim();
              if (name && !deviceNames.includes(name)) deviceNames.push(name);
            }
          }
        }
      } catch { infoError = "请求失败"; }

      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/stability/init", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(deviceNames),
      });
      const data = await res.json();
      await loadStability();
      if (data.added > 0) { alert(`✅ 新增 ${data.added} 个机型`); }
      else if (deviceNames.length > 0) { alert(`ℹ️ 基础信息中有 ${deviceNames.length} 个机型，均已存在`); }
      else { alert(`⚠️ 未从基础信息中获取到机型${infoError ? "（" + infoError + "）" : ""}`); }
    } finally { setSyncing(false); }
  }

  async function saveDevice() {
    if (!activeVersion?.id || !editData.device_name) return;
    setSaving(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/stability", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editData),
      });
      if (res.ok) await loadStability();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  }

  async function deleteDevice(name: string) {
    if (!activeVersion?.id || !confirm(`确认删除机型「${name}」的稳定性数据？`)) return;
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/stability/" + encodeURIComponent(name), { method: "DELETE" });
      if (!res.ok) { alert(`删除失败 (HTTP ${res.status})`); return; }
    } catch { alert("删除请求失败"); return; }
    if (activeDevice === name) { setActiveDevice(""); setEditData({ ...EMPTY_DEVICE }); }
    await loadStability();
  }

  function addDevice() {
    const name = prompt("请输入机型名称（如 X6879）：");
    if (!name || !name.trim()) return;
    if (devices.find(d => d.device_name === name.trim())) { alert("该机型已存在"); return; }
    setEditData({ ...EMPTY_DEVICE, device_name: name.trim() });
    setActiveDevice(name.trim());
  }

  function switchDevice(name: string) {
    setActiveDevice(name);
    const found = devices.find(d => d.device_name === name);
    setEditData(found ? { ...found } : { ...EMPTY_DEVICE, device_name: name });
  }

  function updateField(field: keyof StabilityDevice, value: string) {
    setEditData(prev => ({ ...prev, [field]: value }));
  }

  useEffect(() => { if (!activeVersion?.id) return; loadStability(); }, [activeVersion?.id]);

  const currentDevice = devices.find(d => d.device_name === activeDevice);
  const APR_ITEMS = [
    { key: "sys", label: "系统APR", color: "#3b82f6" },
    { key: "app", label: "应用APR", color: "#10b981" },
    { key: "subsys", label: "子系统APR", color: "#f59e0b" },
    { key: "third", label: "三方APR", color: "#8b5cf6" },
  ];
  const inputStyle: React.CSSProperties = { width: "100%", padding: "5px 8px", fontSize: 12, borderRadius: 6, border: "1px solid var(--card-border)", background: "var(--surface)", color: "var(--text)" };

  return (
    <div className="card">
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <div style={{fontSize:13,color:"var(--text2)"}}>手动填写各机型的稳定性 APR 数据，数据保存在本地数据库。</div>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <button className="smallBtn" onClick={initDevices} disabled={syncing} style={{padding:"3px 10px",fontSize:11}} title="从基础信息读取机型列表同步到稳定性数据">{syncing ? "同步中..." : "📥 同步机型"}</button>
          <button className="smallBtn" onClick={addDevice} style={{padding:"3px 10px",fontSize:11}}>＋ 添加机型</button>
          <button className="smallBtn" onClick={loadStability} disabled={loading} style={{padding:"2px 8px",fontSize:11}}>🔄</button>
        </div>
      </div>

      {loading ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>正在加载...</p>
      ) : devices.length === 0 ? (
        <div style={{textAlign:"center",padding:24}}>
          <p style={{color:"var(--text3)",marginBottom:12}}>暂无机型数据</p>
          <button className="primaryBtn" onClick={initDevices} disabled={syncing} style={{fontSize:13}}>{syncing ? "同步中..." : "📥 从基础信息同步机型"}</button>
        </div>
      ) : (
        <>
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:14}}>
            {devices.map(d => (
              <button key={d.device_name} onClick={() => switchDevice(d.device_name)}
                style={{padding:"6px 16px",fontSize:13,fontWeight:activeDevice===d.device_name?600:400,background:activeDevice===d.device_name?"var(--accent)":"var(--surface)",color:activeDevice===d.device_name?"#fff":"var(--text2)",border:activeDevice===d.device_name?"1px solid var(--accent)":"1px solid var(--card-border)",borderRadius:8,cursor:"pointer",transition:"all .2s",whiteSpace:"nowrap",position:"relative"}}>
                📱 {d.device_name}
                {d.rom_version && <span style={{fontSize:10,marginLeft:4,opacity:0.7}}>{d.rom_version}</span>}
              </button>
            ))}
          </div>

          {activeDevice && (
            <div className="subCard" style={{padding:"14px 18px"}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
                <div style={{display:"flex",alignItems:"center",gap:8}}>
                  <span style={{fontSize:15,fontWeight:600,color:"var(--text)"}}>📱 {activeDevice}</span>
                  <button className="smallBtn" onClick={() => deleteDevice(activeDevice)} style={{padding:"2px 8px",fontSize:10,color:"var(--danger)",border:"1px solid #fecaca"}}>删除机型</button>
                </div>
                <button className="primaryBtn" onClick={saveDevice} disabled={saving} style={{padding:"5px 16px",fontSize:12}}>
                  {saving ? "保存中..." : "💾 保存"}
                </button>
              </div>
              <div style={{marginBottom:14}}>
                <label style={{fontSize:12,fontWeight:600,color:"var(--text2)",marginBottom:4,display:"block"}}>ROM 版本号</label>
                <input style={{...inputStyle, maxWidth:300}} value={editData.rom_version} onChange={e => updateField("rom_version", e.target.value)} placeholder="如 V1.0.0.0" />
              </div>
              <table className="dataTable" style={{margin:0,fontSize:12}}>
                <thead><tr><th style={{width:100}}>APR 类型</th><th>APR 值</th><th>阈值</th><th>时长</th></tr></thead>
                <tbody>
                  {APR_ITEMS.map(item => (
                    <tr key={item.key}>
                      <td style={{fontWeight:600}}><span style={{display:"inline-block",width:8,height:8,borderRadius:"50%",background:item.color,marginRight:6}} />{item.label}</td>
                      <td><input style={inputStyle} value={editData[`${item.key}_apr_value` as keyof StabilityDevice] as string} onChange={e => updateField(`${item.key}_apr_value` as keyof StabilityDevice, e.target.value)} placeholder="输入值" /></td>
                      <td><input style={inputStyle} value={editData[`${item.key}_apr_threshold` as keyof StabilityDevice] as string} onChange={e => updateField(`${item.key}_apr_threshold` as keyof StabilityDevice, e.target.value)} placeholder="输入阈值" /></td>
                      <td><input style={inputStyle} value={editData[`${item.key}_apr_duration` as keyof StabilityDevice] as string} onChange={e => updateField(`${item.key}_apr_duration` as keyof StabilityDevice, e.target.value)} placeholder="输入时长" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{marginTop:14}}>
                <label style={{fontSize:12,fontWeight:600,color:"var(--text2)",marginBottom:4,display:"block"}}>关联 Jira 单</label>
                <input style={inputStyle} value={editData.jira_keys} onChange={e => updateField("jira_keys", e.target.value)} placeholder="如 TOS-1234, TOS-5678（逗号分隔）" />
                {editData.jira_keys && (
                  <div style={{marginTop:4,fontSize:11,color:"var(--text3)"}}>
                    {editData.jira_keys.split(",").map(k => k.trim()).filter(Boolean).map(k => (
                      <a key={k} className="issueId" href={JIRA_BROWSE + k.trim()} target="_blank" rel="noreferrer" style={{marginRight:8}}>{k.trim()}</a>
                    ))}
                  </div>
                )}
              </div>
              <div style={{marginTop:10}}>
                <label style={{fontSize:12,fontWeight:600,color:"var(--text2)",marginBottom:4,display:"block"}}>备注</label>
                <textarea style={{...inputStyle, minHeight:50, resize:"vertical", fontFamily:"inherit"}} value={editData.remark} onChange={e => updateField("remark", e.target.value)} placeholder="补充说明" />
              </div>
              {currentDevice?.updated_at && (
                <div style={{marginTop:8,fontSize:11,color:"var(--text3)"}}>上次保存：{currentDevice.updated_at.replace("T", " ").slice(0, 16)}</div>
              )}
            </div>
          )}
        </>
      )}

      {/* 稳定性测试专家智能体对话模块 */}
      <FeishuAgentChat activeVersion={activeVersion} />
    </div>
  );
}