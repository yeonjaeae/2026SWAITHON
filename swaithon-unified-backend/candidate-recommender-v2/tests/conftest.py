import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv('RECOMMENDATION_DB',str(tmp_path/'snapshots.sqlite3'))
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.delenv('SERVICE_API_KEY',raising=False)
