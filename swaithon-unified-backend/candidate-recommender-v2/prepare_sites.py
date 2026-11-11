"""Convert a real GeoPackage/Shapefile/GeoJSON inventory into Site FeatureCollection.
No footprint is inferred from points and no score is inferred from zoning labels.
"""
import argparse
import json
from pathlib import Path
from shapely.geometry import mapping
from normalization import normalize_collection, crs_value
from schemas import Site

def main():
    p=argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--layer')
    p.add_argument('--source-crs',help='CRS가 없는 자료에 필수. 기존 메타데이터와 충돌하면 오류')
    p.add_argument('--id-field',required=True)
    p.add_argument('--name-field',required=True)
    types=p.add_mutually_exclusive_group(required=True)
    types.add_argument('--type-field')
    types.add_argument('--site-type',choices=['parking_lot','schoolyard','public_plaza','public_rooftop'])
    p.add_argument('--source',required=True,help='기관/자료명/갱신일/라이선스 등 출처')
    p.add_argument('--repair',action='store_true')
    p.add_argument('--out',required=True)
    a=p.parse_args()
    import geopandas as gpd
    frame=gpd.read_file(a.input,**({'layer':a.layer} if a.layer else {}))
    if len(frame)>5000:
        raise SystemExit('시설 5000개 이하로 지역을 나누어 준비하세요.')
    if frame.crs is None and not a.source_crs:
        raise SystemExit('좌표계가 없습니다. 확인된 --source-crs가 필요합니다.')
    if frame.crs is not None and a.source_crs and not crs_value(a.source_crs).equals(frame.crs,ignore_axis_order=True):
        raise SystemExit('명시 좌표계와 파일 좌표계가 다릅니다.')
    source_crs=a.source_crs or frame.crs.to_string()
    for field in [a.id_field,a.name_field,*([a.type_field] if a.type_field else [])]:
        if field not in frame or frame[field].isna().any():
            raise SystemExit(f'필수 속성 {field}가 없거나 비어 있습니다.')
    if frame[a.id_field].astype(str).duplicated().any():
        raise SystemExit('원본 ID가 중복됩니다. 시설 경계를 정리하세요.')
    features=[]
    for _,row in frame.iterrows():
        if row.geometry is None:
            raise SystemExit('geometry가 없는 시설이 있습니다.')
        features.append({'type':'Feature','geometry':mapping(row.geometry),'properties':{
            'site_id':str(row[a.id_field]),'name':str(row[a.name_field]),
            'site_type':str(row[a.type_field]) if a.type_field else a.site_type,
            'source':a.source,'is_demo':False,'is_green':False,
            'impervious_ratio':None,'feasibility_score':None}})
    result=normalize_collection({'type':'FeatureCollection','features':features},source_crs,a.repair)
    for f in result['geojson']['features']:
        Site.model_validate({**f['properties'],'geometry':f['geometry']})
    dest=Path(a.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result['geojson'],ensure_ascii=False,indent=2),encoding='utf-8')
    dest.with_suffix('.report.json').write_text(json.dumps({k:v for k,v in result.items() if k!='geojson'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(features)}개 시설 준비 완료. 기존 녹지 여부·자료 완전성·공사 가능성은 원본 검토가 필요합니다.')

if __name__=='__main__':main()
