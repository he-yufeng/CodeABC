import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { streamOverview, getProject } from "../lib/api";
import { useProjectStore } from "../stores/project";

export default function Overview() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const {
    project,
    overview,
    overviewRaw,
    loading,
    setProject,
    setOverview,
    appendOverviewRaw,
    resetOverviewRaw,
    setLoading,
    setError,
  } = useProjectStore();

  // if we arrived here without project in store (e.g. page refresh),
  // fetch it from the backend
  useEffect(() => {
    if (!projectId || project) return;

    getProject(projectId)
      .then((p) => setProject(p))
      .catch(() => {
        // project doesn't exist anymore, go home
        navigate("/", { replace: true });
      });
  }, [projectId, project, setProject, navigate]);

  // stream the overview once we have a projectId
  useEffect(() => {
    if (!projectId || overview) return;

    setLoading(true);
    resetOverviewRaw();

    streamOverview(
      projectId,
      (chunk) => appendOverviewRaw(chunk),
      (result) => {
        setOverview(result);
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      }
    );
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileClick = (path: string) => {
    navigate(`/project/${projectId}/file/${encodeURIComponent(path)}`);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate("/")}
          className="text-gray-500 hover:text-gray-700"
        >
          ← 返回
        </button>
        <h1 className="text-xl font-semibold text-gray-900">
          {project?.name || "项目说明书"}
        </h1>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        {/* Loading: show raw streaming text */}
        {loading && !overview && (
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-5 h-5 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
              <span className="text-sm text-gray-500">正在生成项目说明书...</span>
            </div>
            {overviewRaw && (
              <pre className="whitespace-pre-wrap text-sm text-gray-600 font-mono">
                {overviewRaw}
              </pre>
            )}
          </div>
        )}

        {/* Rendered overview */}
        {overview && (
          <div className="space-y-6">
            {/* Summary card */}
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {overview.summary}
              </h2>
              <p className="text-gray-600 leading-relaxed">
                {overview.description}
              </p>
            </div>

            {/* File list */}
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                项目文件 ({overview.files.length} 个)
              </h3>
              <div className="space-y-2">
                {overview.files.map((f) => (
                  <button
                    key={f.path}
                    onClick={() => handleFileClick(f.path)}
                    className="w-full text-left flex items-start gap-3 p-3 rounded-lg
                               hover:bg-blue-50 transition-colors group"
                  >
                    <span className="text-lg">
                      {f.importance === "high"
                        ? "🔹"
                        : f.importance === "medium"
                          ? "📄"
                          : "📁"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-sm text-blue-600 group-hover:underline">
                        {f.path}
                      </span>
                      <p className="text-sm text-gray-500 mt-0.5">{f.role}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* How to run */}
            {overview.how_to_run.length > 0 && (
              <div className="bg-white rounded-xl p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  怎么跑起来
                </h3>
                <ol className="list-decimal list-inside space-y-2 text-gray-700">
                  {overview.how_to_run.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {/* Quick tips */}
            {overview.quick_tips.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
                <h3 className="text-lg font-semibold text-amber-900 mb-3">
                  快捷提示
                </h3>
                <ul className="space-y-2 text-amber-800">
                  {overview.quick_tips.map((tip, i) => (
                    <li key={i} className="flex gap-2">
                      <span>💡</span>
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
