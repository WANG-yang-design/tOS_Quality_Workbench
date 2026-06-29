import React from "react";

// 从 App.tsx 第590行原样提取
export function ResourceCard({ title, desc, href }: any) {
  return <div className="subCard" style={{flex:1,display:"flex",alignItems:"center",gap:10,padding:"10px 16px"}}><div><div className="subCardTitle" style={{marginBottom:2}}>{title}</div><div className="smallMuted">{desc}</div></div>{href ? <a href={href} className="textLink" style={{marginLeft:"auto",whiteSpace:"nowrap"}} target="_blank" rel="noreferrer">打开 →</a> : <span className="smallMuted" style={{marginLeft:"auto",whiteSpace:"nowrap"}}>未配置</span>}</div>;
}