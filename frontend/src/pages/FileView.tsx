import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  askQuestion,
  editCode,
  getFileContent,
  getAnnotations,
  getGlossary,
  getProject,
  type Annotation,
  type FilePurpose,
  type GlossaryTerm,
} from "../lib/api";
import { useI18n, LanguageToggle } from "../lib/i18n";
import { friendlyError } from "../lib/errors";
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
  const { t } = useI18n();
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
  const [purpose, setPurpose] = useState<FilePurpose | null>(null);
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
      const raw = e instanceof Error ? e.message : "";
      setQaError(friendlyError(raw, t) || t("提问失败，请重试。", "Question failed — please try again."));
    } finally {
      setQaLoading(false);
    }
  };

  // Natural-language editing: describe a change, get a suggested rewrite
  const [instruction, setInstruction] = useState("");
  const [editedCode, setEditedCode] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleEdit = async () => {
    if (!projectId || !instruction.trim() || editLoading) return;
    const target = selection || code;
    if (!target.trim()) return;
    setEditLoading(true);
    setEditError(null);
    setEditedCode("");
    setCopied(false);
    try {
      const res = await editCode(projectId, {
        instruction: instruction.trim(),
        code: target,
        filePath: decodedPath,
        language,
      });
      setEditedCode(res.edited_code);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "";
      setEditError(friendlyError(raw, t) || t("改写失败，请重试。", "Rewrite failed — please try again."));
    } finally {
      setEditLoading(false);
    }
  };

  const copyEdited = async () => {
    try {
      await navigator.clipboard.writeText(editedCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
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
        setPurpose(res.purpose ?? null);
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
          {t("← 返回说明书", "← Back to manual")}
        </button>
        <span className="font-mono text-sm text-gray-600">{decodedPath}</span>
        {loadingAnnotations && (
          <span className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin" />
            {t("生成批注中...", "Generating annotations...")}
          </span>
        )}
        <LanguageToggle className="ml-auto" />
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6">
        {/* What this file is, inferred from its name — helps a non-coder
            who is staring at an unfamiliar filename. */}
        {purpose && (
          <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
            <span className="text-lg leading-none">📄</span>
            <div className="text-sm">
              <span className="font-semibold text-amber-900">
                {t("这个文件是什么", "What this file is")}
              </span>
              <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                {purpose.kind}
              </span>
              <p className="mt-1 leading-relaxed text-amber-900/90">
                {purpose.explanation}
              </p>
            </div>
          </div>
        )}

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
                {t(
                  "💡 将鼠标悬停在代码上查看中文解释；选中一段代码可在下方就它提问",
                  "💡 Hover over the code for explanations; select a snippet to ask about it below",
                )}
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
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              {t("术语词典", "Terminology")}
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这个文件里出现的编程术语，把鼠标移到词上就能看到大白话解释。",
                "Programming terms found in this file — hover a term for a plain-language definition.",
              )}
            </p>
            <div className="flex flex-wrap gap-2">
              {glossary.map((term) => (
                <span key={term.term} className="relative group">
                  <span
                    tabIndex={0}
                    className="inline-block font-mono text-sm text-blue-700 bg-blue-50
                               border border-blue-100 rounded px-2 py-1 cursor-help
                               hover:bg-blue-100 transition-colors"
                  >
                    {term.term}
                  </span>
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute left-0 top-full z-10 mt-1 w-72
                               rounded-lg bg-gray-900 px-3 py-2 text-sm leading-relaxed
                               text-white opacity-0 shadow-lg transition-opacity
                               group-hover:opacity-100 group-focus-within:opacity-100"
                  >
                    {term.definition}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Q&A: ask a question about the selected code (or the whole file) */}
        {!loadingCode && code && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              {t("问一问这段代码", "Ask about this code")}
            </h3>
            <p className="text-sm text-gray-500 mb-3">
              {t(
                "在上面选中一段代码再提问会更精准；不选就针对整个文件回答。",
                "Select a snippet above for a sharper answer; otherwise the whole file is used.",
              )}
            </p>
            {selection ? (
              <div className="mb-3 text-sm">
                <span className="text-gray-500">
                  {t(`已选中 ${selection.length} 个字符：`, `${selection.length} characters selected:`)}
                </span>
                <button
                  onClick={() => setSelection("")}
                  className="ml-2 text-blue-600 hover:underline"
                >
                  {t("清除选择", "Clear selection")}
                </button>
                <pre className="mt-1 max-h-28 overflow-auto rounded bg-gray-50 p-2 font-mono text-xs text-gray-700">
                  {selection.slice(0, 600)}
                </pre>
              </div>
            ) : (
              <p className="mb-3 text-sm text-gray-400">
                {t("未选中代码，将针对整个文件回答。", "No selection — the whole file will be used.")}
              </p>
            )}
            <div className="flex gap-2">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleAsk();
                }}
                placeholder={t(
                  "比如：这段代码是做什么的？这个参数为什么是这个值？",
                  "e.g. What does this code do? Why is this value set this way?",
                )}
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
                {qaLoading ? t("思考中…", "Thinking…") : t("提问", "Ask")}
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

        {/* Natural-language editing: describe a change, get a suggested rewrite */}
        {!loadingCode && code && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              {t("用大白话改代码", "Edit code in plain words")}
            </h3>
            <p className="text-sm text-gray-500 mb-3">
              {t(
                "选中一段代码（不选则针对整个文件），用一句话说要怎么改，比如「把茅台换成比亚迪」。改完的代码只供你复制，不会动原文件。",
                "Select a snippet (or use the whole file) and describe the change in one line, e.g. \"change Maotai to BYD\". The result is yours to copy — your files are never modified.",
              )}
            </p>
            <div className="flex gap-2">
              <input
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleEdit();
                }}
                placeholder={t(
                  "比如：把所有的茅台换成比亚迪 / 把超时从 3600 改成 600",
                  "e.g. change all Maotai to BYD / change the timeout from 3600 to 600",
                )}
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm
                           focus:border-blue-400 focus:outline-none"
              />
              <button
                onClick={handleEdit}
                disabled={!instruction.trim() || editLoading}
                className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium
                           text-white hover:bg-blue-700 disabled:opacity-40"
              >
                {editLoading ? t("改写中…", "Rewriting…") : t("改写", "Rewrite")}
              </button>
            </div>
            {editError && <p className="mt-3 text-sm text-red-600">{editError}</p>}
            {editedCode && (
              <div className="mt-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700">
                    {t("改写后的代码", "Rewritten code")}
                  </span>
                  <button
                    onClick={copyEdited}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    {copied ? t("已复制 ✓", "Copied ✓") : t("复制", "Copy")}
                  </button>
                </div>
                <pre className="max-h-96 overflow-auto rounded-lg bg-gray-900 p-4 font-mono
                                text-xs leading-relaxed text-gray-100">
                  {editedCode}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* Annotations list (mobile-friendly fallback) */}
        {annotations.length > 0 && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-6 lg:hidden">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              {t("代码批注", "Annotations")}
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
