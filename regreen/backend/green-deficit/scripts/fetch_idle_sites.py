"""서울 유휴 부지 경계를 OpenStreetMap 파일에서 뽑아 후보지 추천 서버용 파일로 만든다.

1) 한국 OSM 파일 받기 (Geofabrik, 약 290MB, 매일 갱신 · 공용 서버를 안 거쳐서 안정적)
   https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
2) python scripts/fetch_idle_sites.py --pbf <받은 파일> --out ../idle_sites_seoul.geojson
3) 후보지 서버: IDLE_SITES_FILE=<그 파일> 로 실행

부지 종류 (site_type)
- parking_lot     주차장 (지하·다층·옥상 주차장 제외)
- schoolyard      학교
- public_plaza    광장·보행 광장
- vacant_lot      공터 (개발 예정지·나대지: landuse=brownfield/greenfield)
- public_facility 공공기관 부지 (주민센터·도서관·경찰서·소방서·우체국 등의 대지)
- public_rooftop  공공 옥상 (위 공공기관이 건물 외곽선으로 그려진 경우, 정부·공공 건물)

불투수율 (impervious_ratio): 위성(Sentinel-2) NDVI 10m 칸 중 0.2 미만(식물이 거의 없는 칸) 비율로 추정.
진짜 포장 면적이 아니라 추정치이고, 칸이 하나도 안 걸리는 작은 부지는 null.
옥상은 위성으로 재면 의미가 없어서 null.

- 서울 경계 안(중심점 기준)만, 너무 작은 조각은 제외.
- 후보지 서버는 한 파일에 5,000곳까지 받으므로 넘으면 종류별 몫을 정해 면적이 큰 순으로 자른다.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import osmium
import rasterio
import rasterio.mask
import shapely
from shapely import wkb
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402

MAX_SITES = 5000
MIN_AREA = {"parking_lot": 300, "schoolyard": 1000, "public_plaza": 300,
            "vacant_lot": 300, "public_facility": 300, "public_rooftop": 300}
# 5,000곳을 넘으면 종류별로 이만큼까지 (큰 순). 남는 자리는 나머지 중 큰 순으로 채움
QUOTA = {"parking_lot": 1800, "schoolyard": 1300, "public_plaza": 600,
         "vacant_lot": 500, "public_facility": 500, "public_rooftop": 300}
TYPE_KO = {"parking_lot": "주차장", "schoolyard": "학교", "public_plaza": "광장",
           "vacant_lot": "공터", "public_facility": "공공기관", "public_rooftop": "공공 건물"}
PUBLIC_AMENITY = {"townhall", "community_centre", "library", "police", "fire_station",
                  "post_office", "courthouse", "social_facility"}
PUBLIC_BUILDING = {"government", "civic", "public"}
NDVI_BARE = 0.2

# 서울 범위 (여유 있게) — 이 밖의 도형은 아예 만들지 않아 빠르게
W, S, E, N = 126.70, 37.38, 127.25, 37.75


def site_type(t):
    if t.get("amenity") == "school":
        return "schoolyard"
    if t.get("amenity") == "parking":
        if t.get("parking") in ("underground", "multi-storey", "rooftop"):
            return None
        return "parking_lot"
    if t.get("place") == "square" or (t.get("highway") == "pedestrian" and t.get("area") == "yes"):
        return "public_plaza"
    if t.get("landuse") in ("brownfield", "greenfield"):
        return "vacant_lot"
    public = t.get("amenity") in PUBLIC_AMENITY or t.get("office") == "government"
    if t.get("building") in PUBLIC_BUILDING or (public and t.get("building")):
        return "public_rooftop"
    if public:
        return "public_facility"
    return None


class Sites(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.wkb = osmium.geom.WKBFactory()

    def area(self, a):
        t = {tag.k: tag.v for tag in a.tags}
        kind = site_type(t)
        if not kind:
            return
        try:
            geom = wkb.loads(self.wkb.create_multipolygon(a), hex=True)
        except Exception:
            return
        x0, y0, x1, y1 = geom.bounds
        if x1 < W or x0 > E or y1 < S or y0 > N:
            return
        osm = f"{'way' if a.from_way() else 'relation'}/{a.orig_id()}"
        self.rows.append({"osm": osm, "type": kind, "name": t.get("name"), "geometry": geom})


def impervious(gdf, ndvi_path):
    """부지마다 NDVI 0.2 미만 칸의 비율 (칸 중심이 부지 안에 있는 것만)."""
    out = []
    with rasterio.open(ndvi_path) as src:
        geoms = gdf.to_crs(src.crs).geometry
        for kind, g in zip(gdf["type"], geoms):
            if kind == "public_rooftop":
                out.append(None)
                continue
            try:
                arr, _ = rasterio.mask.mask(src, [g], crop=True, filled=False)
            except ValueError:            # 래스터 밖
                out.append(None)
                continue
            v = arr[0].compressed()
            v = v[np.isfinite(v)]
            out.append(round(float((v < NDVI_BARE).mean()), 3) if v.size else None)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pbf", required=True, help="Geofabrik south-korea-latest.osm.pbf")
    p.add_argument("--boundary", default=str(config.DATA_RAW / "서울" / "boundary.gpkg"))
    p.add_argument("--ndvi", default=str(config.DATA_RAW / "서울" / "ndvi.tif"))
    p.add_argument("--out", required=True)
    a = p.parse_args()

    h = Sites()
    h.apply_file(a.pbf, locations=True)
    print(f"OSM 에서 찾은 부지 {len(h.rows):,}개", flush=True)

    seoul = gpd.read_file(a.boundary).to_crs(4326)
    gdf = gpd.GeoDataFrame(h.rows, crs=4326)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    gdf = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    inside = gdf.geometry.representative_point().within(shapely.union_all(seoul.geometry.values))
    gdf = gdf[inside].copy()
    gdf["area"] = gdf.to_crs(config.CRS_CALC).area
    gdf = gdf[gdf.apply(lambda r: r["area"] >= MIN_AREA[r["type"]], axis=1)]
    gdf = gdf.drop_duplicates("osm")
    print("서울 안 · 최소 면적 이상:\n" + gdf.groupby("type").size().to_string(), flush=True)

    if len(gdf) > MAX_SITES:
        gdf = gdf.sort_values("area", ascending=False)
        rank = gdf.groupby("type").cumcount()
        keep = rank < gdf["type"].map(QUOTA)
        chosen, rest = gdf[keep], gdf[~keep]
        gdf = gpd.GeoDataFrame(pd.concat([chosen, rest.head(max(0, MAX_SITES - len(chosen)))]),
                               crs=4326).head(MAX_SITES)
        print(f"{MAX_SITES:,}곳으로 줄임 (종류별 몫 · 큰 순):\n" + gdf.groupby("type").size().to_string())

    gdf["impervious"] = impervious(gdf, a.ndvi)
    print(f"불투수율 추정 {gdf['impervious'].notna().sum():,}곳 "
          f"(중앙값 {gdf['impervious'].median():.2f})", flush=True)

    source = f"OpenStreetMap contributors (ODbL), {date.today().isoformat()} 추출"
    features = []
    for _, row in gdf.iterrows():
        name = row["name"] if isinstance(row["name"], str) and row["name"].strip() else f"이름 없는 {TYPE_KO[row['type']]}"
        features.append({"type": "Feature", "geometry": mapping(row.geometry), "properties": {
            "site_id": f"osm-{row['osm'].replace('/', '-')}", "name": name, "site_type": row["type"],
            "source": source, "is_demo": False, "is_green": False,
            "address": None, "impervious_ratio": None if pd.isna(row["impervious"]) else float(row["impervious"]),
            "feasibility_score": None}})
    out = Path(a.out)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    print(f"완료: {len(features):,}곳 → {out} ({out.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
