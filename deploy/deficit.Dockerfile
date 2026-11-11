# 녹지 부족지수 API (green-deficit). 분석 결과(output/)를 그대로 읽어 서비스한다.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/requirements-deficit.txt .
RUN pip install --no-cache-dir -r requirements-deficit.txt
COPY green-deficit/src ./src
COPY green-deficit/output ./output
EXPOSE 8000
# nginx 가 /deficit 접두어를 떼고 넘겨 주므로, Swagger(/docs)가 올바른 주소를 쓰도록 root-path 지정
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/deficit"]
