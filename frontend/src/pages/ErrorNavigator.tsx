import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { locateProjectError, type ErrorLocationResult } from "../lib/api";
import { friendlyError } from "../lib/errors";
import { LanguageToggle, useI18n } from "../lib/i18n";

export default function ErrorNavigator() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [log, setLog] = useState("");
  const [result, setResult] = useState<ErrorLocationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectId || !log.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await locateProjectError(projectId, log));
    } catch (e) {
      const raw = e instanceof Error ? e.message : "";
      setError(friendlyError(raw, t) || t("定位失败，请重试。", "Could not locate the error. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate(`/project/${projectId}`)}
          className="text-gray-500 hover:text-gray-700"
        >
          {t("← 返回项目", "← Back to project")}
        </button>
        <h1 className="text-xl font-semibold text-gray-900">
          {t("报错定位", "Error navigator")}
        </h1>
        <LanguageToggle className="ml-auto" />
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">
            {t("把报错贴进来，直接找到对应代码", "Paste an error and jump to the matching code")}
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {t(
              "支持 Python、Node、Go 等堆栈日志。只匹配这个项目已经扫描的源码，不运行代码，也不需要 API key。",
              "Works with Python, Node, Go, and other stack traces. It only matches source already scanned in this project, runs no code, and needs no API key.",
            )}
          </p>
          <form onSubmit={handleSubmit}>
            <label htmlFor="error-log" className="block text-sm font-medium text-gray-700 mb-2">
              {t("错误日志", "Error log")}
            </label>
            <textarea
              id="error-log"
              value={log}
              onChange={(event) => setLog(event.target.value)}
              rows={10}
              className="w-full rounded-lg border border-gray-300 p-3 font-mono text-sm focus:border-blue-400 focus:outline-none"
              placeholder={'Traceback (most recent call last):\n  File "/path/to/app.py", line 42, in run\nValueError: ...'}
            />
            <button
              type="submit"
              disabled={!log.trim() || loading}
              className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {loading ? t("正在定位…", "Locating…") : t("找到报错位置", "Find error locations")}
            </button>
          </form>
          {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}
        </section>

        {result && (
          <section aria-live="polite">
            <p className="text-sm text-gray-600 mb-4">
              {result.locations.length > 0
                ? t(
                    `在项目里找到 ${result.locations.length} 个位置。`,
                    `Found ${result.locations.length} location(s) in this project.`,
                  )
                : t(
                    "没有匹配到项目源码。日志里的路径可能不在扫描范围内。",
                    "No project source matched. The logged paths may be outside the scanned source.",
                  )}
            </p>
            <div className="space-y-4">
              {result.locations.map((location) => (
                <article key={`${location.path}:${location.line}`} className="bg-white rounded-xl p-5 shadow-sm">
                  <button
                    onClick={() => navigate(`/project/${projectId}/file/${encodeURIComponent(location.path)}`)}
                    className="text-left font-mono text-sm text-blue-600 hover:underline"
                  >
                    {location.path}:{location.line}
                    {location.column ? `:${location.column}` : ""}
                  </button>
                  {location.kind && (
                    <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                      {location.kind}
                    </span>
                  )}
                  {location.purpose && <p className="mt-2 text-sm text-gray-500">{location.purpose}</p>}
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-gray-900 p-4 text-xs leading-6 text-gray-100">
                    {location.excerpt}
                  </pre>
                </article>
              ))}
            </div>
            {result.unresolved > 0 && (
              <p className="mt-4 text-sm text-amber-700">
                {t(
                  `另有 ${result.unresolved} 个日志位置无法确定，已保留为未匹配，没有猜测。`,
                  `${result.unresolved} logged location(s) could not be resolved and were left unmatched rather than guessed.`,
                )}
              </p>
            )}
            {result.truncated && (
              <p className="mt-2 text-sm text-gray-500">
                {t("匹配较多，只显示前 20 个位置。", "Many matches found. Only the first 20 are shown.")}
              </p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
