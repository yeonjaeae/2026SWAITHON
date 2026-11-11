
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from shapely.geometry import shape

from app.sam_service import analyze_region

from app.landcover_api import router as landcover_router
app = FastAPI(title="Re:Green AI API")
app.include_router(landcover_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "regreen-ai"}


@app.post("/ai/segment")
async def segment_region(
    image: UploadFile = File(...),
    world_file: UploadFile = File(...),
    region: str = Form(...),
):
    # 1. 선택한 지역의 GeoJSON 확인
    try:
        region_geojson = json.loads(region)
        geom_data = (
            region_geojson.get("geometry")
            if region_geojson.get("type") == "Feature"
            else region_geojson
        )
        geom = shape(geom_data)

        if (
            geom.is_empty
            or not geom.is_valid
            or geom.geom_type not in ("Polygon", "MultiPolygon")
        ):
            raise ValueError("유효한 영역 Polygon이 필요합니다.")

    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 업로드한 항공사진과 World File 사용
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        image_path = temp_dir / "aerial.png"
        world_path = temp_dir / "aerial.pgw"

        image_path.write_bytes(await image.read())
        world_path.write_bytes(await world_file.read())

        # 3. SAM2 영역 분할
        try:
            result = analyze_region(
                image_path,
                world_path,
                region_geojson,
                image_crs="EPSG:3857",
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 4. 확정 설계 영역이 아닌 검토용 분할 결과
    result["properties"]["status"] = "needs_review"

    return {
        "status": "success",
        "segmentation": result,
    }
