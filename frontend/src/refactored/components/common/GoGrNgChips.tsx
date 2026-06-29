import React from "react";

// 从 App.tsx 第598行原样提取
export function GoGrNgChips({ go, gr, ng }: any) {
  return <div className="chipRow"><span className="chip chipGo">GO <strong>{go}</strong></span><span className="chip chipGr">GR <strong>{gr}</strong></span><span className="chip chipNg">NG <strong>{ng}</strong></span></div>;
}