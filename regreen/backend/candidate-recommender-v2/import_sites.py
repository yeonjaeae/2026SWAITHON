"""Explicit command to validate/import a FeatureCollection into optional PostGIS.
Existing site IDs are rejected; it never overwrites existing records.
"""
import argparse
import json
import os
from pathlib import Path
from schemas import Site
p=argparse.ArgumentParser()
p.add_argument('geojson')
a=p.parse_args()
doc=json.loads(Path(a.geojson).read_text(encoding='utf-8'))
if doc.get('type')!='FeatureCollection':
    raise SystemExit('FeatureCollection이 필요합니다.')
sites=[Site.model_validate({**f['properties'],'geometry':f['geometry']}) for f in doc['features']]
if len({s.site_id for s in sites})!=len(sites):
    raise SystemExit('site_id가 중복됩니다.')
import psycopg
url=os.environ.get('DATABASE_URL')
if not url:
    raise SystemExit('DATABASE_URL을 설정하세요.')
with psycopg.connect(url,connect_timeout=5) as conn:
    with conn.cursor() as cur:
        for s in sites:
            geometry=s.geometry.get('geometry') if s.geometry.get('type')=='Feature' else s.geometry
            cur.execute('''INSERT INTO idle_sites
                (site_id,name,site_type,address,source,is_demo,is_green,impervious_ratio,feasibility_score,geom)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)))''',
                (s.site_id,s.name,s.site_type,s.address,s.source,s.is_demo,s.is_green,
                 s.impervious_ratio,s.feasibility_score,json.dumps(geometry)))
print(f'{len(sites)}개 시설 등록 완료')
