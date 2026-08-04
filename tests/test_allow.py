"""Unit tests for `claudevm allow`."""


def _write_fake_editor(tmp_path, log_path):
    # A stand-in $EDITOR that actually exercises write access to the file
    # it's given, rather than just recording that it was invoked -- catches
    # a real class of bug (e.g. permission issues) a pure recorder would
    # miss, per this task's design interview.
    editor = tmp_path / "fake-editor.sh"
    editor.write_text(
        "#!/bin/sh\n"
        'path="$1"\n'
        f'echo "$path" >> "{log_path}"\n'
        'if [ ! -w "$path" ]; then\n'
        f'  echo "NOT WRITABLE: $path" >> "{log_path}"\n'
        "  exit 1\n"
        "fi\n"
        'printf "\\n# appended by fake editor\\n" >> "$path"\n'
    )
    editor.chmod(0o755)
    return editor


def test_allow_requires_existing_config(run_claudevm):
    result = run_claudevm(["allow", "nope"])

    assert result.returncode != 0
    assert "No config found" in result.stderr


def test_allow_gives_editor_the_real_writable_allowlist_path(
    run_claudevm, claudevm_instances_dir, tmp_path
):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    run_claudevm(["new", "myproject", str(project_dir)])
    allowlist_path = claudevm_instances_dir / "myproject" / "allowlist.txt"
    original_content = allowlist_path.read_text()

    editor_log = tmp_path / "editor-log.txt"
    fake_editor = _write_fake_editor(tmp_path, editor_log)

    result = run_claudevm(
        ["allow", "myproject"], extra_env={"EDITOR": str(fake_editor)}
    )

    assert result.returncode == 0, result.stderr
    assert editor_log.read_text().strip() == str(allowlist_path)
    assert "NOT WRITABLE" not in editor_log.read_text()
    # The fake editor actually wrote to the file -- proves real write
    # access, not just that some editor got invoked with the right path.
    assert allowlist_path.read_text() == original_content + "\n# appended by fake editor\n"
