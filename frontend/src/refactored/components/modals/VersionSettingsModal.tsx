import React, { useState } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5862行原样提取
export function VersionSettingsModal({ version, onClose, onSuccess }: any) {
  const [form, setForm] = useState({
    version_name: version?.version_name || "",
    jira_project: version?.jira_project || "",
    jira_fix_version: version?.jira_fix_version || "",
    owner_name: version?.owner_name || "",
    is_train_version: version?.is_train_version === 1,
    is_pad: version?.is_pad === 1,
    utp_owner_codes: version?.utp_owner_codes || "",
    owner_code: version?.owner_code || "",
    alm_space_bid: version?.alm_space_bid || "",
    alm_app_bid: version?.alm_app_bid || "",
    feishu_sheet_url: version?.feishu_sheet_url || "",
    perf_sheet_url: version?.perf_sheet_url || "",
    battery_sheet_url: version?.battery_sheet_url || "",
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + version.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) { onSuccess(); }
      else { const data = await res.json(); alert(data.detail || "保存失败"); }
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  async function deleteVersion() {
    try {
      const res = await fetch(API_BASE + "/api/versions/" + version.id, { method: "DELETE" });
      if (res.ok) { onSuccess(); }
      else { alert("删除失败"); }
    } catch { alert("删除失败"); }
  }

  return (
    <div className="modalMask" onClick={onClose}>
      <div className="modal" style={{maxHeight:"85vh",overflowY:"auto"}} onClick={e => e.stopPropagation()}>
        <h2>版本设置 - {version?.version_name}</h2>

        <label>版本名称</label>
        <input value={form.version_name} onChange={e => setForm({...form, version_name: e.target.value})} />

        <label>Jira项目</label>
        <input value={form.jira_project} onChange={e => setForm({...form, jira_project: e.target.value})} />

        <label>Jira版本字段</label>
        <input value={form.jira_fix_version} onChange={e => setForm({...form, jira_fix_version: e.target.value})} />

        <label>负责人</label>
        <input value={form.owner_name} onChange={e => setForm({...form, owner_name: e.target.value})} />

        <label className="checkLine">
          <input type="checkbox" checked={form.is_train_version} onChange={e => setForm({...form, is_train_version: e.target.checked})} />
          这是 1+N 版本火车类项目
        </label>
        <label className="checkLine">
          <input type="checkbox" checked={form.is_pad} onChange={e => setForm({...form, is_pad: e.target.checked})} />
          PAD 版本 <span style={{fontSize:11,color:"var(--text3)"}}>（Jira 限制 summary 包含 PAD）</span>
        </label>

        <label>UTP 创建人工号</label>
        <input value={form.utp_owner_codes} onChange={e => setForm({...form, utp_owner_codes: e.target.value})} placeholder="如 18620222（用于 Weekly 报告）" />

        <label>版本负责人（测试）工号</label>
        <input value={form.owner_code} onChange={e => setForm({...form, owner_code: e.target.value})} placeholder="多个用逗号分隔，如 18620222,18658849" />

        <div style={{borderTop:"1px solid var(--border)",margin:"12px 0",paddingTop:12}}>
          <label>飞书管理书 URL</label>
          <input value={form.feishu_sheet_url} onChange={e => setForm({...form, feishu_sheet_url: e.target.value})} placeholder="https://transsioner.feishu.cn/wiki/..." />
        </div>

        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
          <div>
            <label>ALM SPACE_BID</label>
            <input value={form.alm_space_bid} onChange={e => setForm({...form, alm_space_bid: e.target.value})} />
          </div>
          <div>
            <label>ALM APP_BID</label>
            <input value={form.alm_app_bid} onChange={e => setForm({...form, alm_app_bid: e.target.value})} />
          </div>
        </div>

        <div className="modalActions">
          <button className="secondaryBtn" style={{background:"#fee2e2",color:"#dc2626",border:"1px solid #fca5a5"}}
            onClick={() => setShowDeleteConfirm(true)}>
            删除版本
          </button>
          <div style={{flex:1}} />
          <button className="secondaryBtn" onClick={onClose}>取消</button>
          <button className="primaryBtn" onClick={save} disabled={saving}>
            {saving ? "保存中..." : "保存"}
          </button>
        </div>

        {showDeleteConfirm && (
          <div style={{marginTop:12,padding:12,background:"#fef2f2",border:"1px solid #fca5a5",borderRadius:8}}>
            <p style={{fontWeight:600,color:"#dc2626",marginBottom:8}}>确认删除版本？</p>
            <p style={{fontSize:13,color:"var(--text2)",marginBottom:12}}>
              删除后将无法恢复，包括该版本的所有数据（阶段、Jira缓存、SR数据等）都将被删除。
            </p>
            <div style={{display:"flex",gap:8,justifyContent:"flex-end"}}>
              <button className="smallBtn" onClick={() => setShowDeleteConfirm(false)}>取消</button>
              <button className="primaryBtn" style={{background:"#dc2626"}} onClick={deleteVersion}>确认删除</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}