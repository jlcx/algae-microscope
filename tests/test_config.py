import pytest

from server.config import load_config


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no config.toml in cwd
    config = load_config()
    assert config.backend.mode == "postgres"
    assert config.expansion.default_hops == 1
    assert config.witnesses.clone_families == [["ceb", "war", "sv", "vi"]]
    assert config.temporal.undated == "margin"


def test_load_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("""
[backend]
mode = "api"

[expansion]
default_budget = 42

[witnesses]
clone_families = [["ceb", "war"], ["a", "b"]]
family_cap = 2

[witnesses.weights]
ceb = 0.5

[temporal]
undated = "infer"
""")
    config = load_config(path)
    assert config.backend.mode == "api"
    assert config.expansion.default_budget == 42
    assert config.expansion.max_hops == 3  # untouched default
    assert config.witnesses.family_cap == 2
    assert config.witnesses.weights == {"ceb": 0.5}
    assert config.temporal.undated == "infer"


def test_missing_explicit_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")
