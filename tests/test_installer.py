import json
import os
from pathlib import Path
import pty
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- local-video-knowledge:managed installation-id:"


def environment(tmp_path):
    home = tmp_path / "home with spaces"
    home.mkdir()
    # Avoid inherited real agent homes, package caches, or user configuration.
    return os.environ | {
        "HOME": str(home), "LVK_HOME": str(home / "custom lvk"),
        "CLAUDE_CONFIG_DIR": str(home / "claude settings"),
        "CODEX_HOME": str(home / "codex settings"),
        "LVK_SOURCE": str(ROOT), "LVK_OFFLINE_TEST": "1",
        "LVK_TEST_PYTHON": sys.executable, "TMPDIR": str(tmp_path),
    }


def run(script, env, *args, check=True):
    return subprocess.run(["bash", str(ROOT / script), *args], env=env,
                          text=True, capture_output=True, check=check)


def test_shell_syntax():
    subprocess.run(["bash", "-n", str(ROOT / "install.sh"), str(ROOT / "uninstall.sh")], check=True)


def test_offline_install_upgrade_backups_and_uninstall(tmp_path):
    env = environment(tmp_path)
    skill = Path(env["CLAUDE_CONFIG_DIR"]) / "skills/local-video-knowledge/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("A different skill\n")
    result = run("install.sh", env, "--yes", "--all", "--vault", str(tmp_path / "vault"), "--notes-language", "en")
    assert "OFFLINE TEST" in result.stdout
    assert "Backed up existing skill" in result.stdout
    assert MARKER in skill.read_text()
    backups = list(skill.parent.glob("SKILL.md.bak-*"))
    assert len(backups) == 1 and backups[0].read_text() == "A different skill\n"
    installed_home = Path(env["LVK_HOME"])
    assert (installed_home / "src/local_video_knowledge/job.py").exists()
    codex = Path(env["CODEX_HOME"]) / "skills/local-video-knowledge/SKILL.md"
    assert MARKER in codex.read_text()
    wrapper = installed_home / "bin/lvk"
    assert f'Installed wrapper: `"{wrapper}"`' in skill.read_text()
    assert "<!-- local-video-knowledge:wrapper -->" not in skill.read_text()
    link = Path(env["HOME"]) / ".local/bin/lvk"
    assert link.is_symlink()
    # The installed wrapper must retain LVK_HOME in a fresh shell.
    fresh_env = env.copy()
    del fresh_env["LVK_HOME"]
    response = subprocess.run([str(link), "config", "get", "notes_language", "--json"], env=fresh_env,
                              capture_output=True, text=True, check=True)
    assert '"notes_language": "en"' in response.stdout
    targets = installed_home / ".skill-targets"
    # Simulate the duplicates left by previous installer versions.
    targets.write_text(targets.read_text() * 2)
    run("install.sh", env, "--yes", "--all")
    assert targets.read_text().splitlines() == [str(skill.parent), str(codex.parent)]
    assert len(list(skill.parent.glob("SKILL.md.bak-*"))) == 1
    codex.write_text("Replaced by the user\n")
    unrelated = Path(env["HOME"]) / "keep"
    unrelated.write_text("preserved")
    run("uninstall.sh", env)
    assert not installed_home.exists()
    assert not link.is_symlink()
    assert not skill.exists()
    assert backups[0].exists()
    assert codex.read_text() == "Replaced by the user\n"
    assert unrelated.exists()


@pytest.mark.parametrize("flag,target,other", [("--claude", "CLAUDE_CONFIG_DIR", "CODEX_HOME"), ("--codex", "CODEX_HOME", "CLAUDE_CONFIG_DIR")])
def test_explicit_target(tmp_path, flag, target, other):
    env = environment(tmp_path)
    run("install.sh", env, "--yes", flag)
    assert (Path(env[target]) / "skills/local-video-knowledge/SKILL.md").exists()
    assert not (Path(env[other]) / "skills/local-video-knowledge/SKILL.md").exists()


