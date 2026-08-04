"""Unit tests for `claudevm ls` -- the claudevm-managed-only filtering and
synthetic `new` status added in this task (cv-004), moved here from cv-003
since the menubar plugin (cv-003) depends on this interface."""
import json

import pytest


def test_ls_with_no_instances(run_claudevm):
    result = run_claudevm(["ls"])

    assert result.returncode == 0, result.stderr
    assert "No claudevm instances found" in result.stdout


def test_ls_json_with_no_instances(run_claudevm):
    result = run_claudevm(["ls", "--json"])

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_ls_shows_new_status_for_never_booted_instance(run_claudevm, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(["ls", "--json"])

    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)
    assert entries == [
        {"name": "myproject", "status": "new", "projectDir": str(project_dir)}
    ]


def test_ls_shows_real_status_for_booted_instance(run_claudevm, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    run_claudevm(["up", "myproject"])

    result = run_claudevm(["ls", "--json"])

    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)
    assert entries == [
        {"name": "myproject", "status": "Running", "projectDir": str(project_dir)}
    ]


def test_ls_reflects_stopped_status(run_claudevm, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    run_claudevm(["up", "myproject"])
    run_claudevm(["down", "myproject"])

    entries = json.loads(run_claudevm(["ls", "--json"]).stdout)

    assert entries[0]["status"] == "Stopped"


def test_ls_excludes_non_claudevm_instances(run_claudevm, fake_limactl_state):
    # A Lima instance that exists but was never `claudevm new`'d (no
    # $INSTANCES_DIR config) must not appear -- claudevm ls only lists
    # claudevm-managed instances, not every Lima VM on the machine.
    fake_limactl_state.write_text(
        json.dumps({"instances": {"unrelated-vm": "Running"}})
    )

    result = run_claudevm(["ls", "--json"])

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_ls_text_output_includes_header_and_all_columns(run_claudevm, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(["ls"])

    assert result.returncode == 0, result.stderr
    assert "NAME" in result.stdout
    assert "STATUS" in result.stdout
    assert "myproject" in result.stdout
    assert "new" in result.stdout


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_ls_shows_real_running_instance_and_excludes_others(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ls", "--json"], timeout=30)

    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)
    matching = [e for e in entries if e["name"] == name]
    assert len(matching) == 1
    assert matching[0]["status"] == "Running"
    assert matching[0]["projectDir"] == str(project_dir)
    # Real Lima VMs that aren't claudevm-managed (i.e. anything outside this
    # session's isolated CLAUDEVM_INSTANCES dir) must never leak in, even
    # though the same real `limactl list` sees the whole machine.
    assert all(e["name"].startswith("claudevm-test-") for e in entries)
