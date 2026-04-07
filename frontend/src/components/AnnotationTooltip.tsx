import type { CSSProperties } from "react";

interface Props {
  text: string;
  style?: CSSProperties;
}

export default function AnnotationTooltip({ text, style }: Props) {
  return (
    <div
      style={style}
      className="z-50 max-w-xs bg-white border border-blue-200 rounded-lg
                 shadow-lg p-3 text-sm text-gray-700 leading-relaxed
                 pointer-events-none animate-fade-in"
    >
      <div className="flex gap-2">
        <span className="text-blue-500 shrink-0">📖</span>
        <span>{text}</span>
      </div>
    </div>
  );
}
