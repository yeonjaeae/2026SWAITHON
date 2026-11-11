"""Run: python -m uvicorn main:app --reload --port 8001"""
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from shapely.errors import GEOSException
from schemas import Request, Selection, DesignHandoff, NormalizeRequest, AdaptRequest
from service import recommend, select_candidate, design_handoff
from normalization import normalize_collection
from ai_adapter import adapt_landcover, request_ai, UpstreamError
from runtime import BoundaryMiddleware, check_config, production
from storage import save_snapshot, load_snapshot, connection

@asynccontextmanager
async def lifespan(app):
    check_config()
    with connection() as conn:
        conn.execute('SELECT 1')
    yield

app=FastAPI(title='Re:Green 후보지 추천 API',version='2.0.0',lifespan=lifespan)
app.add_middleware(BoundaryMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=[s.strip() for s in os.getenv('CORS_ORIGINS','http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173').split(',') if s.strip()],
    allow_methods=['GET','POST'],allow_headers=['Content-Type','Authorization'])

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    # Never echo binary uploads, NaN inputs, or arbitrary exception objects.
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':e['loc'],'type':e['type'],'msg':e['msg']} for e in exc.errors()]})

def invoke(fn,*args):
    try:
        return fn(*args)
    except UpstreamError as exc:
        raise HTTPException(exc.status,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except (ValueError,GEOSException) as exc:
        raise HTTPException(422,str(exc)) from exc
    except (RuntimeError,sqlite3.Error,OSError) as exc:
        logging.getLogger(__name__).warning('Service operation failed: %s',type(exc).__name__)
        raise HTTPException(503,'데이터 저장소 또는 서비스 설정을 확인하세요.') from exc

@app.get('/health')
@app.get('/api/health')
def health():
    return {'status':'ok','service':'candidate-recommender','version':'2.0.0'}

@app.get('/ready')
def ready():
    def check():
        check_config()
        with connection() as conn:
            conn.execute('SELECT 1')
        return {'status':'ready','snapshot_store':'ok',
                'ai_url_configured':bool(os.getenv('AI_BASE_URL')),
                'site_source_configured':bool(os.getenv('IDLE_SITES_FILE') or os.getenv('DATABASE_URL')),
                'note':'AI/시설 DB 실제 가용성과 데이터 커버리지는 개별 요청에서 검증합니다.'}
    return invoke(check)

@app.post('/data/normalize')
def normalize(request:NormalizeRequest):
    return invoke(normalize_collection,request.geojson,request.source_crs,request.repair)

@app.post('/integrations/ai/normalize-landcover')
def normalize_ai(request:AdaptRequest):
    return invoke(adapt_landcover,request.feature_collection,request.region)

@app.post('/integrations/ai/landcover')
async def ai_landcover(image:UploadFile=File(...),world_file:UploadFile=File(...),
                       region:str=Form(...),image_crs:str=Form(...)):
    try:
        geometry=json.loads(region)
        # Canonicalize Feature wrapper so footprint and returned deficit request agree.
        if isinstance(geometry,dict) and geometry.get('type')=='Feature':
            geometry=geometry.get('geometry')
        image_bytes=await image.read(20*1024*1024+1)
        world_bytes=await world_file.read(1025)
        return await request_ai(image_bytes,world_bytes,geometry,image_crs)
    except UpstreamError as exc:
        raise HTTPException(exc.status,str(exc)) from exc
    except (ValueError,GEOSException) as exc:
        raise HTTPException(422,str(exc)) from exc
    finally:
        await image.close();await world_file.close()

@app.post('/recommendations/from-region-analysis')
def recommendations(request:Request):
    return invoke(lambda:save_snapshot(recommend(request)))

@app.get('/recommendations/demo')
def demo(limit:int=Query(10,ge=1,le=100),min_area_m2:float=Query(80,gt=0,allow_inf_nan=False)):
    if production():
        raise HTTPException(404,'운영 모드에서 데모는 제공하지 않습니다.')
    doc=json.loads((Path(__file__).parent/'examples/recommend_request.json').read_text())
    doc.update(limit=limit,min_area_m2=min_area_m2)
    result=invoke(recommend,Request.model_validate(doc));result['source']='synthetic_demo'
    return invoke(save_snapshot,result)

def resolve_selection(request):
    if request.recommendation_id is not None:
        result=load_snapshot(request.recommendation_id)
        return select_candidate(Selection(candidate_id=request.candidate_id,recommendations=result['recommendations']))
    if production():
        raise ValueError('운영 모드에서는 서버 발급 recommendation_id로 선택하세요.')
    return select_candidate(request)

@app.post('/recommendations/select')
def select(request:Selection):
    return invoke(resolve_selection,request)

@app.post('/recommendations/design-handoff')
def handoff(request:DesignHandoff):
    if request.editable.review_status!='reviewed':
        raise HTTPException(409,'editable 분석/검토가 완료된 후 review_status=reviewed로 전달하세요.')
    def work():
        if request.recommendation_id:
            candidate=resolve_selection(Selection(recommendation_id=request.recommendation_id,candidate_id=request.candidate_id))
            req=request.model_copy(update={'candidate':candidate})
        else:
            if production():
                raise ValueError('운영 설계 요청에는 recommendation_id와 candidate_id가 필요합니다.')
            req=request
        if production() and req.candidate['feature']['properties'].get('is_demo'):
            raise ValueError('가상 후보지로 운영 설계를 계산할 수 없습니다.')
        return design_handoff(req)
    return invoke(work)
