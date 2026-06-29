import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5528行原样提取 - AI 设置弹窗
export function AISettingsModal({ onClose }: any) {
  const ALL_MODELS = ["gpt-5.2-chat", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-3-5-sonnet"];
  const [cfg, setCfg] = useState({ api_base: "https://hk-intra-paas.transsion.com/tranai-proxy/v1", api_key: "", model: "gpt-5.2-chat", user_no: "", user_name: "", user_dept: "" });
  const [masked, setMasked] = useState("");

  useEffect(() => {
    fetch(API_BASE + "/api/ai/config").then(r => r.json()).then(d => {
      if (d.api_base) { setCfg(prev => ({ ...prev, ...d, api_key: "" })); setMasked(d.api_key_masked || ""); }
    }).catch(() => {});
  }, []);

  async function handleSave() {
    const payload: any = { ...cfg };
    if (!payload.api_key) delete payload.api_key;
    const res = await fetch(API_BASE + "/api/ai/config", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (res.ok) { alert("AI 配置已保存"); onClose(); } else { alert("保存失败"); }
  }

  return (
    <div className="modalMask">
      <div className="modal" style={{ width: 520 }}>
        <h2>🤖 AI 分析设置</h2>
        <p className="modalDesc">配置 TranAI 代理地址、API Key 及用户信息</p>
        <label>API 地址</label>
        <input value={cfg.api_base} onChange={e => setCfg({ ...cfg, api_base: e.target.value })} />
        <label>API Key {masked && <span style={{fontSize:11,color:"var(--text3)",fontWeight:400}}>（当前：{masked}）</span>}</label>
        <input type="password" value={cfg.api_key} onChange={e => setCfg({ ...cfg, api_key: e.target.value })} placeholder="留空则不更新" />
        <label>模型</label>
        <select value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })}
          style={{width:"100%",padding:"10px 12px",borderRadius:8,border:"1px solid var(--card-border)",background:"var(--surface)",color:"var(--text)",fontSize:14}}>
          {ALL_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginTop:8}}>
          <div><label>工号</label><input value={cfg.user_no} onChange={e => setCfg({ ...cfg, user_no: e.target.value })} placeholder="如 186xxxxx" /></div>
          <div><label>姓名</label><input value={cfg.user_name} onChange={e => setCfg({ ...cfg, user_name: e.target.value })} placeholder="如 陈xx" /></div>
          <div><label>部门</label><input value={cfg.user_dept} onChange={e => setCfg({ ...cfg, user_dept: e.target.value })} placeholder="AI创新部" /></div>
        </div>
        <div className="modalActions">
          <button className="secondaryBtn" onClick={onClose}>取消</button>
          <button className="primaryBtn" onClick={handleSave}>💾 保存</button>
        </div>
      </div>
    </div>
  );
}