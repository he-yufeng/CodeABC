import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { streamOverview, getProject } from "../lib/api";
import { useProjectStore } from "../stores/project";
import { useI18n, LanguageToggle } from "../lib/i18n";
import { friendlyError } from "../lib/errors";

export default function Overview() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { t } = useI18n();
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
        setError(friendlyError(err, t));
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
          {t("← 返回", "← Back")}
        </button>
        <h1 className="text-xl font-semibold text-gray-900">
          {project?.name || t("项目说明书", "Project manual")}
        </h1>
        <LanguageToggle className="ml-auto" />
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        {project && project.reading_map && project.reading_map.length > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("建议阅读顺序", "Suggested reading order")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "不用等 AI 分析，先按这条路线快速找到项目入口。",
                "No AI needed — follow this route to find the project's entry points fast.",
              )}
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

        {/* Project health: a one-glance summary computed from imports, no LLM */}
        {project && project.health && project.health.notes.length > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("项目体检", "Project health")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "不用等 AI，先看这份从依赖关系算出来的整体结构速览。",
                "No AI needed — a structural overview computed from the dependency graph.",
              )}
            </p>
            <ul className="space-y-2">
              {project.health.notes.map((note) => (
                <li
                  key={note}
                  className="flex gap-2 text-sm text-gray-700"
                >
                  <span className="text-blue-500">•</span>
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Risk hotspots: fuse import centrality with git churn (where bugs concentrate) */}
        {project && (project.risk_hotspots?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-amber-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("风险清单（核心 × 高频变动）", "Risk hotspots (core × frequently changed)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "既被很多文件依赖、又改得频繁的文件——bug 最容易出在这里,审查和测试最该优先。",
                "Files that are both heavily depended on and frequently changed — where defects concentrate, and where review and tests pay off first.",
              )}
            </p>
            <ul className="space-y-2">
              {project.risk_hotspots!.map((r) => (
                <li key={r.path}>
                  <button
                    onClick={() => handleFileClick(r.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{r.path}</span>
                    <span className="ml-2 text-xs font-medium text-amber-600">
                      {t(`风险 ${r.score}`, `risk ${r.score}`)}
                    </span>
                    <span className="ml-2 text-xs text-gray-400">
                      {t(
                        `${r.fan_in} 处依赖 · 改 ${r.commits} 次`,
                        `${r.fan_in} dependents · ${r.commits} commits`,
                      )}
                    </span>
                    <span className="block text-sm text-gray-500 mt-0.5">{r.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {project &&
          project.test_coverage &&
          project.test_coverage.total_source_files > 0 && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-emerald-400">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t("测试覆盖", "Test coverage")}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t(
                  "有多少代码文件配了测试,哪些核心文件没测——没测又被很多文件依赖的,改起来最容易出隐患。",
                  "How many code files have tests, and which core files don't — an untested file that many others depend on is the riskiest to change.",
                )}
              </p>
              <div className="mb-4">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium text-gray-700">
                    {t(
                      `${project.test_coverage.tested_files}/${project.test_coverage.total_source_files} 个代码文件有测试`,
                      `${project.test_coverage.tested_files}/${project.test_coverage.total_source_files} code files tested`,
                    )}
                  </span>
                  <span className="font-semibold text-emerald-600">
                    {project.test_coverage.coverage_percent}%
                  </span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2">
                  <div
                    className="bg-emerald-400 h-2 rounded-full"
                    style={{ width: `${project.test_coverage.coverage_percent}%` }}
                  />
                </div>
              </div>
              {project.test_coverage.notes.length > 0 && (
                <ul className="text-sm text-gray-600 space-y-1 mb-4 list-disc list-inside">
                  {project.test_coverage.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}
              {project.test_coverage.untested_core.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    {t("没有测试、最该补的文件", "Untested files worth covering first")}
                  </h3>
                  <ul className="space-y-2">
                    {project.test_coverage.untested_core.map((u) => (
                      <li key={u.path}>
                        <button
                          onClick={() => handleFileClick(u.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="font-mono text-sm text-blue-600">{u.path}</span>
                          {u.fan_in > 0 && (
                            <span className="ml-2 text-xs text-gray-400">
                              {t(`${u.fan_in} 处依赖`, `${u.fan_in} dependents`)}
                            </span>
                          )}
                          <span className="block text-sm text-gray-500 mt-0.5">{u.reason}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
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
                {t("代码地图", "Code map")}
              </h2>
              <p className="text-sm text-gray-500 mb-2">
                {t(
                  "不用等 AI，这些是直接从文件之间的 import 关系算出来的结构速览。",
                  "No AI needed — a structural overview computed straight from the import graph.",
                )}
              </p>
              <a
                href={`/api/project/${projectId}/codemap.md`}
                download={`${project.name || "codemap"}-codemap.md`}
                className="inline-block text-sm text-blue-600 hover:underline mb-4"
              >
                {t("↓ 下载为 Markdown", "↓ Download as Markdown")}
              </a>

              {project.hotspots && project.hotspots.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    {t("核心文件（被依赖最多）", "Core files (most depended on)")}
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
                      {t(
                        "架构分层（第 0 层是地基，越往上越接近入口）",
                        "Architecture layers (L0 is the foundation; higher is closer to entry points)",
                      )}
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
                      {t("目录之间怎么依赖", "How directories depend on each other")}
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
                              → {t("依赖", "depends on")} {p.depends_on.join(t("、", ", "))}
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
                    {t(
                      "改动影响面（改这些文件波及最广）",
                      "Blast radius (changing these ripples the widest)",
                    )}
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
                      {t(
                        "依赖最多的文件（牵连其他文件最多）",
                        "Files with the most dependencies (entangle the most others)",
                      )}
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
                    {t(
                      "循环依赖（文件互相 import，建议理清）",
                      "Circular dependencies (files import each other — worth untangling)",
                    )}
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
                    {t(
                      "可能没人用的文件（没有被其他文件 import）",
                      "Possibly unused files (not imported anywhere)",
                    )}
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

        {/* Change history (mined from git log) — the dynamic counterpart to the
            static code map: how the code actually evolved, not how it imports. */}
        {project &&
          ((project.churn_hotspots?.length ?? 0) > 0 ||
            (project.co_change_couplings?.length ?? 0) > 0) && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t("变更历史", "Change history")}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t(
                  "从 git 提交历史算出，看的是代码怎么演化，和上面的静态结构互补。",
                  "Computed from git history — how the code actually evolved, complementing the static maps above.",
                )}
              </p>

              {project.churn_hotspots && project.churn_hotspots.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    {t("变更热点（改得最频繁）", "Change hotspots (most frequently changed)")}
                  </h3>
                  <ul className="space-y-2">
                    {project.churn_hotspots.map((h) => (
                      <li key={h.path}>
                        <button
                          onClick={() => handleFileClick(h.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="font-mono text-sm text-blue-600">
                            {h.path}
                          </span>
                          <span className="ml-2 text-xs text-gray-400">
                            {t(
                              `${h.commits} 次 · ${h.authors} 人 · ${h.lines_changed} 行`,
                              `${h.commits} commits · ${h.authors} authors · ${h.lines_changed} lines`,
                            )}
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

              {project.co_change_couplings &&
                project.co_change_couplings.length > 0 && (
                  <div className="mt-5">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      {t("变更耦合（总一起改的文件）", "Change coupling (files that change together)")}
                    </h3>
                    <ul className="space-y-2">
                      {project.co_change_couplings.map((c) => (
                        <li key={`${c.file_a}|${c.file_b}`} className="text-sm">
                          <span className="font-mono text-gray-800">
                            {c.file_a} ↔ {c.file_b}
                          </span>
                          <p className="text-gray-500 mt-0.5">{c.reason}</p>
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
              <span className="text-sm text-gray-500">
                {t("正在生成项目说明书...", "Generating the project manual...")}
              </span>
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
                {t(
                  `项目文件 (${overview.files.length} 个)`,
                  `Project files (${overview.files.length})`,
                )}
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
                  {t("怎么跑起来", "How to run it")}
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
                  {t("快捷提示", "Quick tips")}
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
