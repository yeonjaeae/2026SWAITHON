from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from spatial import polygon

Ratio = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Site(Strict):
    site_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    site_type: str
    geometry: dict
    source: str = Field(min_length=1, description='데이터 기관/파일/객체 ID 등 출처')
    is_demo: bool = False
    is_green: bool = False
    address: str | None = None
    impervious_ratio: Ratio | None = None
    feasibility_score: Ratio | None = None

    @field_validator('geometry')
    @classmethod
    def valid_geometry(cls, v):
        polygon(v)
        return v

class Grid(Strict):
    grid_id: str
    geometry: dict
    deficit_index: Ratio
    _geometry = field_validator('geometry')(classmethod(lambda cls, v: (polygon(v), v)[1]))

class RegionAnalysis(BaseModel):
    # Other fields of Donghee's existing response are intentionally accepted.
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)
    candidates: dict | None
    deficit_index: Ratio | None = None
    @field_validator('candidates')
    @classmethod
    def valid_geometry(cls, v):
        if v is not None:
            polygon(v)
        return v

class Landcover(Strict):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    cls: Literal['green', 'road', 'residential'] = Field(alias='class')
    geometry: dict
    _geometry = field_validator('geometry')(classmethod(lambda cls, v: (polygon(v), v)[1]))

class Request(Strict):
    region_analysis: RegionAnalysis
    # None -> configured local file or PostGIS; [] -> explicitly empty dataset.
    sites: list[Site] | None = None
    grids: list[Grid] = Field(default_factory=list)
    landcover: list[Landcover] = Field(default_factory=list)
    min_area_m2: float = Field(default=80, gt=0, allow_inf_nan=False)
    limit: int = Field(default=10, ge=1, le=100)
    allowed_site_types: list[str] = Field(default_factory=lambda: ['parking_lot', 'schoolyard', 'public_plaza', 'public_rooftop'])

class Selection(Strict):
    candidate_id: str
    recommendations: list[dict[str, Any]]

class Vegetation(Strict):
    grass: Percent
    shrub: Percent
    tree: Percent
    @model_validator(mode='after')
    def check_sum(self):
        if abs(self.grass + self.shrub + self.tree - 100) > .001:
            raise ValueError('식생 비율의 합은 100이어야 합니다.')
        return self

class Editable(Strict):
    candidate_id: str
    geometry_crs: Literal['EPSG:4326'] = 'EPSG:4326'
    editable_geometry: dict | None
    source: str = Field(min_length=1)
    _geometry = field_validator('editable_geometry')(classmethod(lambda cls, v: (polygon(v), v)[1] if v is not None else None))

class DesignHandoff(Strict):
    candidate: dict[str, Any]
    editable: Editable
    green_ratio: Percent
    vegetation: Vegetation
