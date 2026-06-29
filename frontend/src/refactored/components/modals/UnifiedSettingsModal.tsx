import React, { useState, useEffect } from "react";
import { API_BASE } from "../../constants";

// 从 App.tsx 第5023行原样提取 - 统一设置弹窗
const SETTINGS_TABS = [
  { key: "jira",    icon: "🔑", label: "Jira" },
  { key: "alm",     icon: "📦", label: "ALM" },
  { key: "ai",      icon: "🤖", label: "AI 分析" },
  { key: "feishu",  icon: "📎", label: "飞书" },
  { key: "refresh", icon: "🔄", label: "刷新" },
];

export function UnifiedSettingsModal({ version, defaultTab, onClose, onSaved }: any) {
  const [tab, setTab] = useState(defaultTab || "jira");

  return (
    <div className="modalMask">
      <div className="modal" style={{ width: 680, display: "flex", flexDirection: "column", maxHeight: "85vh" }}>
        <h2 style={{ marginBottom: 4 }}>⚙️ 设置</h2>
        <p className="modalDesc" style={{ marginBottom: 12 }}>各平台账号配置一次即可，版本参数按版本独立配置</p>
        <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--card-border)", marginBottom: 16 }}>
          {SETTINGS_TABS.map(t => (
            <button key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: "8px 16px", fontSize: 13, fontWeight: tab === t.key ? 600 : 400,
                background: "none", border: "none", borderBottom: tab === t.key ? "2px solid var(--accent)" : "2px solid transparent",
                color: tab === t.key ? "var(--accent)" : "var(--text3)", cursor: "pointer", transition: "all .2s",
              }}>{t.icon} {t.label}</button>
          ))}
        </div>
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {tab === "jira" && <SettingsTabJira version={version} onSaved={onSaved} />}
          {tab === "alm" && <SettingsTabALM version={version} onSaved={onSaved} />}
          {tab === "ai" && <SettingsTabAI onSaved={onSaved} />}
          {tab === "feishu" && <SettingsTabFeishu version={version} onSaved={onSaved} />}
          {tab === "refresh" && <SettingsTabRefresh version={version} onSaved={onSaved} />}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 12, borderTop: "1px solid var(--card-border)", marginTop: 12 }}>
          <button className="secondaryBtn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

function SettingsSection({ title, desc }: any) {
  return <div style={{ marginBottom: 12 }}><div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>{title}</div>{desc && <div style={{ fontSize: 12, color: "var(--text3)" }}>{desc}</div>}</div>;
}

function SettingsRow({ label, children }: any) {
  return <div style={{ marginBottom: 10 }}><label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 4 }}>{label}</label>{children}</div>;
}

function SaveBtn({ onClick, loading, text }: any) {
  return <button className="primaryBtn" onClick={onClick} disabled={loading} style={{ padding: "6px 16px", fontSize: 12 }}>{loading ? "保存中..." : (text || "💾 保存")}</button>;
}

