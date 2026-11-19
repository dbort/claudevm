"""Unit tests for `claudevm up` -- the create-vs-resume branching that this
project's `--mount`-flag and `base:`-template bugs both lived in."""
import pytest


def test_up_requires_existing_config(run_claudevm, limactl_calls):
    result = run_claudevm(["up", "nope"])

    assert result.returncode != 0
    assert "No config found" in result.stderr
    # require_instance should fail before ever touching limactl.
    assert limactl_calls() == []


def test_up_creates_new_instance(run_claudevm, claudevm_instances_dir, limactl_calls, limactl_state, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    new_result = run_claudevm(["new", "myproject", str(project_dir)])
    assert new_result.returncode == 0, new_result.stderr

    result = run_claudevm(["up", "myproject"])

    assert result.returncode == 0, result.stderr
    calls = limactl_calls()
    # First call must be the exists-check; since it's a fresh instance, the
    # create path (a --name=/--tty=/rendered-file `start`) must follow, NOT
    # a bare resume.
    assert calls[0]["args"][:2] == ["list", "-q"]
    start_calls = [c for c in calls if c["args"][0] == "start"]
    assert len(start_calls) == 1
    start_args = start_calls[0]["args"]
    assert any(a == "--name=myproject" for a in start_args)
    assert any(a == "--tty=false" for a in start_args)
    assert limactl_state()["instances"]["myproject"] == "Running"

    rendered = (claudevm_instances_dir / "myproject" / ".lima.yaml").read_text()
    assert "/mnt/claudevm-config" in rendered
    assert "/workspace" in rendered
    # The VM sees only the project dir and its config: no other mount, and
    # nothing else created in the instance dir for one.
    assert rendered.count("mountPoint:") == 2
    assert sorted(p.name for p in (claudevm_instances_dir / "myproject").iterdir()) == [
        ".lima.yaml",
        "project-dir",
    ]


def test_up_resumes_existing_instance_without_recreating(run_claudevm, limactl_calls, limactl_state, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    first_up = run_claudevm(["up", "myproject"])
    assert first_up.returncode == 0, first_up.stderr

    result = run_claudevm(["up", "myproject"])

    assert result.returncode == 0, result.stderr
    calls = limactl_calls()
    # Everything after the (now-successful) exists-check must be a bare
    # `start <name>` -- passing --name=/--tty=/a rendered file to an
    # instance that already exists is what caused the "instance already
    # exists" failure this project hit and fixed once already.
    resume_start_calls = [c for c in calls if c["args"] == ["start", "myproject"]]
    assert len(resume_start_calls) >= 1
    create_style_calls = [
        c for c in calls if c["args"][0] == "start" and any(a.startswith("--name=") for a in c["args"])
    ]
    # Only the very first `up` (the create) should have used --name=.
    assert len(create_style_calls) == 1
    assert limactl_state()["instances"]["myproject"] == "Running"


def test_up_does_not_crash_when_no_ssh_control_socket_exists(run_claudevm, tmp_path):
    # close_ssh_control checks for $HOME/.lima/<name>/ssh.config before
    # doing anything; in the unit tier no real Lima state exists, so this
    # must be a silent no-op, not a failure.
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(["up", "myproject"])

    assert result.returncode == 0, result.stderr


def _new_project(run_claudevm, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    result = run_claudevm(["new", "myproject", str(project_dir)])
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kvm", ["missing", "unreadable", "unwritable"])
def test_up_without_kvm_on_linux_fails_before_create(run_claudevm, limactl_calls, tmp_path, kvm):
    _new_project(run_claudevm, tmp_path)

    result = run_claudevm(["up", "myproject"], kvm=kvm)

    assert result.returncode != 0
    assert str(tmp_path / f"fake-kvm-{kvm}") in result.stderr
    assert "KVM" in result.stderr
    assert limactl_calls() == []


@pytest.mark.parametrize("kvm", ["missing", "unreadable", "unwritable"])
def test_up_without_kvm_on_linux_fails_before_resume(run_claudevm, limactl_calls, tmp_path, kvm):
    _new_project(run_claudevm, tmp_path)
    first_up = run_claudevm(["up", "myproject"])
    assert first_up.returncode == 0, first_up.stderr
    calls_before = len(limactl_calls())

    result = run_claudevm(["up", "myproject"], kvm=kvm)

    assert result.returncode != 0
    assert str(tmp_path / f"fake-kvm-{kvm}") in result.stderr
    assert len(limactl_calls()) == calls_before


def test_up_on_macos_skips_kvm_check(run_claudevm, limactl_state, tmp_path):
    _new_project(run_claudevm, tmp_path)

    result = run_claudevm(["up", "myproject"], platform="Darwin", kvm="missing")

    assert result.returncode == 0, result.stderr
    assert limactl_state()["instances"]["myproject"] == "Running"


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_down_then_up_resumes_real_instance(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    down_result = run_real_claudevm(["down", name], timeout=120)
    assert down_result.returncode == 0, down_result.stderr

    up_result = run_real_claudevm(["up", name], timeout=180)
    assert up_result.returncode == 0, up_result.stderr

    ssh_result = run_real_claudevm(["ssh", name, "--", "echo", "resumed"], timeout=30)
    assert ssh_result.returncode == 0, ssh_result.stderr
    assert ssh_result.stdout == "resumed\n"
