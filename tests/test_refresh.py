"""Unit tests for `claudevm refresh`."""
import pytest


def test_refresh_invokes_update_firewall_script(run_claudevm, limactl_calls):
    result = run_claudevm(["refresh", "myproject"])

    assert result.returncode == 0, result.stderr
    calls = [c["args"] for c in limactl_calls()]
    assert calls == [
        ["shell", "myproject", "--", "sudo", "/usr/local/bin/update-firewall.sh"]
    ]
    assert "refreshed" in result.stdout


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_refresh_applies_allowlist_change_immediately(
    run_real_claudevm, shared_instance, real_claudevm_instances_dir
):
    name, project_dir = shared_instance
    allowlist_path = real_claudevm_instances_dir / name / "allowlist.txt"
    original_content = allowlist_path.read_text()

    # example.com isn't in the default allowlist -- must be rejected before
    # we add it.
    blocked = run_real_claudevm(
        ["ssh", name, "--", "curl", "-sS", "--max-time", "10", "https://example.com/"],
        timeout=30,
    )
    assert blocked.returncode != 0, blocked.stdout

    try:
        with allowlist_path.open("a") as f:
            f.write("example.com\n")

        refresh_result = run_real_claudevm(["refresh", name], timeout=60)
        assert refresh_result.returncode == 0, refresh_result.stderr

        allowed = run_real_claudevm(
            ["ssh", name, "--", "curl", "-sS", "--max-time", "10", "https://example.com/"],
            timeout=30,
        )
        assert allowed.returncode == 0, allowed.stderr
    finally:
        allowlist_path.write_text(original_content)
        run_real_claudevm(["refresh", name], timeout=60)