function SettingsTabJira({ version, onSaved }: any) {
  const [gf, setGf] = useState({ jira_base_url: "http://jira.transsion.com", username: "", password: "" });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [vf, setVf] = useState({ jira_project: "", jira_fix_version: "" });
  const [vSaving, setVSaving] = useState(false);

  useEffect(() => {
    fetch(API_BASE + "/api/jira/global-credential").then(r => r.json()).then(d => {
      if (d.configured) setGf(prev => ({ ...prev, jira_base_url: d.jira_base_url || prev.jira_base_url, username: d.username || "" }));
    }).catch(() => {});
    if (version) setVf({ jira_project: version.jira_project || "", jira_fix_version: version.jira_fix_version || "" });
  }, [version]);

  async function save() {
    setSaving(true);
    const res = await fetch(API_BASE + "/api/jira/global-credential", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(gf),
    });
    setSaving(false);
    if (res.ok) { alert("Jira 账号已保存，所有版本通用"); onSaved(); } else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  async function testConnection() {
    setTesting(true); setTestResult(null);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + version.id + "/jira-test");
      setTestResult(await res.json());
    } catch (e: any) { setTestResult({ ok: false, error: e.message }); }
    finally { setTesting(false); }
  }

  async function saveVersion() {
    setVSaving(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + version.id, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(vf),
      });
      if (res.ok) { alert("版本 Jira 参数已保存"); onSaved(); } else { alert("保存失败"); }
    } catch { alert("保存失败"); }
    finally { setVSaving(false); }
  }

  return (
    <>
      <SettingsSection title="🔑 Jira 账号" desc="所有版本共用，仅需配置一次。支持密码或 API Token（推荐 Token，不会触发验证码锁定）。" />
      <SettingsRow label="Jira 地址"><input value={gf.jira_base_url} onChange={e => setGf({ ...gf, jira_base_url: e.target.value })} /></SettingsRow>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <SettingsRow label="账号"><input placeholder="如 yang.wang5" value={gf.username} onChange={e => setGf({ ...gf, username: e.target.value })} /></SettingsRow>
        <SettingsRow label="密码 / Token"><input type="password" placeholder="密码或 API Token" value={gf.password} onChange={e => setGf({ ...gf, password: e.target.value })} /></SettingsRow>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16 }}>
        <SaveBtn onClick={save} loading={saving} />
        <button className="smallBtn" onClick={testConnection} disabled={testing} style={{ padding: "5px 12px", fontSize: 12 }}>
          {testing ? "测试中..." : "🔍 测试连接"}
        </button>
      </div>
      {testResult && (
        <div style={{ fontSize: 12, padding: "8px 10px", borderRadius: 6, lineHeight: 1.8, marginBottom: 8,
          background: testResult.ok ? "#f0fdf4" : "#fef2f2",
          border: `1px solid ${testResult.ok ? "#86efac" : "#fca5a5"}`,
          color: testResult.ok ? "#166534" : "#991b1b" }}>
          {testResult.ok ? `✅ 连接成功！用户：${testResult.username}` : `❌ 连接失败：${testResult.error || testResult.message || "未知错误"}`}
        </div>
      )}
      <div style={{ borderTop: "1px solid var(--card-border)", paddingTop: 14, marginTop: 4 }}>
        <SettingsSection title={`📦 ${version?.version_name || ""} — Jira 参数`} desc="Jira 项目名和版本字段，按版本独立配置。" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <SettingsRow label="Jira 项目"><input placeholder="如 TOS" value={vf.jira_project} onChange={e => setVf({ ...vf, jira_project: e.target.value })} /></SettingsRow>
          <SettingsRow label="Fix Version"><input placeholder="如 tOS16.2" value={vf.jira_fix_version} onChange={e => setVf({ ...vf, jira_fix_version: e.target.value })} /></SettingsRow>
        </div>
        <SaveBtn onClick={saveVersion} loading={vSaving} text={`保存 ${version?.version_name || ""} 参数`} />
      </div>
    </>
  );
}

