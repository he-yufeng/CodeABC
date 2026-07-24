import { useState } from "react";
import { useI18n } from "../lib/i18n";
import { getPrReading, type PrReadingAnalysis } from "../lib/api";

const KIND_COLORS: Record<string, string> = {
  code: "bg-blue-50 text-blue-700",
  test: "bg-emerald-50 text-emerald-700",
  docs: "bg-gray-100 text-gray-600",
  config: "bg-amber-50 text-amber-700",
  other: "bg-gray-100 text-gray-600",
};

/** Paste a PR link and get the diff walked through in plain language. */
export default function PrReadingCard() {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PrReadingAnalysis | null>(null);

  async function handleRead() {
    if (!url.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await getPrReading(url.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-indigo-400">
      <h2 className="text-lg font-semibold text-gray-900 mb-1">
        {t("读一个 Pull Request", "Read a pull request")}
      </h2>
      <p className="text-sm text-gray-500 mb-4">
        {t(
          "贴上 PR 链接，先看它改了什么、再按建议顺序读。按 diff 大小把生产代码排在前面，测试和文档殿后。",
          "Paste a PR link to see what it changed and in what order to read it. Big production diffs come first, tests and docs last.",
        )}
      </p>
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRead()}
          placeholder="https://github.com/owner/repo/pull/123"
          className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:border-indigo-500 outline-none text-sm font-mono"
          disabled={loading}
        />
        <button
          onClick={handleRead}
          disabled={loading || !url.trim()}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {loading ? t("读取中…", "Reading…") : t("读这个 PR", "Read it")}
        </button>
      </div>

      {error && <p className="text-sm text-rose-600 mb-2">{error}</p>}

      {result && (
        <div>
          <p className="text-sm text-gray-700 mb-3">
            <a
              href={result.url}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-indigo-700 hover:underline"
            >
              {result.owner}/{result.repo}#{result.number}
            </a>
            <span className="ml-2 text-gray-500">
              {t(
                `${result.summary.file_count} 个文件（+${result.summary.total_added} / -${result.summary.total_deleted}）`,
                `${result.summary.file_count} files (+${result.summary.total_added} / -${result.summary.total_deleted})`,
              )}
            </span>
          </p>
          <ol className="space-y-1.5">
            {result.files.map((f, i) => (
              <li key={f.path} className="flex items-baseline gap-2 text-sm">
                <span className="text-gray-400 w-5 text-right">{i + 1}.</span>
                <span className="font-mono text-gray-800">{f.path}</span>
                <span className={`rounded px-1.5 py-0.5 text-xs ${KIND_COLORS[f.change_type] ?? KIND_COLORS.other}`}>
                  {f.change_type}
                </span>
                <span className="text-xs text-gray-400">
                  +{f.added} / -{f.deleted}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
