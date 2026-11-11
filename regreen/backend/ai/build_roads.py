"""서울 도로를 OSM 파일에서 한 번만 뽑아 seoul_roads.gpkg 로 저장한다.

AI 서버가 매번 공용 도로 서버(Overpass)에 묻지 않고 이 파일을 읽게 하기 위함.
(공용 서버가 바쁘면 AI 분석 전체가 실패/시간 초과됐었음)

1) 한국 OSM 파일 받기 (Geofabrik, 약 290MB, 매일 갱신)
   https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
2) python build_roads.py <받은 .osm.pbf 경로>
   → 같은 폴더에 seoul_roads.gpkg (EPSG:4326, 열: highway, width, geometry)
"""
import sys
from pathlib import Path

import geopandas as gpd
import osmium
from shapely.geometry import LineString, Polygon

# 서울 범위 (조금 여유 있게)
W, S, E, N = 126.70, 37.38, 127.25, 37.75
OUT = Path(__file__).resolve().parent / "seoul_roads.gpkg"


class Roads(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def way(self, w):
        hw = w.tags.get("highway")
        if not hw:
            return
        try:
            pts = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2 or not any(W <= x <= E and S <= y <= N for x, y in pts):
            return
        # 광장처럼 면으로 그린 도로(area=yes)는 면, 나머지는 선
        if w.tags.get("area") == "yes" and len(pts) >= 4 and pts[0] == pts[-1]:
            geom = Polygon(pts)
        else:
            geom = LineString(pts)
        self.rows.append({"highway": hw, "width": w.tags.get("width"), "geometry": geom})


def main():
    pbf = sys.argv[1]
    h = Roads()
    h.apply_file(pbf, locations=True)
    gdf = gpd.GeoDataFrame(h.rows, crs=4326)
    gdf.to_file(OUT, layer="roads", driver="GPKG")
    print(f"서울 도로 {len(gdf):,}개 → {OUT} ({OUT.stat().st_size / 1e6:.1f}MB)")
    print(gdf["highway"].value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
