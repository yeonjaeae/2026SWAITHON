"""Create local Compose configuration once. Never print or overwrite secrets."""
from pathlib import Path
import os
import secrets

def main():
    root=Path(__file__).resolve().parent
    path=root/'.env'
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        print('.env가 이미 있으므로 유지했습니다.')
        return
    with os.fdopen(fd,'w') as f:
        f.write('APP_ENV=development\nBIND_ADDRESS=127.0.0.1\nPUBLIC_PORT=8080\n')
        f.write('SERVICE_API_KEY='+secrets.token_urlsafe(32)+'\n')
        f.write('GATEWAY_API_KEY=\nCORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173\n')
        f.write('IDLE_SITES_FILE=\nIDLE_SITES_CRS=EPSG:4326\nDATABASE_URL=\n')
    print('개발용 .env를 생성했습니다. 키는 출력하지 않았습니다.')

if __name__=='__main__':main()
