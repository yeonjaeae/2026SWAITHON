"""Regenerate Swagger request schemas from each backend's installed environment."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--python',default=sys.executable);a=p.parse_args()
    sys.path.insert(0,str(ROOT))
    from gateway.main import ROUTES
    docs={}
    for name,folder,module in [('candidate','candidate-recommender-v2','main'),('design','green-design-backend','main'),('deficit','green-deficit','src.api')]:
        code=f'import json; from {module} import app; print(json.dumps(app.openapi()))'
        result=subprocess.run([a.python,'-c',code],cwd=ROOT/folder,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},check=True,capture_output=True,text=True)
        docs[name]=json.loads(result.stdout)
    def rename(value,namespace):
        if isinstance(value,dict):
            return {k:(v.replace('#/components/schemas/','#/components/schemas/'+namespace+'__') if k=='$ref' and isinstance(v,str) else rename(v,namespace)) for k,v in value.items()}
        if isinstance(value,list):return [rename(x,namespace) for x in value]
        return value
    result={'schemas':{},'paths':{}}
    for name,doc in docs.items():
        for key,schema in doc.get('components',{}).get('schemas',{}).items():
            result['schemas'][name+'__'+key]=rename(schema,name)
    for method,public,name,private,_ in ROUTES:
        operation=rename(copy.deepcopy(docs[name]['paths'][private][method.lower()]),name)
        result['paths'].setdefault(public,{})[method.lower()]=operation
    (ROOT/'gateway/contracts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Swagger 계약 생성:',len(result['paths']),'개 경로')

if __name__=='__main__':main()
