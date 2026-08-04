"""Unit tests for `claudevm ssh`, including the trailing-command forwarding
added specifically so integration tests can verify real VM internals
through this command's actual code path (cv-004 decision #9)."""
import pytest


def test_ssh_interactive_invocation(run_claudevm, limactl_calls):
    run_claudevm(["ssh", "myproject"])

    calls = [c["args"] for c in limactl_calls()]
    assert calls == [["shell", "--workdir", "/workspace", "myproject"]]


def test_ssh_forwards_trailing_command(run_claudevm, limactl_calls):
    run_claudevm(["ssh", "myproject", "--", "echo", "hello"])

    calls = [c["args"] for c in limactl_calls()]
    assert calls == [["shell", "--workdir", "/workspace", "myproject", "--", "echo", "hello"]]


def test_ssh_forwards_multi_word_command(run_claudevm, limactl_calls):
    run_claudevm(["ssh", "myproject", "--", "sh", "-c", "echo hi; env"])

    calls = [c["args"] for c in limactl_calls()]
    assert calls == [
        ["shell", "--workdir", "/workspace", "myproject", "--", "sh", "-c", "echo hi; env"]
    ]


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_ssh_defaults_to_workspace_workdir_on_real_instance(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "pwd"], timeout=30)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "/workspace\n"


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_ssh_forwards_multi_word_command_on_real_instance(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "sh", "-c", "echo one; echo two"], timeout=30)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "one\ntwo\n"
