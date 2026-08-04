"""Unit tests for `claudevm down`."""


def test_down_stops_the_instance(run_claudevm, limactl_calls, limactl_state, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    run_claudevm(["up", "myproject"])

    result = run_claudevm(["down", "myproject"])

    assert result.returncode == 0, result.stderr
    stop_calls = [c["args"] for c in limactl_calls() if c["args"][0] == "stop"]
    assert stop_calls == [["stop", "myproject"]]
    assert limactl_state()["instances"]["myproject"] == "Stopped"


def test_down_does_not_require_claudevm_config(run_claudevm, limactl_calls):
    # cmd_down calls `limactl stop` directly with no require_instance guard
    # -- it works on any Lima instance, claudevm-managed or not. It still
    # fails here because the fake VM doesn't exist, but the failure must
    # come from limactl itself, not claudevm refusing to even try.
    result = run_claudevm(["down", "some-other-vm"])

    assert result.returncode != 0
    assert "No config found" not in result.stderr
    assert limactl_calls() == [{"args": ["stop", "some-other-vm"]}]
