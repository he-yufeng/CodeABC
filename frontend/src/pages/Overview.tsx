import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { streamOverview, getProject } from "../lib/api";
import { useProjectStore } from "../stores/project";
import { useI18n, LanguageToggle } from "../lib/i18n";
import { friendlyError } from "../lib/errors";
import PrReadingCard from "../components/PrReadingCard";

// A plain-language [zh, en] label for a tunable setting's value kind, fed to t().
function settingKindLabel(kind: string): [string, string] {
  switch (kind) {
    case "number":
      return ["数字", "number"];
    case "text":
      return ["文本", "text"];
    case "flag":
      return ["开关", "flag"];
    case "list":
      return ["列表", "list"];
    case "mapping":
      return ["映射", "mapping"];
    default:
      return ["其它", "other"];
  }
}

// A plain-language [zh, en] label for how a scheduled task is wired up, fed to t().
function scheduleMechanismLabel(mechanism: string): [string, string] {
  switch (mechanism) {
    case "github-actions":
      return ["GitHub Actions 定时", "GitHub Actions cron"];
    case "apscheduler":
      return ["APScheduler", "APScheduler"];
    case "celery":
      return ["Celery 定时", "Celery beat"];
    case "schedule":
      return ["schedule 库", "schedule lib"];
    case "repeat-every":
      return ["FastAPI 周期任务", "FastAPI repeat_every"];
    case "node-cron":
      return ["node-cron", "node-cron"];
    case "nestjs":
      return ["NestJS 定时", "NestJS schedule"];
    case "interval":
      return ["setInterval 定时器", "setInterval timer"];
    default:
      return [mechanism, mechanism];
  }
}

// A plain-language [zh, en] label for a CI quality-gate category, fed to t().
function ciCategoryLabel(category: string): [string, string] {
  switch (category) {
    case "lint":
      return ["代码规范检查", "lint"];
    case "format":
      return ["代码格式检查", "formatting"];
    case "typecheck":
      return ["类型检查", "type check"];
    case "test":
      return ["自动化测试", "tests"];
    case "coverage":
      return ["测试覆盖率", "coverage"];
    case "security":
      return ["安全扫描", "security scan"];
    case "build":
      return ["构建打包", "build"];
    case "deploy":
      return ["部署 / 发布", "deploy / release"];
    default:
      return [category, category];
  }
}

// Plain-language family label for a license category. The backend sends the
// category key; the frontend owns the bilingual presentation (same split as
// ciCategoryLabel).
function licenseCategoryLabel(category: string): [string, string] {
  switch (category) {
    case "permissive":
      return ["宽松型", "permissive"];
    case "weak-copyleft":
      return ["弱著佐权", "weak copyleft"];
    case "strong-copyleft":
      return ["强著佐权", "strong copyleft"];
    case "network-copyleft":
      return ["网络著佐权", "network copyleft"];
    case "public-domain":
      return ["公有领域 / 近似放弃版权", "public domain"];
    case "source-available":
      return ["源码可见但非自由", "source-available"];
    default:
      return ["未识别", "unrecognised"];
  }
}

// One-line "what does this family let me do" gloss, the high-value summary for
// the panel. The full four-question table lives in the codemap.md export.
function licenseCategoryOneLiner(category: string): [string, string] {
  switch (category) {
    case "permissive":
      return [
        "几乎想怎么用都行：商用、改造、闭源都可以，只要保留原作者的版权和许可声明。",
        "Use it almost any way you like — commercial, modified, closed-source — as long as you keep the original copyright and license notice.",
      ];
    case "weak-copyleft":
      return [
        "可以商用，但你改动它原有文件的部分要按同样许可公开；你自己新写的文件可以闭源。",
        "Commercial use is fine, but changes to its own files must be shared under the same license; files you write yourself can stay closed.",
      ];
    case "strong-copyleft":
      return [
        "可以商用、可以改，但只要把成品分发出去，整个衍生项目都得按同样的许可一起开源。",
        "You may use and modify it, but once you distribute the result the whole derivative project must be open-sourced under the same license.",
      ];
    case "network-copyleft":
      return [
        "和强著佐权一样，而且更进一步：哪怕只是放在服务器上联网提供服务，也要把源码给用户。",
        "Like strong copyleft, and then some: even offering it as a network service obliges you to give users the source.",
      ];
    case "public-domain":
      return [
        "作者基本放弃了权利，你几乎可以无条件使用，通常连署名都不强制。",
        "The author has essentially waived their rights — you can use it almost unconditionally, usually without even crediting them.",
      ];
    case "source-available":
      return [
        "源码能看，但不等于能随便用。这类许可常限制商用，或禁止拿去做与原产品竞争的服务，务必先读清楚条款。",
        "The source is visible but that does not mean you may use it freely — these licenses often restrict commercial use or forbid competing services. Read the terms first.",
      ];
    default:
      return [
        "找到了许可证但没认出是哪一种，请人工读一下原文，或联系作者确认。",
        "A license was found but not recognised — read the text yourself or ask the author to confirm.",
      ];
  }
}

