FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# numpy أولاً، ثم نسخة CPU فقط من torch
RUN pip install --no-cache-dir "numpy==1.26.4"
RUN pip install --no-cache-dir torch==2.1.2 torchaudio==2.1.2 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تنزيل نموذج Demucs أثناء البناء حتى لا يتأخر أول فيديو
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

COPY . .

CMD ["python", "bot.py"]
