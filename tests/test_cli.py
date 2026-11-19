"""Unit tests for `claudevm`'s top-level command dispatch."""


def test_secrets_is_an_unknown_command(run_claudevm):
    secrets = run_claudevm(["secrets", "myproject"])
    bogus = run_claudevm(["bogus", "myproject"])

    assert secrets.returncode == bogus.returncode == 1
    assert secrets.stderr == "Unknown command: secrets\n"
    assert secrets.stdout == bogus.stdout
    assert "secrets" not in secrets.stdout
