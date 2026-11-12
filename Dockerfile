FROM python:3.11-slim

WORKDIR /app

ENV TORCH_HOME=/app/torch_cache
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip certifi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir "numpy==1.26.4"
RUN pip install --no-cache-dir torch==2.1.2 torchaudio==2.1.2 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تنزيل النموذج أثناء البناء، وإذا فشل سيظهر السبب الحقيقي في Build Logs
RUN python -c "import ssl; ssl._create_default_https_context = ssl._create_unverified_context; from demucs.pretrained import get_model; get_model('htdemucs'); print('MODEL OK')"
COPY . .

CMD ["python", "bot.py"]
