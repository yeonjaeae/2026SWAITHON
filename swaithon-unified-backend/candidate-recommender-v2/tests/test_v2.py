import copy
import io
import json
from pathlib import Path
import pytest
import httpx
from PIL import Image
from pyproj import Transformer
from shapely import transform
from shapely.geometry import box, mapping, shape
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.testclient import TestClient
from main import app
from normalization import normalize_collection
from ai_adapter import validate_image_world, adapt_landcover
from spatial import metric, geojson
from storage import connection
from test_api import selected, handoff

client=TestClient(app)

def rect(): return mapping(box(126.963,37.545,126.964,37.546))
def collection(label='green',geom=None):
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'class':label},'geometry':geom or rect()}]}

def image_data():
    image=io.BytesIO();Image.new('RGB',(100,100)).save(image,format='PNG')
    t=Transformer.from_crs(4326,3857,always_xy=True)
    x,y=t.transform(126.962,37.547)
    world=f'5\n0\n0\n-5\n{x}\n{y}\n'.encode()
    return image.getvalue(),world

@pytest.mark.parametrize('epsg',[4326,3857,5179,5186])
def test_real_crs_roundtrip(epsg):
    t=Transformer.from_crs(4326,epsg,always_xy=True)
    geom=transform(shape(rect()),t.transform,interleaved=False)
    doc=collection(geom=mapping(geom))
    result=normalize_collection(doc,f'EPSG:{epsg}')
    assert metric(result['geojson']['features'][0]['geometry']).area==pytest.approx(metric(rect()).area,rel=1e-7)

def test_conflicting_crs():
    doc=collection();doc['crs']={'type':'name','properties':{'name':'EPSG:3857'}}
    r=client.post('/data/normalize',json={'geojson':doc,'source_crs':'EPSG:4326'})
    assert r.status_code==422

def test_repair_opt_in():
    bow={'type':'Polygon','coordinates':[[[126.96,37.54],[126.97,37.55],[126.96,37.55],[126.97,37.54],[126.96,37.54]]]}
    doc={'geojson':collection(geom=bow),'source_crs':'EPSG:4326'}
    assert client.post('/data/normalize',json=doc).status_code==422
    r=client.post('/data/normalize',json={**doc,'repair':True})
    assert r.status_code==200,r.text
    assert r.json()['repaired_feature_indices']==[0]

@pytest.mark.parametrize('geom',[{'type':'Point','coordinates':[126.96,37.54]},mapping(box(-74,40,-73,41))])
def test_no_point_inference_or_global_claim(geom):
    r=client.post('/data/normalize',json={'geojson':collection(geom=geom),'source_crs':'EPSG:4326'})
    assert r.status_code==422

def test_ai_classes_overlap_precedence():
    fc=collection();fc['features']+=collection('road')['features']+collection('residential')['features']
    r=adapt_landcover(fc,rect())
    assert [x['class'] for x in r['landcover']]==['green']
    assert r['cross_class_overlap_m2']>0
    assert r['coverage_ratio']==pytest.approx(1)
    assert r['editable_status']=='not_provided_by_ai'

def test_empty_ai_has_no_editable():
    r=adapt_landcover({'type':'FeatureCollection','features':[]},rect())
    assert r['landcover']==[] and r['coverage_ratio']==0
    assert 'editable_geometry' not in r

def test_unknown_ai_class():
    assert client.post('/integrations/ai/normalize-landcover',json={'region':rect(),'feature_collection':collection('building')}).status_code==422

def test_worldfile_and_full_coverage():
    image,world=image_data()
    r=validate_image_world(image,world,rect(),'EPSG:3857')
    assert r['width']==100

@pytest.mark.parametrize('world',[b'1 2 3',b'0 0 0 0 0 0',b'NaN 0 0 -1 1 1'])
def test_bad_worldfile(world):
    with pytest.raises(ValueError): validate_image_world(image_data()[0],world,rect(),'EPSG:3857')

def test_wrong_image_crs():
    with pytest.raises(ValueError,match='EPSG:3857'):validate_image_world(*image_data(),rect(),'EPSG:5179')

def test_image_outside():
    with pytest.raises(ValueError,match='범위 밖'):validate_image_world(*image_data(),mapping(box(127,37.5,127.01,37.51)),'EPSG:3857')

