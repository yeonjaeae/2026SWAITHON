"""Run: python -m uvicorn main:app --reload --port 8001"""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from schemas import Request, Selection, DesignHandoff
from service import recommend, select_candidate, design_handoff

app = FastAPI(title='Re:Green 후보지 추천 API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000',
                  'http://localhost:5173', 'http://127.0.0.1:5173'],
                  allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

def invoke(fn, request):
    try:
        return fn(request)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

@app.get('/health')
@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'candidate-recommender', 'version': '1.0.0'}

@app.post('/recommendations/from-region-analysis')
def recommendations(request: Request):
    return invoke(recommend, request)

@app.get('/recommendations/demo')
def demo(limit: int = Query(10, ge=1, le=100), min_area_m2: float = Query(80, gt=0, allow_inf_nan=False)):
    doc = json.loads((Path(__file__).parent / 'examples/recommend_request.json').read_text())
    doc.update(limit=limit, min_area_m2=min_area_m2)
    result = invoke(recommend, Request.model_validate(doc))
    result['source'] = 'synthetic_demo'
    return result

@app.post('/recommendations/select')
def select(request: Selection):
    return invoke(select_candidate, request)

@app.post('/recommendations/design-handoff')
def handoff(request: DesignHandoff):
    return invoke(design_handoff, request)
