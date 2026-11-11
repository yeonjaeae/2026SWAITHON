
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from environmental import calculate_environmental_effect
from fastapi.middleware.cors import CORSMiddleware
from geometry import calculate_editable_area

app = FastAPI(
    title="Green Design Backend",
    description="공존형 녹지 설계 및 환경 효과 분석 API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"]
)

class VegetationRatio(BaseModel):
    grass: float = Field(ge=0, le=100)
    shrub: float = Field(ge=0, le=100)
    tree: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_ratio(self):
        total = self.grass + self.shrub + self.tree

        if abs(total - 100) > 0.001:
            raise ValueError("식생 비율의 합계는 100이어야 합니다.")

        return self


class DesignRequest(BaseModel):
    candidate_id: str
    total_area: float = Field(gt=0)
    green_ratio: float = Field(ge=0, le=100)
    protected_area: float = Field(ge=0)
    vegetation: VegetationRatio

from typing import Any

class CandidateFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


class CandidateData(BaseModel):
    candidate_id: str
    area_m2: float = Field(gt=0)
    geometry_crs: str
    feature: CandidateFeature

class CandidateDesignRequest(BaseModel):
    candidate: CandidateData
    green_ratio: float = Field(ge=0, le=100)
    protected_area: float = Field(ge=0)
    vegetation: VegetationRatio

@app.get("/")
def home():
    return {
        "message": "Green Design Backend 실행 성공",
        "status": "running"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "green-design-backend"
    }


@app.post("/api/design/calculate")
def calculate_design(data: DesignRequest):

    # 1. 보존 면적 검증
    if data.protected_area > data.total_area:
        raise HTTPException(
            status_code=400,
            detail="보존 면적이 전체 면적보다 클 수 없습니다."
        )

    # 2. 녹지화 면적 계산
    requested_green_area = (
        data.total_area * data.green_ratio / 100
    )

    available_area = (
        data.total_area - data.protected_area
    )

    actual_green_area = min(
        requested_green_area,
        available_area
    )

    remaining_area = (
        data.total_area - actual_green_area
    )

    # 보존 조건 및 설계 가능 여부 확인
    warnings = []

    if requested_green_area > available_area:
        warnings.append(
            "희망 녹지화 면적이 가용 면적을 초과하여 "
            "자동으로 조정되었습니다."
        )

    if actual_green_area == 0:
        warnings.append(
            "녹지화 가능한 면적이 없습니다."
        )

    # 3. 식생 유형별 면적 계산
    grass_area = (
        actual_green_area * data.vegetation.grass / 100
    )

    shrub_area = (
        actual_green_area * data.vegetation.shrub / 100
    )

    tree_area = (
        actual_green_area * data.vegetation.tree / 100
    )

    # 4. 예상 식재 수량 계산
    # 임시 설계 가정: 관목 1주/㎡, 교목 1주/16㎡
    shrub_count = int(shrub_area / 1)
    tree_count = int(tree_area / 16)

     # 5. 환경 효과 및 조성 비용 계산
    environmental_result = calculate_environmental_effect(
    grass_area=grass_area,
    shrub_area=shrub_area,
    tree_count=tree_count
    )

    # AI 이미지 생성 모듈에 전달할 설계 조건
    ai_design_data = {
        "candidate_id": data.candidate_id,
        "green_area_m2": round(actual_green_area, 2),
        "green_ratio_percent": round(
            actual_green_area / data.total_area * 100, 2
        ),
        "vegetation": {
            "grass_percent": data.vegetation.grass,
            "shrub_percent": data.vegetation.shrub,
            "tree_percent": data.vegetation.tree
        },
        "plant_count": {
            "shrub": shrub_count,
            "tree": tree_count
        },
        "protected_area_m2": data.protected_area,
        "instructions": (
            "기존 보행로, 출입구 및 보존 공간을 유지하고 "
            "지정된 녹지화 비율과 식생 구성을 반영한다."
        )
    }

    return {
        "candidate_id": data.candidate_id,
        "total_area": data.total_area,
        "requested_green_area": round(
            requested_green_area, 2
        ),
        "available_area": round(available_area, 2),
        "green_area": round(actual_green_area, 2),
        "remaining_area": round(remaining_area, 2),
        "protected_area": data.protected_area,
        "actual_green_ratio": round(
            actual_green_area / data.total_area * 100, 2
        ),
        "feasible": requested_green_area <= available_area,
        "vegetation_area": {
            "grass": round(grass_area, 2),
            "shrub": round(shrub_area, 2),
            "tree": round(tree_area, 2)
        },
        "plant_count": {
            "shrub": shrub_count,
            "tree": tree_count
        },
        "assumptions": {
            "shrub_density": "1주/㎡ (임시 가정)",
            "tree_density": "1주/16㎡ (임시 가정)"
        },
        "environmental_effect": environmental_result,
        "warnings": warnings,
        "ai_design_data": ai_design_data
    }

