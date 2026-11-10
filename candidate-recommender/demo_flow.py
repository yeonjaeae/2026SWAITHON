"""HTTP end-to-end demo; never claims synthetic editable geometry is AI output."""
import argparse
import json
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--base-url',default='http://127.0.0.1:8001')
parser.add_argument('--design-url',default=None)
parser.add_argument('--out',default='demo_output')
args=parser.parse_args()
out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
def save(name,obj):
    (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
with httpx.Client(base_url=args.base_url,timeout=30) as client:
    r=client.get('/recommendations/demo'); r.raise_for_status(); result=r.json()
    save('recommendations.json',result)
    first=result['recommendations'][0]
    r=client.post('/recommendations/select',json={'candidate_id':first['candidate_id'],'recommendations':result['recommendations']})
    r.raise_for_status(); candidate=r.json(); save('selected_candidate.json',candidate)
    save('selected_candidate.geojson',candidate['feature'])
    # Synthetic demo assumes whole candidate editable ONLY to exercise the contract.
    editable={'candidate_id':candidate['candidate_id'],'geometry_crs':'EPSG:4326',
              'editable_geometry':candidate['feature']['geometry'],'source':'synthetic_demo_full_candidate_NOT_AI'}
    save('editable_demo.json',editable)
    r=client.post('/recommendations/design-handoff',json={'candidate':candidate,'editable':editable,
                  'green_ratio':40,'vegetation':{'grass':50,'shrub':30,'tree':20}})
    r.raise_for_status(); handoff=r.json(); save('design_handoff.json',handoff)
    save('design_spatial_request.json',handoff['payload'])
    if args.design_url:
        r=httpx.post(args.design_url.rstrip('/')+handoff['target_endpoint'],json=handoff['payload'],timeout=30)
        r.raise_for_status(); save('design_response.json',r.json())
print(f'가상 데이터로 연동 완료. 결과: {out.resolve()}')
