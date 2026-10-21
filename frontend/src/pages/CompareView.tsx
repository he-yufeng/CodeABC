import { useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadZone from "../components/UploadZone";
import { compareProjects } from "../lib/api";
import type { ProjectComparison, ComparedFile } from "../lib/api";
import { useI18n, LanguageToggle } from "../lib/i18n";
import { friendlyError } from "../lib/errors";

const STATUS_LABEL: Record<ComparedFile["status"], [string, string]> = {
  added: ["新增", "added"],
  deleted: ["删除", "deleted"],
  modified: ["修改", "modified"],
};

const STATUS_STYLE: Record<ComparedFile["status"], string> = {
  added: "bg-green-100 text-green-700",
  deleted: "bg-red-100 text-red-700",
  modified: "bg-amber-100 text-amber-700",
};

export default function CompareView() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [before, setBefore] = useState<{ path: string; content: string }[]>([]);
  const [after, setAfter] = useState<{ path: string; content: string }[]>([]);
  const [beforeName, setBeforeName] = useState("旧版本");
  const [afterName, setAfterName] = useState("新版本");
  const [result, setResult] = useState<ProjectComparison | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const runCompare = async () => {
    setError("");
    setLoading(true);
    try {
      setResult(await compareProjects(before, beforeName, after, afterName));
    } catch (e: unknown) {
      const raw = e instanceof Error ? e.message : "";
      setError(friendlyError(raw, t) || t("对比失败，请重试。", "Comparison failed — please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="fixed top-4 right-4">
        <LanguageToggle />
      </div>
      <div className="max-w-3xl mx-auto py-10 px-4">
        <button
          onClick={() => navigate("/")}
          className="text-sm text-blue-600 hover:underline mb-6"
        >
          {t("← 返回首页", "← Back home")}
        </button>
        <h1 className="text-2xl font-bold text-gray-900">
          {t("对比两个版本", "Compare two versions")}
        </h1>
        <p className="mt-2 text-gray-600 text-sm">
          {t(
            "把交付前后的两个项目文件夹分别拖进来，看看实际改了哪些文件、有没有新的风险信号。全程离线，不需要 API Key。",
            "Drop the before/after project folders to see what actually changed and whether new risk signals appeared. Fully offline, no API key needed.",
          )}
        </p>

        {!result && (
          <>
            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">
                  {t("旧版本（交付前）", "Before")}
                </p>
                <UploadZone
                  onFilesSelected={(files, name) => {
                    setBefore(files);
                    setBeforeName(name || beforeName);
                  }}
                  disabled={loading}
                />
                {before.length > 0 && (
                  <p className="mt-2 text-xs text-gray-500">
                    {t(`已读取 ${before.length} 个文件`, `${before.length} files read`)}
                  </p>
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">
                  {t("新版本（交付后）", "After")}
                </p>
                <UploadZone
                  onFilesSelected={(files, name) => {
                    setAfter(files);
                    setAfterName(name || afterName);
                  }}
                  disabled={loading}
                />
                {after.length > 0 && (
                  <p className="mt-2 text-xs text-gray-500">
                    {t(`已读取 ${after.length} 个文件`, `${after.length} files read`)}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={runCompare}
              disabled={loading || before.length === 0 || after.length === 0}
              className="mt-6 w-full px-6 py-3 bg-blue-600 text-white rounded-xl font-medium
                         hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors"
            >
              {loading ? t("对比中...", "Comparing...") : t("开始对比", "Compare")}
            </button>
            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}
          </>
        )}

        {result && (
          <>
            <div className="mt-6 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
              <p className="text-sm text-gray-700">
                {t(
                  `${result.before_name} → ${result.after_name}：新增 ${result.summary.added}，删除 ${result.summary.deleted}，修改 ${result.summary.modified}，未变 ${result.summary.unchanged}。`,
                  `${result.before_name} → ${result.after_name}: ${result.summary.added} added, ${result.summary.deleted} deleted, ${result.summary.modified} modified, ${result.summary.unchanged} unchanged.`,
                )}
              </p>
              {result.summary.not_compared > 0 && (
                <p className="mt-1 text-xs text-gray-400">
                  {t(
                    `另有 ${result.summary.not_compared} 个路径被过滤（依赖目录/二进制/超上限），未参与对比。`,
                    `${result.summary.not_compared} more paths were filtered out (dependency dirs, binaries, over limits) and not compared.`,
                  )}
                </p>
              )}
            </div>

            {result.security.complete &&
              ((result.security.introduced ?? 0) > 0 ||
                (result.security.no_longer_detected ?? 0) > 0) && (
                <div className="mt-4 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
                  <h2 className="text-sm font-semibold text-gray-900">
                    {t("风险提示变化", "Risk signal changes")}
                  </h2>
                  <p className="mt-1 text-sm text-gray-700">
                    {t(
                      `新出现 ${result.security.introduced} 处，不再命中 ${result.security.no_longer_detected} 处，仍存在 ${result.security.persistent} 处。`,
                      `${result.security.introduced} new, ${result.security.no_longer_detected} no longer detected, ${result.security.persistent} still present.`,
                    )}
                  </p>
                  <div className="mt-3 space-y-2">
                    {result.security.changes
                      .filter((c) => c.status !== "persistent")
                      .slice(0, 20)
                      .map((c, i) => {
                        const f = c.after ?? c.before;
                        if (!f) return null;
                        return (
                          <div
                            key={i}
                            className="text-xs text-gray-600 flex items-start gap-2"
                          >
                            <span
                              className={`px-2 py-0.5 rounded-full whitespace-nowrap ${
                                c.status === "introduced"
                                  ? "bg-red-100 text-red-700"
                                  : "bg-green-100 text-green-700"
                              }`}
                            >
                              {c.status === "introduced"
                                ? t("新出现", "new")
                                : t("不再命中", "resolved")}
                            </span>
                            <code className="break-all">
                              {f.file}:{f.line}
                            </code>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}

            <div className="mt-6 space-y-3">
              {result.files.map((f) => (
                <div
                  key={f.path}
                  className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[f.status]}`}
                    >
                      {t(...STATUS_LABEL[f.status])}
                    </span>
                    <code className="text-sm font-medium text-gray-900 break-all">
                      {f.path}
                    </code>
                    <span className="text-xs text-gray-400 ml-auto">
                      {f.before_bytes} → {f.after_bytes} B
                    </span>
                  </div>
                  {f.diff && (
                    <pre className="mt-3 text-xs bg-gray-50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                      {f.diff}
                      {f.diff_truncated && "\n…"}
                    </pre>
                  )}
                </div>
              ))}
            </div>

            <button
              onClick={() => {
                setResult(null);
                setBefore([]);
                setAfter([]);
              }}
              className="mt-6 text-sm text-blue-600 hover:underline"
            >
              {t("再对比一对", "Compare another pair")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
