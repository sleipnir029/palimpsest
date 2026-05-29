"""Pytest config: a `--live` opt-in for tests that start real, paid infra.

`@pytest.mark.live` tests (e.g. a real RunPod pod, ~$0.05) are skipped unless
`--live` is passed, so a normal `pytest` run never spends money. Scoped to the
`live` marker only — the existing `slow` marker is left untouched.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="run live tests that start real paid infra",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: starts real paid infra; skipped unless --live"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="needs --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
