import React, { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = "";

interface ToolCall { tool: string; args: Record<string, any>; result_summary: string; }
interface ChatMessage { role: "user" | "assistant"; content: string; }
interface Conversation { id: string; title: string; updated_at: string; }
interface AgentChatProps { activeVersionId: number | null; activeStage: string; }

const TOOL_LABELS: Record<string, string> = {
  // 数据刷新
  refresh_jira_data: "刷新 Jira 数据", refresh_sr_data: "刷新 SR 数据",
  refresh_utp_data: "刷新 UTP 数据", refresh_all_data: "刷新全部数据",
  // 数据导出
  export_issues_to_excel: "导出问题列表", export_sr_list_to_excel: "导出 SR 列表",
  export_weekly_report: "导出周报",
  // 查询工具
  query_jira_issues: "查询 Jira 问题", get_analysis_metrics: "获取风险分析",
  get_sr_locked_summary: "查询 SR 统计", get_sr_details: "查询 SR 详情",
  get_utp_weekly_report: "查询 UTP 报告", get_trend_data: "查询趋势",
  get_custom_risks: "查询风险项", add_custom_risk: "添加风险项",
  get_stability_data: "查询稳定性", get_jira_issue_detail: "查询问题详情",
  get_test_activities: "查询测试活动", get_work_hours: "查询工时数据",
  get_sr_test_progress: "查询 SR 测试进度", get_utp_plan_progress: "查询测试计划进度",
  get_locked_sr_list: "查询加锁 SR", get_jira_trend_comparison: "查询趋势对比",
  // 新增工具
  get_performance_data: "查询性能数据", get_battery_data: "查询续航数据",
  get_value_points: "查询价值点", get_stage_schedule: "查询阶段时间表",
  delete_custom_risk: "删除风险项", update_test_activity: "更新测试活动",
  get_version_info: "查询版本信息", get_daily_report: "查询每日报告",
};

const DRAG_THRESHOLD = 5; // px

function useDraggable(initX: number, initY: number) {
  const [pos, setPos] = useState({ x: initX, y: initY });
  const state = useRef({ dragging: false, moved: false, sx: 0, sy: 0, ox: 0, oy: 0 });

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const s = state.current;
    s.dragging = true; s.moved = false;
    s.sx = e.clientX; s.sy = e.clientY;
    s.ox = pos.x; s.oy = pos.y;
    const onMove = (ev: MouseEvent) => {
      if (!state.current.dragging) return;
      const dx = ev.clientX - state.current.sx;
      const dy = ev.clientY - state.current.sy;
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) state.current.moved = true;
      setPos({ x: state.current.ox + dx, y: state.current.oy + dy });
    };
    const onUp = () => { state.current.dragging = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [pos.x, pos.y]);

  const didDrag = useCallback(() => state.current.moved, []);

  return { pos, onMouseDown, didDrag, setPos };
}

/** SVG bot icon */
function BotIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
      <rect x="6" y="14" width="36" height="26" rx="8" fill="white" fillOpacity="0.9"/>
      <rect x="6" y="14" width="36" height="26" rx="8" stroke="white" strokeWidth="2"/>
      <circle cx="18" cy="27" r="3" fill="#f97316"/>
      <circle cx="30" cy="27" r="3" fill="#f97316"/>
      <path d="M20 33 C22 36 26 36 28 33" stroke="#f97316" strokeWidth="2" strokeLinecap="round"/>
      <rect x="19" y="6" width="10" height="8" rx="2" fill="white" fillOpacity="0.9"/>
      <circle cx="24" cy="8" r="2" fill="#f97316"/>
      <line x1="14" y1="20" x2="6" y2="16" stroke="white" strokeWidth="2" strokeLinecap="round"/>
      <line x1="34" y1="20" x2="42" y2="16" stroke="white" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

