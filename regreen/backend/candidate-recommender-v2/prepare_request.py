"""Build a recommendation request from saved region response + real site file.
Optional --grid-gpkg uses the repository's actual grid (cell_id, deficit_index).
"""
import argparse
import json
from pathlib import Path
from schemas import Request, Site
from spatial import metric
p=argparse.ArgumentParser()
p.add_argument('--analysis',required=True)
p.add_argument('--sites',required=True)
p.add_argument('--grid-gpkg')
p.add_argument('--out',default='recommend_request.json')
a=p.parse_args()
analysis=json.loads(Path(a.analysis).read_text(encoding='utf-8'))
fc=json.loads(Path(a.sites).read_text(encoding='utf-8'))
if fc.get('type')!='FeatureCollection':
    raise SystemExit('sites는 FeatureCollection이어야 합니다.')
sites=[Site.model_validate({**f['properties'],'geometry':f['geometry']}).model_dump() for f in fc['features']]
request={'region_analysis':analysis,'sites':sites}
if a.grid_gpkg and analysis.get('candidates') is not None:
    import geopandas as gpd
    import math
    from shapely.geometry import mapping
    grid=gpd.read_file(a.grid_gpkg,layer='grid').to_crs(5179)
    zone=metric(analysis['candidates'])
    selected=grid.iloc[grid.sindex.query(zone,predicate='intersects')].to_crs(4326)
    request['grids']=[{'grid_id':str(r.cell_id),'deficit_index':float(r.deficit_index),'geometry':mapping(r.geometry)}
                      for r in selected.itertuples() if math.isfinite(float(r.deficit_index))]
validated=Request.model_validate(request)
Path(a.out).write_text(json.dumps(validated.model_dump(by_alias=True),ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{a.out} 저장: 시설 {len(sites)}개, 격자 {len(validated.grids)}개. 데이터 출처/권한은 별도 검토하세요.')
