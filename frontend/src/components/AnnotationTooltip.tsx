import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  arrow,
  FloatingArrow,
} from "@floating-ui/react";
import { useRef } from "react";

interface Props {
  text: string;
  referenceEl: HTMLElement | null;
  open: boolean;
}

export default function AnnotationTooltip({ text, referenceEl, open }: Props) {
  const arrowRef = useRef<SVGSVGElement>(null);

  const { refs, floatingStyles, context } = useFloating({
    open,
    placement: "right-start",
    whileElementsMounted: autoUpdate,
    elements: { reference: referenceEl },
    middleware: [
      offset(12),
      flip({ fallbackPlacements: ["left-start", "top", "bottom"] }),
      shift({ padding: 8 }),
      arrow({ element: arrowRef }),
    ],
  });

  if (!open || !referenceEl) return null;

  return (
    <div
      ref={refs.setFloating}
      style={floatingStyles}
      className="z-50 max-w-xs bg-white border border-blue-200 rounded-lg
                 shadow-lg p-3 text-sm text-gray-700 leading-relaxed"
    >
      <FloatingArrow
        ref={arrowRef}
        context={context}
        fill="white"
        stroke="#bfdbfe"
        strokeWidth={1}
      />
      <span>{text}</span>
    </div>
  );
}
