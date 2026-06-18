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
        {project && project.reading_map && project.reading_map.length > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              建议阅读顺序
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              不用等 AI 分析，先按这条路线快速找到项目入口。
            </p>
            <ol className="space-y-3">
              {project.reading_map.map((step) => (
                <li key={step.path}>
                  <button
                    onClick={() => handleFileClick(step.path)}
                    className="w-full text-left flex gap-3 hover:text-blue-700"
                  >
                    <span className="w-6 h-6 shrink-0 rounded-full bg-blue-50 text-blue-700 text-sm flex items-center justify-center">
                      {step.order}
                    </span>
                    <span>
                      <span className="block font-mono text-sm text-blue-600">
                        {step.path}
                      </span>
                      <span className="block text-sm text-gray-500 mt-0.5">
                        {step.reason}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}

        {/* Deterministic architecture maps (computed from imports, no LLM) */}
        {project &&
          ((project.hotspots?.length ?? 0) > 0 ||
            (project.architecture_layers?.length ?? 0) > 0 ||
            (project.package_dependencies?.length ?? 0) > 0 ||
            (project.blast_radius?.length ?? 0) > 0 ||
            (project.coupling_hotspots?.length ?? 0) > 0 ||
            (project.import_cycles?.length ?? 0) > 0 ||
            (project.orphan_modules?.length ?? 0) > 0) && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                代码地图
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                不用等 AI，这些是直接从文件之间的 import 关系算出来的结构速览。
              </p>

              {project.hotspots && project.hotspots.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    核心文件（被依赖最多）
                  </h3>
                  <ul className="space-y-2">
                    {project.hotspots.map((h) => (
                      <li key={h.path}>
                        <button
                          onClick={() => handleFileClick(h.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="font-mono text-sm text-blue-600">
                            {h.path}
                          </span>
                          <span className="block text-sm text-gray-500 mt-0.5">
                            {h.reason}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {project.architecture_layers &&
                project.architecture_layers.length > 0 && (
                  <div className="mb-5">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      架构分层（第 0 层是地基，越往上越接近入口）
                    </h3>
                    <ul className="space-y-2">
                      {project.architecture_layers.map((a) => (
                        <li key={a.path}>
                          <button
                            onClick={() => handleFileClick(a.path)}
                            className="w-full text-left flex gap-3 items-center hover:text-blue-700"
                          >
                            <span className="w-7 h-6 shrink-0 rounded bg-gray-100 text-gray-600 text-xs flex items-center justify-center">
                              L{a.layer}
                            </span>
                            <span className="font-mono text-sm text-blue-600 truncate">
                              {a.path}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {project.package_dependencies &&
                project.package_dependencies.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      目录之间怎么依赖
                    </h3>
                    <ul className="space-y-3">
                      {project.package_dependencies.map((p) => (
                        <li key={p.package} className="text-sm">
                          <span className="font-mono text-gray-800">
                            {p.package}/
                          </span>
                          {p.depends_on.length > 0 && (
                            <span className="text-gray-500">
                              {" "}
                              → 依赖 {p.depends_on.join("、")}
                            </span>
                          )}
                          <p className="text-gray-500 mt-0.5">{p.reason}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {project.blast_radius && project.blast_radius.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    改动影响面（改这些文件波及最广）
                  </h3>
                  <ul className="space-y-2">
                    {project.blast_radius.map((b) => (
                      <li key={b.path}>
                        <button
                          onClick={() => handleFileClick(b.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="font-mono text-sm text-blue-600">
                            {b.path}
                          </span>
                          <span className="block text-sm text-gray-500 mt-0.5">
                            {b.reason}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {project.coupling_hotspots &&
                project.coupling_hotspots.length > 0 && (
                  <div className="mt-5">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      依赖最多的文件（牵连其他文件最多）
                    </h3>
                    <ul className="space-y-2">
                      {project.coupling_hotspots.map((c) => (
                        <li key={c.path}>
                          <button
                            onClick={() => handleFileClick(c.path)}
                            className="w-full text-left hover:text-blue-700"
                          >
                            <span className="font-mono text-sm text-blue-600">
                              {c.path}
                            </span>
                            <span className="block text-sm text-gray-500 mt-0.5">
                              {c.reason}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {project.import_cycles && project.import_cycles.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    循环依赖（文件互相 import，建议理清）
                  </h3>
                  <ul className="space-y-2">
                    {project.import_cycles.map((c) => (
                      <li key={c.files.join("|")} className="text-sm">
                        <span className="font-mono text-gray-800">
                          {c.files.join(" → ")}
                        </span>
                        <p className="text-gray-500 mt-0.5">{c.reason}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {project.orphan_modules && project.orphan_modules.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    可能没人用的文件（没有被其他文件 import）
                  </h3>
                  <ul className="space-y-2">
                    {project.orphan_modules.map((o) => (
                      <li key={o.path}>
                        <button
                          onClick={() => handleFileClick(o.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="font-mono text-sm text-blue-600">
                            {o.path}
                          </span>
                          <span className="block text-sm text-gray-500 mt-0.5">
                            {o.reason}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

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
