import React, { useState, useEffect, useCallback, useMemo } from "react";
import { API_BASE } from "../../constants";

export function SrTestProgress({ activeVersion, lockedSrData }: { activeVersion: any; lockedSrData: any }) {
  const [utpData, setUtpData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async (force = false) => {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const url = `${API_BASE}/api/versions/${activeVersion.id}/sr-test-progress${force ? "?force=true" : ""}`;
      const res = await fetch(url);
      if (res.ok) setUtpData(await res.json());
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [activeVersion?.id]);

  useEffect(() => { load(); }, [load]);

  // "测试中"的 SR 列表（从 ALM 加锁 SR 中过滤 life_cycle_name === "测试"）
  const testingSRs = useMemo(() => {
    if (!lockedSrData?.sr_list) return [];
    return lockedSrData.sr_list.filter((sr: any) => {
      const name = (sr.life_cycle_name || "").trim();
      const code = (sr.life_cycle_code || "").toUpperCase();
      return name === "测试" || code === "TESTING";
    });
  }, [lockedSrData]);

  // 匹配 UTP 进度
  const matchedList = useMemo(() => {
    const utpMap: Record<string, number> = {};
    (utpData?.sr_list || []).forEach((s: any) => {
      if (s.sr_coding) utpMap[s.sr_coding] = s.max_progress;
    });
    return testingSRs.map((sr: any) => {
      const coding = sr.sr_coding || sr.coding || "";
      return {
        sr_coding: coding,
        sr_name: sr.sr_name || sr.name || "",
        progress: utpMap[coding] ?? null,
      };
    });
  }, [testingSRs, utpData]);

  const total = matchedList.length;
  const withProgress = matchedList.filter((s: any) => s.progress !== null);
  const completed = withProgress.filter((s: any) => s.progress >= 100).length;
  const inProgress = withProgress.filter((s: any) => s.progress !== null && s.progress < 100).length;
  const noData = total - withProgress.length;
  const avgProgress = withProgress.length > 0
    ? Math.round(withProgress.reduce((sum: number, s: any) => sum + (s.progress || 0), 0) / withProgress.length)
    : 0;

  if (!activeVersion) return null;

  const displayList = showAll ? matchedList : matchedList.slice(0, 10);
  const srLoaded = !!lockedSrData?.sr_list;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>🧪 SR 测试进度（UTP）</span>
          {srLoaded ? (
            <span style={{ fontSize: 12, color: "var(--text3)" }}>
              暂定demo
            </span>
          ) : (
            <span style={{ fontSize: 12, color: "var(--text3)" }}>需先加载 SR 数据</span>
          )}
        </div>
        <button className="smallBtn" style={{ fontSize: 11, padding: "3px 10px" }} onClick={() => load(true)} disabled={loading}>
          {loading ? "刷新中..." : "🔄"}
        </button>
      </div>

      {!srLoaded ? (
        <div style={{ textAlign: "center", padding: 24, color: "var(--text3)", fontSize: 13 }}>
          请先在上方「📊 SR 数量展示」中加载 ALM 加锁 SR 数据
        </div>
      ) : total === 0 ? (
        <div style={{ textAlign: "center", padding: 24, color: "var(--text3)", fontSize: 13 }}>
          暂无测试中的 SR（ALM 中无 TESTING 状态的 SR）
        </div>
      ) : (
        <>
          {/* 统计卡片 */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
            <MiniStat label="测试中 SR" value={total} color="var(--accent)" />
            <MiniStat label="有进度" value={withProgress.length} color="var(--ok)" />
            <MiniStat label="无数据" value={noData} color="var(--text3)" />
            <MiniStat label="平均进度" value={avgProgress + "%"} color="var(--accent)" />
          </div>

          {/* SR 列表 */}
          <div style={{ overflowX: "auto" }}>
            <table className="dataTable" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ width: 40, textAlign: "center" }}>#</th>
                  <th>SR 编号</th>
                  <th>SR 名称</th>
                  <th style={{ width: 90, textAlign: "center" }}>测试进度</th>
                </tr>
              </thead>
              <tbody>
                {displayList.map((sr: any, idx: number) => (
                  <tr key={sr.sr_coding || idx}>
                    <td style={{ textAlign: "center", color: "var(--text3)" }}>{idx + 1}</td>
                    <td><strong>{sr.sr_coding}</strong></td>
                    <td style={{ maxWidth: 350, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sr.sr_name || "-"}</td>
                    <td style={{ textAlign: "center" }}>
                      {sr.progress !== null ? <ProgressBadge value={sr.progress} /> : <span style={{ fontSize: 11, color: "var(--text3)" }}>无数据</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {total > 10 && (
            <div style={{ textAlign: "center", marginTop: 10 }}>
              <button className="smallBtn" style={{ fontSize: 12 }} onClick={() => setShowAll(true)}>
                查看全部 {total} 个 SR →
              </button>
            </div>
          )}

          {/* 提示 */}
          <div style={{ marginTop: 10, fontSize: 11, color: "var(--text3)", lineHeight: 1.6 }}>
            💡 以上仅为 UTP 第一轮测试进度，后续轮次进度暂无法自动获取。无数据的 SR 表示 UTP 中未匹配到对应测试计划。
          </div>

          {/* 查看全部弹窗 */}
          {showAll && (
            <div className="modalMask" onClick={() => setShowAll(false)}>
              <div className="modal modalWide" style={{ maxWidth: 800, maxHeight: "80vh" }} onClick={e => e.stopPropagation()}>
                <h2>🧪 测试中 SR 进度（共 {total} 个）</h2>
                <div className="modalScrollBody">
                  <table className="dataTable" style={{ fontSize: 12 }}>
                    <thead><tr><th style={{ width: 40, textAlign: "center" }}>#</th><th>SR 编号</th><th>SR 名称</th><th style={{ width: 90, textAlign: "center" }}>测试进度</th></tr></thead>
                    <tbody>
                      {matchedList.map((sr: any, idx: number) => (
                        <tr key={sr.sr_coding || idx}>
                          <td style={{ textAlign: "center", color: "var(--text3)" }}>{idx + 1}</td>
                          <td><strong>{sr.sr_coding}</strong></td>
                          <td>{sr.sr_name || "-"}</td>
                          <td style={{ textAlign: "center" }}>
                            {sr.progress !== null ? <ProgressBadge value={sr.progress} /> : <span style={{ fontSize: 11, color: "var(--text3)" }}>无数据</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="modalActions">
                  <button className="secondaryBtn" onClick={() => setShowAll(false)}>关闭</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: number | string; color: string }) {
  return <div style={{ background: "var(--surface)", borderRadius: 8, padding: "10px 12px", textAlign: "center", border: "1px solid var(--card-border)" }}><div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div><div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{label}</div></div>;
}

function ProgressBadge({ value }: { value: number }) {
  let bg = "var(--surface)", fg = "var(--text3)";
  if (value >= 100) { bg = "var(--ok-bg)"; fg = "var(--ok)"; }
  else if (value > 0) { bg = "var(--warn-bg)"; fg = "var(--warn)"; }
  return <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 6, background: bg, color: fg, fontSize: 12, fontWeight: 600 }}>{value}%</span>;
}