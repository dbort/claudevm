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

    # Nothing besides the rendered config lands in the instance dir; the
    # rendered mounts are test_up_renders_template_plus_mounts's job.
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


def _start_sizing(limactl_calls):
    """(cpus, memory) from the one create-style `limactl start` call."""
    [start] = [c["args"] for c in limactl_calls() if c["args"][0] == "start"]
    flags = dict(a[2:].split("=", 1) for a in start if a.startswith("--"))
    return flags["cpus"], flags["memory"]


@pytest.mark.parametrize("platform", ["Darwin", "Linux"])
@pytest.mark.parametrize(
    "host, expected",
    [
        ((8, 4), ("4", "4")),  # below both floors
        ((16, 8), ("4", "4")),  # a 16 GB Mac stays at the floors
        ((24, 12), ("6", "6")),
        ((62, 16), ("8", "8")),  # above both caps
    ],
)
def test_up_sizes_new_instance_from_host(run_claudevm, limactl_calls, tmp_path, platform, host, expected):
    _new_project(run_claudevm, tmp_path)

    result = run_claudevm(["up", "myproject"], platform=platform, host=host)

    assert result.returncode == 0, result.stderr
    assert _start_sizing(limactl_calls) == expected


@pytest.mark.parametrize("platform", ["Darwin", "Linux"])
def test_up_env_overrides_host_sizing(run_claudevm, limactl_calls, tmp_path, platform):
    _new_project(run_claudevm, tmp_path)

    result = run_claudevm(
        ["up", "myproject"],
        platform=platform,
        host=(62, 16),
        extra_env={"CLAUDEVM_CPUS": "2", "CLAUDEVM_MEMORY": "3"},
    )

    assert result.returncode == 0, result.stderr
    assert _start_sizing(limactl_calls) == ("2", "3")


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_real_instance_has_zram_swap(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "swapon", "--show=NAME", "--noheadings"], timeout=30)

    assert result.returncode == 0, result.stderr
    assert any(line.startswith("/dev/zram") for line in result.stdout.splitlines()), result.stdout


@pytest.mark.parametrize("platform, mount_type", [("Darwin", ""), ("Linux", "mountType: virtiofs\n")])
def test_up_renders_template_plus_mounts(
    run_claudevm, claudevm_home, claudevm_instances_dir, tmp_path, platform, mount_type
):
    # Darwin's render carries no mountType: vz defaults to virtiofs.
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(["up", "myproject"], platform=platform)

    assert result.returncode == 0, result.stderr
    cfg_dir = claudevm_instances_dir / "myproject"
    template = (claudevm_home / "claude-sandbox.yaml").read_text()
    assert (cfg_dir / ".lima.yaml").read_text() == template + "\n" + mount_type + (
        "mounts:\n"
        f'  - location: "{project_dir}"\n'
        '    mountPoint: "/workspace"\n'
        "    writable: true\n"
        f'  - location: "{cfg_dir}"\n'
        '    mountPoint: "/mnt/claudevm-config"\n'
        "    writable: false\n"
    )


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_real_instance_workspace_mount_type(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance
    result = run_real_claudevm(["ssh", name, "--", "findmnt", "-n", "-o", "FSTYPE", "/workspace"], timeout=30)

    # claudevm sets virtiofs on Linux; vz on macOS defaults to it.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "virtiofs"
