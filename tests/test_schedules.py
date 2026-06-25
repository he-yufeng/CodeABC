"""Tests for the scheduled & automated tasks map."""

from backend.services.schedules import find_scheduled_tasks, render_schedules_markdown


def test_github_actions_cron_quoted_and_unquoted():
    yaml = """
name: nightly
on:
  schedule:
    - cron: "0 3 * * *"
    - cron: '*/15 * * * *'   # quarter-hour sweep
"""
    result = find_scheduled_tasks({".github/workflows/nightly.yml": yaml})
    tasks = result["tasks"]
    assert [t["mechanism"] for t in tasks] == ["github-actions", "github-actions"]
    assert tasks[0]["name"] == "nightly"  # the workflow file stem
    assert tasks[0]["schedule"] == "0 3 * * *"
    assert tasks[0]["schedule_human"] == "每天 03:00"
    assert tasks[1]["schedule"] == "*/15 * * * *"  # trailing comment not swallowed
    assert tasks[1]["schedule_human"] == "每 15 分钟"
    assert result["mechanisms"] == ["github-actions"]


def test_apscheduler_decorator_and_add_job():
    src = """
@scheduler.scheduled_job("cron", hour=0, minute=30)
def nightly_report():
    pass

@sched.scheduled_job("interval", seconds=30)
async def poll_queue():
    pass

scheduler.add_job(cleanup, "interval", minutes=5)
"""
    by_name = {t["name"]: t for t in find_scheduled_tasks({"jobs.py": src})["tasks"]}
    assert set(by_name) == {"nightly_report", "poll_queue", "cleanup"}
    assert by_name["nightly_report"]["mechanism"] == "apscheduler"
    assert by_name["nightly_report"]["schedule"] == "cron, hour=0, minute=30"
    assert by_name["poll_queue"]["schedule"] == "interval, seconds=30"
    assert by_name["cleanup"]["schedule"] == "interval, minutes=5"


def test_celery_periodic_task_and_crontab_and_beat_schedule():
    src = """
@periodic_task(run_every=crontab(minute=0, hour="*/2"))
def heartbeat():
    pass

beat_schedule = {
    "report": {"task": "tasks.report", "schedule": crontab(hour=7, minute=0)},
}
"""
    result = find_scheduled_tasks({"celery_app.py": src})
    mechs = {t["mechanism"] for t in result["tasks"]}
    assert mechs == {"celery"}
    names = {t["name"] for t in result["tasks"]}
    assert "heartbeat" in names
    assert "周期任务表 (beat_schedule)" in names
    # crontab(...) calls are reported with their args verbatim
    crontabs = [t for t in result["tasks"] if t["schedule"].startswith("crontab(")]
    assert any("hour=7" in t["schedule"] for t in crontabs)


def test_schedule_library_chain():
    src = """
import schedule
schedule.every(10).minutes.do(sync_data)
schedule.every().day.at("10:30").do(send_digest)
"""
    by_name = {t["name"]: t for t in find_scheduled_tasks({"worker.py": src})["tasks"]}
    assert by_name["sync_data"]["mechanism"] == "schedule"
    assert by_name["sync_data"]["schedule"] == "every(10).minutes"
    assert by_name["sync_data"]["schedule_human"] == "每 10 分钟"
    assert by_name["send_digest"]["mechanism"] == "schedule"


def test_fastapi_repeat_every_seconds_to_human():
    src = """
@repeat_every(seconds=3600)
async def refresh_cache():
    pass
"""
    task = find_scheduled_tasks({"main.py": src})["tasks"][0]
    assert task["name"] == "refresh_cache"
    assert task["mechanism"] == "repeat-every"
    assert task["schedule_human"] == "每小时"


def test_node_cron_and_set_interval_and_nestjs():
    js = """
cron.schedule("0 0 * * *", () => backup());
setInterval(() => poll(), 5000);
"""
    by_mech = {t["mechanism"]: t for t in find_scheduled_tasks({"app.js": js})["tasks"]}
    assert by_mech["node-cron"]["schedule"] == "0 0 * * *"
    assert by_mech["node-cron"]["schedule_human"] == "每天 00:00"
    assert by_mech["interval"]["schedule"] == "5000 ms"
    assert by_mech["interval"]["schedule_human"] == "每 5 秒"

    ts = """
class TasksService {
  @Cron("*/5 * * * *")
  handleCron() {}

  @Interval(10000)
  handleInterval() {}
}
"""
    by_name = {t["name"]: t for t in find_scheduled_tasks({"tasks.service.ts": ts})["tasks"]}
    assert by_name["handleCron"]["mechanism"] == "nestjs"
    assert by_name["handleCron"]["schedule"] == "*/5 * * * *"
    assert by_name["handleCron"]["schedule_human"] == "每 5 分钟"
    assert by_name["handleInterval"]["schedule_human"] == "每 10 秒"


def test_cron_to_human_shapes():
    # Drive the gloss through GitHub Actions cron lines.
    def human(expr):
        yaml = f'on:\n  schedule:\n    - cron: "{expr}"\n'
        return find_scheduled_tasks({".github/workflows/w.yml": yaml})["tasks"][0]["schedule_human"]

    assert human("* * * * *") == "每分钟"
    assert human("*/5 * * * *") == "每 5 分钟"
    assert human("0 * * * *") == "每小时整点"
    assert human("0 */2 * * *") == "每 2 小时"
    assert human("30 9 * * *") == "每天 09:30"
    assert human("0 9 * * 1") == "每周一 09:00"
    assert human("0 0 1 * *") == "每月 1 日 00:00"
    # Unusual expressions get no gloss rather than a guess.
    assert human("15 14 1 * 5") == ""


def test_non_scheduling_code_is_not_flagged():
    src = """
def setIntervalHelper():  # name only resembles a timer
    return 1

x = schedule  # a bare reference without an every/do chain
result = add_jobs_count()  # a similarly named helper, not a scheduler call
"""
    assert find_scheduled_tasks({"misc.py": src})["tasks"] == []


def test_sorted_by_path_then_line_total_and_mechanisms():
    files = {
        "b.py": "@repeat_every(seconds=60)\nasync def b_job():\n    pass\n",
        "a.yml": 'on:\n  schedule:\n    - cron: "0 0 * * *"\n',
    }
    result = find_scheduled_tasks(files)
    order = [(t["path"], t["name"]) for t in result["tasks"]]
    assert order == [("a.yml", "a"), ("b.py", "b_job")]
    assert result["total"] == 2
    assert result["mechanisms"] == ["github-actions", "repeat-every"]


def test_limit_caps_list_but_total_counts_all():
    lines = "\n".join(f'cron.schedule("0 {i} * * *", t{i});' for i in range(8))
    result = find_scheduled_tasks({"jobs.js": lines}, limit=3)
    assert result["total"] == 8
    assert len(result["tasks"]) == 3


def test_markdown_render_empty_and_grouped():
    assert render_schedules_markdown("Proj", {"tasks": []}) == ""
    assert render_schedules_markdown("Proj", None) == ""

    data = find_scheduled_tasks(
        {".github/workflows/ci.yml": 'on:\n  schedule:\n    - cron: "0 3 * * *"\n'}
    )
    md = render_schedules_markdown("Proj", data)
    assert "# Proj — 会自己定时跑的任务（自动化 / 定时）" in md
    assert "`.github/workflows/ci.yml`" in md
    assert "GitHub Actions 定时" in md
    assert "每天 03:00" in md
