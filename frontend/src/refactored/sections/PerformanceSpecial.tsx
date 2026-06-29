import React, { useState, useEffect } from "react";
import { API_BASE } from "../constants";
import { DeviceTabSelector } from "../components/common/DeviceTabSelector";

// 从 App.tsx 第1105行原样提取 - 性能专项
export function PerformanceSpecialSection({ activeVersion }: any) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [activeDevice, setActiveDevice] = useState("");
  const [plans, setPlans] = useState<any[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [showPlanModal, setShowPlanModal] = useState(false);

  async function loadData() {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/performance");
      const json = await res.json();
      setData(json);
      const devices = json.devices || [];
      if (devices.length > 0) setActiveDevice(devices[0].device_name);
    } catch { setData({ error: "请求失败" }); }
    finally { setLoading(false); }
  }

  async function loadPlans() {
    if (!activeVersion?.id) return;
    setPlansLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/versions/" + activeVersion.id + "/test-plans/performance");
      const json = await res.json();
      setPlans(json.plans || []);
    } catch { /* ignore */ }
    finally { setPlansLoading(false); }
  }

  useEffect(() => { loadData(); loadPlans(); }, [activeVersion?.id]);

  const devices = data?.devices || [];
  const currentDevice = devices.find((d: any) => d.device_name === activeDevice);

  return (
    <div className="card">
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <div style={{fontSize:13,color:"var(--text2)"}}>数据来源：各项目性能体验目标-过程审计数据跟踪表（飞书）</div>
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <button className="smallBtn" onClick={() => setShowPlanModal(true)} style={{padding:"3px 10px",fontSize:11}}>📋 测试计划</button>
          <button className="smallBtn" onClick={loadData} disabled={loading} style={{padding:"3px 10px",fontSize:11}}>
            {loading ? "加载中..." : "🔄 刷新"}
          </button>
        </div>
      </div>
      {plans.length > 0 && (
        <div style={{marginBottom:14,padding:"10px 14px",background:"var(--bg2)",borderRadius:8,border:"1px dashed var(--card-border)"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
            <span style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>📋 测试计划（{plans.length} 项）</span>
            <button className="smallBtn" onClick={() => setShowPlanModal(true)} style={{padding:"2px 8px",fontSize:10}}>编辑</button>
          </div>
          <table className="dataTable" style={{margin:0,fontSize:12}}>
            <thead><tr><th>机型</th><th>测试内容</th><th>状态</th><th>计划时间</th><th>负责人</th><th>备注</th></tr></thead>
            <tbody>{plans.map((p: any) => (
              <tr key={p.device_name}>
                <td style={{fontWeight:600}}>{p.device_name}</td>
                <td style={{maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={p.test_items}>{p.test_items || "-"}</td>
                <td><span className={"badge " + (p.plan_status === "completed" ? "badgeGo" : p.plan_status === "in_progress" ? "badgeInfo" : "badgeWarn")}>{p.plan_status === "completed" ? "已完成" : p.plan_status === "in_progress" ? "进行中" : "计划中"}</span></td>
                <td style={{whiteSpace:"nowrap"}}>{p.plan_start_date && p.plan_end_date ? `${p.plan_start_date.slice(5)} ~ ${p.plan_end_date.slice(5)}` : p.plan_start_date || "-"}</td>
                <td>{p.responsible_person || "-"}</td>
                <td style={{maxWidth:120,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={p.remark}>{p.remark || "-"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {loading ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>正在从飞书读取性能数据...</p>
      ) : !data ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>点击刷新加载性能数据</p>
      ) : data.error ? (
        <p style={{color:"#dc2626",textAlign:"center",padding:24}}>⚠ {data.error}</p>
      ) : data.message ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>{data.message}</p>
      ) : devices.length === 0 && plans.length === 0 ? (
        <p style={{color:"var(--text3)",textAlign:"center",padding:24}}>未找到性能数据（请确认飞书表格中有机型命名的 Sheet，或点击「测试计划」添加计划）</p>
      ) : devices.length > 0 ? (
        <>
          <DeviceTabSelector devices={devices.map((d: any) => d.device_name)} activeDevice={activeDevice} onSelect={setActiveDevice} />
          {currentDevice && <DeviceTestResultCard device={currentDevice} />}
        </>
      ) : null}
    </div>
  );
}

// 通用：机型测试结果卡片（性能/续航共用）
function DeviceTestResultCard({ device, batteryMode }: any) {
  const goCount = device.go_count ?? 0;
  const grCount = device.gr_count ?? 0;
  const ngCount = device.ng_count ?? 0;
  const categories = device.categories || [];

  const trStyle = (v: string) => {
    const vl = (v || "").trim().toLowerCase();
    const isPass = vl === "pass" || vl === "通过" || vl === "ok";
    const isFail = vl === "fail" || vl === "不通过" || vl === "未通过" || vl === "ng";
    return {
      display: "inline-block" as const, padding: "2px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600,
      background: isPass ? "var(--ok-bg)" : isFail ? "var(--danger-bg)" : "transparent",
      border: "1px solid " + (isPass ? "var(--ok)" : isFail ? "var(--danger)" : "var(--card-border)"),
      color: isPass ? "var(--ok)" : isFail ? "var(--danger)" : "var(--text3)",
    };
  };

  return (
    <div className="subCard" style={{padding:"14px 18px"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom: categories.length > 0 ? 14 : 0}}>
        <span style={{fontSize:15,fontWeight:600,color:"var(--text)",display:"flex",alignItems:"center",gap:6,minWidth:0}}>
          <span style={{fontSize:18,flexShrink:0}}>📱</span>
          <span style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{device.device_name}</span>
          {device.sheet_url && <a href={device.sheet_url} target="_blank" rel="noreferrer" style={{fontSize:11,fontWeight:500,color:"var(--accent)",textDecoration:"none",padding:"1px 8px",borderRadius:4,background:"var(--accent-soft)",whiteSpace:"nowrap",flexShrink:0}} title="在飞书中打开此Sheet">📋 飞书</a>}
        </span>
        <div className="chipRow"><span className="chip chipGo">GO <strong>{goCount}</strong></span><span className="chip chipGr">GR <strong>{grCount}</strong></span><span className="chip chipNg">NG <strong>{ngCount}</strong></span></div>
      </div>
      {categories.length === 0 && !device.has_conclusion && (
        <p style={{fontSize:12,color:"var(--text3)",textAlign:"center",padding:"12px 0",margin:0}}>暂无评估结论数据</p>
      )}
      {categories.map((cat: any, ci: number) => (
        <CategorySection key={ci} cat={cat} trStyle={trStyle} />
      ))}
    </div>
  );
}

function CategorySection({ cat, trStyle }: any) {
  const [expanded, setExpanded] = useState(false);
  const hasIssues = cat.fail_items && cat.fail_items.length > 0;
  const borderColor = cat.ng > 0 ? "var(--danger)" : cat.gr > 0 ? "var(--warn)" : "var(--ok)";

  return (
    <div style={{marginBottom: 12, borderLeft: `3px solid ${borderColor}`, paddingLeft: 12, borderRadius: "0 8px 8px 0", background: hasIssues ? "var(--surface)" : "transparent", padding: hasIssues ? "8px 12px 8px 12px" : "4px 0 4px 12px"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",cursor: hasIssues ? "pointer" : "default"}} onClick={() => hasIssues && setExpanded(!expanded)}>
        <div style={{display:"flex",alignItems:"center",gap:6,minWidth:0}}>
          <span style={{fontSize:13,fontWeight:600,color:"var(--text)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={cat.name}>{cat.name || "未分类"}</span>
          {hasIssues && <span style={{fontSize:10,color:"var(--text3)",flexShrink:0,padding:"1px 6px",borderRadius:4,background:"rgba(0,0,0,0.04)"}}>{expanded ? "▲ 收起" : "▼ 展开"}</span>}
        </div>
        <div style={{display:"flex",gap:5,alignItems:"center",flexShrink:0,marginLeft:10}}>
          <span style={{fontSize:11,padding:"2px 8px",borderRadius:4,background: cat.go > 0 ? "var(--ok-bg)" : "var(--surface)",color: cat.go > 0 ? "var(--ok)" : "var(--text3)",fontWeight:700}}>GO {cat.go}</span>
          <span style={{fontSize:11,padding:"2px 8px",borderRadius:4,background: cat.gr > 0 ? "var(--warn-bg)" : "var(--surface)",color: cat.gr > 0 ? "var(--warn)" : "var(--text3)",fontWeight:700}}>GR {cat.gr}</span>
          <span style={{fontSize:11,padding:"2px 8px",borderRadius:4,background: cat.ng > 0 ? "var(--danger-bg)" : "var(--surface)",color: cat.ng > 0 ? "var(--danger)" : "var(--text3)",fontWeight:700}}>NG {cat.ng}</span>
        </div>
      </div>
      {expanded && hasIssues && (
        <div style={{marginTop:8,borderRadius:6,overflow:"hidden",border:"1px solid var(--card-border)"}}>
          <table className="dataTable catDetailTable" style={{margin:0,fontSize:12}}>
            <thead><tr><th>指标</th><th>优先级</th><th>测试结果</th><th>评估结论</th><th>FAIL 原因</th></tr></thead>
            <tbody>
              {cat.fail_items.map((item: any, idx: number) => (
                <tr key={idx}>
                  <td style={{whiteSpace:"normal",wordBreak:"break-word",lineHeight:1.5}}>{item.metric || <span style={{color:"var(--text3)"}}>-</span>}</td>
                  <td style={{textAlign:"center"}}><span className={"badge " + (item.priority === "P0" ? "badgeRisk" : item.priority === "P1" ? "badgeWarn" : "badgeInfo")}>{item.priority || "-"}</span></td>
                  <td style={{textAlign:"center"}}>{item.test_result ? <span style={trStyle(item.test_result)}>{item.test_result}</span> : <span style={{color:"var(--text3)",fontSize:11}}>-</span>}</td>
                  <td style={{textAlign:"center"}}><span className={"badge " + (item.conclusion === "NG" ? "badgeNg" : "badgeGr")}>{item.conclusion || "-"}</span></td>
                  <td style={{fontSize:12,lineHeight:1.6,whiteSpace:"normal",wordBreak:"break-word",color: item.fail_reason ? "var(--text2)" : "var(--text3)"}}>{item.fail_reason || <span style={{fontSize:11}}>-</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}