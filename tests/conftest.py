"""Shared pytest fixtures for claudevm's test suite.

Unit tests (everything NOT marked @pytest.mark.integration) never touch
real Lima or the user's real ~/.config/claudevm / ~/.local/var/claudevm --
`limactl`/`code`/`uname` are faked (see tests/fakes/) and CLAUDEVM_HOME/
CLAUDEVM_INSTANCES point at a fresh temp dir every test.

Integration-tier fixtures (real VM lifecycle) live further down in this
same file -- one tests/ tree, one conftest, per cv-004's design (pytest
markers distinguish tiers, not separate directories or plugin files).
"""
import json
import os
import random
import shutil
import string
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDEVM_BIN = REPO_ROOT / "claudevm"
FAKES_DIR = REPO_ROOT / "tests" / "fakes"

# Modes for an existing fake KVM device; "missing" means no file at all.
KVM_MODES = {"rw": 0o600, "unreadable": 0o200, "unwritable": 0o400}


def make_kvm_device(directory, kvm):
    """make_kvm_device(directory, kvm) -> path for CLAUDEVM_KVM_DEVICE.

    kvm is "missing" or a KVM_MODES key. The unreadable and unwritable
    states skip the calling test as root, which bypasses file modes.
    """
    path = directory / f"fake-kvm-{kvm}"
    if kvm == "missing":
        return path
    if kvm != "rw" and os.geteuid() == 0:
        pytest.skip("file modes do not restrict root")
    if not path.exists():
        path.write_text("")
        path.chmod(KVM_MODES[kvm])
    return path


@pytest.fixture
def fake_home(tmp_path):
    """An isolated $HOME. cmd_new reads $HOME/.gitconfig and $HOME/.vimrc
    to seed dotfiles -- without this, tests would depend on whatever
    happens to be in the real developer's home directory."""
    d = tmp_path / "home"
    d.mkdir()
    return d


@pytest.fixture
def claudevm_home(tmp_path):
    """A fresh CLAUDEVM_HOME, seeded the way install.sh seeds the real one."""
    home = tmp_path / "claudevm-home"
    home.mkdir()
    shutil.copy(REPO_ROOT / "claude-sandbox.yaml", home / "claude-sandbox.yaml")
    return home


@pytest.fixture
def claudevm_instances_dir(tmp_path):
    d = tmp_path / "claudevm-instances"
    d.mkdir()
    return d


@pytest.fixture
def fake_limactl_state(tmp_path):
    state_file = tmp_path / "fake-limactl-state.json"
    state_file.write_text(json.dumps({"instances": {}}))
    return state_file


@pytest.fixture
def fake_limactl_log(tmp_path):
    log_file = tmp_path / "fake-limactl-log.jsonl"
    log_file.write_text("")
    return log_file


@pytest.fixture
def fake_code_log(tmp_path):
    log_file = tmp_path / "fake-code-log.jsonl"
    log_file.write_text("")
    return log_file


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def limactl_calls(fake_limactl_log):
    """limactl_calls() -> list of {"args": [...]}, one per limactl invocation."""
    return lambda: _read_jsonl(fake_limactl_log)


@pytest.fixture
def code_calls(fake_code_log):
    """code_calls() -> list of {"args": [...]}, one per `code` invocation."""
    return lambda: _read_jsonl(fake_code_log)


@pytest.fixture
def limactl_state(fake_limactl_state):
    """limactl_state() -> {"instances": {name: status}}, the fake's current state."""
    return lambda: json.loads(fake_limactl_state.read_text())