function SettingsTabALM({ version, onSaved }: any) {
  const [gf, setGf] = useState({ uac_gateway: "https://pfgatewaysz.transsion.com:9199", alm_app_id: "", uac_username: "", uac_password: "", uac_source: "ALM", alm_base_url: "https://pfgatewaysz.transsion.com:9199/alm-transcend-datadriven" });
  const [hasExisting, setHasExisting] = useState(false);
  const [gSaving, setGSaving] = useState(false);
  const [vf, setVf] = useState({ alm_space_bid: version?.alm_space_bid || "", alm_app_bid: version?.alm_app_bid || "" });
  const [vSaving, setVSaving] = useState(false);
  const [showBidHelp, setShowBidHelp] = useState(false);

  useEffect(() => {
    fetch(API_BASE + "/api/alm/config").then(r => r.json()).then(d => {
      if (d.alm_app_id) { setGf(prev => ({ ...prev, ...d, uac_password: "" })); setHasExisting(d.configured); }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    setVf({ alm_space_bid: version?.alm_space_bid || "", alm_app_bid: version?.alm_app_bid || "" });
  }, [version?.id]);

  async function saveGlobal() {
    if (!gf.alm_app_id || !gf.uac_username || !gf.uac_password) { alert("App ID、工号和密码不能为空"); return; }
    setGSaving(true);
    const res = await fetch(API_BASE + "/api/alm/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(gf) });
    setGSaving(false);
    if (res.ok) { alert("ALM 全局配置已保存"); onSaved(); } else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  async function saveVersion() {
    setVSaving(true);
    const res = await fetch(API_BASE + "/api/versions/" + version.id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(vf) });
    setVSaving(false);
    if (res.ok) { alert(`${version.version_name} ALM 空间已保存`); onSaved(); } else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  return (
    <>
      <SettingsSection title="📦 ALM 全局鉴权" desc="ALM 用户中心鉴权信息，所有版本共用。" />
      <SettingsRow label="用户中心网关（UAC_GATEWAY）"><input value={gf.uac_gateway} onChange={e => setGf({ ...gf, uac_gateway: e.target.value })} /></SettingsRow>
      <SettingsRow label="应用 ID（ALM_APP_ID）"><input value={gf.alm_app_id} onChange={e => setGf({ ...gf, alm_app_id: e.target.value })} placeholder="如 c_MjYwNjAxMDAxaA" /></SettingsRow>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <SettingsRow label="工号"><input placeholder="如 18665088" value={gf.uac_username} onChange={e => setGf({ ...gf, uac_username: e.target.value })} /></SettingsRow>
        <SettingsRow label="密码"><input type="password" placeholder={hasExisting ? "已保存，留空不更新" : "请输入"} value={gf.uac_password} onChange={e => setGf({ ...gf, uac_password: e.target.value })} /></SettingsRow>
        <SettingsRow label="来源"><input value={gf.uac_source} onChange={e => setGf({ ...gf, uac_source: e.target.value })} /></SettingsRow>
      </div>
      <SettingsRow label="ALM 接口地址"><input value={gf.alm_base_url} onChange={e => setGf({ ...gf, alm_base_url: e.target.value })} /></SettingsRow>
      <div style={{ marginBottom: 20 }}><SaveBtn onClick={saveGlobal} loading={gSaving} /></div>

      <div style={{ borderTop: "1px solid var(--card-border)", paddingTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 2 }}>
          <SettingsSection title={`📦 ${version?.version_name || ""} — ALM 空间`} desc="每个版本在 ALM 中有独立 Space，用于区分当前版本 SR。" />
          <button className="smallBtn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => setShowBidHelp(!showBidHelp)}>{showBidHelp ? "收起" : "❓ 如何获取？"}</button>
        </div>
        {showBidHelp && (
          <div style={{ fontSize: 12, color: "var(--text2)", background: "var(--bg2)", padding: "8px 10px", borderRadius: 6, marginBottom: 8, lineHeight: 1.8 }}>
            <strong>获取步骤：</strong><br />
            1. 打开 <a href="https://alm.transsion.com" target="_blank" rel="noreferrer">ALM 平台</a><br />
            2. 进入「{version?.version_name}」的 SR 列表页面<br />
            3. 地址栏 URL 格式：<code style={{ background: "var(--bg3)", padding: "2px 4px", borderRadius: 3 }}>.../apm/space/<strong style={{ color: "#dc2626" }}>{'{spaceBid}'}</strong>/app/<strong style={{ color: "#dc2626" }}>{'{appBid}'}</strong>/...</code><br />
            4. 将两段数字填入下方
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <SettingsRow label="SPACE_BID"><input placeholder="如 1408550301319528448" value={vf.alm_space_bid} onChange={e => setVf({ ...vf, alm_space_bid: e.target.value })} /></SettingsRow>
          <SettingsRow label="APP_BID"><input placeholder="如 1408550513287069698" value={vf.alm_app_bid} onChange={e => setVf({ ...vf, alm_app_bid: e.target.value })} /></SettingsRow>
        </div>
        {(!vf.alm_space_bid || !vf.alm_app_bid) && (
          <p style={{ fontSize: 12, color: "#d97706", margin: "4px 0 8px", padding: "5px 10px", background: "#fffbeb", borderRadius: 4, border: "1px solid #fde68a" }}>⚠ 未配置 BID 时 SR 需求详情将无法查询 ALM 数据</p>
        )}
        <SaveBtn onClick={saveVersion} loading={vSaving} text={`保存 ${version?.version_name || ""} 空间`} />
      </div>
    </>
  );
}

function SettingsTabAI({ onSaved }: any) {
  const ALL_MODELS = ["gpt-5.2-chat", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-3-5-sonnet"];
  const [cfg, setCfg] = useState({ api_base: "https://hk-intra-paas.transsion.com/tranai-proxy/v1", api_key: "", model: "gpt-5.2-chat", user_no: "", user_name: "", user_dept: "", sr_ai_prompt: "" });
  const [saving, setSaving] = useState(false);
  const [masked, setMasked] = useState("");

  useEffect(() => {
    fetch(API_BASE + "/api/ai/config").then(r => r.json()).then(d => {
      if (d.api_base) { setCfg(prev => ({ ...prev, ...d, api_key: "" })); setMasked(d.api_key_masked || ""); }
    }).catch(() => {});
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      const payload: any = { ...cfg };
      if (!payload.api_key) delete payload.api_key;
      const res = await fetch(API_BASE + "/api/ai/config", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (res.ok) { alert("AI 配置已保存"); onSaved(); } else { alert("保存失败"); }
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  return (
    <div>
      <SettingsSection title="🤖 AI 分析设置" desc="配置 TranAI 代理地址、API Key 及用户信息" />
      <SettingsRow label="API 地址"><input value={cfg.api_base} onChange={e => setCfg({ ...cfg, api_base: e.target.value })} /></SettingsRow>
      <SettingsRow label={`API Key ${masked ? "（当前：" + masked + "）" : ""}`}><input type="password" value={cfg.api_key} onChange={e => setCfg({ ...cfg, api_key: e.target.value })} placeholder="留空则不更新" /></SettingsRow>
      <SettingsRow label="模型">
        <select value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })}
          style={{width:"100%",padding:"10px 12px",borderRadius:8,border:"1px solid var(--card-border)",background:"var(--surface)",color:"var(--text)",fontSize:14}}>
          {ALL_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </SettingsRow>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8}}>
        <SettingsRow label="工号"><input value={cfg.user_no} onChange={e => setCfg({ ...cfg, user_no: e.target.value })} placeholder="如 186xxxxx" /></SettingsRow>
        <SettingsRow label="姓名"><input value={cfg.user_name} onChange={e => setCfg({ ...cfg, user_name: e.target.value })} placeholder="如 陈xx" /></SettingsRow>
        <SettingsRow label="部门"><input value={cfg.user_dept} onChange={e => setCfg({ ...cfg, user_dept: e.target.value })} placeholder="AI创新部" /></SettingsRow>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <SaveBtn onClick={handleSave} loading={saving} />
      </div>
    </div>
  );
}

function SettingsTabFeishu({ version, onSaved }: any) {
  const [ff, setFf] = useState({ app_id: "", app_secret: "" });
  const [fSaving, setFSaving] = useState(false);
  const [sheetUrl, setSheetUrl] = useState(version?.feishu_sheet_url || "");
  const [perfUrl, setPerfUrl] = useState(version?.perf_sheet_url || "");
  const [batteryUrl, setBatteryUrl] = useState(version?.battery_sheet_url || "");
  const [uSaving, setUSaving] = useState(false);
  const [feishuLoggedIn, setFeishuLoggedIn] = useState(false);

  useEffect(() => {
    fetch(API_BASE + "/api/feishu/config").then(r => r.json()).then(d => {
      if (d.app_id) setFf(prev => ({ ...prev, app_id: d.app_id }));
    }).catch(() => {});
    fetch(API_BASE + "/api/feishu/token-status").then(r => r.json()).then(d => {
      setFeishuLoggedIn(!!d.logged_in);
    }).catch(() => setFeishuLoggedIn(false));
  }, []);

  useEffect(() => {
    setSheetUrl(version?.feishu_sheet_url || "");
    setPerfUrl(version?.perf_sheet_url || "");
    setBatteryUrl(version?.battery_sheet_url || "");
  }, [version?.id, version?.feishu_sheet_url, version?.perf_sheet_url, version?.battery_sheet_url]);

  async function saveFeishu() {
    if (!ff.app_id || !ff.app_secret) { alert("App ID 和 App Secret 不能为空"); return; }
    setFSaving(true);
    const res = await fetch(API_BASE + "/api/feishu/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ff) });
    setFSaving(false);
    if (res.ok) { alert("飞书应用配置已保存"); onSaved?.(); } else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  async function saveSheetUrls() {
    setUSaving(true);
    const res = await fetch(API_BASE + "/api/versions/" + version.id, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feishu_sheet_url: sheetUrl, perf_sheet_url: perfUrl, battery_sheet_url: batteryUrl }),
    });
    setUSaving(false);
    if (res.ok) { alert(`${version.version_name} 飞书表格地址已保存`); onSaved?.(); } else { const d = await res.json(); alert(d.detail || "保存失败"); }
  }

  function handleFeishuLogin() {
    const loginWin = window.open(API_BASE + "/api/feishu/login", "feishu_oauth", "width=600,height=700,scrollbars=yes");
    const poll = setInterval(() => {
      if (!loginWin || loginWin.closed) {
        clearInterval(poll);
        fetch(API_BASE + "/api/feishu/token-status").then(r => r.json()).then(d => setFeishuLoggedIn(!!d.logged_in)).catch(() => {});
      }
    }, 1000);
  }

  return (
    <>
      <SettingsSection title="📎 飞书应用配置" desc="用于从飞书管理书导入 STR 时间表、读取性能/续航数据等。" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <SettingsRow label="App ID"><input value={ff.app_id} onChange={e => setFf({ ...ff, app_id: e.target.value })} placeholder="飞书应用 App ID" /></SettingsRow>
        <SettingsRow label="App Secret"><input type="password" value={ff.app_secret} onChange={e => setFf({ ...ff, app_secret: e.target.value })} placeholder="飞书应用 App Secret" /></SettingsRow>
      </div>
      <div style={{ marginBottom: 16 }}><SaveBtn onClick={saveFeishu} loading={fSaving} /></div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: feishuLoggedIn ? "#ecfdf5" : "#fef3c7", borderRadius: 10, border: "1px solid " + (feishuLoggedIn ? "#a7f3d0" : "#fde68a"), marginBottom: 16 }}>
        <span style={{ fontSize: 14 }}>{feishuLoggedIn ? "✅" : "⚠️"}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: feishuLoggedIn ? "#065f46" : "#92400e" }}>{feishuLoggedIn ? "飞书已授权" : "飞书未授权 — 请先登录"}</span>
        <button className={feishuLoggedIn ? "secondaryBtn" : "primaryBtn"} onClick={handleFeishuLogin} style={{ marginLeft: "auto", padding: "5px 14px", fontSize: 12 }}>{feishuLoggedIn ? "重新授权" : "🔑 飞书登录"}</button>
      </div>

      <div style={{ borderTop: "1px solid var(--card-border)", paddingTop: 16 }}>
        <SettingsSection title={`📎 ${version?.version_name || ""} — 飞书表格配置`} desc="配置该版本关联的各类飞书表格地址。管理书用于导入STR时间和机型信息；性能表和续航表用于读取专项测试数据。" />
        <SettingsRow label="📄 测试管理书 URL"><input value={sheetUrl} onChange={e => setSheetUrl(e.target.value)} placeholder="https://transsioner.feishu.cn/wiki/..." /></SettingsRow>
        <div style={{ fontSize: 12, color: "var(--text3)", marginTop: "-6px", marginBottom: 12 }}>用于导入 STR 时间表、读取机型信息</div>
        <SettingsRow label="⚡ 性能体验表 URL"><input value={perfUrl} onChange={e => setPerfUrl(e.target.value)} placeholder="https://transsioner.feishu.cn/wiki/..." /></SettingsRow>
        <div style={{ fontSize: 12, color: "var(--text3)", marginTop: "-6px", marginBottom: 12 }}>各项目性能体验目标-过程审计数据跟踪表</div>
        <SettingsRow label="🔋 续航体验表 URL"><input value={batteryUrl} onChange={e => setBatteryUrl(e.target.value)} placeholder="https://transsioner.feishu.cn/wiki/..." /></SettingsRow>
        <div style={{ fontSize: 12, color: "var(--text3)", marginTop: "-6px", marginBottom: 12 }}>续航温升体验数据表</div>
        <SaveBtn onClick={saveSheetUrls} loading={uSaving} text={`保存 ${version?.version_name || ""} 飞书表格配置`} />
      </div>
    </>
  );
}

function SettingsTabRefresh({ version, onSaved }: any) {
  const [cfg, setCfg] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);

  useEffect(() => {
    fetch(API_BASE + "/api/auto-refresh/config").then(r => r.json()).then(setCfg).catch(() => {});
    fetch(API_BASE + "/api/versions").then(r => r.json()).then(setVersions).catch(() => {});
  }, []);

  async function handleSave() {
    if (!cfg) return;
    setSaving(true);
    try {
      const res = await fetch(API_BASE + "/api/auto-refresh/config", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg),
      });
      if (res.ok) alert("刷新配置已保存");
      else alert("保存失败");
    } catch { alert("保存失败"); }
    finally { setSaving(false); }
  }

  if (!cfg) return <p style={{ textAlign: "center", padding: 20, color: "var(--text3)" }}>加载中...</p>;

  const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const selectedDays = (cfg.weekdays || "0,1,2,3,4").split(",").map((d: string) => parseInt(d.trim()));

  function toggleDay(day: number) {
    const newDays = selectedDays.includes(day) ? selectedDays.filter((d: number) => d !== day) : [...selectedDays, day].sort();
    setCfg({ ...cfg, weekdays: newDays.join(",") });
  }

  const selectedVersionIds = (cfg.version_ids || "").split(",").map((s: string) => parseInt(s.trim())).filter(Boolean);

  function toggleVersion(vid: number) {
    const newIds = selectedVersionIds.includes(vid) ? selectedVersionIds.filter((id: number) => id !== vid) : [...selectedVersionIds, vid];
    setCfg({ ...cfg, version_ids: newIds.join(",") });
  }

  return (
    <>
      <SettingsSection title="🔄 自动刷新设置" desc="配置全平台数据自动刷新的间隔、工作时间和目标版本。不含 SR 需求详情和 AI 分析。" />

      <SettingsRow label="启用自动刷新">
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
          <input type="checkbox" checked={!!cfg.enabled} onChange={e => setCfg({ ...cfg, enabled: e.target.checked ? 1 : 0 })} />
          <span style={{ fontSize: 13 }}>{cfg.enabled ? "已启用" : "已关闭"}</span>
        </label>
      </SettingsRow>

      <SettingsRow label="刷新间隔（分钟）">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="number" min={5} max={240} value={cfg.interval_minutes} onChange={e => setCfg({ ...cfg, interval_minutes: parseInt(e.target.value) || 30 })} style={{ width: 100 }} />
          <span style={{ fontSize: 11, color: "var(--text3)" }}>范围 5-240 分钟</span>
        </div>
      </SettingsRow>

      <SettingsRow label="工作时间">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="time" value={cfg.work_start} onChange={e => setCfg({ ...cfg, work_start: e.target.value })} style={{ width: 100 }} />
          <span style={{ color: "var(--text3)" }}>至</span>
          <input type="time" value={cfg.work_end} onChange={e => setCfg({ ...cfg, work_end: e.target.value })} style={{ width: 100 }} />
        </div>
      </SettingsRow>

      <SettingsRow label="工作日">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {weekdays.map((name, idx) => (
            <button key={idx} onClick={() => toggleDay(idx)}
              style={{ padding: "4px 12px", borderRadius: 6, border: "1px solid " + (selectedDays.includes(idx) ? "var(--accent)" : "var(--card-border)"), background: selectedDays.includes(idx) ? "var(--accent-soft)" : "var(--surface)", color: selectedDays.includes(idx) ? "var(--accent)" : "var(--text3)", fontSize: 12, fontWeight: selectedDays.includes(idx) ? 600 : 400, cursor: "pointer", transition: "all .2s" }}>
              {name}
            </button>
          ))}
        </div>
      </SettingsRow>

      {versions.length > 0 && (
        <SettingsRow label="刷新版本">
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {versions.map((v: any) => (
              <button key={v.id} onClick={() => toggleVersion(v.id)}
                style={{ padding: "4px 12px", borderRadius: 6, border: "1px solid " + (selectedVersionIds.includes(v.id) ? "var(--accent)" : "var(--card-border)"), background: selectedVersionIds.includes(v.id) ? "var(--accent-soft)" : "var(--surface)", color: selectedVersionIds.includes(v.id) ? "var(--accent)" : "var(--text3)", fontSize: 12, fontWeight: selectedVersionIds.includes(v.id) ? 600 : 400, cursor: "pointer", transition: "all .2s" }}>
                {v.version_name}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4 }}>不选则刷新所有版本</div>
        </SettingsRow>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <SaveBtn onClick={handleSave} loading={saving} />
      </div>
    </>
  );
}