@app.post("/api/design/candidate")
def receive_candidate(data: CandidateData):

    if data.geometry_crs != "EPSG:4326":
        raise HTTPException(
            status_code=400,
            detail="현재 EPSG:4326 좌표계만 지원합니다."
        )

    if data.feature.id != data.candidate_id:
        raise HTTPException(
            status_code=400,
            detail="후보지 ID가 일치하지 않습니다."
        )

    return {
        "status": "received",
        "candidate_id": data.candidate_id,
        "total_area_m2": data.area_m2,
        "geometry_crs": data.geometry_crs,
        "geometry": data.feature.geometry
    }

@app.post("/api/design/from-candidate")
def calculate_from_candidate(data: CandidateDesignRequest):

    candidate = data.candidate

    if candidate.geometry_crs != "EPSG:4326":
        raise HTTPException(
            status_code=400,
            detail="현재 EPSG:4326 좌표계만 지원합니다."
        )

    if candidate.feature.id != candidate.candidate_id:
        raise HTTPException(
            status_code=400,
            detail="후보지 ID가 일치하지 않습니다."
        )

    design_request = DesignRequest(
        candidate_id=candidate.candidate_id,
        total_area=candidate.area_m2,
        green_ratio=data.green_ratio,
        protected_area=data.protected_area,
        vegetation=data.vegetation
    )

    result = calculate_design(design_request)

    result["candidate_geometry"] = candidate.feature.geometry
    result["geometry_crs"] = candidate.geometry_crs

    return result

class SpatialDesignRequest(BaseModel):
    candidate: CandidateData
    editable_geometry: dict[str, Any]
    green_ratio: float = Field(ge=0, le=100)
    vegetation: VegetationRatio


@app.post("/api/design/spatial")
def calculate_spatial_design(data: SpatialDesignRequest):

    candidate = data.candidate

    # 후보지 데이터 확인
    if candidate.geometry_crs != "EPSG:4326":
        raise HTTPException(
            status_code=400,
            detail="현재 EPSG:4326 좌표계만 지원합니다."
        )

    if candidate.feature.id != candidate.candidate_id:
        raise HTTPException(
            status_code=400,
            detail="후보지 ID가 일치하지 않습니다."
        )

    # 후보지와 녹지화 대상 영역의 교차 면적 계산
    try:
        spatial_result = calculate_editable_area(
            candidate_geometry=candidate.feature.geometry,
            editable_geometry=data.editable_geometry
        )
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    editable_area = spatial_result["editable_area_m2"]

    # 전체 후보지 면적을 기준으로 희망 녹지화 면적 계산
    requested_green_area = candidate.area_m2 * data.green_ratio / 100

    # 실제 녹지화 면적은 editable 영역을 초과할 수 없음
    actual_green_area = min(
        requested_green_area,
        editable_area
    )

    # 식생별 면적
    grass_area = actual_green_area * data.vegetation.grass / 100
    shrub_area = actual_green_area * data.vegetation.shrub / 100
    tree_area = actual_green_area * data.vegetation.tree / 100

    # 식재 수량 (임시 기준)
    shrub_count = int(shrub_area / 1)
    tree_count = int(tree_area / 16)

    # 기존 환경 효과 계산 재사용
    environmental_result = calculate_environmental_effect(
        grass_area=grass_area,
        shrub_area=shrub_area,
        tree_count=tree_count
    )

    warnings = []

    if requested_green_area > editable_area:
        warnings.append(
            "희망 녹지화 면적이 녹지화 가능 영역을 초과하여 자동 조정되었습니다."
        )

    return {
        "candidate_id": candidate.candidate_id,
        "total_area_m2": candidate.area_m2,
        "editable_area_m2": editable_area,
        "requested_green_area_m2": round(requested_green_area, 2),
        "green_area_m2": round(actual_green_area, 2),
        "actual_green_ratio": round(
            actual_green_area / candidate.area_m2 * 100, 2
        ),
        "vegetation_area": {
            "grass": round(grass_area, 2),
            "shrub": round(shrub_area, 2),
            "tree": round(tree_area, 2)
        },
        "plant_count": {
            "shrub": shrub_count,
            "tree": tree_count
        },
        "environmental_effect": environmental_result,
        "editable_geometry": spatial_result["editable_geometry"],
        "warnings": warnings
    }