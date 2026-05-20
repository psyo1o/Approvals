FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# fonts-nanum: PDF 한글 / svglib 1.5.x는 pycairo 없이 동작 (1.6+는 빌드 도구 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app

ENV TZ=Asia/Seoul
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app"]
