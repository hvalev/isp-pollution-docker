"""Unit tests for the parts of the vendored script that need no browser.

The module runs its argparse setup only under ``__main__``, so it can be
imported and exercised directly. Anything that drives chromedriver is covered
by ``tools/smoke_test.sh`` against a real container instead.
"""

import importlib.util
import pathlib
import sys

import pytest

MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "isp_data_pollution.py"


@pytest.fixture(scope="module")
def isp():
    spec = importlib.util.spec_from_file_location("isp_data_pollution", MODULE_PATH)
    assert spec is not None and spec.loader is not None, MODULE_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def polluter(isp, tmp_path):
    """A bare instance: skips __init__ (which starts Xvfb and chromedriver)."""
    obj = object.__new__(isp.ISPDataPollution)
    obj.domain_links = {}
    obj.max_links_cached = 1000
    obj.max_links_per_domain = 5
    obj.data_usage = 0
    return obj


def test_env_seconds_accepts_a_real_value(isp, monkeypatch):
    monkeypatch.setenv("SEED_SEARCH_BUDGET", "45")
    assert isp.env_seconds("SEED_SEARCH_BUDGET", 20) == 45


@pytest.mark.parametrize("value", ["", "abc", "0", "-5", None])
def test_env_seconds_falls_back_to_the_default(isp, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SEED_SEARCH_BUDGET", raising=False)
    else:
        monkeypatch.setenv("SEED_SEARCH_BUDGET", value)
    assert isp.env_seconds("SEED_SEARCH_BUDGET", 20) == 20


def test_word_list_accepts_a_real_list(isp):
    # A dictionary list holds alphabetic words; anything else (digits, markup,
    # JavaScript punctuation) is exactly what the filter is there to drop.
    letters = "abcdefghij"
    text = "\n".join(
        letters[i % 10]
        + letters[(i // 10) % 10]
        + letters[(i // 100) % 10]
        + letters[(i // 1000) % 10]
        for i in range(500)
    )
    assert len(isp.ISPDataPollution.word_list_from_text(text)) == 500


def test_word_list_rejects_html_and_bot_challenges(isp):
    html = "<!doctype html><html><head><title>Making sure you're not a robot"
    fragment = "<p>var f=(e,t={0})=>Math.random();</p>"
    html += "".join(fragment.format(i) for i in range(300))
    assert isp.ISPDataPollution.word_list_from_text(html) == []


def test_word_list_rejects_a_too_short_list(isp):
    assert isp.ISPDataPollution.word_list_from_text("apple\npear\nfig") == []


def test_read_word_list_on_a_missing_file(isp, polluter, tmp_path):
    assert polluter.read_word_list(tmp_path / "does-not-exist.txt") == []


def test_read_word_list_uses_the_vendored_file(isp, polluter):
    words = polluter.read_word_list(str(data_dir(isp) / "seedwords/seed-words.txt"))
    assert len(words) > 10_000
    assert all(w.isalpha() and w.islower() for w in words)


def data_dir(isp):
    return pathlib.Path(isp.__file__).resolve().parent


def test_vendored_data_files_ship_in_the_repository(isp):
    assert (data_dir(isp) / "seedwords/seed-words.txt").is_file()
    assert (data_dir(isp) / "blocklist/blocklist-domains.txt").is_file()


def test_add_link_keeps_only_http_targets(isp, polluter):
    assert polluter.add_link("https://example.com/a") is True
    assert polluter.add_link("http://example.com/b") is True
    junk = (
        "data:text/html,<script>x</script>",
        "blob:https://example.com/abc",
        "javascript:void(0)",
    )
    for target in junk:
        assert polluter.add_link(target) is False, target
    assert polluter.link_count() == 2


def test_add_link_dedupes_and_caps_a_domain(isp, polluter):
    for i in range(10):
        polluter.add_link(f"https://example.com/page{i}")
    assert len(polluter.domain_links["example.com"]) == polluter.max_links_per_domain
    again = polluter.add_link("https://example.com/page0")
    assert again is False


def test_heartbeat_touches_the_health_file(isp, polluter, tmp_path, monkeypatch):
    health = tmp_path / "health"
    monkeypatch.setenv("HEALTH_FILE", str(health))
    polluter.heartbeat()
    assert health.exists()
    stamp, usage = health.read_text().split()
    assert float(stamp) > 0 and float(usage) == 0


def test_seed_cooldown_state_starts_inactive(isp, polluter):
    assert getattr(polluter, "seed_search_cooldown_until", 0.0) == 0.0
