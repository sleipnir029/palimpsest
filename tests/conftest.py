"""Pytest config: a `--live` opt-in for tests that start real, paid infra.

`@pytest.mark.live` tests (e.g. a real RunPod pod, ~$0.05) are skipped unless
`--live` is passed, so a normal `pytest` run never spends money. The `slow`
marker (network or paid APIs, no infra start) is also registered here — T18
made it the major marker user, so registering avoids the warning noise.
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
    config.addinivalue_line(
        "markers", "slow: hits the network or paid APIs (no infra start)"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="needs --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
