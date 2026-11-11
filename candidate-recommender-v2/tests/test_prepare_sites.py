import json
from pathlib import Path
import subprocess
import sys
import pytest
from shapely.geometry import box,mapping
pytest.importorskip('geopandas')

@pytest.mark.parametrize('case',['polygon','point','wrong_crs'])
def test_vector_file_preparation(tmp_path,case):
    doc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':'source_1','name':'synthetic facility'},
        'geometry':{'type':'Point','coordinates':[126.96,37.54]} if case=='point' else mapping(box(126.96,37.54,126.961,37.541))}]}
    src=tmp_path/'source.geojson';src.write_text(json.dumps(doc))
    out=tmp_path/'sites.geojson'
    cmd=[sys.executable,str(Path(__file__).parents[1]/'prepare_sites.py'),str(src),'--id-field','id','--name-field','name',
         '--site-type','parking_lot','--source','synthetic unit fixture','--out',str(out)]
    if case=='wrong_crs':cmd+=['--source-crs','EPSG:3857']
    r=subprocess.run(cmd,capture_output=True,text=True)
    if case=='polygon':
        assert r.returncode==0,r.stderr
        result=json.loads(out.read_text())
        assert result['features'][0]['properties']['site_id']=='source_1'
        assert result['features'][0]['properties']['impervious_ratio'] is None
        assert out.with_suffix('.report.json').exists()
    else:
        assert r.returncode!=0
        assert not out.exists()