// 渲染消息内容，处理链接
function renderMessageContent(content: string) {
  if (!content) return null;
  // 匹配 Markdown 链接格式 [text](url) 或纯 URL
  const urlRegex = /(\[([^\]]+)\]\(([^)]+)\))|(https?:\/\/[^\s<>"]+)/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;

  while ((match = urlRegex.exec(content)) !== null) {
    // 添加匹配前的文本
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // Markdown 链接 [text](url)
      parts.push(
        <a key={match.index} href={match[3]} target="_blank" rel="noopener noreferrer"
          style={{ color: "#f97316", textDecoration: "underline", fontWeight: 500 }}>
          {match[2]}
        </a>
      );
    } else if (match[4]) {
      // 纯 URL
      parts.push(
        <a key={match.index} href={match[4]} target="_blank" rel="noopener noreferrer"
          style={{ color: "#f97316", textDecoration: "underline", wordBreak: "break-all" }}>
          {match[4]}
        </a>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // 添加剩余文本
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return parts.length > 0 ? parts : content;
}

export function AgentChat({ activeVersionId, activeStage }: AgentChatProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [lastToolCalls, setLastToolCalls] = useState<ToolCall[]>([]);
  const [generatingWeekly, setGeneratingWeekly] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const W = typeof window !== "undefined" ? window.innerWidth : 1200;
  const H = typeof window !== "undefined" ? window.innerHeight : 800;
  const btnDrag = useDraggable(W - 80, H - 90);
  const panelDrag = useDraggable(W - 450, H - 580);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, 100);
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, loading, scrollToBottom]);
  useEffect(() => { if (open && activeVersionId) loadConversations(); }, [open, activeVersionId]);

  async function loadConversations() {
    if (!activeVersionId) return;
    try { const r = await fetch(`${API_BASE}/api/agent/conversations?version_id=${activeVersionId}`); setConversations((await r.json()).conversations || []); } catch {}
  }
  async function loadConversation(id: string) {
    try { const r = await fetch(`${API_BASE}/api/agent/conversations/${id}`); const d = await r.json(); setMessages(d.messages || []); setConvId(id); setShowHistory(false); } catch {}
  }
  async function deleteConversation(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await fetch(`${API_BASE}/api/agent/conversations/${id}`, { method: "DELETE" });
    if (convId === id) { setConvId(null); setMessages([]); }
    loadConversations();
  }
  function startNewChat() { setConvId(null); setMessages([]); setLastToolCalls([]); setShowHistory(false); inputRef.current?.focus(); }

  async function generateWeeklyReport() {
    if (!activeVersionId || generatingWeekly) return;
    setGeneratingWeekly(true);
    try {
      const r = await fetch(`${API_BASE}/api/agent/weekly-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: activeVersionId, stage: activeStage || "ALL" })
      });
      const d = await r.json();
      if (d.report) {
        // 添加到消息列表
        setMessages(p => [...p, { role: "user", content: "生成本周周报" }, { role: "assistant", content: d.report }]);
        if (d.conversation_id && !convId) setConvId(d.conversation_id);
        // 触发下载
        const blob = new Blob([d.report], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = d.filename || `周报_${new Date().toISOString().slice(0, 10)}.md`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      setMessages(p => [...p, { role: "assistant", content: `周报生成失败：${e.message}` }]);
    } finally {
      setGeneratingWeekly(false);
      loadConversations();
    }
  }

  async function sendMessage() {
    const msg = input.trim();
    if (!msg || !activeVersionId || loading) return;
    setInput("");
    setMessages(p => [...p, { role: "user", content: msg }]);
    setLoading(true); setLastToolCalls([]);
    try {
      const r = await fetch(`${API_BASE}/api/agent/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg, version_id: activeVersionId, stage: activeStage || "ALL", conversation_id: convId }) });
      const d = await r.json();
      if (!r.ok) { setMessages(p => [...p, { role: "assistant", content: `错误：${d.detail || "请求失败"}` }]); }
      else {
        // 检查工具调用结果中是否有下载链接
        let downloadUrl = null;
        if (d.tool_calls?.length) {
          setLastToolCalls(d.tool_calls);
          for (const tc of d.tool_calls) {
            if (tc.result?.download_url) {
              downloadUrl = tc.result.download_url;
              break;
            }
          }
        }
        setMessages(p => [...p, { role: "assistant", content: d.reply || "", download_url: downloadUrl }]);
        if (d.conversation_id && !convId) setConvId(d.conversation_id);

        // 自动触发下载
        if (downloadUrl) {
          setTimeout(() => {
            const a = document.createElement("a");
            a.href = API_BASE + downloadUrl;
            a.download = "";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }, 500);
        }
      }
    } catch (e: any) { setMessages(p => [...p, { role: "assistant", content: `请求失败：${e.message}` }]); }
    finally { setLoading(false); loadConversations(); }
  }

  if (!activeVersionId) return null;

  const grad = "linear-gradient(135deg, #f97316 0%, #eab308 100%)";

  return (
    <>
      {/* Floating button */}
      {!open && (
        <div
          onMouseDown={btnDrag.onMouseDown}
          onClick={() => { if (!btnDrag.didDrag()) setOpen(true); }}
          style={{
            position: "fixed", left: btnDrag.pos.x, top: btnDrag.pos.y, zIndex: 998,
            width: 54, height: 54, borderRadius: "50%",
            background: grad, boxShadow: "0 4px 20px rgba(249,115,22,0.35)",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "grab", userSelect: "none",
            transition: "transform .15s, box-shadow .15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = "scale(1.12)"; e.currentTarget.style.boxShadow = "0 6px 28px rgba(249,115,22,0.5)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "0 4px 20px rgba(249,115,22,0.35)"; }}
          title="AI 智能助手（可拖动）"
        >
          <BotIcon size={30} />
        </div>
      )}

      {/* Chat panel */}
      {open && (
        <div style={{
          position: "fixed", left: Math.max(0, Math.min(panelDrag.pos.x, W - 420)), top: Math.max(0, Math.min(panelDrag.pos.y, H - 200)),
          zIndex: 1000, width: 420, maxHeight: "80vh", display: "flex", flexDirection: "column",
          background: "var(--card, #fff)", borderRadius: 16,
          boxShadow: "0 8px 40px rgba(0,0,0,0.18), 0 0 0 1px var(--card-border, #e5e7eb)", overflow: "hidden",
        }}>
          {/* Header */}
          <div onMouseDown={panelDrag.onMouseDown} style={{
            padding: "12px 16px", display: "flex", alignItems: "center", gap: 10,
            background: grad, color: "#fff", cursor: "grab", userSelect: "none",
          }}>
            <BotIcon size={28} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>tOS 智能助手</div>
              <div style={{ fontSize: 10, opacity: 0.8 }}>{convId ? "对话中" : "新对话"} · 拖动移动</div>
            </div>
            <button onClick={() => setShowHistory(!showHistory)} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>📋</button>
            <button onClick={generateWeeklyReport} disabled={generatingWeekly} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: generatingWeekly ? "wait" : "pointer", fontSize: 12 }} title="生成周报">{generatingWeekly ? "⏳" : "📊"}</button>
            <button onClick={startNewChat} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>✚</button>
            <button onClick={() => setOpen(false)} style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 14 }}>✕</button>
          </div>

          {/* History */}
          {showHistory && (
            <div style={{ maxHeight: 240, overflowY: "auto", borderBottom: "1px solid var(--card-border)", background: "var(--bg2)" }}>
              {conversations.length === 0 && <p style={{ padding: 16, textAlign: "center", color: "var(--text3)", fontSize: 12 }}>暂无历史对话</p>}
              {conversations.map(c => (
                <div key={c.id} onClick={() => loadConversation(c.id)} style={{ padding: "8px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid var(--card-border, #f3f4f6)", fontSize: 12 }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(249,115,22,0.05)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title || "未命名"}</span>
                  <span style={{ color: "var(--text3)", fontSize: 10, whiteSpace: "nowrap" }}>{(c.updated_at || "").slice(5, 16).replace("T", " ")}</span>
                  <button onClick={(e) => deleteConversation(c.id, e)} style={{ background: "none", border: "none", color: "var(--text3)", cursor: "pointer", fontSize: 12, padding: "0 4px" }}>🗑</button>
                </div>
              ))}
            </div>
          )}

          {/* Messages */}
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10, minHeight: 280, maxHeight: 400 }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "var(--text3)", padding: "40px 20px", fontSize: 13 }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}><BotIcon size={40} /></div>
                <div>试试问我：</div>
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  {/* 数据查询 */}
                  <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 600, marginTop: 4 }}>📊 数据查询</div>
                  {["当前有哪些 Blocker 没关闭？", "SR 需求交付进度如何？", "对比上周问题变化趋势", "测试计划进度怎么样？", "价值点验收情况如何？"].map(q => (
                    <button key={q} onClick={() => setInput(q)} style={{ background: "rgba(249,115,22,0.06)", border: "1px solid var(--card-border, #e5e7eb)", borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontSize: 12, color: "#f97316", textAlign: "left" }}>{q}</button>
                  ))}
                  {/* 数据刷新 */}
                  <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 600, marginTop: 8 }}>🔄 数据刷新</div>
                  {["刷新全部数据", "刷新 Jira 数据", "刷新 SR 数据"].map(q => (
                    <button key={q} onClick={() => setInput(q)} style={{ background: "rgba(16,185,129,0.06)", border: "1px solid #d1fae5", borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontSize: 12, color: "#059669", textAlign: "left" }}>{q}</button>
                  ))}
                  {/* 数据导出 */}
                  <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 600, marginTop: 8 }}>📥 数据导出</div>
                  <button onClick={generateWeeklyReport} disabled={generatingWeekly} style={{ background: "rgba(37,99,235,0.06)", border: "1px solid #dbeafe", borderRadius: 8, padding: "6px 12px", cursor: generatingWeekly ? "wait" : "pointer", fontSize: 12, color: "#2563eb", textAlign: "left", fontWeight: 600 }}>
                    {generatingWeekly ? "⏳ 生成中..." : "📊 生成本周周报（含下载）"}
                  </button>
                  {["导出遗留问题到 Excel", "导出 SR 列表到 Excel"].map(q => (
                    <button key={q} onClick={() => setInput(q)} style={{ background: "rgba(37,99,235,0.06)", border: "1px solid #dbeafe", borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontSize: 12, color: "#2563eb", textAlign: "left" }}>{q}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{
                  maxWidth: "85%", padding: "10px 14px", borderRadius: 12, fontSize: 13, lineHeight: 1.7, whiteSpace: "pre-wrap",
                  background: m.role === "user" ? "#f97316" : "var(--bg2, #f3f4f6)",
                  color: m.role === "user" ? "#fff" : "var(--text)",
                  borderBottomRightRadius: m.role === "user" ? 4 : 12,
                  borderBottomLeftRadius: m.role === "assistant" ? 4 : 12,
                }}>
                  {renderMessageContent(m.content)}
                  {/* 检测下载链接并显示下载按钮 */}
                  {m.role === "assistant" && m.download_url && (
                    <div style={{ marginTop: 8 }}>
                      <a href={API_BASE + m.download_url} download
                        style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "6px 14px", background: "#f97316", color: "#fff", borderRadius: 8, fontSize: 12, textDecoration: "none", fontWeight: 600, cursor: "pointer" }}
                        onMouseEnter={e => { e.currentTarget.style.background = "#ea580c"; }}
                        onMouseLeave={e => { e.currentTarget.style.background = "#f97316"; }}>
                        📥 下载文件
                      </a>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <div style={{ padding: "10px 14px", borderRadius: 12, fontSize: 13, background: "var(--bg2)", color: "var(--text3)", borderBottomLeftRadius: 4 }}>
                  {lastToolCalls.length > 0 ? "⚙ 正在分析..." : "🤔 思考中..."}
                </div>
              </div>
            )}
          </div>

          {/* Tool calls */}
          {lastToolCalls.length > 0 && !loading && (
            <div style={{ padding: "6px 14px", borderTop: "1px solid var(--card-border, #f3f4f6)", display: "flex", gap: 6, flexWrap: "wrap" }}>
              {lastToolCalls.map((tc, i) => (
                <span key={i} style={{ fontSize: 10, color: "var(--text3)", background: "rgba(249,115,22,0.06)", padding: "2px 8px", borderRadius: 4 }} title={`${tc.tool} -> ${tc.result_summary}`}>
                  ⚙ {TOOL_LABELS[tc.tool] || tc.tool}
                </span>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{ padding: "10px 14px", borderTop: "1px solid var(--card-border, #e5e7eb)", display: "flex", gap: 8, alignItems: "flex-end" }}>
            <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder="输入问题... (Enter 发送)" rows={1}
              style={{ flex: 1, padding: "8px 12px", borderRadius: 10, border: "1px solid var(--card-border)", background: "var(--surface)", color: "var(--text)", fontSize: 13, resize: "none", outline: "none", lineHeight: 1.5, maxHeight: 80 }} />
            <button onClick={sendMessage} disabled={!input.trim() || loading}
              style={{ width: 38, height: 38, borderRadius: 10, border: "none", cursor: loading ? "wait" : "pointer", background: input.trim() ? "#f97316" : "var(--bg2)", color: input.trim() ? "#fff" : "var(--text3)", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>➤</button>
          </div>
        </div>
      )}
    </>
  );
}

export default AgentChat;