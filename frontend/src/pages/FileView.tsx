import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getFileContent,
  getAnnotations,
  getGlossary,
  getProject,
  type Annotation,
  type GlossaryTerm,
} from "../lib/api";
import { useProjectStore } from "../stores/project";
import CodeViewer from "../components/CodeViewer";

export default function FileView() {
  const { projectId, "*": filePath } = useParams<{
    projectId: string;
    "*": string;
  }>();
  const navigate = useNavigate();
  const { project, setProject } = useProjectStore();

  const decodedPath = filePath ? decodeURIComponent(filePath) : "";

  // restore project metadata on refresh
  useEffect(() => {
    if (!projectId || project) return;

    getProject(projectId)
      .then((p) => setProject(p))
      .catch(() => navigate("/", { replace: true }));
  }, [projectId, project, setProject, navigate]);

  return (
    <FileContent
      key={`${projectId ?? ""}:${decodedPath}`}
      projectId={projectId}
      decodedPath={decodedPath}
      onBack={() => navigate(`/project/${projectId}`)}
    />
  );
}

function FileContent({
  projectId,
  decodedPath,
  onBack,
}: {
  projectId: string | undefined;
  decodedPath: string;
  onBack: () => void;
}) {
  const { annotationsCache, cacheAnnotations } = useProjectStore();
  const cachedAnnotations = decodedPath ? annotationsCache[decodedPath] : undefined;

  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("text");
  const [annotations, setAnnotations] = useState<Annotation[]>(
    () => cachedAnnotations ?? [],
  );
  const [loadingCode, setLoadingCode] = useState(Boolean(projectId && decodedPath));
  const [loadingAnnotations, setLoadingAnnotations] = useState(
    Boolean(projectId && decodedPath && !cachedAnnotations),
  );
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([]);
  const [error, setError] = useState<string | null>(null);

  // load file content
  useEffect(() => {
    if (!projectId || !decodedPath) return;
    let active = true;

    getFileContent(projectId, decodedPath)
      .then((res) => {
        if (!active) return;
        setCode(res.content);
        setLanguage(res.language);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoadingCode(false);
      });

    return () => {
      active = false;
    };
  }, [projectId, decodedPath]);

  // load terminology dictionary (deterministic, no API key, so always safe)
  useEffect(() => {
    if (!projectId || !decodedPath) return;
    let active = true;

    getGlossary(projectId, decodedPath)
      .then((res) => {
        if (active) setGlossary(res.terms);
      })
      .catch(() => {
        if (active) setGlossary([]);
      });

    return () => {
      active = false;
    };
  }, [projectId, decodedPath]);

  // load annotations (check cache first)
  useEffect(() => {
    if (!projectId || !decodedPath || cachedAnnotations) return;
    let active = true;

    getAnnotations(projectId, decodedPath)
      .then((res) => {
        if (!active) return;
        setAnnotations(res.annotations);
        cacheAnnotations(decodedPath, res.annotations);
      })
      .catch(() => {
        if (active) setAnnotations([]);
      })
      .finally(() => {
        if (active) setLoadingAnnotations(false);
      });

    return () => {
      active = false;
    };
  }, [projectId, decodedPath, cachedAnnotations, cacheAnnotations]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <button
          onClick={onBack}
          className="text-gray-500 hover:text-gray-700"
        >
          ← 返回说明书
        </button>
        <span className="font-mono text-sm text-gray-600">{decodedPath}</span>
        {loadingAnnotations && (
          <span className="ml-auto flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin" />
            生成批注中...
          </span>
        )}
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6">
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {loadingCode ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Hint */}
            {annotations.length > 0 && (
              <div className="bg-blue-50 px-4 py-2 text-sm text-blue-700 border-b border-blue-100">
                💡 将鼠标悬停在代码上，查看中文解释
              </div>
            )}
            <CodeViewer
              code={code}
              language={language}
              annotations={annotations}
            />
          </div>
        )}

        {/* Terminology dictionary: hover a keyword to see a plain-language definition */}
        {glossary.length > 0 && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-1">术语词典</h3>
            <p className="text-sm text-gray-500 mb-4">
              这个文件里出现的编程术语，把鼠标移到词上就能看到大白话解释。
            </p>
            <div className="flex flex-wrap gap-2">
              {glossary.map((t) => (
                <span key={t.term} className="relative group">
                  <span
                    tabIndex={0}
                    className="inline-block font-mono text-sm text-blue-700 bg-blue-50
                               border border-blue-100 rounded px-2 py-1 cursor-help
                               hover:bg-blue-100 transition-colors"
                  >
                    {t.term}
                  </span>
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute left-0 top-full z-10 mt-1 w-72
                               rounded-lg bg-gray-900 px-3 py-2 text-sm leading-relaxed
                               text-white opacity-0 shadow-lg transition-opacity
                               group-hover:opacity-100 group-focus-within:opacity-100"
                  >
                    {t.definition}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Annotations list (mobile-friendly fallback) */}
        {annotations.length > 0 && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6 lg:hidden">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              代码批注
            </h3>
            <div className="space-y-3">
              {annotations.map((a, i) => (
                <div key={i} className="flex gap-3 text-sm">
                  <span className="text-gray-400 font-mono shrink-0">
                    L{a.line_start}
                    {a.line_end !== a.line_start && `-${a.line_end}`}
                  </span>
                  <span className="text-gray-700">{a.annotation}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
