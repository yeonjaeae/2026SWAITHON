"""Service-to-service authentication and bounded request bodies."""
import hmac
import os
from starlette.responses import JSONResponse

MAX_BODY=24*1024*1024

def production():
    return os.getenv('APP_ENV','development')=='production'

def check_config():
    if production() and len(os.getenv('SERVICE_API_KEY','')) < 32:
        raise RuntimeError('운영 모드는 32자 이상 SERVICE_API_KEY가 필요합니다.')
    ttl=int(os.getenv('RECOMMENDATION_TTL_SECONDS','86400'))
    if not 60<=ttl<=604800:
        raise RuntimeError('RECOMMENDATION_TTL_SECONDS는 60~604800이어야 합니다.')

class BoundaryMiddleware:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        async def reject(status,detail):
            await JSONResponse({'detail':detail},status_code=status)(scope,receive,send)
        key=os.getenv('SERVICE_API_KEY','')
        path=scope.get('path','')
        headers=dict(scope['headers'])
        if path not in ('/health','/api/health') and scope['method']!='OPTIONS':
            if production() and len(key)<32:
                return await reject(503,'운영 인증 설정이 필요합니다.')
            if key and not hmac.compare_digest(headers.get(b'authorization',b''),('Bearer '+key).encode()):
                return await reject(401,'유효한 서비스 인증이 필요합니다.')
        if scope['method'] in ('POST','PUT','PATCH'):
            try:
                if int(headers.get(b'content-length',b'0'))>MAX_BODY:
                    return await reject(413,'요청은 24MB 이하여야 합니다.')
            except ValueError:
                return await reject(400,'잘못된 Content-Length입니다.')
            chunks=[]; size=0
            while True:
                msg=await receive()
                if msg['type']=='http.disconnect': return
                chunk=msg.get('body',b'');size+=len(chunk)
                if size>MAX_BODY:
                    return await reject(413,'요청은 24MB 이하여야 합니다.')
                chunks.append(chunk)
                if not msg.get('more_body',False): break
            first=True
            async def replay():
                nonlocal first
                if first:
                    first=False
                    return {'type':'http.request','body':b''.join(chunks),'more_body':False}
                return await receive()
            return await self.app(scope,replay,send)
        await self.app(scope,receive,send)
