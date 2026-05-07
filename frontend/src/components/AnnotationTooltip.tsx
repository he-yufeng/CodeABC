interface Props {
  text: string;
  referenceEl: HTMLElement | null;
  open: boolean;
}

export default function AnnotationTooltip({ text, referenceEl, open }: Props) {
  if (!open || !referenceEl || typeof window === "undefined") return null;

  const rect = referenceEl.getBoundingClientRect();
  const maxWidth = 320;
  const gap = 12;
  const showRight = rect.right + gap + maxWidth < window.innerWidth;
  const top = Math.max(8, Math.min(rect.top - 4, window.innerHeight - 96));
  const horizontalStyle = showRight
    ? { left: rect.right + gap }
    : { right: window.innerWidth - rect.left + gap };

  return (
    <div
      style={{ top, maxWidth, ...horizontalStyle }}
      className="fixed z-50 bg-white border border-blue-200 rounded-lg
                 shadow-lg p-3 text-sm text-gray-700 leading-relaxed"
    >
      <span
        className={`absolute top-3 h-3 w-3 rotate-45 bg-white border-blue-200 ${
          showRight ? "-left-1.5 border-l border-b" : "-right-1.5 border-r border-t"
        }`}
      />
      <span>{text}</span>
    </div>
  );
}