def test_piped_installer_and_default_home(tmp_path):
    env = environment(tmp_path)
    del env["LVK_HOME"]
    env["LVK_SOURCE"] = "."
    result = subprocess.run(["bash", "-s", "--", "--yes", "--all"], input=(ROOT / "install.sh").read_text(),
                            cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    assert "Next:" in result.stdout
    assert (Path(env["HOME"]) / ".local-video-knowledge/src/SKILL.md").exists()


def test_uninstall_refuses_unowned_home(tmp_path):
    env = environment(tmp_path)
    directory = Path(env["LVK_HOME"])
    directory.mkdir()
    (directory / "keep").write_text("user data")
    result = run("uninstall.sh", env, check=False)
    assert result.returncode != 0
    assert (directory / "keep").exists()


@pytest.mark.parametrize("reserved", ["src", "venv", "bin", "state", "config.json", ".lvk-installation", ".lvk-manifest", ".skill-targets"])
@pytest.mark.parametrize("symlink", [False, True])
def test_install_refuses_unmarked_owned_path_before_writes(tmp_path, reserved, symlink):
    env = environment(tmp_path)
    directory = Path(env["LVK_HOME"])
    directory.mkdir()
    (directory / "keep").write_text("personal")
    path = directory / reserved
    if symlink:
        path.symlink_to(tmp_path / "missing")
    else:
        path.write_text("unowned")
    result = run("install.sh", env, "--yes", "--all", check=False)
    assert result.returncode != 0
    assert sorted(p.name for p in directory.iterdir()) == sorted(["keep", reserved])
    assert (directory / "keep").read_text() == "personal"
    assert not (Path(env["HOME"]) / ".local/bin").exists()


def test_install_and_uninstall_preserve_unrelated_unmarked_home(tmp_path):
    env = environment(tmp_path)
    directory = Path(env["LVK_HOME"])
    directory.mkdir()
    (directory / "keep").write_text("personal")
    run("install.sh", env, "--yes", "--all")
    run("uninstall.sh", env)
    assert sorted(p.name for p in directory.iterdir()) == ["keep"]
    assert (directory / "keep").read_text() == "personal"


def test_uninstall_preserves_unrecorded_home_file(tmp_path):
    env = environment(tmp_path)
    run("install.sh", env, "--yes", "--all")
    home = Path(env["LVK_HOME"])
    (home / "personal.txt").write_text("keep")
    run("uninstall.sh", env)
    assert (home / "personal.txt").read_text() == "keep"


def test_uninstall_preserves_preexisting_empty_install_directory(tmp_path):
    env = environment(tmp_path)
    home = Path(env["LVK_HOME"])
    home.mkdir()
    run("install.sh", env, "--yes", "--all")
    run("uninstall.sh", env)
    assert home.is_dir()
    assert not list(home.iterdir())


def test_old_install_cannot_remove_new_install_skill(tmp_path):
    env = environment(tmp_path)
    first = env["LVK_HOME"]
    run("install.sh", env, "--yes", "--all")
    env["LVK_HOME"] = str(Path(env["HOME"]) / "second install")
    run("install.sh", env, "--yes", "--all")
    skill = Path(env["CODEX_HOME"]) / "skills/local-video-knowledge/SKILL.md"
    assert env["LVK_HOME"] in skill.read_text()
    env["LVK_HOME"] = first
    run("uninstall.sh", env)
    assert skill.exists()
    assert str(Path(env["HOME"]) / "second install") in skill.read_text()


def test_unknown_flag_rejected_before_install(tmp_path):
    env = environment(tmp_path)
    result = run("install.sh", env, "--surprise", check=False)
    assert result.returncode != 0
    assert not Path(env["LVK_HOME"]).exists()


def run_with_tty(env, *args, answer="\n"):
    master, slave = pty.openpty()
    try:
        with subprocess.Popen(
            ["bash", str(ROOT / "install.sh"), "--all", "--vault", "", "--notes-language", "", *args],
            env=env, stdin=slave, stdout=slave, stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            os.close(slave)
            slave = None
            os.write(master, answer.encode())
            _, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr.decode()
            return os.read(master, 65536).decode()
    finally:
        os.close(master)
        if slave is not None:
            os.close(slave)


@pytest.mark.parametrize("shell,platform,existing,expected", [
    ("/bin/zsh", "Darwin", None, ".zshrc"),
    ("/bin/bash", "Linux", None, ".bashrc"),
    ("/bin/bash", "Darwin", None, ".bash_profile"),
    ("/bin/bash", "Darwin", ".bashrc", ".bashrc"),
    ("/bin/bash", "Darwin", ".bash_profile", ".bash_profile"),
])
def test_tty_path_opt_in_and_rc_selection(tmp_path, shell, platform, existing, expected):
    env = environment(tmp_path)
    env["SHELL"] = shell
    # Exercise macOS rc selection on Linux without claiming a macOS execution.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    uname = binaries / "uname"
    uname.write_text(f"#!/bin/sh\nprintf '%s\\n' '{platform}'\n")
    uname.chmod(0o755)
    env["PATH"] = f"{binaries}:/usr/bin:/bin"
    if existing:
        (Path(env["HOME"]) / existing).write_text("# Keep my settings\n")
    output = run_with_tty(env, answer="y\n")
    assert "[y/N]" in output
    rc = Path(env["HOME"]) / expected
    assert rc.read_text().endswith('export PATH="$HOME/.local/bin:$PATH"\n')
    if existing:
        assert rc.read_text().startswith("# Keep my settings\n")
    previous = rc.read_text()
    run_with_tty(env, answer="y\n")
    assert rc.read_text() == previous


@pytest.mark.parametrize("args,answer", [((), "\n"), ((), "n\n"), (("--yes",), "y\n")])
def test_tty_path_default_no_and_yes_flag(tmp_path, args, answer):
    env = environment(tmp_path)
    env.update(SHELL="/bin/zsh", PATH="/usr/bin:/bin")
    run_with_tty(env, *args, answer=answer)
    assert not (Path(env["HOME"]) / ".zshrc").exists()


def test_noninteractive_never_edits_rc(tmp_path):
    env = environment(tmp_path)
    env.update(SHELL="/bin/zsh", PATH="/usr/bin:/bin")
    subprocess.run(
        ["bash", str(ROOT / "install.sh"), "--all", "--vault", "", "--notes-language", ""],
        env=env, input="y\n", capture_output=True, text=True, check=True,
    )
    assert not (Path(env["HOME"]) / ".zshrc").exists()


def test_path_already_available_does_not_offer_rc_edit(tmp_path):
    env = environment(tmp_path)
    env.update(SHELL="/bin/zsh", PATH=f'{env["HOME"]}/.local/bin:/usr/bin:/bin')
    assert "[y/N]" not in run_with_tty(env, answer="y\n")
    assert not (Path(env["HOME"]) / ".zshrc").exists()


def test_piped_install_offers_rc_edit_on_controlling_tty(tmp_path):
    import fcntl
    import termios

    env = environment(tmp_path)
    env.update(SHELL="/bin/bash", PATH="/usr/bin:/bin")
    master, slave = pty.openpty()
    try:
        def controlling_tty():
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        with subprocess.Popen(
            ["bash", "-s", "--", "--all", "--vault", "", "--notes-language", ""],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=slave, stderr=slave,
            start_new_session=True, preexec_fn=controlling_tty,
        ) as process:
            os.close(slave)
            slave = None
            os.write(master, b"y\n")
            process.communicate(input=(ROOT / "install.sh").read_bytes(), timeout=15)
            assert process.returncode == 0
            output = os.read(master, 65536).decode()
            assert "[y/N]" in output
            assert (Path(env["HOME"]) / ".bashrc").read_text().endswith(
                'export PATH="$HOME/.local/bin:$PATH"\n'
            )
    finally:
        os.close(master)
        if slave is not None:
            os.close(slave)


def test_runtime_state_job_clean_uninstall_reinstall(tmp_path):
    env = environment(tmp_path)
    run("install.sh", env, "--yes", "--all")
    home = Path(env["LVK_HOME"])
    assert (home / "state").is_dir()
    assert "home:state" in (home / ".lvk-manifest").read_text().splitlines()
    # Execute installed source with the test interpreter; the offline venv is stubbed.
    script = '''
import json
from pathlib import Path
from unittest.mock import patch
from local_video_knowledge import job

clips = Path("clips")
clips.mkdir(exist_ok=True)
(clips / "a.mp4").write_bytes(b"x")

def transcribe(engine, media, output, language, vocabulary, on_progress):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("[00:00:00] Lifecycle speech")
    return {"language": "en", "lines": 1}

with patch.object(job, "probe", return_value={"duration": 1.0, "has_audio": True, "recorded_date": None}), \
        patch.object(job, "load_model", return_value=object()), patch.object(job, "transcribe", transcribe):
    result = job.start(clips.resolve(), foreground=True)
    assert result["state"] == "complete", result
    assert job.clean(result["workdir"], result["lease"])["removed"]
    print(json.dumps(result))
'''
    runtime = subprocess.run([sys.executable, "-c", script.replace('Path("clips")', f'Path({str(tmp_path / "clips")!r})')],
                             cwd=home / "src", env=env | {"PYTHONPATH": str(home / "src")}, capture_output=True, text=True, check=True)
    workdir = Path(json.loads(runtime.stdout)["workdir"])
    assert not workdir.exists()
    assert list((home / "state/locks").glob("*.lock"))
    assert not (home / "workdirs").exists()
    assert not list(workdir.parent.glob(".lvk-*.lock"))
    (home / "unrelated.txt").write_text("user data")
    run("uninstall.sh", env)
    assert sorted(p.name for p in home.iterdir()) == ["unrelated.txt"]
    assert (home / "unrelated.txt").read_text() == "user data"
    run("install.sh", env, "--yes", "--all")
    assert (home / "state").is_dir()
    assert (home / "unrelated.txt").read_text() == "user data"
    (home / "state/nested").mkdir()
    (home / "state/nested/owned").write_text("runtime data")
    run("uninstall.sh", env)
    assert (home / "unrelated.txt").read_text() == "user data"
    assert sorted(p.name for p in home.iterdir()) == ["unrelated.txt"]


def test_uninstall_refuses_while_worker_runs(tmp_path):
    env = environment(tmp_path)
    run("install.sh", env, "--yes", "--all")
    home = Path(env["LVK_HOME"])
    # A process whose command line matches this installation's worker.
    fake = subprocess.Popen(["bash", "-c", "exec -a \"$0\" sleep 30",
                             f"{home}/venv/bin/python -m local_video_knowledge.job"])
    try:
        result = run("uninstall.sh", env, check=False)
        assert result.returncode != 0 and "still running" in result.stderr
        assert (home / "state").is_dir()
    finally:
        fake.kill()
        fake.wait()
    run("uninstall.sh", env)
    assert not (home / "state").exists()
