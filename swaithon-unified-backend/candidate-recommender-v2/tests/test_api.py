import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping
from main import app
from spatial import metric, geojson

client = TestClient(app)
@pytest.fixture
def request_data():
    return json.loads((Path(__file__).parents[1] / 'examples/recommend_request.json').read_text())

def recommend(doc):
    r = client.post('/recommendations/from-region-analysis', json=doc)
    assert r.status_code == 200, r.text
    return r.json()

def selected():
    rows = client.get('/recommendations/demo').json()['recommendations']
    r = client.post('/recommendations/select', json={'candidate_id':rows[0]['candidate_id'], 'recommendations':rows})
    assert r.status_code == 200, r.text
    return r.json()

def handoff(candidate, geometry):
    return {'candidate': candidate, 'editable': {'candidate_id': candidate['candidate_id'], 'editable_geometry': geometry, 'source':'synthetic_test','review_status':'reviewed'},
            'green_ratio':40, 'vegetation':{'grass':50,'shrub':30,'tree':20}}

def test_demo():
    r=client.get('/recommendations/demo').json()
    assert r['count']==3
    assert all(c['is_demo'] for c in r['recommendations'])
    assert [c['rank'] for c in r['recommendations']] == [1,2,3]

@pytest.mark.parametrize('query',['limit=0','limit=101','min_area_m2=-1'])
def test_bad_query(query):
    assert client.get('/recommendations/demo?'+query).status_code==422

def test_null_zone(request_data):
    request_data['region_analysis']['candidates']=None
    request_data.pop('sites')
    assert recommend(request_data)['count']==0

def test_missing_site_source_returns_503(request_data,monkeypatch):
    monkeypatch.delenv('IDLE_SITES_FILE',raising=False)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    request_data.pop('sites')
    assert client.post('/recommendations/from-region-analysis',json=request_data).status_code==503

def test_empty_sites(request_data):
    request_data['sites']=[]
    assert recommend(request_data)['count']==0

def test_geometry_area_and_green_exclusion(request_data):
    result=recommend(request_data)
    c=next(c for c in result['recommendations'] if c['site_id']=='demo_parking')
    assert c['area_m2']==pytest.approx(metric(c['geometry']).area,abs=1e-5)
    green=metric(request_data['landcover'][0]['geometry'])
    assert metric(c['geometry']).intersection(green).area<.001
    assert c['area_m2']<c['original_site_area_m2']

def test_road_does_not_mean_editable_or_excluded(request_data):
    c=next(c for c in recommend(request_data)['recommendations'] if c['site_id']=='demo_school')
    assert c['editable_status']=='pending_ai_review'
    assert c['area_m2']==pytest.approx(c['original_site_area_m2'],abs=.01)

def test_unknown_metrics_not_fabricated(request_data):
    c=next(c for c in recommend(request_data)['recommendations'] if c['site_id']=='demo_school')
    assert c['impervious_ratio'] is None and c['feasibility_score'] is None
    assert c['score_data_coverage']==pytest.approx(.70)
    assert c['total_score']==pytest.approx((.45*.65+.25)/.7,abs=1e-6)

def test_duplicate_site_id(request_data):
    request_data['sites'].append(copy.deepcopy(request_data['sites'][0]))
    assert client.post('/recommendations/from-region-analysis',json=request_data).status_code==422

@pytest.mark.parametrize('geometry',[
 {'type':'Point','coordinates':[126.96,37.54]},
 {'type':'Polygon','coordinates':[]},
 {'type':'Polygon','coordinates':[[[37.54,126.96],[37.55,126.96],[37.55,126.97],[37.54,126.96]]]},
 {'type':'Polygon','coordinates':[[[126.96,37.54],[126.97,37.55],[126.96,37.55],[126.97,37.54],[126.96,37.54]]]},
 {'type':'Polygon','coordinates':[[[126.96,37.54],[126.97,37.54],[126.97,37.55]]]},
])
def test_invalid_geometry(request_data,geometry):
    request_data['sites'][0]['geometry']=geometry
    assert client.post('/recommendations/from-region-analysis',json=request_data).status_code==422

