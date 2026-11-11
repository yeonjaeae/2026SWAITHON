import json
import os
from pathlib import Path
import sys
import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gateway.main import app, Upstream, Settings, ROUTES

@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('SERVICE_API_KEY','internal-secret')
    monkeypatch.delenv('GATEWAY_API_KEY',raising=False)
    seen=[]
    async def handler(req):
        seen.append(req)
        return httpx.Response(200,json={'ok':True})
    with TestClient(app) as client:
        upstream=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app.state.upstream=Upstream(upstream,Settings())
        yield client,seen,app.state.upstream
        client.portal.call(upstream.aclose)

@pytest.mark.parametrize('method,path,service,target,tag',ROUTES)
def test_route_mapping(gateway,method,path,service,target,tag):
    client,seen,_=gateway
    r=client.request(method,path+'?limit=2',content=b'{}',headers={'content-type':'application/json','authorization':'Bearer browser-value'})
    assert r.status_code==200
    req=seen[0]
    assert req.url.path==target and req.url.query==b'limit=2'
    assert req.content==b'{}'
    assert req.headers.get('authorization')==('Bearer internal-secret' if service=='candidate' else None)

def test_multipart_bytes_not_reencoded(gateway):
    client,seen,_=gateway
    r=client.post('/api/ai/landcover',data={'region':'{}','image_crs':'EPSG:3857'},files={'image':('a.png',b'pixels'),'world_file':('a.pgw',b'1 0 0 -1 0 0')})
    assert r.status_code==200
    assert 'boundary=' in seen[0].headers['content-type']
    assert b'pixels' in seen[0].content and b'name="world_file"' in seen[0].content

def test_error_status_is_preserved(gateway):
    client,seen,upstream=gateway
    upstream.client._transport=httpx.MockTransport(lambda req:httpx.Response(409,json={'detail':'pending editable'}))
    r=client.post('/api/recommendations/design-handoff',json={})
    assert r.status_code==409 and r.json()['detail']=='pending editable'

@pytest.mark.parametrize('exc,expected',[(httpx.ConnectError('offline'),502),(httpx.ReadTimeout('timeout'),504)])
def test_upstream_failures(gateway,exc,expected):
    client,_,upstream=gateway
    def handler(req):raise exc
    upstream.client._transport=httpx.MockTransport(handler)
    r=client.post('/api/region/analyze',json={})
    assert r.status_code==expected
    assert r.json()['detail']['service']=='deficit'

def test_no_arbitrary_proxy(gateway):
    client,seen,_=gateway
    assert client.get('/api/proxy/http://example.com').status_code==404
    assert seen==[]

def test_cors_at_one_entrypoint(gateway):
    client,_,_=gateway
    r=client.options('/api/region/analyze',headers={'origin':'http://localhost:5173','access-control-request-method':'POST','access-control-request-headers':'content-type'})
    assert r.status_code==200
    assert r.headers['access-control-allow-origin']=='http://localhost:5173'

def test_large_request_rejected(gateway):
    client,seen,_=gateway
    r=client.post('/api/region/analyze',content=b'{}',headers={'content-length':str(25*1024*1024)})
    assert r.status_code==413 and not seen

def test_recommend_workflow(gateway):
    client,seen,upstream=gateway
    def handler(req):
        seen.append(req)
        if req.url.path=='/api/region/analyze':return httpx.Response(200,json={'candidates':None,'deficit_index':.5})
        data=json.loads(req.content)
        assert data['region_analysis']['candidates'] is None
        assert data['landcover']==[]
        return httpx.Response(200,json={'recommendation_id':'server-id','count':0,'recommendations':[]})
    upstream.client._transport=httpx.MockTransport(handler)
    r=client.post('/api/workflows/recommend',json={'analysis':{'region':{},'landcover':[]},'options':{'sites':[]}})
    assert r.status_code==200,r.text
    assert r.json()['recommendation']['recommendation_id']=='server-id'
    assert len(seen)==2

def test_recommend_failure_stops_chain(gateway):
    client,seen,upstream=gateway
    def handler(req):seen.append(req);return httpx.Response(422,json={'detail':'outside Seoul'})
    upstream.client._transport=httpx.MockTransport(handler)
    r=client.post('/api/workflows/recommend',json={'analysis':{}})
    assert r.status_code==422 and len(seen)==1

def test_cannot_override_analysis(gateway):
    client,seen,_=gateway
    r=client.post('/api/workflows/recommend',json={'analysis':{},'options':{'region_analysis':{}}})
    assert r.status_code==422 and not seen

def design_request():return {'recommendation_id':'id','candidate_id':'site','editable':{},'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}}

@pytest.mark.parametrize('target',['/api/design/spatial','/api/design/from-candidate'])
def test_design_workflow(gateway,target):
    client,seen,upstream=gateway
    def handler(req):
        seen.append(req)
        if req.url.path=='/recommendations/design-handoff':return httpx.Response(200,json={'target_endpoint':target,'payload':{'candidate':'validated'}})
        assert req.url.path==target
        assert json.loads(req.content)=={'candidate':'validated'}
        return httpx.Response(200,json={'green_area':0})
    upstream.client._transport=httpx.MockTransport(handler)
    r=client.post('/api/workflows/design',json=design_request())
    assert r.status_code==200 and r.json()['design']['green_area']==0

def test_handoff_cannot_redirect(gateway):
    client,_,upstream=gateway
    upstream.client._transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'target_endpoint':'https://example.com','payload':{}}))
    assert client.post('/api/workflows/design',json=design_request()).status_code==502

def test_pending_handoff_stops_design(gateway):
    client,seen,upstream=gateway
    def handler(req):seen.append(req);return httpx.Response(409,json={'detail':'pending'})
    upstream.client._transport=httpx.MockTransport(handler)
    assert client.post('/api/workflows/design',json=design_request()).status_code==409
    assert len(seen)==1

def test_merged_swagger_refs(gateway):
    client,_,_=gateway
    doc=client.get('/openapi.json').json()
    def check(value):
        if isinstance(value,dict):
            if '$ref' in value:
                ref=value['$ref'];assert ref.startswith('#/components/schemas/')
                assert ref.split('/')[-1] in doc['components']['schemas']
            for v in value.values():check(v)
        elif isinstance(value,list):
            for v in value:check(v)
    check(doc)
    schema=doc['paths']['/api/ai/landcover']['post']['requestBody']
    assert 'multipart/form-data' in schema['content']

def test_optional_gateway_auth(monkeypatch,gateway):
    client,_,_=gateway
    monkeypatch.setenv('GATEWAY_API_KEY','gateway-secret')
    assert client.get('/api/status').status_code==401
    assert client.get('/api/health').status_code==200
    assert client.get('/api/status',headers={'authorization':'Bearer gateway-secret'}).status_code==200

def test_nonfinite_workflow_input_is_422(gateway):
    client,seen,_=gateway
    doc=design_request();doc['green_ratio']=None
    raw=json.dumps(doc).replace('"green_ratio": null','"green_ratio": NaN')
    r=client.post('/api/workflows/design',content=raw,headers={'content-type':'application/json'})
    assert r.status_code==422 and not seen
