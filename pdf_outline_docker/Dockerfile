FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY extract_outline.py .
COPY input ./input
RUN mkdir -p output

CMD ["python", "extract_outline.py"]
