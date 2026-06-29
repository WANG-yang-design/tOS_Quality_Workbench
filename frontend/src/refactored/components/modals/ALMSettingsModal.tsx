import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5593行原样提取 - ALM 设置弹窗
export function ALMSettingsModal({ onClose }: any) {
  const [cfg, setCfg] = useState({
    uac_gateway: "https://pfgatewaysz.transsion.com:9199",
    alm_app_id: "", uac_username: "", uac_password: "",
    uac_source: "ALM",
    alm_base_url: "https://pfgatewaysz.transsion.com:9199/alm-transcend-datadriven",
  });
  const [hasExisting, setHasExisting] = useState(false);

  useEffect(() => {
    fetch(API_BASE + "/api/alm/config").then(r => r.json()).then(d => {
      if (d.alm_app_id) { setCfg(prev => ({ ...prev, ...d, uac_password: "" })); setHasExisting(d.configured); }
    }).catch(() => {});
  }, []);

  async function handleSave() {
    if (!cfg.alm_app_id || !cfg.uac_username || !cfg.uac_password) { alert("App ID、工号和密码不能为空"); return; }
    const res = await fetch(API_BASE + "/api/alm/config", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg),
    });
    if (res.ok) { alert("ALM 配置已保存"); onClose(); }
    else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  return (
    <div className="modalMask">
      <div className="modal" style={{ width: 560 }}>
        <h2>⚙️ ALM 平台设置</h2>
        <p className="modalDesc">配置 ALM 用户中心鉴权信息（全局通用）</p>
        <label>用户中心网关（UAC_GATEWAY）</label>
        <input value={cfg.uac_gateway} onChange={e => setCfg({ ...cfg, uac_gateway: e.target.value })} />
        <label>应用 ID（ALM_APP_ID）</label>
        <input value={cfg.alm_app_id} onChange={e => setCfg({ ...cfg, alm_app_id: e.target.value })} placeholder="如 c_MjYwNjAxMDAxaA" />
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
          <div><label>工号（UAC_USERNAME）</label><input value={cfg.uac_username} onChange={e => setCfg({ ...cfg, uac_username: e.target.value })} placeholder="如 18665088" /></div>
          <div><label>密码（UAC_PASSWORD）</label><input type="password" value={cfg.uac_password} onChange={e => setCfg({ ...cfg, uac_password: e.target.value })} placeholder={hasExisting ? "已保存，留空不更新" : "请输入密码"} /></div>
        </div>
        <label>ALM 接口地址（ALM_BASE_URL）</label>
        <input value={cfg.alm_base_url} onChange={e => setCfg({ ...cfg, alm_base_url: e.target.value })} />
        <p style={{fontSize:12,color:"var(--text3)",margin:"8px 0 0 0",lineHeight:1.6}}>
          💡 <strong>ALM_SPACE_BID 和 ALM_APP_BID</strong> 已改为按版本配置。请在左侧版本列表中，点击对应版本的 ⚙️ 按钮设置该版本的 BID。
        </p>
        <div className="modalActions">
          <button className="secondaryBtn" onClick={onClose}>取消</button>
          <button className="primaryBtn" onClick={handleSave}>💾 保存</button>
        </div>
      </div>
    </div>
  );
}