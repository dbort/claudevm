"""Unit tests for install.sh: per-platform dependency handling, and the
install steps that follow it.

Each test runs install.sh with an isolated HOME and a PATH holding only the
coreutils it needs plus logging stubs for the tools under test, so the real
host's Lima, QEMU, Homebrew or dnf never affect the result.
"""
import os
import shutil
import subprocess

import pytest

from conftest import FAKES_DIR, REPO_ROOT, make_kvm_device

INSTALL_SH = REPO_ROOT / "install.sh"
COREUTILS = ["basename", "cat", "chmod", "cp", "dirname", "grep", "mkdir", "mv", "touch"]
INCLUDE_LINE = "Include ~/.lima/*/ssh.config"

# The brew stub "installs" a formula by copying itself to the command the
# formula provides, as later steps run that command.
STUB = """#!/bin/sh
name=$(basename "$0")
printf '%s\\n' "$name $*" >> "{log}"
case "$name" in
  limactl) echo "limactl version 2.3.0" ;;
  brew)
    cmd="$2"
    if [ "$cmd" = lima ]; then cmd=limactl; fi
    cp "$0" "$(dirname "$0")/$cmd"
    ;;
esac
"""

@pytest.fixture
def install_env(tmp_path, fake_home):
    """install_env(tools, platform=..., machine=..., kvm=...) -> (env, log).

    tools names the stubbed commands to put on PATH. Every stub appends
    "<name> <args>" to log when run. kvm is a make_kvm_device state.
    """
    log = tmp_path / "install-tool-log.txt"
    log.write_text("")
    # Created up front so install.sh picks it over /usr/local/bin, which
    # may be writable on the machine running the tests.
    (fake_home / ".local" / "bin").mkdir(parents=True)

    def _make(tools, platform="Linux", machine="x86_64", kvm="rw"):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in COREUTILS:
            real = shutil.which(name)
            assert real, f"{name} not found on PATH"
            (bin_dir / name).symlink_to(real)
        python3 = shutil.which("python3")
        assert python3, "python3 not found on PATH"
        (bin_dir / "python3").symlink_to(python3)
        (bin_dir / "uname").symlink_to(FAKES_DIR / "uname")
        for name in tools:
            stub = bin_dir / name
            stub.write_text(STUB.format(log=log))
            stub.chmod(0o755)

        env = {
            "PATH": str(bin_dir),
            "HOME": str(fake_home),
            "FAKE_UNAME_S": platform,
            "FAKE_UNAME_M": machine,
            "CLAUDEVM_KVM_DEVICE": str(make_kvm_device(tmp_path, kvm)),
        }
        return env, log

    return _make


def run_install(env):
    bash = shutil.which("bash")
    assert bash
    return subprocess.run(
        [bash, str(INSTALL_SH)], env=env, capture_output=True, text=True, timeout=30
    )


def tool_calls(log):
    return log.read_text().splitlines()


def assert_installed(home):
    assert (home / ".config" / "claudevm" / "claude-sandbox.yaml").is_file()
    assert os.access(home / ".local" / "bin" / "claudevm", os.X_OK)
    assert (home / ".ssh" / "config").read_text().startswith(INCLUDE_LINE + "\n")


def assert_nothing_installed(home):
    assert not (home / ".config" / "claudevm").exists()
    assert not (home / ".local" / "bin" / "claudevm").exists()
    assert not (home / ".ssh").exists()


LINUX_DEPS = ["limactl", "qemu-system-x86_64", "jq"]


def test_linux_with_every_dependency_installs(install_env, fake_home):
    env, log = install_env([*LINUX_DEPS, "dnf", "brew", "sudo"])

    result = run_install(env)

    assert result.returncode == 0, result.stderr
    assert_installed(fake_home)
    assert tool_calls(log) == ["limactl --version"]
    assert "'code' CLI isn't on your PATH" in result.stdout
    assert "Cmd+Shift+P" not in result.stdout


def test_linux_reports_every_missing_item_with_dnf_hint(install_env, fake_home, tmp_path):
    env, log = install_env(["dnf", "brew", "sudo"], kvm="missing")

    result = run_install(env)

    assert result.returncode != 0
    missing_line = next(l for l in result.stderr.splitlines() if l.startswith("Missing:"))
    assert missing_line.split()[1:] == [*LINUX_DEPS, str(tmp_path / "fake-kvm-missing")]
    assert "https://lima-vm.io/docs/installation/" in result.stderr
    dnf_lines = [l for l in result.stderr.splitlines() if "sudo dnf install" in l]
    assert len(dnf_lines) == 1
    assert dnf_lines[0].endswith("sudo dnf install qemu-kvm qemu-img jq")
    assert "usermod -aG kvm" in result.stderr
    assert_nothing_installed(fake_home)
    assert tool_calls(log) == []


def test_linux_without_dnf_prints_no_dnf_hint(install_env, fake_home):
    env, log = install_env(["limactl"])

    result = run_install(env)

    assert result.returncode != 0
    assert "Missing: qemu-system-x86_64 jq" in result.stderr
    assert "dnf" not in result.stderr
    assert "lima-vm.io" not in result.stderr
    assert_nothing_installed(fake_home)


@pytest.mark.parametrize("kvm", ["missing", "unreadable", "unwritable"])
def test_linux_missing_only_kvm_prints_no_dnf_hint(install_env, fake_home, tmp_path, kvm):
    env, log = install_env([*LINUX_DEPS, "dnf"], kvm=kvm)

    result = run_install(env)

    assert result.returncode != 0
    assert f"Missing: {tmp_path / f'fake-kvm-{kvm}'}" in result.stderr
    assert "usermod -aG kvm" in result.stderr
    assert "dnf install" not in result.stderr
    assert_nothing_installed(fake_home)
    assert tool_calls(log) == []


def test_linux_checks_qemu_for_host_arch(install_env, fake_home):
    env, log = install_env(["limactl", "jq", "qemu-system-x86_64"], machine="aarch64")

    result = run_install(env)

    assert result.returncode != 0
    assert "Missing: qemu-system-aarch64" in result.stderr
    assert_nothing_installed(fake_home)


def test_macos_installs_missing_lima_and_jq_with_brew(install_env, fake_home):
    # macOS checks neither QEMU nor KVM, so neither is provided here.
    env, log = install_env(["brew"], platform="Darwin", kvm="missing")

    result = run_install(env)

    assert result.returncode == 0, result.stderr
    assert tool_calls(log) == ["brew install lima", "brew install jq", "limactl --version"]
    assert_installed(fake_home)


def test_macos_brew_installs_each_missing_tool(install_env, fake_home):
    env, log = install_env(["brew", "limactl"], platform="Darwin", kvm="missing")

    result = run_install(env)

    assert result.returncode == 0, result.stderr
    assert tool_calls(log) == ["brew install jq", "limactl --version"]
    assert_installed(fake_home)


def test_macos_with_lima_and_jq_runs_no_brew(install_env, fake_home):
    env, log = install_env(["brew", "limactl", "jq"], platform="Darwin", kvm="missing")

    result = run_install(env)

    assert result.returncode == 0, result.stderr
    assert "Cmd+Shift+P" in result.stdout
    assert tool_calls(log) == ["limactl --version"]
    assert_installed(fake_home)


def test_macos_without_brew_names_homebrew(install_env, fake_home):
    env, log = install_env(["limactl"], platform="Darwin")

    result = run_install(env)

    assert result.returncode != 0
    assert "jq not found and Homebrew isn't available" in result.stderr
    assert "brew install jq" in result.stderr
    assert_nothing_installed(fake_home)

