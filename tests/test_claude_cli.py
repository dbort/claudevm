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


@pytest.mark.integration
@pytest.mark.timeout(1800)
def test_real_instance_boots_after_failed_claude_download_then_retries(run_real_claudevm, fresh_instance):
    # A fresh VM, since this removes the CLI and a failure partway would
    # leave the shared one without it.
    name, project_dir = fresh_instance()

    def ssh(script):
        result = run_real_claudevm(["ssh", name, "--", "sh", "-c", script], timeout=60)
        assert result.returncode == 0, result.stderr
        return result.stdout

    def restart():
        for args in (["down", name], ["up", name]):
            result = run_real_claudevm(args, timeout=600)
            assert result.returncode == 0, result.stderr

    # The installer fetches from both hosts. Lima rewrites only its own
    # host.lima.internal line in /etc/hosts at boot, so the block persists.
    ssh(
        "rm ~/.local/bin/claude && sudo rm /usr/local/bin/claude"
        " && echo '127.0.0.1 claude.ai downloads.claude.ai' | sudo tee -a /etc/hosts"
    )
    restart()
    # Lima runs provisioning from cloud-init's per-boot hook, which appends
    # each boot's output here; the first boot installed cleanly.
    assert "Claude Code CLI install failed" in ssh("sudo cat /var/log/cloud-init-output.log")

    ssh("sudo sed -i '/claude\\.ai/d' /etc/hosts")
    restart()
    assert "Claude Code" in ssh("/usr/local/bin/claude --version")
