FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/models OMP_NUM_THREADS=2
WORKDIR /app
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install -r requirements.txt && useradd -m -u 10001 studio && mkdir data models && chown -R studio:studio /app
COPY studio ./studio
USER studio
EXPOSE 8000
CMD ["uvicorn","studio.api:app","--host","0.0.0.0","--port","8000","--workers","1"]
