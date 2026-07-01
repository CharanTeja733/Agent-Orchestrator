FROM python:3.12-slim

WORKDIR /app

COPY index.html .

EXPOSE 8501

CMD ["python", "-m", "http.server", "8501"]