// Where a license finding came from.
function licenseSourceKindLabel(kind: string): [string, string] {
  switch (kind) {
    case "license-file":
      return ["许可证文件", "LICENSE file"];
    case "manifest":
      return ["项目清单的 license 字段", "manifest license field"];
    case "classifier":
      return ["项目清单的分类标签", "trove classifier"];
    case "spdx-tag":
      return ["源码里的 SPDX 标记", "SPDX tag in source"];
    default:
      return [kind, kind];
  }
}

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
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-sm text-blue-600">
                          {step.path}
                        </span>
                        {step.kind && (
                          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                            {step.kind}
                          </span>
                        )}
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

        {/* Health score: a single letter grade + scored breakdown, the
            quantified executive summary of the structural analyses. */}
        {project &&
          project.health_score &&
          Object.keys(project.health_score.category_scores).length > 0 && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t("代码体检评分", "Code health score")}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t(
                  "把上面所有结构分析拧成一个分数和等级，一眼看出这份代码大概什么水平。",
                  "Every structural analysis above rolled into one grade — a quick sense of where this code stands.",
                )}
              </p>
              {(() => {
                const h = project.health_score!;
                const g = (h.grade || "F").toUpperCase();
                const gradeCls = g.startsWith("A")
                  ? "bg-green-100 text-green-700"
                  : g.startsWith("B")
                    ? "bg-blue-100 text-blue-700"
                    : g.startsWith("C")
                      ? "bg-amber-100 text-amber-700"
                      : "bg-red-100 text-red-700";
                return (
                  <>
                    <div className="flex items-center gap-4 mb-4">
                      <span
                        className={`flex h-14 w-14 items-center justify-center rounded-xl text-2xl font-bold ${gradeCls}`}
                      >
                        {g}
                      </span>
                      <span className="text-2xl font-semibold text-gray-900">
                        {h.score}
                        <span className="text-base font-normal text-gray-400"> / 100</span>
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
                      {Object.entries(h.category_scores).map(([cat, sc]) => {
                        const labels: Record<string, [string, string]> = {
                          security: ["安全", "security"],
                          test_coverage: ["测试覆盖", "test coverage"],
                          activity: ["活跃度", "activity"],
                          complexity: ["复杂度", "complexity"],
                          tech_debt: ["技术债", "tech debt"],
                          architecture: ["架构", "architecture"],
                        };
                        const lab = labels[cat];
                        return (
                          <div key={cat} className="flex items-center justify-between text-sm">
                            <span className="text-gray-600">
                              {lab ? t(lab[0], lab[1]) : cat}
                            </span>
                            <span className="font-mono text-gray-800">{sc}</span>
                          </div>
                        );
                      })}
                    </div>
                    {(h.strengths.length > 0 || h.weaknesses.length > 0) && (
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        {h.strengths.length > 0 && (
                          <div>
                            <h3 className="text-sm font-semibold text-green-700 mb-1">
                              {t("做得好的", "Strengths")}
                            </h3>
                            <ul className="space-y-1">
                              {h.strengths.map((s) => (
                                <li key={s} className="flex gap-2 text-sm text-gray-600">
                                  <span className="text-green-500">+</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {h.weaknesses.length > 0 && (
                          <div>
                            <h3 className="text-sm font-semibold text-amber-700 mb-1">
                              {t("拖后腿的", "Weaknesses")}
                            </h3>
                            <ul className="space-y-1">
                              {h.weaknesses.map((w) => (
                                <li key={w} className="flex gap-2 text-sm text-gray-600">
                                  <span className="text-amber-500">−</span>
                                  <span>{w}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                );
              })()}
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

        {/* Is the project still alive? — git activity tells you whether code
            you're evaluating is maintained or effectively abandoned. */}
        {project && project.activity?.available && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("还在维护吗？", "Is it still maintained?")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "从 git 提交历史看这个项目的「生命体征」：还在更新，还是已经没人动了。",
                "The project's vital signs, read from its git history — still moving, or effectively abandoned.",
              )}
            </p>
            {(() => {
              const a = project.activity!;
              const lbl = a.label;
              const cls =
                lbl === "active"
                  ? "bg-green-100 text-green-700"
                  : lbl === "slowing"
                    ? "bg-amber-100 text-amber-700"
                    : lbl === "abandoned"
                      ? "bg-red-100 text-red-700"
                      : "bg-gray-100 text-gray-500";
              return (
                <>
                  <div className="flex items-center gap-3 flex-wrap mb-3">
                    <span className={`rounded px-2 py-0.5 text-sm font-medium ${cls}`}>
                      {t(a.label_zh || lbl, lbl)}
                    </span>
                    {a.last_commit_days_ago != null && (
                      <span className="text-sm text-gray-600">
                        {t(
                          `最近一次提交：${Math.round(a.last_commit_days_ago)} 天前`,
                          `last commit ${Math.round(a.last_commit_days_ago)} days ago`,
                        )}
                      </span>
                    )}
                    <span className="text-sm text-gray-400">
                      {t(`共 ${a.total_commits} 次提交`, `${a.total_commits} commits`)}
                    </span>
                  </div>
                  {a.top_contributors.length > 0 && (
                    <p className="text-sm text-gray-500">
                      {t("主要贡献者：", "Top contributors: ")}
                      {a.top_contributors
                        .slice(0, 5)
                        .map((c) => `${c.author} (${c.commits})`)
                        .join(" · ")}
                    </p>
                  )}
                  {a.notes.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {a.notes.map((n) => (
                        <li key={n} className="flex gap-2 text-sm text-gray-600">
                          <span className="text-blue-500">•</span>
                          <span>{n}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              );
            })()}
          </section>
        )}

        {/* Priority action plan: turns every analysis into a ranked "what do
            I fix first?" list — the obvious next question after the health score. */}
        {project && (project.action_plan?.items.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-blue-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("先做什么？", "What to fix first")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "把上面所有的体检结果拧成一句话：如果你只有时间做几件事，按这个顺序做。每条都标了大概多大工程量。",
                "Every check above, distilled into one ordered list — if you only have time for a few things, do them in this order. Each is tagged with roughly how big the job is.",
              )}
            </p>
            <ol className="space-y-3">
              {project.action_plan!.items.map((item, i) => {
                const prio =
                  item.priority === "high"
                    ? { zh: "高", en: "high", cls: "bg-red-100 text-red-700" }
                    : item.priority === "medium"
                      ? { zh: "中", en: "medium", cls: "bg-amber-100 text-amber-700" }
                      : { zh: "低", en: "low", cls: "bg-gray-100 text-gray-500" };
                const effort =
                  item.effort === "small"
                    ? t("小改动", "small")
                    : item.effort === "large"
                      ? t("大工程", "large")
                      : t("中等", "medium");
                return (
                  <li key={`${item.title}-${i}`} className="flex gap-3">
                    <span className="w-6 h-6 shrink-0 rounded-full bg-blue-50 text-blue-700 text-sm flex items-center justify-center">
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${prio.cls}`}
                        >
                          {t(prio.zh, prio.en)}
                        </span>
                        <span className="text-sm font-medium text-gray-900">
                          {item.title}
                        </span>
                        <span className="text-xs text-gray-400">
                          {t("工程量", "effort")}: {effort}
                        </span>
                      </div>
                      {item.detail && (
                        <p className="text-sm text-gray-500 mt-0.5">{item.detail}</p>
                      )}
                      {item.target && (
                        <button
                          onClick={() => handleFileClick(item.target)}
                          className="font-mono text-xs text-blue-600 hover:text-blue-800 mt-0.5"
                        >
                          {item.target}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
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
              {project.test_coverage.run_command && (
                <div className="mb-4 text-sm text-gray-600">
                  {project.test_coverage.test_frameworks.length > 0 && (
                    <span>
                      {t("测试框架", "Test runner")}：
                      {project.test_coverage.test_frameworks.join("、")}
                    </span>
                  )}
                  <span className="ml-2">
                    {t("运行", "Run")}:{" "}
                    <code className="px-1.5 py-0.5 bg-gray-100 rounded font-mono text-gray-800">
                      {project.test_coverage.run_command}
                    </code>
                  </span>
                </div>
              )}
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

        {/* Knowledge silos: files whose history is held by a single person (git ownership) */}
        {project && (project.knowledge_silos?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-rose-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("知识孤岛（只压在一个人身上）", "Knowledge silos (held by one person)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这些文件几乎只有一个人改过——ta 离开就没人懂,最该补文档、结对或 code review 分散知识。",
                "Files almost entirely owned by one person — if they leave, nobody understands this code. Worth documenting, pairing, or reviewing to spread the knowledge.",
              )}
            </p>
            <ul className="space-y-2">
              {project.knowledge_silos!.map((s) => (
                <li key={s.path}>
                  <button
                    onClick={() => handleFileClick(s.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{s.path}</span>
                    <span className="ml-2 text-xs font-medium text-rose-600">
                      {t(`${s.primary_author} 占 ${s.ownership}%`, `${s.primary_author} ${s.ownership}%`)}
                    </span>
                    <span className="ml-2 text-xs text-gray-400">
                      {t(`改 ${s.commits} 次`, `${s.commits} commits`)}
                    </span>
                    <span className="block text-sm text-gray-500 mt-0.5">{s.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Tech-debt markers the authors left themselves (TODO/FIXME/HACK/XXX) */}
        {project && (project.tech_debt_files?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-orange-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("待办与技术债（TODO / FIXME / HACK / XXX）", "Tech-debt markers (TODO / FIXME / HACK / XXX)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "作者自己在代码里留的待办标记最多的文件——了解“作者知道哪里还没做好”的最快线索。",
                "Files with the most TODO/FIXME/HACK/XXX markers the authors left themselves — the fastest read on what they know is unfinished.",
              )}
            </p>
            <ul className="space-y-2">
              {project.tech_debt_files!.map((d) => (
                <li key={d.path}>
                  <button
                    onClick={() => handleFileClick(d.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{d.path}</span>
                    <span className="ml-2 text-xs font-medium text-orange-600">
                      {t(`${d.count} 处`, `${d.count} markers`)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* External services — what accounts / keys you need to run it */}
        {project && (project.integrations?.services?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-purple-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("外部服务依赖", "External services it depends on")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "想在自己电脑上把它跑起来，下面这些服务的账号或密钥可能绕不开（有些按使用量收费）。",
                "To run this on your own machine you'll likely need accounts or keys for these services (some bill by usage).",
              )}
            </p>
            <ul className="space-y-2">
              {project.integrations!.services.map((s) => (
                <li key={s.name} className="text-sm">
                  <span className="font-medium text-purple-700">{s.name}</span>
                  <span className="ml-2 text-xs text-gray-400">({s.category})</span>
                  <p className="text-gray-600 mt-0.5">{s.note}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* API endpoints — the URLs a web project exposes to the outside */}
        {project && (project.api_map?.routes?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("对外提供的接口", "Endpoints it exposes")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "如果这是一个网络服务，下面是它对外开放的地址（接口）。每条是「用什么方式访问 + 访问哪个地址 + 由哪段代码处理」。",
                "If this is a web service, these are the addresses (endpoints) it opens up — each is a method, a path, and the code that handles it.",
              )}
              {(project.api_map?.frameworks?.length ?? 0) > 0 && (
                <span className="ml-1 text-gray-400">
                  {t("框架", "framework")}: {project.api_map!.frameworks.join(", ")}
                </span>
              )}
            </p>
            <ul className="space-y-1.5">
              {project.api_map!.routes.map((r, i) => {
                const m = r.method.toUpperCase();
                const cls = m.startsWith("GET")
                  ? "bg-green-100 text-green-700"
                  : m.startsWith("POST")
                    ? "bg-blue-100 text-blue-700"
                    : m.startsWith("DELETE")
                      ? "bg-red-100 text-red-700"
                      : m === "PUT" || m === "PATCH"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-gray-100 text-gray-500";
                return (
                  <li key={`${r.file}-${r.line}-${i}`} className="text-sm flex items-baseline gap-2 flex-wrap">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-mono font-medium ${cls}`}>
                      {m}
                    </span>
                    <span className="font-mono text-gray-800">{r.path}</span>
                    {r.handler && <span className="text-xs text-gray-400">{r.handler}</span>}
                    {r.file && (
                      <button
                        onClick={() => handleFileClick(r.file)}
                        className="font-mono text-xs text-blue-600 hover:text-blue-800"
                      >
                        {r.file}:{r.line}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* Third-party dependencies — what libraries it installs, each in plain words */}
        {project && (project.dependencies?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("用了哪些第三方库", "Third-party libraries it uses")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这个项目装了哪些现成的库，每个大概是干嘛的。常见的库给了大白话解释，没收录的只列名字。",
                "The off-the-shelf libraries this project installs, and what each is for. Common ones get a plain-language note; the rest just list the name.",
              )}
            </p>
            <ul className="space-y-2">
              {project.dependencies!.map((d) => {
                const kindLabel =
                  d.kind === "dev"
                    ? t("开发依赖", "dev")
                    : d.kind === "optional"
                      ? t("可选依赖", "optional")
                      : t("运行依赖", "runtime");
                return (
                  <li key={`${d.manifest}-${d.name}`} className="text-sm">
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-gray-800">{d.name}</span>
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                        {kindLabel}
                      </span>
                    </span>
                    {d.purpose && <p className="text-gray-600 mt-0.5">{d.purpose}</p>}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* Silent failures — where errors are swallowed without a trace */}
        {project && (project.error_handling?.findings?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-red-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("静默失败的地方", "Where errors are silently swallowed")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这些地方把错误接住后什么都不做：出问题时既不报错也不留日志，是 bug 最容易长期藏身的角落。",
                "These catch an error and then do nothing — a real failure leaves no error and no log, the corner where bugs hide longest.",
              )}
            </p>
            <ul className="space-y-2">
              {project.error_handling!.findings.map((f) => (
                <li key={`${f.path}:${f.line}`}>
                  <button
                    onClick={() => handleFileClick(f.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">
                      {f.path}:{f.line}
                    </span>
                    <p className="text-xs text-gray-600 mt-0.5">{f.reason}</p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Security findings — secrets and dangerous calls worth a human look */}
        {project && (project.security?.findings?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-red-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("安全检查发现", "Security findings")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                `扫出 ${project.security!.total} 处，其中 ${project.security!.critical} 处是硬编码密钥或危险调用这类优先项。每一条都附了它引用的原句和一句大白话解释，点进去就能看上下文。`,
                `${project.security!.total} findings, ${project.security!.critical} of them the priority kind (hardcoded secrets, dangerous calls). Each carries the line it matched and a plain-language reason; click through for the context.`,
              )}
            </p>
            <ul className="space-y-2">
              {project.security!.findings.map((f) => (
                <li key={`${f.file}:${f.line}:${f.category}`}>
                  <button
                    onClick={() => handleFileClick(f.file)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">
                      {f.file}:{f.line}
                    </span>
                    <span className="ml-2 inline-block rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700">
                      {f.category}
                    </span>
                    <p className="text-xs text-gray-600 mt-0.5">{f.reason}</p>
                    <p className="text-xs text-gray-400 font-mono mt-0.5 truncate">{f.snippet}</p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Data models — the shapes a project declares */}
        {project && (project.data_models?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-indigo-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("项目里声明的数据模型", "Data models declared in the project")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这些 dataclass / Pydantic 模型 / TypedDict 是项目数据结构的主干，读代码时先把它们看懂，后面处处都是它们的影子。",
                "These dataclasses, Pydantic models, and TypedDicts are the project's data backbone — learn their shapes first and the rest of the code keeps referencing them.",
              )}
            </p>
            <ul className="space-y-2">
              {project.data_models!.map((m) => (
                <li key={`${m.path}:${m.line}:${m.name}`}>
                  <button
                    onClick={() => handleFileClick(m.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{m.name}</span>
                    <span className="ml-2 inline-block rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-700">
                      {m.kind}
                    </span>
                    <span className="ml-2 text-xs text-gray-500">
                      {m.fields.length} {t("个字段", "fields")}
                    </span>
                    <p className="text-xs text-gray-400 font-mono mt-0.5">
                      {m.path}:{m.line}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Unused exports — public symbols nothing else calls */}
        {project && (project.unused_exports?.findings?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-amber-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("没有被调用的公开函数和类", "Public symbols nothing calls")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "这些函数和类的名字在项目其他地方一次都没出现过，是待人工复核的死代码候选，重构时最容易先坏。",
                "These names never appear anywhere else in the project — candidate dead code for human review, usually the first to break in a refactor.",
              )}
            </p>
            <ul className="space-y-2">
              {project.unused_exports!.findings.map((f) => (
                <li key={`${f.path}:${f.line}:${f.name}`}>
                  <button
                    onClick={() => handleFileClick(f.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">
                      {f.path}:{f.line} {f.name}
                    </span>
                    <p className="text-xs text-gray-600 mt-0.5">{f.reason}</p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Documentation coverage — code that's there but unexplained */}
        {project && (project.doc_coverage?.under_documented?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-sky-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("最该补文档的文件", "Files that most need documentation")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                `${project.doc_coverage!.total_source_files} 个源文件里约 ${project.doc_coverage!.doc_percent}% 带注释或文档。下面这些「代码不少、却几乎没解释」的文件，对刚接手的人最难读、改起来最容易踩坑。`,
                `About ${project.doc_coverage!.doc_percent}% of ${project.doc_coverage!.total_source_files} source files carry comments or docs. These have plenty of code but almost no explanation — the hardest to read and the riskiest to change blind.`,
              )}
            </p>
            <ul className="space-y-2">
              {project.doc_coverage!.under_documented.map((d) => (
                <li key={d.path}>
                  <button
                    onClick={() => handleFileClick(d.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{d.path}</span>
                    <p className="text-xs text-gray-600 mt-0.5">{d.reason}</p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Environment variables the code reads — the setup checklist */}
        {project && (project.env_vars?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-sky-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("环境变量（运行前要配什么）", "Environment variables (what to configure)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "代码读取的环境变量,标“必填”的没有默认值、缺了会直接报错。",
                "Environment variables the code reads — the ones marked required have no default and will error if unset.",
              )}
            </p>
            <ul className="flex flex-wrap gap-2">
              {project.env_vars!.map((v) => (
                <li key={v.name}>
                  <span
                    className={`font-mono text-xs px-2 py-1 rounded ${
                      v.required ? "bg-red-50 text-red-700" : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {v.name}
                    {v.required && (
                      <span className="ml-1 font-sans">{t("必填", "required")}</span>
                    )}
                    {v.documented === false && (
                      <span className="ml-1 font-sans rounded bg-amber-100 text-amber-800 px-1">
                        {t("未见文档", "undocumented")}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Entry points — where execution starts / how to run the project */}
        {project && (project.entry_points?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-teal-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("怎么跑起来（入口点）", "How to run it (entry points)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "程序从这些“门”开始运行——作者声明的命令行命令、能直接跑的脚本、按惯例的入口文件。",
                "The doors execution starts from — declared commands, runnable scripts, and conventional entry files.",
              )}
            </p>
            <ul className="space-y-2">
              {project.entry_points!.map((e) => (
                <li key={`${e.path}:${e.command}`}>
                  <button
                    onClick={() => handleFileClick(e.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-teal-700">{e.command}</span>
                    <span className="ml-2 text-xs text-gray-400">{e.path}</span>
                    <span className="block text-sm text-gray-500 mt-0.5">{e.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* CLI commands — the sub-commands you can actually type, once you're past the front door */}
        {project && (project.cli_commands?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-cyan-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("能敲哪些命令（CLI 命令）", "What you can type (CLI commands)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "入口点告诉你“用哪个命令启动”，这里告诉你“启动后能敲哪些子命令”——作者用 argparse / click / typer 声明的命令，以及每个的一句话说明。",
                "Entry points tell you how to start it; this tells you the sub-commands you can run once you're in — declared via argparse / click / typer, each with a one-line description.",
              )}
            </p>
            <ul className="space-y-2">
              {project.cli_commands!.map((c) => (
                <li key={`${c.path}:${c.line}:${c.name}`}>
                  <button
                    onClick={() => handleFileClick(c.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-cyan-700">{c.name}</span>
                    <span className="ml-2 text-xs text-gray-400">{c.framework}</span>
                    <span className="ml-2 text-xs text-gray-400">{c.path}</span>
                    {c.help && (
                      <span className="block text-sm text-gray-500 mt-0.5">{c.help}</span>
                    )}
                    {c.options.length > 0 && (
                      <span className="block font-mono text-xs text-gray-400 mt-0.5">
                        {c.options.join("  ")}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Tunable settings — hard-coded constants a reader might want to change */}
        {project && (project.tunable_settings?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-emerald-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("能改哪些值（可调设置）", "What you can change (tunable settings)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "环境变量是“在代码外面要设置什么”，这里是“代码里面写死、你可能想改的值”——重试次数、超时、默认模型、开关之类。改前看清它在哪、是什么类型。",
                "Env vars are what you set outside the code; these are the values hard-coded inside that you might want to tweak — retry counts, timeouts, default model, feature flags. Check where each lives and its type before changing it.",
              )}
            </p>
            <ul className="space-y-2">
              {project.tunable_settings!.map((s) => (
                <li key={`${s.path}:${s.line}:${s.name}`}>
                  <button
                    onClick={() => handleFileClick(s.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-emerald-700">{s.name}</span>
                    <span className="mx-1 text-sm text-gray-400">=</span>
                    <span className="font-mono text-sm text-gray-700">{s.value}</span>
                    <span className="ml-2 text-xs text-gray-400">{s.path}</span>
                    <span className="ml-2 text-xs rounded bg-emerald-50 text-emerald-600 px-1.5 py-0.5">
                      {t(...settingKindLabel(s.kind))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Config files — the yaml/toml/ini the project ships, and their top-level knobs */}
        {project && (project.config_files?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-lime-500">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("项目自带的配置文件", "Config files the project ships")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "新人改配置不读代码，先开这些文件：config.yaml、settings.toml、*.ini 之类。这里列出每个文件和它的顶层键（TOML/INI 显示为节名），按内容丰富程度排序。",
                "Newcomers configure a project here before reading any code: config.yaml, settings.toml, *.ini and friends. Each file is listed with its top-level keys (sections for TOML/INI), richest first.",
              )}
            </p>
            <ul className="space-y-3">
              {project.config_files!.map((f) => (
                <li key={f.path}>
                  <button
                    onClick={() => handleFileClick(f.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-lime-700">{f.path}</span>
                    <span className="ml-2 text-xs rounded bg-lime-50 text-lime-700 px-1.5 py-0.5">
                      {f.kind}
                    </span>
                    <span className="ml-2 text-xs text-gray-400">
                      {t(`${f.setting_count} 个设置`, `${f.setting_count} settings`)}
                    </span>
                    {(f.sections.length > 0 || f.keys.length > 0) && (
                      <span className="mt-1 flex flex-wrap gap-1.5">
                        {f.sections.map((s) => (
                          <span
                            key={s}
                            className="font-mono text-xs rounded bg-lime-50 text-lime-800 px-1.5 py-0.5"
                          >
                            [{s}]
                          </span>
                        ))}
                        {f.keys.map((k) => (
                          <span
                            key={k}
                            className="font-mono text-xs rounded bg-gray-100 text-gray-600 px-1.5 py-0.5"
                          >
                            {k}
                          </span>
                        ))}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <PrReadingCard />

        {/* Scheduled & automated tasks — what the project runs on its own */}
        {project && (project.scheduled_tasks?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-amber-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("会自己定时跑的任务（自动化）", "What runs on its own (scheduled tasks)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "入口是“我怎么手动启动”，这里是“项目会不会自己定时做点什么”——比如每天发一封报告、每 30 秒重试一次队列、每晚跑一次 CI。这类任务不用你按按钮就会发生，看清它跑什么、多久跑一次。",
                "Entry points are how you start things by hand; these run on their own — a daily report, a queue retried every 30 seconds, a nightly CI job. They fire without you pressing anything, so it helps to see what runs and how often.",
              )}
            </p>
            <ul className="space-y-2">
              {project.scheduled_tasks!.map((s) => (
                <li key={`${s.path}:${s.line}:${s.name}:${s.mechanism}`}>
                  <button
                    onClick={() => handleFileClick(s.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-amber-700">{s.name}</span>
                    {s.schedule_human && (
                      <span className="ml-2 text-sm text-gray-700">{s.schedule_human}</span>
                    )}
                    {s.schedule && (
                      <span className="ml-2 font-mono text-xs text-gray-500">{s.schedule}</span>
                    )}
                    <span className="ml-2 text-xs text-gray-400">{s.path}</span>
                    <span className="ml-2 text-xs rounded bg-amber-50 text-amber-600 px-1.5 py-0.5">
                      {t(...scheduleMechanismLabel(s.mechanism))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* CI quality gates — the checks a change must pass on push / PR */}
        {project && (project.ci_checks?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-sky-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("提交后会自动跑的检查（CI 质量门禁）", "Checks that run on push / PR (CI gates)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "你把改动交上去（push 或开 PR）之后，这些检查会自动跑一遍——可以当成“机器人审稿”，任何一项亮红叉，改动通常就进不去。提前知道有哪几道关卡，红叉就不再吓人。",
                "After you hand a change in (push or open a PR), these run automatically — think of them as a robot reviewer; one red cross usually blocks the merge. Knowing the gates up front makes the red crosses far less scary.",
              )}
            </p>
            <ul className="space-y-2">
              {project.ci_checks!.map((c) => (
                <li key={`${c.path}:${c.line}:${c.category}:${c.tool}`}>
                  <button
                    onClick={() => handleFileClick(c.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="text-xs rounded bg-sky-50 text-sky-700 px-1.5 py-0.5">
                      {t(...ciCategoryLabel(c.category))}
                    </span>
                    <span className="ml-2 font-mono text-sm text-sky-700">{c.tool}</span>
                    {c.trigger && (
                      <span className="ml-2 text-sm text-gray-700">{c.trigger}</span>
                    )}
                    <span className="ml-2 text-xs text-gray-400">{c.path}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Release & versioning — how the project ships new versions, and what changed */}
        {project?.release &&
          (project.release.version ||
            project.release.dynamic_from_vcs ||
            project.release.changelog_path ||
            project.release.automation.length > 0) && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-violet-400">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t("版本与发布（现在第几版、怎么发新版）", "Release & versioning")}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t(
                  "想知道这个项目现在是第几版、出新版本时去哪看改了什么、新版又是怎么发出去的，看这里。",
                  "What version this is, where to see what changed between versions, and how a new release goes out.",
                )}
              </p>

              <div className="mb-3">
                <span className="text-xs rounded bg-violet-50 text-violet-700 px-1.5 py-0.5">
                  {t("当前版本", "Version")}
                </span>
                {project.release.version ? (
                  <>
                    <span className="ml-2 font-mono text-sm font-semibold text-gray-900">
                      {project.release.version}
                    </span>
                    {project.release.scheme_zh && (
                      <span className="ml-2 text-sm text-gray-600">
                        {project.release.scheme_zh}
                      </span>
                    )}
                    {project.release.version_source && (
                      <span className="ml-2 text-xs text-gray-400">
                        {project.release.version_source}
                      </span>
                    )}
                  </>
                ) : project.release.dynamic_from_vcs ? (
                  <span className="ml-2 text-sm text-gray-700">
                    {t("由 git tag 在打包时自动推导", "derived from git tags at build time")}
                  </span>
                ) : (
                  <span className="ml-2 text-sm text-gray-700">
                    {t("没找到写明的版本号", "no declared version found")}
                  </span>
                )}
              </div>

              <div className="mb-3">
                <span className="text-xs rounded bg-violet-50 text-violet-700 px-1.5 py-0.5">
                  {t("更新日志", "Changelog")}
                </span>
                {project.release.changelog_path ? (
                  <button
                    onClick={() => handleFileClick(project.release!.changelog_path)}
                    className="ml-2 text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-violet-700">
                      {project.release.changelog_path}
                    </span>
                    {project.release.changelog_style_zh && (
                      <span className="ml-2 text-sm text-gray-600">
                        {project.release.changelog_style_zh}
                      </span>
                    )}
                  </button>
                ) : (
                  <span className="ml-2 text-sm text-gray-700">
                    {t(
                      "没有更新日志文件，只能翻提交记录或 Release 页面",
                      "no changelog file; check the commits or the Releases page",
                    )}
                  </span>
                )}
              </div>

              {project.release.automation.length > 0 && (
                <div>
                  <span className="text-xs rounded bg-violet-50 text-violet-700 px-1.5 py-0.5">
                    {t("自动发布", "Release pipeline")}
                  </span>
                  <ul className="mt-2 space-y-2">
                    {project.release.automation.map((a) => (
                      <li key={`${a.path}:${a.line}:${a.target}`}>
                        <button
                          onClick={() => handleFileClick(a.path)}
                          className="w-full text-left hover:text-blue-700"
                        >
                          <span className="text-sm font-semibold text-gray-900">{a.target}</span>
                          {a.trigger_zh && (
                            <span className="ml-2 text-sm text-gray-700">{a.trigger_zh}</span>
                          )}
                          <span className="ml-2 text-xs text-gray-400">
                            {a.path}:{a.line}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

        {/* Contribution map — what the project asks of you before it takes a change */}
        {project?.contribution && project.contribution.requirements.length > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-sky-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("怎么给这个项目贡献代码", "How to get a change accepted")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "想把自己的改动提给这个项目，又怕一上来就踩流程的坑被打回？这些是它对贡献者的要求，全部来自项目里现成的“社区规范”文件，提 PR 前照着对一遍。",
                "What this project expects from a contributor — which file to read first, what to sign, how your commits and pull request must look. All read from its community-health files.",
              )}
            </p>

            <ul className="space-y-3">
              {project.contribution.requirements.map((r) => (
                <li key={`${r.kind}:${r.path}:${r.line}`}>
                  <div>
                    <span className="text-xs rounded bg-sky-50 text-sky-700 px-1.5 py-0.5">
                      {r.label_zh}
                    </span>
                    <button
                      onClick={() => handleFileClick(r.path)}
                      className="ml-2 text-left hover:text-blue-700"
                    >
                      <span className="font-mono text-xs text-gray-400">
                        {r.path}
                        {r.line > 0 ? `:${r.line}` : ""}
                      </span>
                    </button>
                  </div>
                  <p className="mt-1 text-sm text-gray-700">{r.detail_zh}</p>
                </li>
              ))}
            </ul>

            {project.contribution.notes.length > 0 && (
              <ul className="mt-4 border-t border-gray-100 pt-3 space-y-1">
                {project.contribution.notes.map((note, i) => (
                  <li key={i} className="text-sm text-gray-600">
                    {note}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* Open-source license — what you're actually allowed to do with the code */}
        {project?.licenses &&
          (project.licenses.found.length > 0 ||
            project.licenses.notes.some((n) => n.includes("没找到许可证"))) && (
            <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-emerald-400">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t(
                  "开源许可证（你能不能用、能不能商用）",
                  "License (what you're allowed to do)",
                )}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t(
                  "许可证决定了你能拿这份代码做什么——能不能商用、能不能闭源用、改了要不要公开。没有许可证不等于免费随便用，默认是“保留所有权利”。",
                  "The license decides what you may do with this code — commercial use, closed-source use, whether changes must be published. No license does not mean free-for-all; the default is all rights reserved.",
                )}
              </p>

              {project.licenses.primary && project.licenses.primary !== "unknown" ? (
                <div className="mb-4">
                  <div>
                    <span className="text-xs rounded bg-emerald-50 text-emerald-700 px-1.5 py-0.5">
                      {t(...licenseCategoryLabel(project.licenses.primary_category))}
                    </span>
                    <span className="ml-2 font-semibold text-gray-900">
                      {project.licenses.found.find(
                        (f) => f.spdx === project.licenses!.primary,
                      )?.name_zh || project.licenses.primary}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mt-2">
                    {t(...licenseCategoryOneLiner(project.licenses.primary_category))}
                  </p>
                </div>
              ) : project.licenses.primary === "unknown" ? (
                <p className="text-sm text-gray-700 mb-4">
                  {t(
                    "找到了许可证文件但没认出是哪一种，请人工读一下原文，或联系作者确认。",
                    "A license file was found but not recognised — read the text yourself or ask the author to confirm.",
                  )}
                </p>
              ) : (
                <p className="text-sm text-amber-700 bg-amber-50 rounded px-3 py-2 mb-4">
                  {t(
                    "⚠ 没找到许可证。没有许可证不等于可以随便用——默认是“保留所有权利”，别人原则上不能合法使用或分发这份代码。如果这是你的项目，建议补一个 LICENSE。",
                    "⚠ No license found. That does not make it free to use — the default is all rights reserved, so others may not legally use or distribute this code. If this is your project, consider adding a LICENSE.",
                  )}
                </p>
              )}

              {project.licenses.found.length > 0 && (
                <ul className="space-y-2">
                  {project.licenses.found.map((f) => (
                    <li key={`${f.source_path}:${f.line}:${f.spdx}`}>
                      <button
                        onClick={() => handleFileClick(f.source_path)}
                        className="w-full text-left hover:text-blue-700"
                      >
                        <span className="text-sm text-emerald-700">
                          {f.name_zh || f.name || t("未识别的许可证", "unrecognised license")}
                        </span>
                        <span className="ml-2 text-xs text-gray-500">
                          {t(...licenseSourceKindLabel(f.source_kind))}
                        </span>
                        <span className="ml-2 text-xs text-gray-400">{f.source_path}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <p className="text-xs text-gray-400 mt-3">
                {t(
                  "以上是大白话概括，不是法律意见；正式用途请读许可证原文或咨询法务。",
                  "This is a plain-language summary, not legal advice; for anything that matters, read the license text or consult a lawyer.",
                )}
              </p>
            </section>
          )}

        {/* Logic complexity — which files carry the gnarliest branching */}
        {project && (project.complexity_files?.length ?? 0) > 0 && (
          <section className="bg-white rounded-xl p-6 shadow-sm mb-6 border-l-4 border-fuchsia-400">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              {t("逻辑复杂度（最难看懂的文件）", "Logic complexity (hardest files to follow)")}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "按代码里的判断分支（if / 循环 / 异常 / 与或 / 三元等）多少排序——分支越多，逻辑越绕、越要小心读。和“被很多文件依赖”“改得勤”是不同的角度。",
                "Ranked by decision points (if / loops / except / and-or / ternaries) — the more branches, the more tangled the logic and the more careful the read. A different axis from how central or how frequently changed a file is.",
              )}
            </p>
            <ul className="space-y-2">
              {project.complexity_files!.map((c) => (
                <li key={c.path}>
                  <button
                    onClick={() => handleFileClick(c.path)}
                    className="w-full text-left hover:text-blue-700"
                  >
                    <span className="font-mono text-sm text-blue-600">{c.path}</span>
                    <span className="ml-2 text-xs font-medium text-fuchsia-600">
                      {t(`复杂度 ${c.complexity}`, `complexity ${c.complexity}`)}
                    </span>
                    <span className="block text-sm text-gray-500 mt-0.5">{c.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
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
              <div className="flex flex-wrap gap-x-4 gap-y-1 mb-4">
                <a
                  href={`/api/project/${projectId}/codemap.md`}
                  download={`${project.name || "codemap"}-codemap.md`}
                  className="inline-block text-sm text-blue-600 hover:underline"
                >
                  {t("↓ 下载为 Markdown", "↓ Download as Markdown")}
                </a>
                <a
                  href={`/api/project/${projectId}/report.html`}
                  download={`${project.name || "codemap"}-report.html`}
                  className="inline-block text-sm text-blue-600 hover:underline"
                >
                  {t("↓ 下载网页报告（可离线发给同事）", "↓ Download HTML report (offline, shareable)")}
                </a>
              </div>

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
