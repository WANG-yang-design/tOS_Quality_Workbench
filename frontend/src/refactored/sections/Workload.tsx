import React, { useEffect, useState, useCallback, useRef } from "react";
import { API_BASE } from "../constants";

// ═══════════════════════════════════════════════════════════
// 工时情况 - 全新实现
// ═══════════════════════════════════════════════════════════

type WorkHourRow = {
  name: string;
  test_hours: number;
  regression_hours: number;
  other_hours: number;
  total_hours: number;
  week?: string;
  remark?: string;
};

type WorkHoursData = {
  data: WorkHourRow[];
  ai_analysis: string;
  imported_at: string | null;
  analyzed_at: string | null;
};

export function WorkloadSection({ activeVersion }: any) {
  const [workData, setWorkData] = useState<WorkHoursData | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // 加载工时数据
  const loadData = useCallback(async () => {
    if (!activeVersion?.id) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/work-hours`);
      const data = await res.json();
      setWorkData(data);
    } catch (e) {
      console.error("加载工时数据失败", e);
    } finally {
      setLoading(false);
    }
  }, [activeVersion?.id]);

  useEffect(() => { loadData(); }, [loadData]);

  // 处理文件上传
  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportError("");

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setImportText(text);
    };
    reader.readAsText(file);
  }

  // 解析 CSV / TSV 文本为标准化 JSON
  function parseTextToRows(text: string): WorkHourRow[] {
    const lines = text.trim().split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) return [];

    // 自动检测分隔符
    const header = lines[0];
    const delimiter = header.includes("\t") ? "\t" : ",";

    const rows: WorkHourRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(delimiter).map(c => c.trim().replace(/^["']|["']$/g, ""));
      if (cols.length < 2) continue;

      const name = cols[0] || "";
      const test_hours = parseFloat(cols[1]) || 0;
      const regression_hours = parseFloat(cols[2]) || 0;
      const other_hours = parseFloat(cols[3]) || 0;
      const total = parseFloat(cols[4]) || (test_hours + regression_hours + other_hours);

      rows.push({
        name,
        test_hours,
        regression_hours,
        other_hours,
        total_hours: total,
        week: cols[5] || "",
        remark: cols[6] || "",
      });
    }
    return rows;
  }

  // 导入工时数据
  async function handleImport() {
    if (!activeVersion?.id || !importText.trim()) return;
    setImporting(true);
    setImportError("");

    try {
      // 尝试直接 JSON 解析
      let rows: WorkHourRow[];
      const trimmed = importText.trim();
      if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
        const parsed = JSON.parse(trimmed);
        rows = Array.isArray(parsed) ? parsed : [parsed];
      } else {
        // CSV / TSV 解析
        rows = parseTextToRows(trimmed);
      }

      if (rows.length === 0) {
        setImportError("未能解析出有效数据，请检查格式");
        setImporting(false);
        return;
      }

      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/work-hours/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: rows }),
      });

      if (res.ok) {
        setShowImport(false);
        setImportText("");
        loadData();
      } else {
        const err = await res.json();
        setImportError(err.detail || "导入失败");
      }
    } catch (e: any) {
      setImportError("数据格式错误：" + (e.message || "请检查 JSON 或 CSV 格式"));
    } finally {
      setImporting(false);
    }
  }

  // 触发 AI 分析
  async function runAiAnalysis() {
    if (!activeVersion?.id) return;
    setAiLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/versions/${activeVersion.id}/work-hours/ai-analysis`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.analysis) {
        loadData(); // 重新加载以获取缓存结果
      }
    } catch (e) {
      console.error("AI 分析失败", e);
    } finally {
      setAiLoading(false);
    }
  }

  const rows = workData?.data || [];
  const hasData = rows.length > 0;

  // 统计
  const totalTest = rows.reduce((s, r) => s + (r.test_hours || 0), 0);
  const totalRegression = rows.reduce((s, r) => s + (r.regression_hours || 0), 0);
  const totalOther = rows.reduce((s, r) => s + (r.other_hours || 0), 0);
  const totalAll = rows.reduce((s, r) => s + (r.total_hours || 0), 0);

  return (
    <div className="reportSection">
      {/* 头部操作栏 */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16, padding: "0 4px",
      }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>
          ⏱️ 工时情况
          {workData?.imported_at && (
            <span style={{ fontSize: 11, color: "var(--text3)", fontWeight: 400, marginLeft: 8 }}>
              最近导入：{formatTime(workData.imported_at)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="secondaryBtn" style={{ fontSize: 12 }} onClick={() => setShowImport(!showImport)}>
            📥 导入工时
          </button>
        </div>
      </div>

      {/* 导入面板 */}
      {showImport && (
        <div className="card" style={{ marginBottom: 16, padding: 20, border: "2px dashed var(--card-border)" }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: "var(--text)" }}>
            📥 导入工时数据
          </div>
          <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 12, lineHeight: 1.6 }}>
            支持以下格式：<br />
            1. <b>JSON 数组</b>：[{`{name, test_hours, regression_hours, other_hours}`} ]<br />
            2. <b>CSV / TSV</b>：人员, 测试工时, 回归工时, 其他工时, 合计, 周次, 备注<br />
            3. 可直接从 Excel 复制粘贴表格内容
          </div>
          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            <button className="smallBtn" onClick={() => fileRef.current?.click()}>选择文件</button>
            <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,.json" style={{ display: "none" }} onChange={handleFileUpload} />
          </div>
          <textarea
            value={importText}
            onChange={e => setImportText(e.target.value)}
            placeholder={'粘贴表格内容或 JSON 数据，例如：\n人员, 测试工时, 回归工时, 其他工时\n张三, 40, 10, 5\n李四, 35, 15, 8'}
            style={{
              width: "100%", minHeight: 120, padding: 10, borderRadius: 8,
              border: "1px solid var(--card-border)", fontSize: 13, fontFamily: "monospace",
              resize: "vertical", background: "var(--surface)", color: "var(--text)",
            }}
          />
          {importError && (
            <div style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>⚠ {importError}</div>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button className="primaryBtn" onClick={handleImport} disabled={importing || !importText.trim()}>
              {importing ? "⏳ 导入中..." : "确认导入"}
            </button>
            <button className="secondaryBtn" onClick={() => { setShowImport(false); setImportText(""); setImportError(""); }}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* 统计卡片 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <WorkStatCard label="总工时" value={`${totalAll}h`} subtitle="全部投入" color="var(--accent)" />
        <WorkStatCard label="测试工时" value={`${totalTest}h`} subtitle={totalAll > 0 ? `${Math.round(totalTest / totalAll * 100)}%` : "0%"} color="var(--ok)" />
        <WorkStatCard label="回归工时" value={`${totalRegression}h`} subtitle={totalAll > 0 ? `${Math.round(totalRegression / totalAll * 100)}%` : "0%"} color="var(--warn)" />
        <WorkStatCard label="其他工时" value={`${totalOther}h`} subtitle={totalAll > 0 ? `${Math.round(totalOther / totalAll * 100)}%` : "0%"} color="#8b5cf6" />
      </div>

      {/* 工时表格 */}
      {loading ? (
        <div className="card" style={{ textAlign: "center", padding: 32 }}>
          <div className="dataLoadingSpinner" style={{ margin: "0 auto 12px" }} />
          <div style={{ color: "var(--text3)", fontSize: 13 }}>加载中...</div>
        </div>
      ) : hasData ? (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="dataTable" style={{ margin: 0 }}>
            <thead>
              <tr>
                <th style={{ width: 50, textAlign: "center" }}>序号</th>
                <th>人员</th>
                <th style={{ width: 100, textAlign: "center" }}>测试工时</th>
                <th style={{ width: 100, textAlign: "center" }}>回归工时</th>
                <th style={{ width: 100, textAlign: "center" }}>其他工时</th>
                <th style={{ width: 100, textAlign: "center" }}>合计</th>
                {rows.some(r => r.week) && <th style={{ width: 80, textAlign: "center" }}>周次</th>}
                {rows.some(r => r.remark) && <th>备注</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx}>
                  <td style={{ textAlign: "center", color: "var(--text3)", fontSize: 13 }}>{idx + 1}</td>
                  <td style={{ fontWeight: 500 }}>{row.name}</td>
                  <td style={{ textAlign: "center" }}>{row.test_hours}h</td>
                  <td style={{ textAlign: "center" }}>{row.regression_hours}h</td>
                  <td style={{ textAlign: "center" }}>{row.other_hours}h</td>
                  <td style={{ textAlign: "center", fontWeight: 600 }}>{row.total_hours}h</td>
                  {rows.some(r => r.week) && <td style={{ textAlign: "center", fontSize: 12, color: "var(--text3)" }}>{row.week || "-"}</td>}
                  {rows.some(r => r.remark) && <td style={{ fontSize: 12, color: "var(--text3)" }}>{row.remark || "-"}</td>}
                </tr>
              ))}
              {/* 合计行 */}
              <tr style={{ background: "var(--surface)", fontWeight: 600 }}>
                <td></td>
                <td>合计</td>
                <td style={{ textAlign: "center" }}>{totalTest}h</td>
                <td style={{ textAlign: "center" }}>{totalRegression}h</td>
                <td style={{ textAlign: "center" }}>{totalOther}h</td>
                <td style={{ textAlign: "center" }}>{totalAll}h</td>
                {rows.some(r => r.week) && <td></td>}
                {rows.some(r => r.remark) && <td></td>}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text2)", marginBottom: 8 }}>
            暂无工时数据
          </div>
          <div style={{ fontSize: 13, color: "var(--text3)", marginBottom: 16 }}>
            点击「导入工时」按钮，导入 Excel 或 JSON 格式的工时数据
          </div>
          <button className="primaryBtn" onClick={() => setShowImport(true)}>📥 导入工时数据</button>
        </div>
      )}

      {/* 工时分布占比图 */}
      {hasData && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: "var(--text)" }}>
            📈 工时分布
          </div>
          <div style={{ display: "flex", gap: 6, height: 12, borderRadius: 6, overflow: "hidden", background: "var(--surface)" }}>
            {totalAll > 0 && (
              <>
                <div style={{ width: `${totalTest / totalAll * 100}%`, background: "var(--ok)", transition: "width .3s" }} title={`测试 ${Math.round(totalTest / totalAll * 100)}%`} />
                <div style={{ width: `${totalRegression / totalAll * 100}%`, background: "var(--warn)", transition: "width .3s" }} title={`回归 ${Math.round(totalRegression / totalAll * 100)}%`} />
                <div style={{ width: `${totalOther / totalAll * 100}%`, background: "#8b5cf6", transition: "width .3s" }} title={`其他 ${Math.round(totalOther / totalAll * 100)}%`} />
              </>
            )}
          </div>
          <div style={{ display: "flex", gap: 20, marginTop: 10, fontSize: 12, color: "var(--text2)" }}>
            <span><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "var(--ok)", marginRight: 4 }} />测试 {totalAll > 0 ? Math.round(totalTest / totalAll * 100) : 0}%</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "var(--warn)", marginRight: 4 }} />回归 {totalAll > 0 ? Math.round(totalRegression / totalAll * 100) : 0}%</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "#8b5cf6", marginRight: 4 }} />其他 {totalAll > 0 ? Math.round(totalOther / totalAll * 100) : 0}%</span>
          </div>
        </div>
      )}

    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════

function WorkStatCard({ label, value, subtitle, color }: {
  label: string; value: string; subtitle: string; color: string;
}) {
  return (
    <div style={{
      background: "var(--card)",
      borderRadius: 12,
      padding: "16px 18px",
      border: "1px solid var(--card-border)",
    }}>
      <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{subtitle}</div>
    </div>
  );
}

function formatTime(isoStr: string): string {
  if (!isoStr) return "-";
  try {
    const d = new Date(isoStr);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${mm}.${dd} ${hh}:${mi}`;
  } catch {
    return isoStr;
  }
}