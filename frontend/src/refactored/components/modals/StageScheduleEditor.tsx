import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";
import { formatStageName } from "../../utils/date";

const ALL_STAGES = ["概念启动", "STR1", "STR2", "STR3", "STR4", "STR4A", "STR5", "1+N版本火车"];

export function StageScheduleEditor({ versionId, versionName, stages, onClose, onSuccess }: any) {
  // 截止日期
  const [deadlines, setDeadlines] = useState<Record<string, string>>({});
  // 当前阶段
  const [currentStage, setCurrentStage] = useState<string>("");
  const [userOverridden, setUserOverridden] = useState(false);
  const [saving, setSaving] = useState(false);

  // 飞书导入
  const [feishuUrl, setFeishuUrl] = useState("");
  const [feishuLoggedIn, setFeishuLoggedIn] = useState(false);
  const [importing, setImporting] = useState(false);
  const [showFeishu, setShowFeishu] = useState(false);
  const [lastImportResult, setLastImportResult] = useState("");

  // 初始化
  useEffect(() => {
    const map: Record<string, string> = {};
    let dbCurrent = "";
    (stages || []).forEach((s: any) => {
      if (s.end_date) map[s.stage_name] = s.end_date;
      if (s.current_flag === 1) dbCurrent = s.stage_name;
    });
    setDeadlines(map);
    setCurrentStage(dbCurrent || "");
    if (dbCurrent) setUserOverridden(true);

    // 加载飞书 URL
    fetch(API_BASE + "/api/versions").then(r => r.json()).then(vers => {
      const v = vers.find((ver: any) => ver.id === versionId);
      if (v?.feishu_sheet_url) setFeishuUrl(v.feishu_sheet_url);
    }).catch(() => {});
    checkFeishuToken();
  }, [stages, versionId]);

  async function checkFeishuToken() {
    try {
      const d = await (await fetch(API_BASE + "/api/feishu/token-status")).json();
      setFeishuLoggedIn(!!d.logged_in);
    } catch { setFeishuLoggedIn(false); }
  }

  function handleFeishuLogin() {
    const loginWin = window.open(API_BASE + "/api/feishu/login", "feishu_oauth", "width=600,height=700,scrollbars=yes");
    const poll = setInterval(() => {
      if (!loginWin || loginWin.closed) { clearInterval(poll); checkFeishuToken(); }
    }, 1000);
  }

  // 自动识别当前阶段
  useEffect(() => {
    if (userOverridden) return;
    const detected = detectCurrentStage(deadlines);
    if (detected) setCurrentStage(detected);
  }, [deadlines, userOverridden]);

  function detectCurrentStage(dl: Record<string, string>): string {
    const today = new Date().toISOString().slice(0, 10);
    for (let i = 0; i < ALL_STAGES.length; i++) {
      const end = dl[ALL_STAGES[i]];
      if (!end) continue;
      const prevEnd = i > 0 ? dl[ALL_STAGES[i - 1]] : null;
      const startBound = prevEnd ? new Date(new Date(prevEnd).getTime() + 86400000).toISOString().slice(0, 10) : "0000-00-00";
      if (startBound <= today && today <= end) return ALL_STAGES[i];
    }
    const lastEnd = dl[ALL_STAGES[ALL_STAGES.length - 1]];
    if (lastEnd && today > lastEnd) return ALL_STAGES[ALL_STAGES.length - 1];
    return "";
  }

  function computeStartDate(name: string): string {
    const idx = ALL_STAGES.indexOf(name);
    if (idx === 0) return "从基线开始";
    const prevEnd = deadlines[ALL_STAGES[idx - 1]];
    if (!prevEnd) return "";
    try { const d = new Date(prevEnd); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); }
    catch { return ""; }
  }

  async function handleFeishuImport() {
    if (!feishuUrl) { alert("请输入飞书表格URL"); return; }
    if (!feishuLoggedIn) { alert("请先完成飞书 OAuth 授权"); return; }
    setImporting(true);
    setLastImportResult("");
    try {
      fetch(`${API_BASE}/api/versions/${versionId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feishu_sheet_url: feishuUrl }),
      }).catch(() => {});

      const res = await fetch(`${API_BASE}/api/versions/${versionId}/stages/import-feishu`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feishu_url: feishuUrl }),
      });
      const data = await res.json();
      if (!res.ok) { alert(data.detail || "导入失败"); return; }

      // 刷新阶段数据
      const stagesRes = await fetch(`${API_BASE}/api/versions/${versionId}/stages`);
      const stagesData = await stagesRes.json();
      const newDeadlines: Record<string, string> = {};
      (stagesData || []).forEach((s: any) => { if (s.end_date) newDeadlines[s.stage_name] = s.end_date; });
      setDeadlines(newDeadlines);
      setUserOverridden(false);
      setLastImportResult(data.message || "导入成功");
      onSuccess(stagesData);
    } catch (e: any) {
      alert("导入出错：" + (e.message || "未知错误"));
    } finally { setImporting(false); }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const payload = {
        stages: ALL_STAGES.map(name => ({
          stage_name: name,
          end_date: deadlines[name] || "",
          current_flag: name === currentStage ? 1 : 0,
        })),
      };
      const res = await fetch(`${API_BASE}/api/versions/${versionId}/stages/batch`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) { const d = await res.json(); alert(d.detail || "保存失败"); return; }
      const stagesRes = await fetch(`${API_BASE}/api/versions/${versionId}/stages`);
      onSuccess(await stagesRes.json());
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal modalWide" onClick={e => e.stopPropagation()}>
        <h2>📋 阶段时间表 — {versionName}</h2>
        <div className="modalScrollBody">
          <p className="modalDesc">填写各阶段的<strong>截止日期</strong>，开始时间自动推算。1+N版本火车自动从 STR5 截止次日开始。</p>

          <div className="stageScheduleTable">
            <table className="dataTable">
              <thead><tr><th>阶段</th><th>自动开始</th><th>截止日期</th><th>当前阶段</th></tr></thead>
              <tbody>
                {ALL_STAGES.map(name => {
                  const end = deadlines[name] || "";
                  const start = computeStartDate(name);
                  const isCurrent = currentStage === name;
                  const isLast = name === "1+N版本火车";
                  return (
                    <tr key={name} className={isCurrent ? "currentStageRow" : ""}>
                      <td style={{ fontWeight: 600 }}>{formatStageName(name)}</td>
                      <td className="autoStartCell">{start || "—"}</td>
                      <td>
                        {isLast ? (
                          <span className="autoStartCell">自动（无需填写）</span>
                        ) : (
                          <input type="date" value={end} onChange={e => { setDeadlines(prev => ({ ...prev, [name]: e.target.value })); setUserOverridden(false); }} />
                        )}
                      </td>
                      <td>
                        <button
                          className={"smallBtn " + (isCurrent ? "primaryBtn" : "secondaryBtn")}
                          onClick={() => { setCurrentStage(name); setUserOverridden(true); }}>
                          {isCurrent ? "✦ 当前" : "设为当前"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 飞书导入 */}
          <div className="feishuImportSection">
            <button className="textLink" onClick={() => setShowFeishu(!showFeishu)}>
              {showFeishu ? "收起飞书导入 ▲" : "📥 从飞书表格导入截止时间 ▼"}
            </button>
            {showFeishu && (
              <div className="feishuForm">
                <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.8, marginBottom: 8 }}>
                  从飞书「研测项目管理书」表格自动导入各阶段的截止时间。<br />
                  <strong>表格要求：</strong>第一列包含版本名，表头含 STR1~STR5 / STR4A / 概念启动 标识，附近有「计划」日期行。
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: feishuLoggedIn ? "#ecfdf5" : "#fef3c7", borderRadius: 10, border: "1px solid " + (feishuLoggedIn ? "#a7f3d0" : "#fde68a") }}>
                  <span style={{ fontSize: 14 }}>{feishuLoggedIn ? "✅" : "⚠️"}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: feishuLoggedIn ? "#065f46" : "#92400e" }}>
                    {feishuLoggedIn ? "飞书已授权" : "飞书未授权 — 请先登录"}
                  </span>
                  <button className={feishuLoggedIn ? "secondaryBtn" : "primaryBtn"} onClick={handleFeishuLogin} style={{ marginLeft: "auto", padding: "5px 14px", fontSize: 12 }}>
                    {feishuLoggedIn ? "重新授权" : "🔑 飞书登录"}
                  </button>
                </div>
                <label>飞书表格 URL</label>
                <input placeholder="https://transsioner.feishu.cn/wiki/XXX?sheet=YYY" value={feishuUrl} onChange={e => setFeishuUrl(e.target.value)} />
                <button className="primaryBtn" onClick={handleFeishuImport} disabled={importing || !feishuLoggedIn} style={{ marginTop: 6 }}>
                  {importing ? "⏳ 正在从飞书读取..." : "📥 从飞书导入阶段时间"}
                </button>
                {lastImportResult && <div style={{ fontSize: 13, color: "#059669", fontWeight: 600, marginTop: 6 }}>✅ {lastImportResult}</div>}
              </div>
            )}
          </div>
        </div>

        <div className="modalActions">
          <button className="secondaryBtn" onClick={onClose}>取消</button>
          <button className="primaryBtn" onClick={handleSave} disabled={saving}>{saving ? "保存中..." : "💾 保存时间表"}</button>
        </div>
      </div>
    </div>
  );
}