def test_image_corrupt():
    with pytest.raises(ValueError):validate_image_world(b'not image',image_data()[1],rect(),'EPSG:3857')

def test_snapshot_survives_new_client():
    result=client.get('/recommendations/demo').json()
    req={'recommendation_id':result['recommendation_id'],'candidate_id':result['recommendations'][0]['candidate_id']}
    c=TestClient(app).post('/recommendations/select',json=req)
    assert c.status_code==200,c.text
    doc={'recommendation_id':req['recommendation_id'],'candidate_id':req['candidate_id'],
         'editable':{'candidate_id':req['candidate_id'],'editable_geometry':None,'review_status':'reviewed','source':'synthetic review'},
         'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}}
    r=client.post('/recommendations/design-handoff',json=doc)
    assert r.status_code==200,r.text
    assert r.json()['editable_area_m2']==0

def test_expired_snapshot():
    result=client.get('/recommendations/demo').json()
    with connection() as conn:conn.execute('UPDATE snapshots SET expires=0')
    r=client.post('/recommendations/select',json={'recommendation_id':result['recommendation_id'],'candidate_id':result['recommendations'][0]['candidate_id']})
    assert r.status_code==404

def test_review_pending_is_not_empty_editable():
    doc=handoff(selected(),None);doc['editable']['review_status']='pending'
    assert client.post('/recommendations/design-handoff',json=doc).status_code==409

def test_protected_region_overrides_editable():
    c=selected();doc=handoff(c,c['feature']['geometry']);doc['protected_geometries']=[c['feature']['geometry']]
    r=client.post('/recommendations/design-handoff',json=doc)
    assert r.status_code==200,r.text
    assert r.json()['editable_area_m2']==0

def test_production_auth_and_demo_disabled(monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('SERVICE_API_KEY','k'*32)
    assert client.get('/recommendations/demo').status_code==401
    assert client.get('/recommendations/demo',headers={'Authorization':'Bearer '+'k'*32}).status_code==404
    assert client.get('/health').status_code==200

def test_production_cannot_use_forged_legacy_candidate(monkeypatch):
    c=selected();doc=handoff(c,None)
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('SERVICE_API_KEY','k'*32)
    r=client.post('/recommendations/design-handoff',headers={'Authorization':'Bearer '+'k'*32},json=doc)
    assert r.status_code==422

def test_body_size_limit():
    r=client.post('/data/normalize',content=b'{}',headers={'content-length':str(25*1024*1024)})
    assert r.status_code==413

def test_nan_is_422_not_server_error():
    r=client.post('/recommendations/from-region-analysis',content='{"region_analysis":{"candidates":null,"deficit_index":NaN}}',headers={'content-type':'application/json'})
    assert r.status_code==422,r.text

def test_production_cannot_start_without_key(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError,match='SERVICE_API_KEY'):
        with TestClient(app):pass

def test_multipart_matches_supplied_ai_contract(monkeypatch):
    fake=FastAPI()
    @fake.post('/ai/landcover')
    async def ai(image:UploadFile=File(...),world_file:UploadFile=File(...),region:str=Form(...)):
        assert (await image.read())[:8]==b'\x89PNG\r\n\x1a\n'
        assert len((await world_file.read()).split())==6
        return collection(geom=json.loads(region))
    original=httpx.AsyncClient
    monkeypatch.setenv('AI_BASE_URL','http://test-ai')
    monkeypatch.setattr('ai_adapter.httpx.AsyncClient',lambda **kw:original(transport=httpx.ASGITransport(app=fake),**kw))
    image,world=image_data()
    r=client.post('/integrations/ai/landcover',data={'region':json.dumps(rect()),'image_crs':'EPSG:3857'},files={'image':('test.png',image),'world_file':('test.pgw',world)})
    assert r.status_code==200,r.text
    assert r.json()['landcover'][0]['class']=='green'
    assert r.json()['editable_status']=='not_provided_by_ai'

@pytest.mark.parametrize('mode,expected',[('timeout',504),('invalid',502),('error',502)])
def test_ai_failure_never_becomes_fake_success(monkeypatch,mode,expected):
    async def handler(req):
        if mode=='timeout':raise httpx.ReadTimeout('slow')
        if mode=='invalid':return httpx.Response(200,json={'invalid':True})
        return httpx.Response(500,json={'detail':'internal'})
    original=httpx.AsyncClient
    monkeypatch.setenv('AI_BASE_URL','http://test-ai')
    monkeypatch.setattr('ai_adapter.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    image,world=image_data()
    r=client.post('/integrations/ai/landcover',data={'region':json.dumps(rect()),'image_crs':'EPSG:3857'},files={'image':('t.png',image),'world_file':('t.pgw',world)})
    assert r.status_code==expected,r.text

def test_supplied_ai_endpoint_code_with_inference_stubbed(monkeypatch):
    import ast,os
    from fastapi import HTTPException
    root=os.getenv('TEAM_REPO')
    if not root:pytest.skip('TEAM_REPO 미설정')
    source=(Path(root)/'ai/main.py').read_text()
    tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('make_feature','analyze_landcover')]
    fake=FastAPI()
    namespace={'app':fake,'File':File,'Form':Form,'UploadFile':UploadFile,'HTTPException':HTTPException,
               'json':json,'io':io,'Image':Image,'shape':shape,'mapping':mapping,
               'predict_green':lambda image:None,
               'get_road_features':lambda region:[], 'get_residential_features':lambda region:[]}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<provided-ai-endpoint>','exec'),namespace)
    namespace['green_to_features']=lambda mask,pgw,region:[namespace['make_feature']('green',region)]
    original=httpx.AsyncClient
    monkeypatch.setenv('AI_BASE_URL','http://team-ai')
    monkeypatch.setattr('ai_adapter.httpx.AsyncClient',lambda **kw:original(transport=httpx.ASGITransport(app=fake),**kw))
    image,world=image_data()
    r=client.post('/integrations/ai/landcover',data={'region':json.dumps(rect()),'image_crs':'EPSG:3857'},files={'image':('x.png',image),'world_file':('x.pgw',world)})
    assert r.status_code==200,r.text
    assert r.json()['deficit_request']['landcover'][0]['class']=='green'

def test_production_snapshot_selection_and_handoff(monkeypatch):
    doc=json.loads((Path(__file__).parents[1]/'examples/recommend_request.json').read_text())
    # This is a controlled fixture, not a claim to have authentic real-world facility data.
    for s in doc['sites']:s['is_demo']=False
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('SERVICE_API_KEY','p'*32)
    headers={'Authorization':'Bearer '+'p'*32}
    r=client.post('/recommendations/from-region-analysis',json=doc,headers=headers)
    assert r.status_code==200,r.text
    data=r.json();cid=data['recommendations'][0]['candidate_id']
    ids={'recommendation_id':data['recommendation_id'],'candidate_id':cid}
    c=client.post('/recommendations/select',json=ids,headers=headers)
    assert c.status_code==200,c.text
    h={**ids,'editable':{'candidate_id':cid,'editable_geometry':c.json()['feature']['geometry'],'source':'test fixture','review_status':'reviewed'},
       'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}}
    r=client.post('/recommendations/design-handoff',json=h,headers=headers)
    assert r.status_code==200,r.text
    assert r.json()['target_endpoint']=='/api/design/spatial'

def test_rotation_and_pixel_center_boundary():
    from shapely.geometry import Polygon
    image,world=image_data()
    _,_,_,_,C,F=[float(v) for v in world.split()]
    # affine rotation/skew is preserved, not replaced by an axis-aligned bbox.
    pgw=[4,1,1,-4,C,F]
    t=Transformer.from_crs(3857,4326,always_xy=True)
    coords=[t.transform(4*x+y+C,x-4*y+F) for x,y in [(10,10),(80,10),(80,80),(10,80)]]
    r=validate_image_world(image,'\n'.join(map(str,pgw)).encode(),mapping(Polygon(coords)),'EPSG:3857')
    assert r['world_file']==pgw

def test_ai_output_directly_accepted_by_recommender():
    doc=json.loads((Path(__file__).parents[1]/'examples/recommend_request.json').read_text())
    doc.pop('landcover')
    doc['ai_landcover']=collection('green',doc['region_analysis']['candidates'])
    r=client.post('/recommendations/from-region-analysis',json=doc)
    assert r.status_code==200,r.text
    assert r.json()['count']==0

def test_overflow_worldfile_is_rejected():
    with pytest.raises(ValueError):
        validate_image_world(image_data()[0],b'1e308 0 0 -1e308 0 0',rect(),'EPSG:3857')
