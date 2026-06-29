import React, { useState, useEffect } from "react";
import { API_BASE, JIRA_BROWSE } from "../constants";
import { MetricCard } from "../components/common/MetricCard";
import { JiraLinkText } from "../components/common/JiraLinkText";
import type { ValuePoint } from "../types";

// 从 App.tsx 第1481行原样提取 - 价值点验收
export function ValuePointSection({ activeVersion }: any) {
  const [items, setItems] = useState<ValuePoint[]>([]);
  const [stats, setStats] = useState({ total: 0, pass_count: 0, fail_count: 0, pass_rate: 0, fail_items: [] as ValuePoint[] });
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showFailDetail, setShowFailDetail] = useState(false);

  async function loadData() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/value-points");
      const json = await res.json();
      setItems(json.items || []);
      setStats(json.stats || { total: 0, pass_count: 0, fail_count: 0, pass_rate: 0, fail_items: [] });
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, [activeVersion?.id]);

  return (
    <div className="card">
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <div style={{fontSize:13,color:"var(--text2)"}}>手动录入各价值点/价值方向的 IR 验收结论，数据保存在本地数据库。</div>
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <button className="smallBtn" onClick={() => setShowModal(true)} style={{padding:"3px 10px",fontSize:11}}>✏️ 录入价值点</button>
          <button className="smallBtn" onClick={loadData} disabled={loading} style={{padding:"2px 8px",fontSize:11}}>🔄</button>
        </div>
      </div>
      <div className="grid3" style={{marginBottom:14}}>
        <MetricCard label="价值点总数" value={stats.total} note="已录入" />
        <MetricCard label="PASS（通过）" value={stats.pass_count} note={`通过率 ${stats.pass_rate}%`} />
        <MetricCard label="FAIL（不通过）" value={stats.fail_count} note="需关注" danger={stats.fail_count > 0} />
      </div>
      {stats.fail_count > 0 && (
        <div style={{marginBottom:14,padding:"10px 14px",background:"var(--danger-bg)",borderRadius:8,border:"1px solid var(--danger)"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
            <span style={{fontSize:13,fontWeight:600,color:"var(--danger)"}}>⚠️ FAIL 风险分析（{stats.fail_count} 项）</span>
            <button className="smallBtn" onClick={() => setShowFailDetail(!showFailDetail)} style={{padding:"2px 8px",fontSize:10}}>
              {showFailDetail ? "收起" : "展开详情"}
            </button>
          </div>
          <div style={{fontSize:12,color:"var(--text2)",lineHeight:1.8}}>
            {(() => {
              const failReasons = (stats.fail_items || []).map((f: ValuePoint) => f.fail_reason).filter(Boolean);
              const jiraKeys: string[] = [];
              failReasons.forEach(r => { const matches = r.match(/\b[A-Z][A-Z0-9]+-\d+\b/g); if (matches) jiraKeys.push(...matches); });
              const owners = [...new Set((stats.fail_items || []).map((f: ValuePoint) => f.test_owner).filter(Boolean))];
              return (
                <>
                  <p style={{margin:"2px 0"}}>• 共 <strong>{stats.fail_count}</strong> 个价值点未通过 IR 验收，通过率 <strong>{stats.pass_rate}%</strong></p>
                  {jiraKeys.length > 0 && <p style={{margin:"2px 0"}}>• FAIL 原因中关联 <strong>{jiraKeys.length}</strong> 个 Jira 问题：
                    {[...new Set(jiraKeys)].map(k => <a key={k} className="issueId" href={JIRA_BROWSE + k} target="_blank" rel="noreferrer" style={{margin:"0 4px"}}>{k}</a>)}
                  </p>}
                  {owners.length > 0 && <p style={{margin:"2px 0"}}>• 涉及负责人：{owners.join("、")}</p>}
                </>
              );
            })()}
          </div>
          {showFailDetail && (
            <table className="dataTable" style={{margin:"8px 0 0",fontSize:12}}>
              <thead><tr><th>价值点/价值方向</th><th>FAIL 原因</th><th>负责人</th><th>更新时间</th></tr></thead>
              <tbody>{(stats.fail_items || []).map((item: ValuePoint) => (
                <tr key={item.id}>
                  <td style={{fontWeight:600}}>{item.value_name}</td>
                  <td style={{maxWidth:300,whiteSpace:"normal",wordBreak:"break-word",lineHeight:1.6}}>{item.fail_reason ? <JiraLinkText text={item.fail_reason} /> : <span style={{color:"var(--text3)"}}>-</span>}</td>
                  <td>{item.test_owner || "-"}</td>
                  <td style={{whiteSpace:"nowrap",fontSize:11,color:"var(--text3)"}}>{item.updated_at ? item.updated_at.replace("T", " ").slice(0, 16) : "-"}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}
      {loading ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>加载中...</p>
      ) : items.length === 0 ? (
        <div style={{textAlign:"center",padding:24}}>
          <p style={{color:"var(--text3)",marginBottom:12}}>暂无价值点数据</p>
          <button className="primaryBtn" onClick={() => setShowModal(true)} style={{fontSize:13}}>✏️ 录入价值点</button>
        </div>
      ) : (
        <div className="subCard" style={{padding:0}}>
          <table className="dataTable" style={{margin:0,fontSize:12}}>
            <thead><tr><th style={{width:40}}>#</th><th>价值点/价值方向</th><th style={{width:80}}>IR 结论</th><th>FAIL 原因 / 测试数据</th><th style={{width:80}}>负责人</th><th style={{width:90}}>更新时间</th></tr></thead>
            <tbody>{items.map((item, idx) => (
              <tr key={item.id}>
                <td style={{color:"var(--text3)",textAlign:"center"}}>{idx + 1}</td>
                <td style={{fontWeight:600,maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={item.value_name}>{item.value_name}</td>
                <td style={{textAlign:"center"}}><span className={"badge " + (item.ir_conclusion === "PASS" ? "badgeGo" : "badgeNg")}>{item.ir_conclusion}</span></td>
                <td style={{maxWidth:300,whiteSpace:"normal",wordBreak:"break-word",lineHeight:1.6,fontSize:12,color: item.fail_reason ? "var(--text2)" : "var(--text3)"}}>
                  {item.fail_reason ? <JiraLinkText text={item.fail_reason} /> : (item.ir_conclusion === "FAIL" ? <span style={{fontSize:11}}>未填写</span> : "-")}
                </td>
                <td>{item.test_owner || "-"}</td>
                <td style={{whiteSpace:"nowrap",fontSize:11,color:"var(--text3)"}}>{item.updated_at ? item.updated_at.replace("T", " ").slice(0, 16) : "-"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {showModal && <ValuePointModal versionId={activeVersion?.id} existingItems={items} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); loadData(); }} />}
    </div>
  );
}

function ValuePointModal({ versionId, existingItems, onClose, onSaved }: any) {
  const [mode, setMode] = useState<"list" | "edit">("list");
  const [form, setForm] = useState<ValuePoint>({ value_name: "", ir_conclusion: "PASS", fail_reason: "", test_owner: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  async function save() {
    if (!form.value_name.trim()) { alert("请输入价值点/价值方向"); return; }
    if (form.ir_conclusion === "FAIL" && !form.fail_reason.trim()) { alert("FAIL 时请填写测试数据/Fail 原因"); return; }
    setSaving(true);
    try {
      const payload = { ...form };
      if (payload.ir_conclusion === "PASS") { payload.fail_reason = ""; }
      const res = await fetch(API_BASE + `/api/versions/${versionId}/value-points`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (res.ok) onSaved();
      else alert("保存失败");
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  async function deleteItem(item: ValuePoint) {
    if (!confirm(`确认删除价值点「${item.value_name}」？`)) return;
    try {
      await fetch(API_BASE + `/api/versions/${versionId}/value-points/${item.id}`, { method: "DELETE" });
      onSaved();
    } catch { alert("删除失败"); }
  }

  function startEdit(item?: ValuePoint) {
    if (item) { setForm({ ...item }); }
    else { setForm({ value_name: "", ir_conclusion: "PASS", fail_reason: "", test_owner: "" }); }
    setMode("edit");
  }

  const inputStyle: React.CSSProperties = { width: "100%", padding: "6px 10px", fontSize: 13, borderRadius: 6, border: "1px solid var(--card-border)", background: "var(--surface)", color: "var(--text)" };

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal" style={{ width: 680, display: "flex", flexDirection: "column", maxHeight: "85vh" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <h2 style={{ margin: 0 }}>✏️ 价值点 IR 验收录入</h2>
          <span style={{ fontSize: 12, color: "var(--text3)" }}>{existingItems.length} 项</span>
        </div>
        <p style={{ fontSize: 12, color: "var(--text3)", margin: "0 0 14px" }}>录入价值点/价值方向的 IR 验收评审结论，FAIL 时需填写原因。</p>
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {mode === "list" ? (
            <>
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
                <button className="primaryBtn" onClick={() => startEdit()} style={{ padding: "5px 14px", fontSize: 12 }}>＋ 添加价值点</button>
              </div>
              {existingItems.length === 0 ? (
                <p style={{ color: "var(--text3)", textAlign: "center", padding: 24 }}>暂无价值点</p>
              ) : (
                <table className="dataTable" style={{ margin: 0, fontSize: 12 }}>
                  <thead><tr><th>价值点</th><th style={{ width: 70 }}>结论</th><th>FAIL 原因</th><th style={{ width: 70 }}>负责人</th><th style={{ width: 100 }}>操作</th></tr></thead>
                  <tbody>{existingItems.map((item: ValuePoint) => (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 600, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.value_name}>{item.value_name}</td>
                      <td style={{ textAlign: "center" }}><span className={"badge " + (item.ir_conclusion === "PASS" ? "badgeGo" : "badgeNg")}>{item.ir_conclusion}</span></td>
                      <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11 }} title={item.fail_reason}>{item.fail_reason || "-"}</td>
                      <td>{item.test_owner || "-"}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button className="smallBtn" onClick={() => startEdit(item)} style={{ padding: "2px 8px", fontSize: 10, marginRight: 4 }}>编辑</button>
                        <button className="smallBtn" onClick={() => deleteItem(item)} style={{ padding: "2px 8px", fontSize: 10, color: "var(--danger)", border: "1px solid #fecaca" }}>删除</button>
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </>
          ) : (
            <div className="subCard" style={{ padding: "14px 18px" }}>
              <h3 style={{ fontSize: 14, margin: "0 0 14px", color: "var(--text)" }}>{form.id ? "编辑价值点" : "添加价值点"}</h3>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>价值点 / 价值方向 *</label>
                <input style={inputStyle} value={form.value_name} onChange={e => setForm({ ...form, value_name: e.target.value })} placeholder="如：AI 通话摘要、智能省电策略" />
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 6, display: "block" }}>IR 验收/评审结论 *</label>
                <div style={{ display: "flex", gap: 10 }}>
                  <button onClick={() => setForm({ ...form, ir_conclusion: "PASS" })} style={{ padding: "8px 28px", fontSize: 14, fontWeight: form.ir_conclusion === "PASS" ? 700 : 400, background: form.ir_conclusion === "PASS" ? "var(--ok)" : "var(--surface)", color: form.ir_conclusion === "PASS" ? "#fff" : "var(--text2)", border: form.ir_conclusion === "PASS" ? "2px solid var(--ok)" : "2px solid var(--card-border)", borderRadius: 8, cursor: "pointer", transition: "all .2s" }}>✅ PASS</button>
                  <button onClick={() => setForm({ ...form, ir_conclusion: "FAIL" })} style={{ padding: "8px 28px", fontSize: 14, fontWeight: form.ir_conclusion === "FAIL" ? 700 : 400, background: form.ir_conclusion === "FAIL" ? "var(--danger)" : "var(--surface)", color: form.ir_conclusion === "FAIL" ? "#fff" : "var(--text2)", border: form.ir_conclusion === "FAIL" ? "2px solid var(--danger)" : "2px solid var(--card-border)", borderRadius: 8, cursor: "pointer", transition: "all .2s" }}>❌ FAIL</button>
                </div>
              </div>
              {form.ir_conclusion === "FAIL" && (
                <>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>测试数据 / Fail 原因 *</label>
                    <textarea style={{ ...inputStyle, minHeight: 80, resize: "vertical", fontFamily: "inherit" }} value={form.fail_reason} onChange={e => setForm({ ...form, fail_reason: e.target.value })} placeholder="描述 fail 原因、测试数据、关联 Jira 单号等" />
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>测试负责人</label>
                    <input style={{ ...inputStyle, maxWidth: 200 }} value={form.test_owner} onChange={e => setForm({ ...form, test_owner: e.target.value })} placeholder="如 张三" />
                  </div>
                </>
              )}
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
                <button className="secondaryBtn" onClick={() => setMode("list")} style={{ padding: "5px 14px", fontSize: 12 }}>取消</button>
                <button className="primaryBtn" onClick={save} disabled={saving} style={{ padding: "5px 16px", fontSize: 12 }}>{saving ? "保存中..." : "💾 保存"}</button>
              </div>
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 12, borderTop: "1px solid var(--card-border)", marginTop: 12 }}>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}