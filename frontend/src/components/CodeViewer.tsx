import { useEffect, useRef, useState, useCallback } from "react";
import { codeToHtml } from "shiki";
import type { Annotation } from "../lib/api";
import AnnotationTooltip from "./AnnotationTooltip";

interface Props {
  code: string;
  language: string;
  annotations: Annotation[];
}

const SUPPORTED_LANGS = new Set([
  "python", "javascript", "typescript", "jsx", "tsx", "html",
  "css", "json", "yaml", "shell", "go", "rust", "java", "c", "cpp",
  "ruby", "php", "sql", "toml", "markdown", "r", "swift", "kotlin",
  "scala", "lua", "dart", "vue", "svelte", "zig",
]);

export default function CodeViewer({ code, language, annotations }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  const [activeAnnotation, setActiveAnnotation] = useState<string | null>(null);
  const [activeLineEl, setActiveLineEl] = useState<HTMLElement | null>(null);

  // render code with shiki
  useEffect(() => {
    let cancelled = false;
    const lang = SUPPORTED_LANGS.has(language) ? language : "text";

    codeToHtml(code, { lang, theme: "github-light" }).then((result) => {
      if (!cancelled) setHtml(result);
    });

    return () => { cancelled = true; };
  }, [code, language]);

  const findAnnotation = useCallback(
    (lineNum: number): Annotation | undefined => {
      return annotations.find(
        (a) => lineNum >= a.line_start && lineNum <= a.line_end
      );
    },
    [annotations]
  );

  const getLineNum = (target: HTMLElement): number | null => {
    const lineEl = target.closest(".line");
    if (!lineEl) return null;
    const codeEl = lineEl.parentElement;
    if (!codeEl) return null;
    const lines = Array.from(codeEl.querySelectorAll(".line"));
    return lines.indexOf(lineEl) + 1;
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const lineNum = getLineNum(e.target as HTMLElement);
    if (lineNum === null) {
      setActiveAnnotation(null);
      setActiveLineEl(null);
      return;
    }
    const ann = findAnnotation(lineNum);
    if (ann) {
      const lineEl = (e.target as HTMLElement).closest(".line") as HTMLElement;
      setActiveAnnotation(ann.annotation);
      setActiveLineEl(lineEl);
    } else {
      setActiveAnnotation(null);
      setActiveLineEl(null);
    }
  };

  // touch: tap a line to toggle its annotation
  const handleClick = (e: React.MouseEvent) => {
    // only handle real taps on touch devices
    if (!("ontouchstart" in window)) return;

    const lineNum = getLineNum(e.target as HTMLElement);
    if (lineNum === null) {
      setActiveAnnotation(null);
      setActiveLineEl(null);
      return;
    }
    const ann = findAnnotation(lineNum);
    const lineEl = (e.target as HTMLElement).closest(".line") as HTMLElement;

    if (ann && lineEl !== activeLineEl) {
      setActiveAnnotation(ann.annotation);
      setActiveLineEl(lineEl);
    } else {
      // tap again to dismiss
      setActiveAnnotation(null);
      setActiveLineEl(null);
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => {
        setActiveAnnotation(null);
        setActiveLineEl(null);
      }}
      onClick={handleClick}
    >
      {/* Rendered code */}
      <div
        className="overflow-x-auto text-sm leading-6 [&_pre]:p-4 [&_pre]:m-0
                   [&_.line]:px-2 [&_.line]:hover:bg-blue-50 [&_.line]:rounded
                   [&_.line]:transition-colors [&_.line]:cursor-pointer"
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* Annotation tooltip (floating-ui positioned) */}
      <AnnotationTooltip
        text={activeAnnotation || ""}
        referenceEl={activeLineEl}
        open={!!activeAnnotation}
      />
    </div>
  );
}
