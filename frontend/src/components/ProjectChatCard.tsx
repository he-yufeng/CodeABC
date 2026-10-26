import { useEffect, useRef, useState } from "react";
import { projectChat } from "../lib/api";
import type { ProjectChatResponse } from "../lib/api";
import { useI18n } from "../lib/i18n";

interface ChatMessage extends ProjectChatResponse {
  question: string;
}

function reasonLabel(reason: string): [string, string] {
  switch (reason) {
    case "named in the question":
      return ["问题里点名", "named in your question"];
    case "selected project map":
      return ["相关图谱指向", "selected project map"];
    case "deterministic reading route":
      return ["确定性阅读路线", "deterministic reading route"];
    default:
      return ["问题关键词匹配", "question keyword match"];
  }
}

export default function ProjectChatCard({
  projectId,
  onFileClick,
}: {
  projectId: string;
  onFileClick: (path: string) => void;
}) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current += 1;
    setMessages([]);
    setQuestion("");
    setLoading(false);
    setError(null);
    return () => {
      requestVersion.current += 1;
    };
  }, [projectId]);

  const clearChat = () => {
    requestVersion.current += 1;
    setMessages([]);
    setLoading(false);
    setError(null);
  };

  const ask = async () => {
    const submittedQuestion = question;
    const current = submittedQuestion.trim();
    if (!current || loading) return;
    const version = requestVersion.current;
    setLoading(true);
    setError(null);
    const history = messages.slice(-6).map(({ question: q, answer }) => ({ question: q, answer }));
    try {
      const result = await projectChat(projectId, { question: current, history });
      if (version !== requestVersion.current) return;
      setMessages((existing) => [...existing, { question: current, ...result }]);
      setQuestion((existing) => (existing === submittedQuestion ? "" : existing));
    } catch (err) {
      if (version === requestVersion.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  return (
    <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-violet-400">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-1">
            {t("整项目对话", "Whole-project chat")}
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {t(
              "跨图谱和源码提问。每次只读下列证据，不假装读完整个项目。",
              "Ask across maps and source. Each answer shows exactly what it read instead of pretending to know the whole tree.",
            )}
          </p>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={clearChat}
            className="shrink-0 text-xs text-gray-400 hover:text-gray-600"
          >
            {t("清空对话", "Clear chat")}
          </button>
        )}
      </div>

      {messages.length > 0 && (
        <div className="mb-4 space-y-3">
          {messages.map((message, index) => (
            <div key={`${message.question}-${index}`} className="space-y-2">
              <div className="rounded-lg bg-violet-50 px-3 py-2 text-sm text-violet-900">
                {message.question}
              </div>
              <div className="rounded-lg bg-gray-50 px-3 py-3">
                <p className="whitespace-pre-wrap text-sm leading-6 text-gray-800">
                  {message.answer}
                </p>
                {message.sources.length > 0 ? (
                  <details className="mt-3 text-xs text-gray-500">
                    <summary className="cursor-pointer select-none">
                      {t(
                        `实际读取 ${message.sources.length} 个源码片段${message.maps_used.length ? ` · ${message.maps_used.length} 张图谱` : ""}`,
                        `${message.sources.length} source excerpts${message.maps_used.length ? ` · ${message.maps_used.length} maps` : ""}`,
                      )}
                    </summary>
                    <ul className="mt-2 space-y-1.5">
                      {message.sources.map((source) => {
                        const label = reasonLabel(source.reason);
                        return (
                          <li key={source.path}>
                            <button
                              type="button"
                              onClick={() => onFileClick(source.path)}
                              className="font-mono text-blue-600 hover:text-blue-800"
                            >
                              {source.path}:{source.line_start}-{source.line_end}
                            </button>
                            <span className="ml-2">{t(label[0], label[1])}</span>
                            {source.truncated && (
                              <span className="ml-2 text-amber-600">{t("已截断", "truncated")}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                    {message.maps_used.length > 0 && (
                      <p className="mt-2 font-mono text-[11px] text-gray-400">
                        {message.maps_used.join(" · ")}
                      </p>
                    )}
                  </details>
                ) : (
                  <p className="mt-3 text-xs text-amber-600">
                    {t("本轮没有可展示的源码证据", "No displayable source evidence for this turn")}
                  </p>
                )}
                {message.truncated && (
                  <p className="mt-2 text-xs text-gray-400">
                    {t("证据经过筛选或截断，不能据此推断未读内容。", "Evidence was selected or truncated; unread code is not evidence.")}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <textarea
        aria-label={t("向整个项目提问", "Ask the whole project")}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            void ask();
          }
        }}
        rows={3}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-300"
        placeholder={t(
          "例如：这个项目怎么启动？数据保存经过哪些文件？",
          "Try: how does this project start, or which files does saving data pass through?",
        )}
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void ask()}
          disabled={!question.trim() || loading}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {loading ? t("正在读取证据并思考…", "Reading evidence and thinking…") : t("提问", "Ask")}
        </button>
        <span className="text-xs text-gray-400">{t("⌘/Ctrl + Enter", "⌘/Ctrl + Enter")}</span>
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </section>
  );
}
