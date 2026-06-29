import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";
import { EMPTY_PLAN } from "../../types";
import type { TestPlan } from "../../types";

// 从 App.tsx 第1777行原样提取 - 测试计划弹窗
export function TestPlanModal({ versionId, planType, title, onClose, onSaved }: { versionId: number; planType: string; title: string; onClose: () => void; onSaved: () => void }) {
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingPlan, setEditingPlan] = useState<TestPlan | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  async function loadPlans() {
    setLoading(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${versionId}/test-plans/${planType}`);
      const json = await res.json();
      setPlans(json.plans || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => { loadPlans(); }, [versionId, planType]);

  async function savePlan() {
    if (!editingPlan?.device_name.trim()) { alert("请输入机型名称"); return; }
    setSaving(true);
    try {
      const res = await fetch(API_BASE + `/api/versions/${versionId}/test-plans/${planType}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editingPlan),
      });
      if (res.ok) { setShowForm(false); setEditingPlan(null); await loadPlans(); onSaved(); }
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  async function deletePlan(deviceName: string) {
    if (!confirm(`确认删除「${deviceName}」的测试计划？`)) return;
    try {
      await fetch(API_BASE + `/api/versions/${versionId}/test-plans/${planType}/${encodeURIComponent(deviceName)}`, { method: "DELETE" });
      await loadPlans(); onSaved();
    } catch { alert("删除失败"); }
  }

  function startEdit(plan?: TestPlan) {
    setEditingPlan(plan ? { ...plan } : { ...EMPTY_PLAN });
    setShowForm(true);
  }

  const inputStyle: React.CSSProperties = { width: "100%", padding: "6px 10px", fontSize: 13, borderRadius: 6, border: "1px solid var(--card-border)", background: "var(--surface)", color: "var(--text)" };

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal" style={{ width: 700, display: "flex", flexDirection: "column", maxHeight: "85vh" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <h2 style={{ margin: 0 }}>📋 {title}</h2>
          <span style={{ fontSize: 12, color: "var(--text3)" }}>{plans.length} 项计划</span>
        </div>
        <p style={{ fontSize: 12, color: "var(--text3)", margin: "0 0 14px" }}>为尚未开始测试的机型添加测试计划，数据保存在本地数据库。</p>
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {loading ? (
            <p style={{ color: "var(--text3)", textAlign: "center", padding: 24 }}>加载中...</p>
          ) : plans.length === 0 && !showForm ? (
            <div style={{ textAlign: "center", padding: 24 }}>
              <p style={{ color: "var(--text3)", marginBottom: 12 }}>暂无测试计划</p>
              <button className="primaryBtn" onClick={() => startEdit()} style={{ fontSize: 13 }}>＋ 添加计划</button>
            </div>
          ) : (
            <>
              {!showForm && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                    <button className="primaryBtn" onClick={() => startEdit()} style={{ padding: "4px 14px", fontSize: 12 }}>＋ 添加计划</button>
                  </div>
                  <table className="dataTable" style={{ margin: 0, fontSize: 12 }}>
                    <thead><tr><th>机型</th><th>测试内容</th><th>状态</th><th>计划时间</th><th>负责人</th><th>操作</th></tr></thead>
                    <tbody>{plans.map((p: any) => (
                      <tr key={p.device_name}>
                        <td style={{ fontWeight: 600 }}>{p.device_name}</td>
                        <td style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.test_items}>{p.test_items || "-"}</td>
                        <td><span className={"badge " + (p.plan_status === "completed" ? "badgeGo" : p.plan_status === "in_progress" ? "badgeInfo" : "badgeWarn")}>{p.plan_status === "completed" ? "已完成" : p.plan_status === "in_progress" ? "进行中" : "计划中"}</span></td>
                        <td style={{ whiteSpace: "nowrap" }}>{p.plan_start_date && p.plan_end_date ? `${p.plan_start_date} ~ ${p.plan_end_date}` : p.plan_start_date || "-"}</td>
                        <td>{p.responsible_person || "-"}</td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <button className="smallBtn" onClick={() => startEdit(p)} style={{ padding: "2px 8px", fontSize: 10, marginRight: 4 }}>编辑</button>
                          <button className="smallBtn" onClick={() => deletePlan(p.device_name)} style={{ padding: "2px 8px", fontSize: 10, color: "var(--danger)", border: "1px solid #fecaca" }}>删除</button>
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {showForm && editingPlan && (
                <div className="subCard" style={{ padding: "14px 18px" }}>
                  <h3 style={{ fontSize: 14, margin: "0 0 14px", color: "var(--text)" }}>{editingPlan.id ? "编辑计划" : "添加计划"}</h3>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
                    <div><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>机型名称 *</label><input style={inputStyle} value={editingPlan.device_name} onChange={e => setEditingPlan({ ...editingPlan, device_name: e.target.value })} placeholder="如 X6879" /></div>
                    <div><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>负责人</label><input style={inputStyle} value={editingPlan.responsible_person} onChange={e => setEditingPlan({ ...editingPlan, responsible_person: e.target.value })} placeholder="如 张三" /></div>
                  </div>
                  <div style={{ marginBottom: 10 }}><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>测试内容</label><input style={inputStyle} value={editingPlan.test_items} onChange={e => setEditingPlan({ ...editingPlan, test_items: e.target.value })} placeholder="如 功耗测试、性能基线测试" /></div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
                    <div><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>状态</label><select style={{ ...inputStyle, cursor: "pointer" }} value={editingPlan.plan_status} onChange={e => setEditingPlan({ ...editingPlan, plan_status: e.target.value })}><option value="planned">计划中</option><option value="in_progress">进行中</option><option value="completed">已完成</option></select></div>
                    <div><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>计划开始</label><input type="date" style={inputStyle} value={editingPlan.plan_start_date} onChange={e => setEditingPlan({ ...editingPlan, plan_start_date: e.target.value })} /></div>
                    <div><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>计划结束</label><input type="date" style={inputStyle} value={editingPlan.plan_end_date} onChange={e => setEditingPlan({ ...editingPlan, plan_end_date: e.target.value })} /></div>
                  </div>
                  <div style={{ marginBottom: 10 }}><label style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4, display: "block" }}>备注</label><textarea style={{ ...inputStyle, minHeight: 50, resize: "vertical", fontFamily: "inherit" }} value={editingPlan.remark} onChange={e => setEditingPlan({ ...editingPlan, remark: e.target.value })} placeholder="补充说明" /></div>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button className="secondaryBtn" onClick={() => { setShowForm(false); setEditingPlan(null); }} style={{ padding: "5px 14px", fontSize: 12 }}>取消</button>
                    <button className="primaryBtn" onClick={savePlan} disabled={saving} style={{ padding: "5px 16px", fontSize: 12 }}>{saving ? "保存中..." : "💾 保存"}</button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 12, borderTop: "1px solid var(--card-border)", marginTop: 12 }}>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}