@pytest.fixture
def run_claudevm(
    fake_home,
    claudevm_home,
    claudevm_instances_dir,
    fake_limactl_state,
    fake_limactl_log,
    fake_code_log,
    tmp_path,
):
    """run_claudevm(["up", "name"], input="...\\n") -> CompletedProcess.

    Runs the real claudevm script with limactl/code/uname faked and
    HOME/CLAUDEVM_HOME/CLAUDEVM_INSTANCES isolated to this test's own temp
    dirs -- never touches the user's real config, secrets, or dotfiles.

    include_code=False puts a PATH with the fake limactl but no `code` on
    it, for testing cmd_code's "not installed" error path.

    platform is what the fake `uname -s` reports. kvm picks the state of
    the fake device CLAUDEVM_KVM_DEVICE points at (make_kvm_device), so the
    result never depends on the real host's /dev/kvm.
    """

    def _run(args, input=None, timeout=30, include_code=True, platform="Linux", kvm="rw"):
        env = dict(os.environ)
        if include_code:
            env["PATH"] = f"{FAKES_DIR}:{env.get('PATH', '')}"
        else:
            # Not enough to just leave our fake `code` out -- the machine
            # actually running these tests may have a real VS Code CLI
            # installed somewhere on PATH already, which would make cmd_code
            # find that instead of genuinely seeing `code` as missing.
            # Exclude every PATH entry that contains a real `code` binary.
            bin_dir = tmp_path / "fakes-no-code"
            if not bin_dir.exists():
                bin_dir.mkdir()
                (bin_dir / "limactl").symlink_to(FAKES_DIR / "limactl")
                (bin_dir / "uname").symlink_to(FAKES_DIR / "uname")
            real_dirs = env.get("PATH", "").split(os.pathsep)
            filtered_dirs = [d for d in real_dirs if not os.path.isfile(os.path.join(d, "code"))]
            env["PATH"] = os.pathsep.join([str(bin_dir), *filtered_dirs])
        env["HOME"] = str(fake_home)
        env["CLAUDEVM_HOME"] = str(claudevm_home)
        env["CLAUDEVM_INSTANCES"] = str(claudevm_instances_dir)
        env["FAKE_LIMACTL_STATE"] = str(fake_limactl_state)
        env["FAKE_LIMACTL_LOG"] = str(fake_limactl_log)
        env["FAKE_CODE_LOG"] = str(fake_code_log)
        env["FAKE_UNAME_S"] = platform
        env["FAKE_UNAME_M"] = "x86_64"
        env["CLAUDEVM_KVM_DEVICE"] = str(make_kvm_device(tmp_path, kvm))
        return subprocess.run(
            [str(CLAUDEVM_BIN), *args],
            env=env,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return _run


# --- Integration tier: real limactl, real VMs -------------------------------
#
# Nothing here touches real, persistent user state, even though this tier
# drives the real `limactl` and boots real VMs:
#   - CLAUDEVM_HOME/CLAUDEVM_INSTANCES: isolated to temp dirs, same as the
#     unit tier.
#   - Lima's own VM/instance state (normally ~/.lima/<name>): isolated via
#     LIMA_HOME, a real Lima env var -- confirmed (via `limactl info` and an
#     empirical probe boot) that this does NOT force Lima to re-download its
#     cached base image, which is keyed independently off the real $HOME.
#     Set once per session and applied to every call below; test VMs can
#     never appear in the real ~/.lima this way, not just "probably won't
#     collide by name" (though the claudevm-test-* naming stays too, as
#     defense in depth).
#   - cmd_new's ~/.gitconfig/~/.vimrc seeding: isolated via
#     CLAUDEVM_DOTFILES_SOURCE, a claudevm-level env var added specifically
#     for this (defaults to $HOME, so real usage is unaffected).
# The real, unmodified $HOME is deliberately left alone for everything else,
# specifically so Lima's real image-download cache stays warm across runs.


def _test_instance_name():
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"claudevm-test-{suffix}"


@pytest.fixture(scope="session")
def real_claudevm_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("real-claudevm-home")
    shutil.copy(REPO_ROOT / "claude-sandbox.yaml", home / "claude-sandbox.yaml")
    return home


@pytest.fixture(scope="session")
def real_claudevm_instances_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("real-claudevm-instances")


@pytest.fixture(scope="session")
def real_lima_home():
    """An isolated LIMA_HOME for the whole session -- Lima's own VM/instance
    state lives here instead of the real ~/.lima, so test VMs structurally
    cannot appear alongside real instances like deploy-pb/partybot.

    Deliberately NOT tmp_path_factory: pytest's default temp root nests deep
    enough (/private/var/folders/.../pytest-of-<user>/pytest-<N>/...) that
    Lima's own SSH control socket path -- <LIMA_HOME>/<instance>/ssh.sock.*
    -- exceeds macOS's 104-char UNIX_PATH_MAX, confirmed by a real failure
    here. Linux's limit is 108. The resolved /tmp (/private/tmp on macOS)
    is short enough on both to leave headroom for that suffix.
    """
    d = tempfile.mkdtemp(dir=os.path.realpath("/tmp"), prefix="claudevm-lima-home-")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="session")
def real_dotfiles_source(tmp_path_factory):
    """A fake ~/.gitconfig/~/.vimrc source for cmd_new's seeding step, with
    dummy content clearly marked as integration-tier (distinct from the unit
    tier's own dummy dotfiles) so it's unambiguous which tier produced
    something if it ever surfaces in debug output. Seeded rather than left
    empty, so the seed-from-source behavior is still genuinely exercised."""
    d = tmp_path_factory.mktemp("real-dotfiles-source")
    (d / ".gitconfig").write_text(
        "[user]\n"
        "\tname = claudevm-integration-test\n"
        "\temail = claudevm-integration-test@example.invalid\n"
    )
    (d / ".vimrc").write_text(
        '" claudevm-integration-test dummy vimrc -- not a real user\'s vimrc\n'
        "set number\n"
    )
    return d


