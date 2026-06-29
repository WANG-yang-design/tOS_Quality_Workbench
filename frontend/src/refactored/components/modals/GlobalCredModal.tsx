import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5490行原样提取 - 全局凭证弹窗
export function GlobalCredModal({ onClose }: any) {
  const [form, setForm] = useState({ jira_base_url: "http://jira.transsion.com", username: "", password: "" });
  async function submit() {
    const res = await fetch(API_BASE + "/api/jira/global-credential", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
    });
    if (res.ok) { alert("Jira 账号已保存，所有版本通用"); onClose(); }
    else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }
  return (
    <div className="modalMask">
      <div className="modal" style={{ width: 480 }}>
        <h2>🔑 Jira 账号设置</h2>
        <p className="modalDesc">配置的账号密码所有版本通用，仅需设置一次。</p>
        <label>Jira 地址</label>
        <input value={form.jira_base_url} onChange={e => setForm({ ...form, jira_base_url: e.target.value })} />
        <label>账号</label>
        <input placeholder="Jira 账号" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
        <label>密码</label>
        <input type="password" placeholder="Jira 密码" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
        <div className="modalActions">
          <button className="secondaryBtn" onClick={onClose}>取消</button>
          <button className="primaryBtn" onClick={submit}>💾 保存</button>
        </div>
      </div>
    </div>
  );
}