# 녹지 설계 API (green-design-backend). 폴더에 requirements.txt 가 없어 코드가 쓰는 패키지를 직접 적는다.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "pydantic>=2.9,<3" "shapely>=2.1,<3" "pyproj>=3.6,<4"
COPY green-design-backend/ ./
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--root-path", "/design"]
