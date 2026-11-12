import time
import subprocess
from pathlib import Path

import httpx

from config import REPLICATE_API_TOKEN


class ProcessingError(Exception):
    """خطأ معروف، ورسالته تُعرض للمستخدم كما هي."""


API = "https://api.replicate.com/v1"

# نموذج ryan5453/demucs على Replicate (يدعم htdemucs)
DEMUCS_VERSION = (
    "1e214c25ff584f7f82ddc116cc0780007101ae531e3d9ecc426e9fd434437e40"
)

HEADERS = {"Authorization": f"Bearer {REPLICATE_API_TOKEN}"}


def run_command(command, timeout=None):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise ProcessingError("استغرقت المعالجة وقتاً أطول من المسموح.")

    if result.returncode != 0:
        stderr = result.stderr or ""

        if "does not contain any stream" in stderr or (
            "Stream map" in stderr and "matches no streams" in stderr
        ):
            raise ProcessingError("هذا الفيديو لا يحتوي على صوت.")

        raise RuntimeError(stderr[-1500:])

    return result


def upload_file(path):
    """رفع الملف الصوتي إلى Replicate وإرجاع رابطه."""
    with open(path, "rb") as f:
        response = httpx.post(
            f"{API}/files",
            headers=HEADERS,
            files={"content": (Path(path).name, f, "audio/mpeg")},
            timeout=120
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Upload failed: {response.text[-500:]}")

    return response.json()["urls"]["get"]


def separate_with_replicate(audio_path, timeout=600):
    """يفصل الصوت عبر Demucs على Replicate ويرجع (رابط_الكلام, رابط_الموسيقى)."""
    audio_url = upload_file(audio_path)

    response = httpx.post(
        f"{API}/predictions",
        headers=HEADERS,
        json={
            "version": DEMUCS_VERSION,
            "input": {
                "audio": audio_url,
                "model": "htdemucs",
                "stem": "vocals",
                "output_format": "mp3",
                "mp3_bitrate": 320,
                "shifts": 1,
                "overlap": 0.25,
                "split": True,
            },
        },
        timeout=60
    )

    if response.status_code == 402:
        raise ProcessingError("رصيد Replicate غير كافٍ. اشحن الحساب.")
    if response.status_code == 401:
        raise ProcessingError("توكن Replicate غير صحيح.")
    if response.status_code >= 400:
        raise RuntimeError(f"Replicate error: {response.text[-500:]}")

    prediction = response.json()
    poll_url = prediction["urls"]["get"]

    start = time.time()
    while True:
        if time.time() - start > timeout:
            raise ProcessingError("استغرقت خدمة الفصل وقتاً طويلاً.")

        time.sleep(3)

        poll = httpx.get(poll_url, headers=HEADERS, timeout=60)
        poll.raise_for_status()
        data = poll.json()
        status = data["status"]

        if status == "succeeded":
            output = data.get("output")
            break

        if status in ("failed", "canceled"):
            raise ProcessingError(
                f"فشلت خدمة الفصل: {str(data.get('error'))[:200]}"
            )

    if not isinstance(output, dict):
        raise RuntimeError(f"Unexpected output: {output}")

    vocals_url = output.get("vocals")
    music_url = (
        output.get("no_vocals")
        or output.get("other")
        or output.get("accompaniment")
    )

    if not vocals_url or not music_url:
        raise RuntimeError(f"Missing stems in output: {list(output.keys())}")

    return vocals_url, music_url


def download(url, destination):
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)


def process_video(video_path, work_dir):

    work_dir = Path(work_dir)
    video_path = Path(video_path)

    audio_path = work_dir / "input.mp3"

    # استخراج الصوت (MP3 لتقليل حجم الرفع)
    run_command([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        "-b:a", "256k",
        str(audio_path)
    ], timeout=120)

    if not audio_path.exists() or audio_path.stat().st_size < 1000:
        raise ProcessingError("هذا الفيديو لا يحتوي على صوت.")

    # الفصل عبر الخدمة الخارجية
    vocals_url, music_url = separate_with_replicate(audio_path)

    vocals = work_dir / "vocals.mp3"
    music_file = work_dir / "Extracted_Music.mp3"

    download(vocals_url, vocals)
    download(music_url, music_file)

    # فيديو بالكلام فقط
    clean_video = work_dir / "Video_No_Music.mp4"

    run_command([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(vocals),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(clean_video)
    ], timeout=180)

    return clean_video, music_file
