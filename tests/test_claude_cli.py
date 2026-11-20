"""Integration tests for the Claude Code CLI that claude-sandbox.yaml
installs. The reboot-doesn't-reinstall check lives in
test_up.py::test_down_then_up_resumes_real_instance, which already restarts
the shared VM."""
import pytest

# `claudevm ssh -- cmd` runs cmd in a login shell; this is the PATH a shell
# that skips ~/.profile gets, such as VS Code's integrated terminal.
NO_PROFILE_PATH = "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_real_instance_runs_claude(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "claude", "--version"], timeout=60)

    assert result.returncode == 0, result.stderr
    assert "Claude Code" in result.stdout


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_real_instance_runs_claude_without_profile_path(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "env", NO_PROFILE_PATH, "claude", "--version"], timeout=60)

    assert result.returncode == 0, result.stderr
    assert "Claude Code" in result.stdout


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_real_instance_finds_claude_in_interactive_login_shell(run_real_claudevm, shared_instance):
    name, project_dir = shared_instance

    result = run_real_claudevm(["ssh", name, "--", "bash", "-lic", "command -v claude"], timeout=60)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("/claude"), result.stdout
