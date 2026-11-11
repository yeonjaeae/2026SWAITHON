"""Optional file/PostGIS site input; never silently falls back to demo data."""
import json
import os
from pathlib import Path
from schemas import Site


def load_sites(zone):
    path = os.getenv('IDLE_SITES_FILE')
    if path:
        try:
            if Path(path).stat().st_size > 50*1024*1024:
                raise ValueError('시설 파일은 50MB 이하여야 합니다. 큰 자료는 PostGIS를 사용하세요.')
            doc = json.loads(Path(path).read_text(encoding='utf-8'))
            from normalization import normalize_collection
            doc = normalize_collection(doc,os.getenv('IDLE_SITES_CRS','EPSG:4326'))['geojson']
            if doc.get('type') != 'FeatureCollection':
                raise ValueError('FeatureCollection이 필요합니다.')
            return [Site.model_validate({**f['properties'], 'geometry': f['geometry']}) for f in doc['features']], 'geojson_file'
        except (OSError, KeyError, ValueError) as exc:
            raise RuntimeError('IDLE_SITES_FILE을 읽거나 검증하지 못했습니다.') from exc
    url = os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('sites를 요청에 넣거나 IDLE_SITES_FILE 또는 DATABASE_URL을 설정하세요.')
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout = '15s'")
            rows = conn.execute('''
                SELECT site_id, name, site_type, address, source, is_demo, is_green,
                       impervious_ratio, feasibility_score, ST_AsGeoJSON(geom, 15)::json AS geometry
                FROM idle_sites
                WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))
                ORDER BY site_id LIMIT 5001
            ''', (json.dumps(zone['geometry'] if zone.get('type') == 'Feature' else zone),)).fetchall()
            if len(rows)>5000:
                raise RuntimeError('조회 시설이 5000개를 초과합니다. 분석 구역을 나누세요.')
            return [Site.model_validate(r) for r in rows], 'postgis'
    except Exception as exc:
        raise RuntimeError('PostGIS 조회 실패: 연결과 sql/schema.sql의 테이블을 확인하세요.') from exc
