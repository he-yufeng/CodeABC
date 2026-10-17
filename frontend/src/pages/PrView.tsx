import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { getPrReading } from "../lib/api";
import type { PrReadingAnalysis } from "../lib/api";
import { useI18n, LanguageToggle } from "../lib/i18n";

const KIND_STYLE: Record<string, string> = {
  code: "bg-blue-100 text-blue-700",
  test: "bg-green-100 text-green-700",
  docs: "bg-purple-100 text-purple-700",
  config: "bg-amber-100 text-amber-700",
  other: "bg-gray-100 text-gray-600",
};

export default function PrView() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const url = params.get("url") ?? "";

  const [data, setData] = useState<PrReadingAnalysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!url) {
      setError(t("缺少 PR 链接。", "Missing PR URL."));
      setLoading(false);
      return;
    }
    let cancelled = false;
    getPrReading(url, true)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(
            e instanceof Error
              ? e.message
              : t("读取失败，请重试。", "Failed to read the PR — please try again."),
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [url, t]);

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

        {loading && (
          <div className="text-gray-500 text-center py-20">
            {t("正在读取这个 PR…", "Reading this pull request…")}
          </div>
        )}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {data && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 break-all">
              {data.owner}/{data.repo}#{data.number}
            </h1>
            <p className="mt-2 text-gray-600">
              {t(
                `共 ${data.summary.file_count} 个文件，+${data.summary.total_added} / -${data.summary.total_deleted} 行。`,
                `${data.summary.file_count} files touched, +${data.summary.total_added} / -${data.summary.total_deleted} lines.`,
              )}
            </p>
            <p className="mt-1 text-sm text-gray-400">
              {t(
                "按建议阅读顺序排列：先看最大的代码改动，再是测试、配置和文档。",
                "Suggested reading order: biggest code changes first, then tests, config and docs.",
              )}
            </p>

            <div className="mt-6 space-y-4">
              {data.files.map((f, i) => (
                <div
                  key={f.path}
                  className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-gray-400 text-sm">{i + 1}.</span>
                    <code className="text-sm font-medium text-gray-900 break-all">
                      {f.path}
                    </code>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${KIND_STYLE[f.change_type] ?? KIND_STYLE.other}`}
                    >
                      {f.change_type}
                    </span>
                    <span className="text-xs text-gray-400 ml-auto">
                      +{f.added} / -{f.deleted}
                    </span>
                  </div>
                  {data.explanations?.[f.path] && (
                    <p className="mt-3 text-sm text-gray-700 leading-relaxed">
                      {data.explanations[f.path]}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
