"""Unit tests for `claudevm code`."""
import pytest


@pytest.mark.parametrize("platform", ["Darwin", "Linux"])
def test_code_invokes_vscode_remote_ssh(run_claudevm, code_calls, platform):
    result = run_claudevm(["code", "myproject"], platform=platform)

    assert result.returncode == 0, result.stderr
    calls = [c["args"] for c in code_calls()]
    assert calls == [["--remote", "ssh-remote+lima-myproject", "/workspace"]]


@pytest.mark.parametrize("platform", ["Darwin", "Linux"])
def test_code_errors_clearly_when_cli_missing(run_claudevm, code_calls, platform):
    result = run_claudevm(["code", "myproject"], include_code=False, platform=platform)

    assert result.returncode != 0
    assert result.stderr == (
        "The 'code' CLI isn't on your PATH. In VS Code: Cmd+Shift+P -> "
        "'Shell Command: Install code command in PATH'.\n"
    )
    assert code_calls() == []


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_code_invokes_vscode_remote_ssh_on_real_instance(run_real_claudevm, shared_instance, real_code_calls):
    # `code` itself stays faked even in the integration tier -- this only
    # verifies cmd_code builds the right invocation against a real instance
    # name, not that VS Code actually launches.
    name, project_dir = shared_instance

    result = run_real_claudevm(["code", name], fake_code=True, timeout=30)

    assert result.returncode == 0, result.stderr
    calls = [c["args"] for c in real_code_calls()]
    assert calls == [["--remote", f"ssh-remote+lima-{name}", "/workspace"]]
