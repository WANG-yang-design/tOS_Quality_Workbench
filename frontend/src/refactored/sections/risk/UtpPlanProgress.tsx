import React, { useState, useEffect, useCallback } from "react";
import { API_BASE } from "../../constants";

const STATUS_LABEL: Record<string, string> = {
  INIT: "待下发", RUNNING: "执行中", COMPLETED: "完成", CLOSED: "完成", INVALID: "失效",
};
const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  INIT: { bg: "#fef3c7", fg: "#d97706" },
  RUNNING: { bg: "#dbeafe", fg: "#2563eb" },
  COMPLETED: { bg: "#d1fae5", fg: "#059669" },
  CLOSED: { bg: "#d1fae5", fg: "#059669" },
  INVALID: { bg: "#f3f4f6", fg: "#9ca3af" },
};

export function UtpPlanProgress({ activeVersion }: { activeVersion: any }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [editCode, setEditCode] = useState(false);
  const [code, setCode] = useState("");

  const load = useCallback(async (force = false) => {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/utp-plan-progress${force ? "?force=true" : ""}`);
      if (r.ok) { const d = await r.json(); setData(d); if (d.owner_code) setCode(d.owner_code); }
    } catch {}
    finally { setLoading(false); }
  }, [activeVersion?.id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (activeVersion?.owner_code) setCode(activeVersion.owner_code); }, [activeVersion?.owner_code]);

  async function saveCode() {
    if (!activeVersion?.id) return;
    await fetch(`${API_BASE}/api/versions/${activeVersion.id}/utp-plan-progress/save-owner-code`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_code: code.trim() }),
    });
    setEditCode(false);
    load(true);
  }

  if (!activeVersion) return null;
  const plans = data?.plans || [];
  const st = data?.stats;
  const top10 = plans.slice(0, 10);

  return (
    <div className="card" style={{ marginTop: 0 }}>
      {/* 头部 */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>📋 测试计划进度</span>
          {st && <span style={{ fontSize: 12, color: "var(--text3)" }}>共 {st.total} · 待下发 {st.not_started} · 执行中 {st.in_progress} · 完成 {st.completed}{st.invalid > 0 ? ` · 失效 ${st.invalid}` : ''}</span>}
          {data?.synced_at && (
            <span style={{ fontSize: 11, color: "var(--text3)", marginLeft: 8 }}>
              🕐 刷新：{data.synced_at.replace("T", " ").slice(0, 16)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {editCode ? (
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text3)" }}>工号：</span>
              <input value={code} onChange={e => setCode(e.target.value)} placeholder="多个逗号分隔" style={{ width: 150, padding: "3px 8px", fontSize: 12, borderRadius: 6, border: "1px solid var(--card-border)", background: "var(--surface)" }} />
              <button className="primaryBtn" style={{ fontSize: 11, padding: "3px 12px" }} onClick={saveCode}>确定</button>
              <button className="secondaryBtn" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => setEditCode(false)}>取消</button>
            </span>
          ) : (
            <span style={{ fontSize: 11, color: code ? "var(--text)" : "var(--warn)", cursor: "pointer", borderBottom: "1px dashed var(--card-border)" }} onClick={() => setEditCode(true)}>
              {code ? `工号：${code}` : "⚠ 设置工号 ✏️"}
            </span>
          )}
          <button className="smallBtn" style={{ fontSize: 11, padding: "3px 10px" }} onClick={() => load(true)} disabled={loading}>{loading ? "..." : "🔄"}</button>
        </div>
      </div>

      {/* 提示 */}
      {data?.warning && <div style={{ marginBottom: 12, padding: "8px 14px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, fontSize: 12, color: "#92400e" }}>⚠ {data.warning}</div>}

      {/* 统计 */}
      {st && st.total > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
          <S label="待下发" value={st.not_started} c="#d97706" />
          <S label="执行中" value={st.in_progress} c="#2563eb" />
          <S label="已完成" value={st.completed} c="#059669" />
          <S label="平均进度" value={st.avg_progress + "%"} c="var(--accent)" />
        </div>
      )}

      {/* 表格 */}
      {plans.length === 0 && !loading ? (
        <div style={{ textAlign: "center", padding: 32, color: "var(--text3)", fontSize: 13 }}>
          {data?.warning ? "" : "暂无数据，点击 🔄 加载"}
        </div>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="dataTable" style={{ fontSize: 12, minWidth: 700 }}>
              <thead><tr>
                <th style={{ width: 36, textAlign: "center" }}>#</th>
                <th>计划名称</th>
                <th style={{ width: 56, textAlign: "center" }}>阶段</th>
                <th style={{ width: 64, textAlign: "center" }}>状态</th>
                <th style={{ width: 110, textAlign: "center" }}>执行进度</th>
                <th style={{ width: 56, textAlign: "center" }}>等级</th>
                <th style={{ width: 64, textAlign: "center" }}>创建人</th>
                <th style={{ width: 88, textAlign: "center" }}>截止</th>
              </tr></thead>
              <tbody>
                {top10.map((p: any, i: number) => <Row key={p.plan_id} p={p} i={i} />)}
              </tbody>
            </table>
          </div>
          {plans.length > 10 && (
            <div style={{ textAlign: "center", marginTop: 10 }}>
              <button className="smallBtn" style={{ fontSize: 12 }} onClick={() => setShowAll(true)}>查看全部 {plans.length} 个 →</button>
            </div>
          )}
        </>
      )}

      {/* 弹窗 */}
      {showAll && (
        <div className="modalMask" onClick={() => setShowAll(false)}>
          <div className="modal modalWide" style={{ maxWidth: 960, maxHeight: "80vh" }} onClick={e => e.stopPropagation()}>
            <h2>📋 全部测试计划（{plans.length}）</h2>
            <div className="modalScrollBody">
              <table className="dataTable" style={{ fontSize: 12 }}>
                <thead><tr>
                  <th style={{ width: 36, textAlign: "center" }}>#</th><th>计划名称</th>
                  <th style={{ width: 56, textAlign: "center" }}>阶段</th><th style={{ width: 64, textAlign: "center" }}>状态</th>
                  <th style={{ width: 110, textAlign: "center" }}>执行进度</th><th style={{ width: 56, textAlign: "center" }}>等级</th>
                  <th style={{ width: 64, textAlign: "center" }}>创建人</th><th style={{ width: 88, textAlign: "center" }}>截止</th>
                </tr></thead>
                <tbody>{plans.map((p: any, i: number) => <Row key={p.plan_id} p={p} i={i} />)}</tbody>
              </table>
            </div>
            <div className="modalActions"><button className="secondaryBtn" onClick={() => setShowAll(false)}>关闭</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ p, i }: { p: any; i: number }) {
  const ps = (p.plan_status || "").toUpperCase();
  const es = p.execute_schedule || 0;
  const isDone = es >= 100 || ps === "COMPLETED" || ps === "CLOSED";
  const isDelayed = p.warning_status === "delay" && !isDone;
  const ss = STATUS_STYLE[ps] || { bg: "#f3f4f6", fg: "#6b7280" };
  return (
    <tr style={{ background: isDelayed ? "var(--danger-bg)" : undefined }}>
      <td style={{ textAlign: "center", color: "var(--text3)" }}>{i + 1}</td>
      <td><div style={{ fontWeight: 500, maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.plan_name}>{p.plan_name}</div></td>
      <td style={{ textAlign: "center" }}><span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 4, background: "var(--accent-soft)", color: "var(--accent)", fontWeight: 600 }}>{p.test_stage || "-"}</span></td>
      <td style={{ textAlign: "center" }}><span style={{ fontSize: 11, padding: "1px 8px", borderRadius: 4, background: ss.bg, color: ss.fg, fontWeight: 600 }}>{STATUS_LABEL[ps] || ps || "-"}</span></td>
      <td style={{ textAlign: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
          <div style={{ width: 50, height: 6, background: "var(--surface)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: Math.min(es, 100) + "%", height: "100%", background: isDone ? "var(--ok)" : "var(--accent)", borderRadius: 3 }} />
          </div>
          <span style={{ fontSize: 11, fontWeight: 600, color: isDone ? "var(--ok)" : "var(--accent)", minWidth: 30 }}>{es}%</span>
        </div>
      </td>
      <td style={{ textAlign: "center", fontWeight: 600, color: p.level === "H" ? "var(--danger)" : undefined }}>{p.level || "-"}</td>
      <td style={{ textAlign: "center", fontSize: 11 }}>{p.created_by_name || "-"}</td>
      <td style={{ textAlign: "center", fontSize: 11, color: isDelayed ? "var(--danger)" : "var(--text3)" }}>{p.end_time ? p.end_time.slice(0, 10) : "-"}</td>
    </tr>
  );
}

function S({ label, value, c }: { label: string; value: number | string; c: string }) {
  return <div style={{ background: "var(--surface)", borderRadius: 8, padding: "10px 12px", textAlign: "center", border: "1px solid var(--card-border)" }}>
    <div style={{ fontSize: 20, fontWeight: 700, color: c }}>{value}</div>
    <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{label}</div>
  </div>;
}