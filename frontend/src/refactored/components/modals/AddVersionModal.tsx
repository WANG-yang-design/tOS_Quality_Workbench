import React, { useState } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5818行原样提取
export function AddVersionModal({ onClose, onSuccess }: any) {
  const [form, setForm] = useState({ version_name: "", jira_project: "TOS", jira_fix_version: "", owner_name: "", is_train_version: false, is_pad: false, alm_space_bid: "", alm_app_bid: "" });
  const [showBidHelp, setShowBidHelp] = useState(false);
  async function submit() {
    if (!form.version_name) { alert("请输入版本名称"); return; }
    const res = await fetch(API_BASE + "/api/versions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, jira_fix_version: form.jira_fix_version || form.version_name }) });
    const data = await res.json();
    if (!res.ok) { alert(data.detail || "创建失败"); return; }
    onSuccess();
  }
  return (
    <div className="modalMask"><div className="modal" style={{maxHeight:"85vh",overflowY:"auto"}}>
      <h2>新增系统版本</h2>
      <label>版本名称</label><input placeholder="例如 tOS17.1" value={form.version_name} onChange={e => setForm({ ...form, version_name: e.target.value })} />
      <label>Jira项目</label><input value={form.jira_project} onChange={e => setForm({ ...form, jira_project: e.target.value })} />
      <label>Jira版本字段</label><input placeholder="默认与版本名称一致" value={form.jira_fix_version} onChange={e => setForm({ ...form, jira_fix_version: e.target.value })} />
      <label>负责人</label><input placeholder="例如 张三" value={form.owner_name} onChange={e => setForm({ ...form, owner_name: e.target.value })} />
      <label className="checkLine"><input type="checkbox" checked={form.is_train_version} onChange={e => setForm({ ...form, is_train_version: e.target.checked })} />这是 1+N 版本火车类项目</label>
      <label className="checkLine"><input type="checkbox" checked={form.is_pad} onChange={e => setForm({ ...form, is_pad: e.target.checked })} />PAD 版本 <span style={{fontSize:11,color:"var(--text3)"}}>（Jira 限制 summary 包含 PAD）</span></label>
      <div style={{borderTop:"1px solid var(--border)",margin:"12px 0",paddingTop:12}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:4}}>
          <label style={{margin:0}}>ALM 版本空间（可选，后续可补填）</label>
          <button className="smallBtn" style={{fontSize:11,padding:"2px 8px"}} onClick={() => setShowBidHelp(!showBidHelp)}>{showBidHelp ? "收起帮助" : "❓ 如何获取？"}</button>
        </div>
        {showBidHelp && (
          <div style={{fontSize:12,color:"var(--text2)",background:"var(--bg2)",padding:"8px 10px",borderRadius:6,marginBottom:8,lineHeight:1.8}}>
            <strong>获取步骤：</strong><br/>
            1. 打开 <a href="https://alm.transsion.com" target="_blank" rel="noreferrer">ALM 平台</a><br/>
            2. 进入对应版本的 SR 列表页面<br/>
            3. 查看浏览器地址栏 URL，格式为：<br/>
            <code style={{background:"var(--bg3)",padding:"2px 4px",borderRadius:3}}>.../apm/space/<strong style={{color:"#dc2626"}}>{'{spaceBid}'}</strong>/app/<strong style={{color:"#dc2626"}}>{'{appBid}'}</strong>/...</code><br/>
            4. 将 URL 中的两段数字分别填入下方
          </div>
        )}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
          <div><label style={{fontSize:12}}>SPACE_BID</label><input value={form.alm_space_bid} onChange={e => setForm({ ...form, alm_space_bid: e.target.value })} placeholder="如 1387390492731400192" /></div>
          <div><label style={{fontSize:12}}>APP_BID</label><input value={form.alm_app_bid} onChange={e => setForm({ ...form, alm_app_bid: e.target.value })} placeholder="如 1387390756582481922" /></div>
        </div>
      </div>
      <div className="modalActions"><button className="secondaryBtn" onClick={onClose}>取消</button><button className="primaryBtn" onClick={submit}>保存</button></div>
    </div></div>
  );
}