@pytest.fixture(scope="session")
def run_real_claudevm(
    real_claudevm_home,
    real_claudevm_instances_dir,
    real_lima_home,
    real_dotfiles_source,
    tmp_path_factory,
):
    """run_real_claudevm(["up", "name"]) -> CompletedProcess.

    Runs the real claudevm script against the REAL limactl/code on PATH --
    genuinely boots real VMs. Default timeout is generous (VM boot,
    possibly a cold image download, can take a while); pass timeout= to
    override per call.
    """

    fake_code_dir = tmp_path_factory.mktemp("fake-code-only")
    (fake_code_dir / "code").symlink_to(FAKES_DIR / "code")

    def _run(args, input=None, timeout=600, fake_code=False):
        env = dict(os.environ)
        env["CLAUDEVM_HOME"] = str(real_claudevm_home)
        env["CLAUDEVM_INSTANCES"] = str(real_claudevm_instances_dir)
        env["LIMA_HOME"] = str(real_lima_home)
        env["CLAUDEVM_DOTFILES_SOURCE"] = str(real_dotfiles_source)
        if fake_code:
            # Real limactl, but `code` faked -- exercises cmd_code's actual
            # invocation without launching a real VS Code window. Only
            # `code`: FAKES_DIR also holds fakes for limactl and uname.
            env["PATH"] = f"{fake_code_dir}:{env.get('PATH', '')}"
            env["FAKE_CODE_LOG"] = str(real_claudevm_home / "fake-code-log.jsonl")
        return subprocess.run(
            [str(CLAUDEVM_BIN), *args],
            env=env,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return _run


@pytest.fixture
def real_code_calls(real_claudevm_home):
    """real_code_calls() -> list of {"args": [...]} logged by the fake `code`
    binary when run_real_claudevm(..., fake_code=True) was used."""
    return lambda: _read_jsonl(real_claudevm_home / "fake-code-log.jsonl")


@pytest.fixture(scope="session")
def shared_instance(run_real_claudevm, tmp_path_factory):
    """(name, project_dir), a single real VM created and booted once for
    the whole test session, reused by most integration tests (ssh,
    secrets, ls, down/up resume) that don't need a fresh instance. Torn
    down once at the end of the session."""
    name = _test_instance_name()
    project_dir = tmp_path_factory.mktemp("shared-instance-project")

    # try/finally, not code-after-yield: if `up` fails partway through, the
    # instance may already be partially registered with limactl and must
    # still be cleaned up -- code after a bare yield never runs when the
    # setup itself raises. cmd_rm tolerates a partial/missing instance fine.
    try:
        new_result = run_real_claudevm(["new", name, str(project_dir)])
        assert new_result.returncode == 0, new_result.stderr
        up_result = run_real_claudevm(["up", name])
        assert up_result.returncode == 0, up_result.stderr

        yield name, project_dir
    finally:
        try:
            run_real_claudevm(["rm", name], input="y\n", timeout=120)
        except subprocess.TimeoutExpired:
            pass


@pytest.fixture
def fresh_instance(run_real_claudevm, tmp_path):
    """A factory: fresh_instance() -> (name, project_dir), a brand-new,
    namespaced claudevm-test-* instance via `claudevm new` + `claudevm up`.
    For tests specifically about the creation path itself (mounts,
    project-dir handling) -- everything else should use shared_instance.
    Each created instance is torn down on teardown, even if the test
    fails; one failed cleanup doesn't block the others."""
    created = []

    def _make():
        name = _test_instance_name()
        # Tracked before `up` runs, not after: if `up` fails partway through,
        # the instance may already be partially registered with limactl and
        # must still be cleaned up below (this is exactly what happened
        # during this fixture's own development -- a failed `up` left a real
        # VM behind because this line used to come after the assertion).
        created.append(name)
        project_dir = tmp_path / f"project-{name}"
        project_dir.mkdir()
        new_result = run_real_claudevm(["new", name, str(project_dir)])
        assert new_result.returncode == 0, new_result.stderr
        up_result = run_real_claudevm(["up", name])
        assert up_result.returncode == 0, up_result.stderr
        return name, project_dir

    yield _make

    for name in created:
        try:
            run_real_claudevm(["rm", name], input="y\n", timeout=120)
        except subprocess.TimeoutExpired:
            pass
