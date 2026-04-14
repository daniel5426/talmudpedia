from __future__ import annotations

from pathlib import Path

from app.workers.dev_reload import (
    WorkerProcessInfo,
    acquire_supervisor_lock,
    build_run_celery_command,
    build_worker_process_patterns,
    classify_worker_command,
    extract_queue_fragment,
    has_matching_worker_processes,
    list_matching_worker_processes,
    managed_supervisor_lock_path,
    plan_unmanaged_worker_cleanup,
    snapshot_watch_state,
    watch_state_changed,
)


def test_build_run_celery_command_includes_reload_flag_only_when_requested() -> None:
    script_path = Path("/tmp/run_celery.py")
    celery_args = ["worker", "-Q", "agent_runs", "-l", "info"]

    command = build_run_celery_command(
        script_path=script_path,
        celery_args=celery_args,
        reload_enabled=True,
    )

    assert command[1] == str(script_path)
    assert "--reload" in command
    assert command[-5:] == celery_args

    command_without_reload = build_run_celery_command(
        script_path=script_path,
        celery_args=celery_args,
        reload_enabled=False,
    )
    assert "--reload" not in command_without_reload


def test_build_worker_process_patterns_cover_supervisor_and_direct_worker() -> None:
    patterns = build_worker_process_patterns(queue_fragment="artifact_test")

    assert len(patterns) == 2
    assert "run_celery" in patterns[0]
    assert "artifact_test" in patterns[0]
    assert "celery -A app\\.workers\\.celery_app\\.celery_app worker" in patterns[1]


def test_extract_queue_fragment_returns_queue_list() -> None:
    assert (
        extract_queue_fragment(["worker", "-Q", "apps_build,agent_runs,default", "-l", "info"])
        == "apps_build,agent_runs,default"
    )
    assert extract_queue_fragment(["worker", "-l", "info"]) is None


def test_classify_worker_command_distinguishes_supervisor_managed_and_legacy() -> None:
    queue_fragment = "apps_build,agent_runs,default"

    assert (
        classify_worker_command(
            "python backend/run_celery.py --reload worker -Q apps_build,agent_runs,default -l info",
            queue_fragment,
        )
        == "supervisor"
    )
    assert (
        classify_worker_command(
            "python backend/run_celery.py worker -Q apps_build,agent_runs,default -l info",
            queue_fragment,
        )
        == "managed_worker"
    )
    assert (
        classify_worker_command(
            "python -m celery -A app.workers.celery_app.celery_app worker -Q apps_build,agent_runs,default -l info",
            queue_fragment,
        )
        == "legacy_worker"
    )


def test_list_matching_worker_processes_and_managed_only_filter(monkeypatch) -> None:
    queue_fragment = "apps_build,agent_runs,default"

    class _Completed:
        stdout = "\n".join(
            [
                "100 1 python backend/run_celery.py --reload worker -Q apps_build,agent_runs,default -l info",
                "200 100 python backend/run_celery.py worker -Q apps_build,agent_runs,default -l info",
                "201 200 python backend/run_celery.py worker -Q apps_build,agent_runs,default -l info",
                "300 1 python -m celery -A app.workers.celery_app.celery_app worker -Q apps_build,agent_runs,default -l info",
            ]
        )

    monkeypatch.setattr(
        "app.workers.dev_reload.subprocess.run",
        lambda *args, **kwargs: _Completed(),
    )

    processes = list_matching_worker_processes(queue_fragment)

    assert [process.kind for process in processes] == [
        "supervisor",
        "managed_worker",
        "managed_worker",
        "legacy_worker",
    ]
    assert has_matching_worker_processes(queue_fragment, managed_only=False) is True
    assert has_matching_worker_processes(queue_fragment, managed_only=True) is True


def test_plan_unmanaged_worker_cleanup_targets_root_pools_only() -> None:
    processes = [
        WorkerProcessInfo(pid=100, ppid=1, command="supervisor", kind="supervisor"),
        WorkerProcessInfo(pid=200, ppid=100, command="managed-root", kind="managed_worker"),
        WorkerProcessInfo(pid=201, ppid=200, command="managed-child", kind="managed_worker"),
        WorkerProcessInfo(pid=300, ppid=1, command="legacy-root", kind="legacy_worker"),
        WorkerProcessInfo(pid=301, ppid=300, command="legacy-child", kind="legacy_worker"),
    ]

    planned = plan_unmanaged_worker_cleanup(processes)

    assert [(process.pid, process.kind) for process in planned] == [
        (200, "managed_worker"),
        (300, "legacy_worker"),
    ]


def test_snapshot_watch_state_detects_python_file_changes(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    target = app_dir / "worker.py"
    target.write_text("value = 1\n", encoding="utf-8")

    before = snapshot_watch_state(tmp_path, ["app"])
    target.write_text("value = 2\n", encoding="utf-8")
    after = snapshot_watch_state(tmp_path, ["app"])

    assert str(target.resolve()) in before
    assert watch_state_changed(before, after) is True


def test_snapshot_watch_state_ignores_missing_paths(tmp_path: Path) -> None:
    existing = tmp_path / ".env"
    existing.write_text("A=1\n", encoding="utf-8")

    snapshot = snapshot_watch_state(tmp_path, [".env", "missing_dir"])

    assert snapshot == {str(existing.resolve()): existing.stat().st_mtime_ns}
    assert watch_state_changed(snapshot, dict(snapshot)) is False


def test_acquire_supervisor_lock_uses_queue_specific_path(tmp_path: Path, monkeypatch) -> None:
    queue_fragment = "apps_build,agent_runs,default"
    lock_path = tmp_path / "apps.lock"
    monkeypatch.setattr(
        "app.workers.dev_reload.managed_supervisor_lock_path",
        lambda _queue_fragment: lock_path,
    )

    handle = acquire_supervisor_lock(queue_fragment)
    assert handle is not None
    handle.close()
    assert managed_supervisor_lock_path("artifact_test").name.startswith(
        "talmudpedia-celery-supervisor-"
    )
