"""Unit tests for `claudevm secrets`.

The interactive flow is driven with a single piped multi-line stdin stream,
one line per prompt in sequence -- `read -s` only suppresses terminal echo,
it doesn't change how `read` consumes input, so no special driver is needed
(resolved during this task's design interview).
"""
import stat

import pytest


def _perm_octal(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_secrets_requires_existing_config(run_claudevm):
    result = run_claudevm(["secrets", "nope"], input="\n")

    assert result.returncode != 0
    assert "No config found" in result.stderr


def test_secrets_saves_both_tokens_on_fresh_instance(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(
        ["secrets", "myproject"],
        input="fake-claude-token\ny\nfake-gh-token\n",
    )

    assert result.returncode == 0, result.stderr
    secrets_dir = claudevm_instances_dir / "myproject" / "secrets"
    claude_file = secrets_dir / "claude_oauth_token.txt"
    gh_file = secrets_dir / "gh_api_token.txt"
    assert claude_file.read_text() == "fake-claude-token"
    assert gh_file.read_text() == "fake-gh-token"
    assert _perm_octal(claude_file) == 0o600
    assert _perm_octal(gh_file) == 0o600
    assert _perm_octal(secrets_dir) == 0o700


def test_secrets_skips_claude_prompt_when_already_saved(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    secrets_dir = claudevm_instances_dir / "myproject" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "claude_oauth_token.txt").write_text("existing-token")

    # Only one prompt left (GitHub); decline it.
    result = run_claudevm(["secrets", "myproject"], input="n\n")

    assert result.returncode == 0, result.stderr
    assert "already saved" in result.stdout
    assert (secrets_dir / "claude_oauth_token.txt").read_text() == "existing-token"


def test_secrets_declining_github_token_skips_it(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])

    result = run_claudevm(
        ["secrets", "myproject"], input="fake-claude-token\nn\n"
    )

    assert result.returncode == 0, result.stderr
    assert "Skipped." in result.stdout
    secrets_dir = claudevm_instances_dir / "myproject" / "secrets"
    assert not (secrets_dir / "gh_api_token.txt").exists()


def test_secrets_offers_to_replace_existing_github_token(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    secrets_dir = claudevm_instances_dir / "myproject" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "claude_oauth_token.txt").write_text("existing-claude-token")
    (secrets_dir / "gh_api_token.txt").write_text("old-gh-token")

    result = run_claudevm(["secrets", "myproject"], input="y\nnew-gh-token\n")

    assert result.returncode == 0, result.stderr
    # `read -p`'s prompt text goes to the controlling TTY, not
    # stdout/stderr -- unobservable under subprocess.run, so this only
    # asserts the behavioral outcome (confirmed replace -> new content).
    assert (secrets_dir / "gh_api_token.txt").read_text() == "new-gh-token"
    assert "Saved. Restart the VM" in result.stdout


def test_secrets_declining_replace_keeps_old_github_token(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    secrets_dir = claudevm_instances_dir / "myproject" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "claude_oauth_token.txt").write_text("existing-claude-token")
    (secrets_dir / "gh_api_token.txt").write_text("old-gh-token")

    result = run_claudevm(["secrets", "myproject"], input="n\n")

    assert result.returncode == 0, result.stderr
    assert (secrets_dir / "gh_api_token.txt").read_text() == "old-gh-token"


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_secrets_are_wired_into_environment_and_git_config_on_next_boot(
    run_real_claudevm, shared_instance
):
    name, project_dir = shared_instance

    secrets_result = run_real_claudevm(
        ["secrets", name], input="fake-claude-token\ny\nfake-gh-token\n", timeout=30
    )
    assert secrets_result.returncode == 0, secrets_result.stderr

    down_result = run_real_claudevm(["down", name], timeout=120)
    assert down_result.returncode == 0, down_result.stderr
    up_result = run_real_claudevm(["up", name], timeout=180)
    assert up_result.returncode == 0, up_result.stderr

    env_result = run_real_claudevm(["ssh", name, "--", "cat", "/etc/environment"], timeout=30)
    assert env_result.returncode == 0, env_result.stderr
    assert 'CLAUDE_CODE_OAUTH_TOKEN="fake-claude-token"' in env_result.stdout
    assert 'GH_TOKEN="fake-gh-token"' in env_result.stdout

    git_result = run_real_claudevm(
        ["ssh", name, "--", "git", "config", "--global", "--get-all",
         'url.https://github.com/.insteadOf'],
        timeout=30,
    )
    assert git_result.returncode == 0, git_result.stderr
    assert "git@github.com:" in git_result.stdout
