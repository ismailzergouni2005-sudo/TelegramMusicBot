FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# إذا لم يكن numpy أو torch يعمل، يفشل البناء هنا وليس وقت التشغيل
RUN python -c "import numpy, torch, torchaudio, demucs; print('OK', numpy.__version__, torch.__version__)"

COPY . .

CMD ["python", "bot.py"]
