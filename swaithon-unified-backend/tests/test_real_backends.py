import importlib.util
import json
from pathlib import Path
import sys
import httpx
import pytest
from fastapi.testclient import TestClient
from gateway.main import app,Upstream,Settings

ROOT=Path(__file__).resolve().parents[1]

def load(name,folder):
    sys.path.insert(0,str(ROOT/folder))
    spec=importlib.util.spec_from_file_location(name,ROOT/folder/'main.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.app

@pytest.fixture
def integrated(monkeypatch,tmp_path):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('SERVICE_API_KEY','internal-secret')
    monkeypatch.delenv('GATEWAY_API_KEY',raising=False)
    monkeypatch.setenv('RECOMMENDATION_DB',str(tmp_path/'real-test.sqlite3'))
    candidate=load('real_candidate','candidate-recommender-v2')
    design=load('real_design','green-design-backend')
    sys.path.insert(0,str(ROOT/'green-deficit'))
    from src.api import app as deficit
    class Dispatch(httpx.AsyncBaseTransport):
        def __init__(self):
            self.transports={8101:httpx.ASGITransport(app=candidate),8102:httpx.ASGITransport(app=deficit),8103:httpx.ASGITransport(app=design)}
        async def handle_async_request(self,request):
            return await self.transports[request.url.port].handle_async_request(request)
        async def aclose(self):
            for t in self.transports.values():await t.aclose()
    with TestClient(app) as client:
        upstream=httpx.AsyncClient(transport=Dispatch())
        app.state.upstream=Upstream(upstream,Settings())
        yield client
        client.portal.call(upstream.aclose)

@pytest.mark.parametrize('empty',[False,True])
def test_real_candidate_selection_and_design(integrated,empty):
    r=integrated.get('/api/recommendations/demo');assert r.status_code==200,r.text
    data=r.json();assert data['count']==3
    cid=data['recommendations'][0]['candidate_id']
    ids={'recommendation_id':data['recommendation_id'],'candidate_id':cid}
    r=integrated.post('/api/recommendations/select',json=ids);assert r.status_code==200,r.text
    selected=r.json()
    doc={**ids,'editable':{'candidate_id':cid,'geometry_crs':'EPSG:4326',
         'editable_geometry':None if empty else selected['feature']['geometry'],
         'source':'synthetic integration fixture','review_status':'reviewed'},
         'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}}
    r=integrated.post('/api/workflows/design',json=doc);assert r.status_code==200,r.text
    result=r.json()
    assert result['design']['candidate_id']==cid
    if empty:
        assert result['design']['green_area']==0
    else:
        assert result['design']['green_area_m2']==pytest.approx(selected['area_m2']*.4,abs=.02)

def test_real_region_and_recommendation(integrated):
    analysis=json.loads((ROOT/'candidate-recommender-v2/examples/real_region_request.json').read_text())
    r=integrated.post('/api/workflows/recommend',json={'analysis':analysis,'options':{'sites':[]}})
    assert r.status_code==200,r.text
    data=r.json()
    assert data['analysis']['grid_cells']==42
    assert data['analysis']['deficit_index']==pytest.approx(.513)
    assert data['recommendation']['count']==0
    assert data['recommendation']['recommendation_id']

def test_real_ai_normalization_path(integrated):
    doc=json.loads((ROOT/'candidate-recommender-v2/examples/ai_normalize_request.json').read_text())
    r=integrated.post('/api/ai/normalize-landcover',json=doc)
    assert r.status_code==200,r.text
    assert r.json()['editable_status']=='not_provided_by_ai'

def test_real_pending_editable_stops_before_design(integrated):
    data=integrated.get('/api/recommendations/demo').json();cid=data['recommendations'][0]['candidate_id']
    r=integrated.post('/api/workflows/design',json={'recommendation_id':data['recommendation_id'],'candidate_id':cid,
        'editable':{'candidate_id':cid,'editable_geometry':None,'source':'not reviewed','review_status':'pending'},
        'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}})
    assert r.status_code==409
