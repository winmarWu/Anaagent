"""Pytest 配置：隔离 ~/.anaagent，避免测试污染真实用户目录。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_anaagent_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
