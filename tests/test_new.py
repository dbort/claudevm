"""Unit tests for `claudevm new`."""
import pytest


def test_new_requires_project_dir(run_claudevm):
    # Regression test: cmd_new used to default to $PWD when the project-dir
    # argument was omitted, which silently mounted whatever directory the
    # user happened to be standing in (see this project's git history).
    result = run_claudevm(["new", "myproject"])
    assert result.returncode != 0
    assert "project directory required" in result.stderr


def test_new_creates_instance_config(run_claudevm, claudevm_instances_dir, tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    result = run_claudevm(["new", "myproject", str(project_dir)])

    assert result.returncode == 0, result.stderr
    instance_dir = claudevm_instances_dir / "myproject"
    assert instance_dir.is_dir()
    assert (instance_dir / "project-dir").read_text().strip() == str(project_dir)


def test_new_relative_project_dir(run_claudevm, claudevm_instances_dir, tmp_path, monkeypatch):
    project_dir = tmp_path / "relproject"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = run_claudevm(["new", "relproject", "."])

    assert result.returncode == 0, result.stderr
    saved = (claudevm_instances_dir / "relproject" / "project-dir").read_text().strip()
    assert saved == str(project_dir.resolve())


def test_new_seeds_dotfiles_when_present(run_claudevm, claudevm_instances_dir, fake_home, tmp_path):
    (fake_home / ".gitconfig").write_text("[user]\n\tname = Test\n")
    (fake_home / ".vimrc").write_text("set number\n")
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    result = run_claudevm(["new", "myproject", str(project_dir)])

    assert result.returncode == 0, result.stderr
    instance_dir = claudevm_instances_dir / "myproject"
    assert (instance_dir / "gitconfig").read_text() == "[user]\n\tname = Test\n"
    assert (instance_dir / "vimrc").read_text() == "set number\n"


def test_new_skips_dotfiles_when_absent(run_claudevm, claudevm_instances_dir, tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    result = run_claudevm(["new", "myproject", str(project_dir)])

    assert result.returncode == 0, result.stderr
    instance_dir = claudevm_instances_dir / "myproject"
    assert not (instance_dir / "gitconfig").exists()
    assert not (instance_dir / "vimrc").exists()


def test_new_does_not_invoke_limactl(run_claudevm, limactl_calls, tmp_path):
    # Creating config is pure filesystem work -- no VM involved yet.
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    result = run_claudevm(["new", "myproject", str(project_dir)])

    assert result.returncode == 0, result.stderr
    assert limactl_calls() == []


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_new_and_up_mount_project_dir_and_config(run_real_claudevm, fresh_instance):
    name, project_dir = fresh_instance()

    marker = project_dir / "marker.txt"
    marker.write_text("hello from host\n")

    workspace_cat = run_real_claudevm(["ssh", name, "--", "cat", "/workspace/marker.txt"], timeout=30)
    assert workspace_cat.returncode == 0, workspace_cat.stderr
    assert workspace_cat.stdout == "hello from host\n"

    config_check = run_real_claudevm(["ssh", name, "--", "test", "-d", "/mnt/claudevm-config"], timeout=30)
    assert config_check.returncode == 0, config_check.stderr
