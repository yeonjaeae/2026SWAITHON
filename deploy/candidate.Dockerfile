# 후보지 추천 API (candidate-recommender-v2)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY candidate-recommender-v2/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY candidate-recommender-v2/ ./
# 추천 결과 저장용 SQLite 는 볼륨(/data)에 둔다 (docker-compose.yml 의 RECOMMENDATION_DB)
RUN mkdir -p /data
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--root-path", "/candidate"]
