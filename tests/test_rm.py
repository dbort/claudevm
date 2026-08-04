"""Unit tests for `claudevm rm`."""
import pytest


def test_rm_confirmed_removes_vm_and_config(run_claudevm, claudevm_instances_dir, limactl_calls, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    run_claudevm(["up", "myproject"])

    result = run_claudevm(["rm", "myproject"], input="y\n")

    assert result.returncode == 0, result.stderr
    assert not (claudevm_instances_dir / "myproject").exists()
    call_names = [c["args"][0] for c in limactl_calls()]
    assert "stop" in call_names
    assert "delete" in call_names


def test_rm_aborted_keeps_vm_and_config(run_claudevm, claudevm_instances_dir, limactl_calls, tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    run_claudevm(["up", "myproject"])
    calls_before = len(limactl_calls())

    result = run_claudevm(["rm", "myproject"], input="n\n")

    assert result.returncode == 0, result.stderr
    assert "Aborted" in result.stdout
    assert (claudevm_instances_dir / "myproject").exists()
    # No stop/delete calls should have happened after the abort.
    assert len(limactl_calls()) == calls_before


def test_rm_default_answer_is_no(run_claudevm, claudevm_instances_dir, tmp_path):
    # Bare Enter (empty line) must abort, not confirm -- the prompt is [y/N].
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(["rm", "myproject"], input="\n")

    assert result.returncode == 0, result.stderr
    assert (claudevm_instances_dir / "myproject").exists()


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_rm_aborted_survives_on_real_instance(run_real_claudevm, shared_instance, real_claudevm_instances_dir):
    # Safe against shared_instance: an aborted rm must be a no-op, so this
    # can't disturb other tests reusing the same VM.
    name, project_dir = shared_instance

    result = run_real_claudevm(["rm", name], input="n\n", timeout=30)

    assert result.returncode == 0, result.stderr
    assert "Aborted" in result.stdout
    assert (real_claudevm_instances_dir / name).exists()
    ssh_result = run_real_claudevm(["ssh", name, "--", "echo", "still alive"], timeout=30)
    assert ssh_result.returncode == 0, ssh_result.stderr


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_rm_confirmed_deletes_real_instance(run_real_claudevm, fresh_instance, real_claudevm_instances_dir):
    name, project_dir = fresh_instance()

    result = run_real_claudevm(["rm", name], input="y\n", timeout=120)

    assert result.returncode == 0, result.stderr
    assert not (real_claudevm_instances_dir / name).exists()
    list_result = run_real_claudevm(["ls", "--json"], timeout=30)
    assert name not in list_result.stdout
