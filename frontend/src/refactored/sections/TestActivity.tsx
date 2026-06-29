import React, { useEffect, useState, useCallback } from "react";
import { API_BASE } from "../constants";
import { detectCurrentStageFromSchedule, formatStageDisplayName } from "../utils/stage";

type ActivityItem = {
  id: number; version_id: number; stage_name: string; activity_index: number;
  activity_name: string; status: "unconfirmed" | "pass" | "fail";
  operator: string; employee_id: string; remark: string; updated_at: string;
};

type ActivityStats = {
  total: number; pass: number; fail: number; unconfirmed: number; completion_rate: number;
};

// 编辑中的单条变更
type EditChange = { status: "pass" | "fail"; remark: string };

export function TestActivitySection({ activeVersion, stageSchedule }: any) {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [currentStage, setCurrentStage] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<string>("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiGeneratedAt, setAiGeneratedAt] = useState<string>("");

  // 编辑模式：记录被修改的活动 ID → 变更内容
  const [changes, setChanges] = useState<Record<number, EditChange>>({});
  // 正在展开编辑的行 ID
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editStatus, setEditStatus] = useState<"pass" | "fail">("pass");
  const [editRemark, setEditRemark] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (stageSchedule?.length > 0) setCurrentStage(detectCurrentStageFromSchedule(stageSchedule) || "");
  }, [stageSchedule]);

  const loadActivities = useCallback(async () => {
    if (!activeVersion?.id || !currentStage) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/test-activities?stage=${encodeURIComponent(currentStage)}`);
      const data = await res.json();
      setActivities(data.activities || []);
      setStats(data.stats || null);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [activeVersion?.id, currentStage]);

  const loadAiAnalysis = useCallback(async () => {
    if (!activeVersion?.id || !currentStage) return;
    try {
      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/test-activities/ai-analysis?stage=${encodeURIComponent(currentStage)}`);
      const data = await res.json();
      if (data.analysis) { setAiAnalysis(data.analysis.analysis_text || ""); setAiGeneratedAt(data.analysis.generated_at || ""); }
    } catch { /* ignore */ }
  }, [activeVersion?.id, currentStage]);

  useEffect(() => { loadActivities(); loadAiAnalysis(); }, [loadActivities, loadAiAnalysis]);

  // 点击"修改"→ 展开该行编辑
  function startEdit(item: ActivityItem) {
    const existing = changes[item.id];
    setEditingId(item.id);
    setEditStatus(existing?.status ?? (item.status === "fail" ? "fail" : "pass"));
    setEditRemark(existing?.remark ?? item.remark ?? "");
    setSaveMsg(null);
  }

  // 确认当前行编辑 → 记入 changes
  function confirmEdit() {
    if (editingId === null) return;
    setChanges(prev => ({ ...prev, [editingId]: { status: editStatus, remark: editRemark } }));
    setEditingId(null);
  }

  function cancelEdit() { setEditingId(null); }

  // 取消某条变更
  function revertChange(id: number) {
    setChanges(prev => { const n = { ...prev }; delete n[id]; return n; });
  }

  // 批量保存所有变更
  async function saveAll() {
    if (Object.keys(changes).length === 0) { setSaveMsg({ type: "err", text: "没有需要保存的变更" }); return; }

    setSaving(true);
    setSaveMsg(null);
    let okCount = 0;
    let errMsg = "";

    for (const [idStr, change] of Object.entries(changes)) {
      try {
        const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/test-activities/${idStr}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: change.status, remark: change.remark }),
        });
        if (res.ok) okCount++;
        else { const d = await res.json().catch(() => ({})); errMsg = d.detail || `第${idStr}条保存失败`; }
      } catch (e: any) { errMsg = e.message || "网络错误"; }
    }

    setSaving(false);
    if (errMsg) setSaveMsg({ type: "err", text: `${okCount}条成功，失败：${errMsg}` });
    else setSaveMsg({ type: "ok", text: `成功保存 ${okCount} 条变更` });

    setChanges({});
    loadActivities();
    setTimeout(() => setSaveMsg(null), 5000);
  }

  async function runAiAnalysis() {
    if (!activeVersion?.id || !currentStage) return;
    setAiLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/test-activities/ai-analysis?stage=${encodeURIComponent(currentStage)}`, { method: "POST" });
      const data = await res.json();
      setAiAnalysis(data.analysis || "");
      setAiGeneratedAt(data.generated_at || "");
    } catch { /* ignore */ }
    finally { setAiLoading(false); }
  }

  // 获取某条活动的当前显示状态（优先用 changes 中的）
  function getDisplay(item: ActivityItem) {
    const c = changes[item.id];
    return { status: c?.status ?? item.status, remark: c?.remark ?? item.remark };
  }

  const hasChanges = Object.keys(changes).length > 0;

  if (!currentStage) {
    return (
      <div className="reportSection">
        <div className="card" style={{ textAlign: "center", padding: "48px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text2)", marginBottom: 8 }}>暂未识别到当前版本阶段</div>
          <div style={{ fontSize: 13, color: "var(--text3)" }}>请检查版本阶段时间配置，确保当前日期处于某个阶段的时间范围内</div>
        </div>
      </div>
    );
  }

  return (
    <div className="reportSection">
      {/* 头部 */}
      <div style={{ background: "linear-gradient(135deg, var(--accent-soft), transparent)", borderRadius: 14, padding: "20px 24px", marginBottom: 16, border: "1px solid var(--card-border)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>🎯 {activeVersion?.version_name || ""} · 重点测试活动</div>
            <div style={{ fontSize: 14, color: "var(--text2)", marginTop: 4 }}>
              当前阶段：<span style={{ display: "inline-block", background: "var(--accent)", color: "#fff", padding: "2px 12px", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>{formatStageDisplayName(currentStage)}</span>
            </div>
          </div>
        </div>
        {stats && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
            <StatMini label="活动总数" value={stats.total} color="var(--accent)" />
            <StatMini label="已通过" value={stats.pass} color="var(--ok)" />
            <StatMini label="未通过" value={stats.fail} color="var(--danger)" />
            <StatMini label="未确认" value={stats.unconfirmed} color="var(--warn)" />
            <StatMini label="完成率" value={`${stats.completion_rate}%`} color="var(--accent)" />
          </div>
        )}
      </div>

      {/* 活动列表 */}
      {loading ? (
        <div className="card" style={{ textAlign: "center", padding: 32 }}>
          <div className="dataLoadingSpinner" style={{ margin: "0 auto 12px" }} />
          <div style={{ color: "var(--text3)", fontSize: 13 }}>加载中...</div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="dataTable" style={{ margin: 0 }}>
            <thead>
              <tr>
                <th style={{ width: 50, textAlign: "center" }}>序号</th>
                <th>活动名称</th>
                <th style={{ width: 90, textAlign: "center" }}>状态</th>
                <th style={{ width: 130, textAlign: "center" }}>更新时间</th>
                <th style={{ width: 90, textAlign: "center" }}>操作人</th>
                <th style={{ width: 100, textAlign: "center" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {activities.map((item, idx) => {
                const disp = getDisplay(item);
                const isEditing = editingId === item.id;
                const isChanged = !!changes[item.id];
                return (
                  <React.Fragment key={item.id}>
                    <tr style={{ background: isChanged ? "var(--accent-soft)" : disp.status === "fail" ? "var(--danger-bg)" : undefined }}>
                      <td style={{ textAlign: "center", color: "var(--text3)", fontSize: 13 }}>{idx + 1}</td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{item.activity_name}</div>
                        {disp.status === "fail" && disp.remark && !isEditing && (
                          <div style={{ fontSize: 12, color: "var(--danger)", marginTop: 2, fontStyle: "italic" }}>备注：{disp.remark}</div>
                        )}
                        {isChanged && !isEditing && (
                          <div style={{ fontSize: 11, color: "var(--accent)", marginTop: 1 }}>⬤ 已修改（待保存）</div>
                        )}
                      </td>
                      <td style={{ textAlign: "center" }}><StatusBadge status={disp.status} /></td>
                      <td style={{ textAlign: "center", fontSize: 12, color: "var(--text3)" }}>{item.updated_at ? formatTime(item.updated_at) : "-"}</td>
                      <td style={{ textAlign: "center", fontSize: 12, color: "var(--text2)" }}>{item.operator || "-"}</td>
                      <td style={{ textAlign: "center" }}>
                        <button className="activityBtn activityBtnEdit" onClick={() => isEditing ? cancelEdit() : startEdit(item)}>
                          {isEditing ? "取消" : "✏ 修改"}
                        </button>
                      </td>
                    </tr>
                    {isEditing && (
                      <tr>
                        <td colSpan={6} style={{ padding: "12px 16px", background: "var(--surface)" }}>
                          <div style={{ display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
                            <div>
                              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4 }}>状态</div>
                              <div style={{ display: "flex", gap: 6 }}>
                                <button className={editStatus === "pass" ? "activityBtn activityBtnPassActive" : "activityBtn activityBtnPass"} onClick={() => setEditStatus("pass")}>✓ Pass</button>
                                <button className={editStatus === "fail" ? "activityBtn activityBtnFailActive" : "activityBtn activityBtnFail"} onClick={() => setEditStatus("fail")}>✗ Fail</button>
                              </div>
                            </div>
                            <div style={{ flex: 1, minWidth: 200 }}>
                              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4 }}>备注</div>
                              <input value={editRemark} onChange={e => setEditRemark(e.target.value)} placeholder={editStatus === "fail" ? "建议填写 Fail 原因..." : "备注（可选）"} style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--card-border)", fontSize: 13, background: "var(--card)", color: "var(--text)" }} />
                            </div>
                            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, paddingTop: 18 }}>
                              <button className="primaryBtn" style={{ fontSize: 12, padding: "6px 20px" }} onClick={confirmEdit}>确认</button>
                              <button className="secondaryBtn" style={{ fontSize: 12, padding: "6px 16px" }} onClick={cancelEdit}>取消</button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
              {activities.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 32, color: "var(--text3)" }}>当前阶段暂无活动项</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* 底部操作栏：保存 */}
      <div style={{
        marginTop: 16, padding: "16px 20px", background: "var(--card)", borderRadius: 12,
        border: hasChanges ? "2px solid var(--accent)" : "1px solid var(--card-border)",
        boxShadow: hasChanges ? "0 0 0 3px var(--accent-glow)" : "none",
        transition: "all .3s",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
          {hasChanges && (
            <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600, marginRight: "auto" }}>
              已修改 {Object.keys(changes).length} 项
            </span>
          )}
          {hasChanges && (
            <button className="secondaryBtn" style={{ fontSize: 12 }} onClick={() => setChanges({})}>撤销全部</button>
          )}
          <button className="primaryBtn" style={{ fontSize: 13, padding: "8px 24px" }} onClick={saveAll} disabled={saving || !hasChanges}>
            {saving ? "⏳ 保存中..." : "💾 保存"}
          </button>
        </div>
        {saveMsg && (
          <div style={{ marginTop: 10, fontSize: 13, fontWeight: 600, color: saveMsg.type === "ok" ? "var(--ok)" : "var(--danger)" }}>
            {saveMsg.type === "ok" ? "✅ " : "⚠ "}{saveMsg.text}
          </div>
        )}
      </div>
    </div>
  );
}

function StatMini({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div style={{ background: "var(--card)", borderRadius: 10, padding: "10px 14px", textAlign: "center", border: "1px solid var(--card-border)" }}>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "pass") return <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 6, background: "var(--ok-bg)", color: "var(--ok)", fontSize: 12, fontWeight: 600 }}>✓ Pass</span>;
  if (status === "fail") return <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 6, background: "var(--danger-bg)", color: "var(--danger)", fontSize: 12, fontWeight: 600 }}>✗ Fail</span>;
  return <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 6, background: "var(--surface)", color: "var(--text3)", fontSize: 12, fontWeight: 500 }}>未确认</span>;
}

function formatTime(isoStr: string): string {
  if (!isoStr) return "-";
  try { const d = new Date(isoStr); return `${String(d.getMonth()+1).padStart(2,"0")}.${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; }
  catch { return isoStr; }
}