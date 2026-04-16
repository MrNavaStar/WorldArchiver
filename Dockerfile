FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y openjdk-25-jdk && rm -rf /var/cache/apt/archives /var/lib/apt/lists/*

COPY . .

CMD ["python3", "main.py"]