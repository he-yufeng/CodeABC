import { useEffect, useRef, useState } from "react";
import { codeToHtml } from "shiki";
import type { Annotation } from "../lib/api";
import AnnotationTooltip from "./AnnotationTooltip";

interface Props {
  code: string;
  language: string;
  annotations: Annotation[];
}

export default function CodeViewer({ code, language, annotations }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  const [tooltip, setTooltip] = useState<{
    text: string;
    x: number;
    y: number;
  } | null>(null);

  // render code with shiki
  useEffect(() => {
    let cancelled = false;

    // shiki might not support the exact language name, fall back to text
    const lang = ["python", "javascript", "typescript", "jsx", "tsx", "html",
      "css", "json", "yaml", "shell", "go", "rust", "java", "c", "cpp",
      "ruby", "php", "sql", "toml", "markdown", "r"].includes(language)
      ? language
      : "text";

    codeToHtml(code, {
      lang,
      theme: "github-light",
    }).then((result) => {
      if (!cancelled) setHtml(result);
    });

    return () => { cancelled = true; };
  }, [code, language]);

  // find annotation for a given line number
  const findAnnotation = (lineNum: number): Annotation | undefined => {
    return annotations.find(
      (a) => lineNum >= a.line_start && lineNum <= a.line_end
    );
  };

  // handle hover on code lines
  const handleMouseMove = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    // shiki renders each line in a <span class="line"> inside <code>
    const lineEl = target.closest(".line");
    if (!lineEl) {
      setTooltip(null);
      return;
    }

    // find line number by counting previous siblings
    const codeEl = lineEl.parentElement;
    if (!codeEl) return;
    const lines = Array.from(codeEl.querySelectorAll(".line"));
    const lineNum = lines.indexOf(lineEl) + 1;

    const ann = findAnnotation(lineNum);
    if (ann) {
      const rect = lineEl.getBoundingClientRect();
      const containerRect = containerRef.current?.getBoundingClientRect();
      if (containerRect) {
        setTooltip({
          text: ann.annotation,
          x: rect.right - containerRect.left + 12,
          y: rect.top - containerRect.top,
        });
      }
    } else {
      setTooltip(null);
    }
  };

  return (
    <div ref={containerRef} className="relative" onMouseMove={handleMouseMove} onMouseLeave={() => setTooltip(null)}>
      {/* Rendered code */}
      <div
        className="overflow-x-auto text-sm leading-6 [&_pre]:p-4 [&_pre]:m-0
                   [&_.line]:px-2 [&_.line]:hover:bg-blue-50 [&_.line]:rounded
                   [&_.line]:transition-colors [&_.line]:cursor-pointer"
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* Annotation tooltip */}
      {tooltip && (
        <AnnotationTooltip
          text={tooltip.text}
          style={{
            position: "absolute",
            top: tooltip.y,
            left: Math.min(tooltip.x, 600),
          }}
        />
      )}
    </div>
  );
}
