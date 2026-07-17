"""Assemble the full deterministic code map as a single Markdown document.

The browser UI renders each analysis (import graph, risk, churn, coverage, ...)
in its own panel. The ``codemap.md`` export stitches the same analyses into one
file you can download and read offline or hand to someone else. Every section is
produced by the service that owns that analysis; this module only decides which
sections run, in what order, and how they are joined.
"""

from __future__ import annotations

from backend.services import (
    action_plan as action_plan_svc,
)
from backend.services import (
    activity,
    apimap,
    async_surface,
    churn,
    ci_checks,
    commands,
    complexity,
    contributing,
    coverage,
    datamodels,
    deep_nesting,
    dependencies,
    docs,
    docstrings,
    entrypoints,
    envscan,
    error_handling,
    importgraph,
    integrations,
    licenses,
    long_functions,
    ownership,
    release_map,
    risk,
    schedules,
    security,
    settings_map,
    techdebt,
    too_many_params,
    typing_coverage,
)
from backend.services import (
    health_score as health_score_svc,
)

_SECTION_SEPARATOR = "\n\n---\n\n"


def _ordered_sections(proj: dict) -> list[str]:
    """Render every optional code-map section in display order.

    Each service returns an empty string when it has nothing to report (for
    example, churn/ownership need git history, so an uploaded folder skips them).
    The import-graph code map is the always-present base and is handled by the
    caller, so it is not part of this list.
    """
    name = proj["name"]
    files = proj["files"]
    contents = proj.get("file_contents", {})

    return [
        risk.render_risk_markdown(
            risk.rank_risk(
                importgraph.rank_hotspots(files, limit=500),
                (proj.get("churn") or {}).get("hotspots", []),
            )
        ),
        churn.render_churn_markdown(name, proj.get("churn")),
        ownership.render_ownership_markdown(name, proj.get("ownership")),
        coverage.render_coverage_markdown(name, coverage.assess_test_coverage(files)),
        techdebt.render_techdebt_markdown(name, techdebt.scan_tech_debt(contents)),
        envscan.render_env_markdown(name, envscan.scan_env_vars(contents)),
        entrypoints.render_entrypoints_markdown(name, entrypoints.find_entry_points(contents)),
        commands.render_commands_markdown(name, commands.find_cli_commands(contents)),
        datamodels.render_data_models_markdown(name, datamodels.find_data_models(contents)),
        settings_map.render_settings_markdown(name, settings_map.find_tunable_settings(contents)),
        schedules.render_schedules_markdown(name, schedules.find_scheduled_tasks(contents)),
        ci_checks.render_ci_checks_markdown(name, ci_checks.find_ci_checks(contents)),
        release_map.render_release_markdown(name, release_map.find_release_info(contents)),
        contributing.render_contributing_markdown(
            name, contributing.find_contribution_guide(contents)
        ),
        licenses.render_licenses_markdown(name, licenses.find_licenses(contents)),
        complexity.render_complexity_markdown(name, complexity.scan_complexity(contents)),
        deep_nesting.render_deep_nesting_markdown(name, deep_nesting.scan_deep_nesting(contents)),
        long_functions.render_long_functions_markdown(
            name, long_functions.scan_long_functions(contents)
        ),
        too_many_params.render_too_many_params_markdown(
            name, too_many_params.scan_too_many_params(contents)
        ),
        dependencies.render_dependencies_markdown(name, dependencies.scan_dependencies(contents)),
        security.render_security_markdown(name, security.scan_security(contents)),
        apimap.render_apimap_markdown(name, apimap.scan_api_routes(contents)),
        docs.render_doc_coverage_markdown(name, docs.assess_doc_coverage(contents)),
        docstrings.render_docstring_coverage_markdown(
            name, docstrings.scan_docstring_coverage(contents)
        ),
        typing_coverage.render_typing_coverage_markdown(
            name, typing_coverage.scan_typing_coverage(contents)
        ),
        async_surface.render_async_surface_markdown(
            name, async_surface.scan_async_surface(contents)
        ),
        error_handling.render_error_handling_markdown(
            name, error_handling.find_swallowed_errors(contents)
        ),
        integrations.render_integrations_markdown(
            name, integrations.detect_external_services(contents)
        ),
        activity.render_activity_markdown(name, proj.get("activity")),
        health_score_svc.render_health_score_markdown(name, proj.get("health_score")),
        action_plan_svc.render_action_plan_markdown(name, proj.get("action_plan")),
    ]


def build_codemap_markdown(proj: dict) -> str:
    """Build the downloadable ``codemap.md`` for a scanned project.

    The import-graph code map always leads; every other analysis is appended only
    when it has content, separated by a horizontal rule.
    """
    markdown = importgraph.render_codemap_markdown(proj["name"], proj["files"])
    for section in _ordered_sections(proj):
        if section:
            markdown = f"{markdown.rstrip()}{_SECTION_SEPARATOR}{section}"
    return markdown
