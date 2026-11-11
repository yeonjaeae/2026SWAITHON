"""Run with TEAM_REPO=/path/to/2026SWAITHON-main pytest -q."""
import importlib.util
import os
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
from test_api import selected, handoff, client

@pytest.fixture(scope='module')
def design_client():
    root=os.getenv('TEAM_REPO')
    if not root:
        pytest.skip('TEAM_REPO 미설정: 팀원 원본 API 연동 테스트')
    path=Path(root)/'green-design-backend'
    sys.path.insert(0,str(path))
    spec=importlib.util.spec_from_file_location('team_design_main',path/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TestClient(module.app)

@pytest.mark.parametrize('empty',[False,True])
def test_existing_design_api(design_client,empty):
    c=selected()
    h=client.post('/recommendations/design-handoff',json=handoff(c,None if empty else c['feature']['geometry'])).json()
    r=design_client.post(h['target_endpoint'],json=h['payload'])
    assert r.status_code==200,r.text
    result=r.json()
    if empty:
        assert result['green_area']==0
    else:
        assert result['green_area_m2']==pytest.approx(c['area_m2']*.4,abs=.02)
    assert result['candidate_id']==c['candidate_id']

def test_existing_candidate_receiver(design_client):
    r=design_client.post('/api/design/candidate',json=selected())
    assert r.status_code==200,r.text
