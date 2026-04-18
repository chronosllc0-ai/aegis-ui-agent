"""Regression tests for committed Netlify frontend deployment targets."""

from __future__ import annotations

from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_API_URL = "https://web-production-5b3f.up.railway.app"
EXPECTED_WS_URL = "wss://web-production-5b3f.up.railway.app/ws/navigate"
NETLIFY_CONFIGS = [
    ROOT / "netlify.toml",
    ROOT / "frontend/.netlify/netlify.toml",
]


def _build_environment(path: Path) -> dict[str, str]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data["build"]["environment"]


def test_committed_netlify_configs_target_the_current_railway_backend() -> None:
    """Both committed Netlify configs should point at the live Railway backend domain."""
    for path in NETLIFY_CONFIGS:
        env = _build_environment(path)
        assert env["VITE_API_URL"] == EXPECTED_API_URL, path.as_posix()
        assert env["VITE_WS_URL"] == EXPECTED_WS_URL, path.as_posix()


def test_committed_netlify_configs_stay_in_sync() -> None:
    """The checked-in root + frontend Netlify configs must not drift."""
    environments = [_build_environment(path) for path in NETLIFY_CONFIGS]

    assert len({env["VITE_API_URL"] for env in environments}) == 1
    assert len({env["VITE_WS_URL"] for env in environments}) == 1
