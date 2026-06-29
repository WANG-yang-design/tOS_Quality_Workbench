import React from "react";

// 从 App.tsx 第577行原样提取
export function MajorSectionDivider({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="majorSectionDivider">
      <span className="sectionIcon">{icon}</span>
      <h2>{title}</h2>
    </div>
  );
}