"""백엔드 서버 4개를 한 번에 켠다.  (끄기: Ctrl + C)

    python run_backend.py

- 8000 녹지 부족지수 · 8001 후보지 추천 · 8002 녹지 설계 → 지금 실행한 파이썬(.venv)으로 켬
- 8003 AI 토지 피복 → ai/.venv 가 있으면 그 파이썬으로 켬, 없으면 건너뜀
  (AI 가 없어도 화면은 공공 데이터 기준으로 동작한다)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(line_buffering=True)   # 안내 문구가 바로 보이게


def venv_python(folder: Path):
    for p in (folder / ".venv" / "Scripts" / "python.exe", folder / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return None


SERVERS = [
    # (이름, 폴더, 모듈, 포트, 추가 환경 변수)
    ("녹지 부족지수", "green-deficit", "src.api:app", 8000, {}),
    ("후보지 추천", "candidate-recommender-v2", "main:app", 8001,
     {"IDLE_SITES_FILE": str(HERE / "candidate-recommender-v2" / "data" / "idle_sites_seoul.geojson")}),
    ("녹지 설계", "green-design-backend", "main:app", 8002, {}),
]


def main():
    procs = []
    for name, folder, module, port, env in SERVERS:
        procs.append((name, port, subprocess.Popen(
            [sys.executable, "-m", "uvicorn", module, "--port", str(port)],
            cwd=HERE / folder, env={**os.environ, **env})))

    ai_python = venv_python(HERE / "ai")
    if ai_python:
        procs.append(("AI 토지 피복", 8003, subprocess.Popen(
            [ai_python, "-m", "uvicorn", "main:app", "--port", "8003"], cwd=HERE / "ai")))
    else:
        print("※ ai/.venv 가 없어 AI 서버(8003)는 건너뜁니다. README 의 'AI 서버 설치'를 보세요.")

    time.sleep(3)
    print("\n켜진 서버")
    for name, port, p in procs:
        state = "실행 중" if p.poll() is None else "꺼짐 (위 오류를 확인하세요)"
        print(f"  {port}  {name:<8} {state}   http://localhost:{port}/docs")
    print("\n프론트: regreen/frontend 에서 npm run dev → http://localhost:5173")
    print("끄려면 Ctrl + C\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
