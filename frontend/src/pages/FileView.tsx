import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  askQuestion,
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

  // Q&A: select code in the viewer, ask a question about it
  const [selection, setSelection] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaError, setQaError] = useState<string | null>(null);

  const captureSelection = () => {
    const text = window.getSelection?.()?.toString().trim() ?? "";
    if (text) setSelection(text);
  };

  const handleAsk = async () => {
    if (!projectId || !question.trim() || qaLoading) return;
    setQaLoading(true);
    setQaError(null);
    setAnswer("");
    try {
      const res = await askQuestion(projectId, {
        question: question.trim(),
        code: selection || code,
        filePath: decodedPath,
        language,
      });
      setAnswer(res.answer);
    } catch (e) {
      setQaError(e instanceof Error ? e.message : "提问失败");
    } finally {
      setQaLoading(false);
    }
  };

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
          <div
            className="bg-white rounded-xl shadow-sm overflow-hidden"
            onMouseUp={captureSelection}
          >
            {/* Hint */}
            {annotations.length > 0 && (
              <div className="bg-blue-50 px-4 py-2 text-sm text-blue-700 border-b border-blue-100">
                💡 将鼠标悬停在代码上查看中文解释；选中一段代码可在下方就它提问
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

        {/* Q&A: ask a question about the selected code (or the whole file) */}
        {!loadingCode && code && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-1">问一问这段代码</h3>
            <p className="text-sm text-gray-500 mb-3">
              在上面选中一段代码再提问会更精准；不选就针对整个文件回答。
            </p>
            {selection ? (
              <div className="mb-3 text-sm">
                <span className="text-gray-500">已选中 {selection.length} 个字符：</span>
                <button
                  onClick={() => setSelection("")}
                  className="ml-2 text-blue-600 hover:underline"
                >
                  清除选择
                </button>
                <pre className="mt-1 max-h-28 overflow-auto rounded bg-gray-50 p-2 font-mono text-xs text-gray-700">
                  {selection.slice(0, 600)}
                </pre>
              </div>
            ) : (
              <p className="mb-3 text-sm text-gray-400">未选中代码，将针对整个文件回答。</p>
            )}
            <div className="flex gap-2">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleAsk();
                }}
                placeholder="比如：这段代码是做什么的？这个参数为什么是这个值？"
                rows={2}
                className="flex-1 resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm
                           focus:border-blue-400 focus:outline-none"
              />
              <button
                onClick={handleAsk}
                disabled={!question.trim() || qaLoading}
                className="shrink-0 self-start rounded-lg bg-blue-600 px-4 py-2 text-sm
                           font-medium text-white hover:bg-blue-700 disabled:opacity-40"
              >
                {qaLoading ? "思考中…" : "提问"}
              </button>
            </div>
            {qaError && (
              <p className="mt-3 text-sm text-red-600">{qaError}</p>
            )}
            {answer && (
              <div className="mt-4 whitespace-pre-wrap rounded-lg bg-blue-50 p-4 text-sm
                              leading-relaxed text-gray-800">
                {answer}
              </div>
            )}
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