def test_stable_id_and_changed_clip(request_data):
    a=recommend(request_data)['recommendations']
    b=recommend(request_data)['recommendations']
    assert [c['candidate_id'] for c in a]==[c['candidate_id'] for c in b]
    request_data['landcover']=[]
    c=recommend(request_data)['recommendations']
    ids=lambda rows:next(r['candidate_id'] for r in rows if r['site_id']=='demo_parking')
    assert ids(a)!=ids(c)

def test_select_recalculates_area():
    rows=client.get('/recommendations/demo').json()['recommendations']
    rows[0]['area_m2']=99999999
    r=client.post('/recommendations/select',json={'candidate_id':rows[0]['candidate_id'],'recommendations':rows}).json()
    assert r['area_m2']<99999999
    assert r['feature']['id']==r['candidate_id']

def test_unknown_selection():
    assert client.post('/recommendations/select',json={'candidate_id':'missing','recommendations':[]}).status_code==404

def test_editable_clip():
    c=selected()
    g=metric(c['feature']['geometry'])
    r=client.post('/recommendations/design-handoff',json=handoff(c,geojson(g.buffer(20))))
    assert r.status_code==200,r.text
    assert r.json()['editable_area_m2']==pytest.approx(c['area_m2'],abs=.01)
    assert r.json()['target_endpoint']=='/api/design/spatial'

def test_zero_editable():
    c=selected()
    r=client.post('/recommendations/design-handoff',json=handoff(c,None)).json()
    assert r['target_endpoint']=='/api/design/from-candidate'
    assert r['payload']['protected_area']==c['area_m2']

def test_unrelated_editable_id():
    c=selected(); doc=handoff(c,None); doc['editable']['candidate_id']='another'
    assert client.post('/recommendations/design-handoff',json=doc).status_code==422

def test_vegetation_sum():
    c=selected(); doc=handoff(c,None); doc['vegetation']['tree']=30
    assert client.post('/recommendations/design-handoff',json=doc).status_code==422

def test_file_mode(request_data, monkeypatch):
    monkeypatch.setenv('IDLE_SITES_FILE',str(Path(__file__).parents[1]/'examples/synthetic_sites.geojson'))
    request_data.pop('sites')
    assert recommend(request_data)['source']=='geojson_file'

def test_weighted_grid(request_data):
    request_data['grids']=[{'grid_id':'1','geometry':request_data['region_analysis']['candidates'],'deficit_index':.9}]
    for c in recommend(request_data)['recommendations']:
        assert c['green_deficit_score']==pytest.approx(.9,abs=1e-5)
        assert c['green_deficit_source']=='grid_weighted'

def test_overlapping_grids(request_data):
    grid={'grid_id':'1','geometry':request_data['region_analysis']['candidates'],'deficit_index':.9}
    request_data['grids']=[grid,{**grid,'grid_id':'2'}]
    assert client.post('/recommendations/from-region-analysis',json=request_data).status_code==422

def test_hole_and_multipolygon(request_data):
    from shapely.geometry import Polygon, MultiPolygon
    outer=box(126.963,37.545,126.9635,37.5455)
    hole=box(126.9631,37.5451,126.9632,37.5452)
    g=MultiPolygon([Polygon(outer.exterior.coords,[hole.exterior.coords]), box(126.964,37.546,126.9641,37.5461)])
    request_data['sites']=[{**request_data['sites'][0],'geometry':mapping(g)}]
    request_data['landcover']=[]
    c=recommend(request_data)['recommendations'][0]
    assert c['geometry']['type']=='MultiPolygon'
    assert c['area_m2']==pytest.approx(metric(mapping(g)).area,abs=.01)

def test_boundary_touch_not_candidate(request_data):
    request_data['sites'][0]['geometry']=mapping(box(126.9655,37.545,126.966,37.546))
    request_data['sites']=request_data['sites'][:1]
    assert recommend(request_data)['count']==0

@pytest.mark.parametrize('typ',['Polygon','MultiPolygon'])
def test_invalid_nesting(request_data,typ):
    request_data['sites'][0]['geometry']={'type':typ,'coordinates':[126.96,37.54]}
    assert client.post('/recommendations/from-region-analysis',json=request_data).status_code==422

def test_malformed_feature_in_handoff():
    c=selected(); doc=handoff(c,None); doc['candidate']['feature']=None
    assert client.post('/recommendations/design-handoff',json=doc).status_code==422
