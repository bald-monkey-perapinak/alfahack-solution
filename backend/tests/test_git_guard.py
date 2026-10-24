import secrets
import subprocess

from scripts import check_secrets


def test_secret_in_index_is_found_even_when_worktree_is_clean(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(check_secrets, "ROOT", tmp_path)
    path = tmp_path / "config.py"
    value = secrets.token_hex(32)
    path.write_text("api_" + "key = " + repr(value))
    subprocess.run(["git", "add", "config.py"], cwd=tmp_path, check=True)
    path.write_text('config = "clean"')
    assert check_secrets.main() == 1
    output = capsys.readouterr().out
    assert value not in output and "config.py" in output
    subprocess.run(["git", "add", "config.py"], cwd=tmp_path, check=True)
    assert check_secrets.main() == 0


def test_forced_tracked_env_is_blocked(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(check_secrets, "ROOT", tmp_path)
    (tmp_path / ".env.production").write_text("PRIVATE=placeholder")
    subprocess.run(["git", "add", ".env.production"], cwd=tmp_path, check=True)
    assert check_secrets.main() == 1


def test_short_configured_secret_is_found_without_printing(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(check_secrets, "ROOT", tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n")
    value = secrets.token_urlsafe(12)
    (tmp_path / ".env").write_text("LLM_API_KEY=" + value)
    (tmp_path / "settings.py").write_text("credential = " + repr(value))
    assert check_secrets.main() == 1
    assert value not in capsys.readouterr().out
