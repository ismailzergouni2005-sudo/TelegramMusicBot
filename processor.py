import sys
import subprocess
from pathlib import Path


class ProcessingError(Exception):
    """خطأ معروف، ورسالته تُعرض للمستخدم كما هي."""


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
        raise ProcessingError(
            "استغرقت المعالجة وقتاً أطول من المسموح. "
            "جرّب فيديو أقصر."
        )

    if result.returncode != 0:
        stderr = result.stderr or ""

        # العملية قُتلت بسبب نفاد الذاكرة
        if result.returncode in (-9, 137) or "Killed" in stderr:
            raise ProcessingError(
                "نفدت ذاكرة الخادم أثناء المعالجة. "
                "جرّب فيديو أقصر (10 ثوانٍ مثلاً)."
            )

        # الفيديو بدون صوت
        if "does not contain any stream" in stderr or \
           "Stream map" in stderr and "matches no streams" in stderr:
            raise ProcessingError("هذا الفيديو لا يحتوي على صوت.")

        raise RuntimeError(stderr[-1500:])

    return result


def process_video(video_path, work_dir):

    work_dir = Path(work_dir)
    video_path = Path(video_path)

    audio_path = work_dir / "input.wav"
    output_dir = work_dir / "separated"

    # استخراج الصوت من الفيديو
    run_command([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        str(audio_path)
    ], timeout=120)

    if not audio_path.exists() or audio_path.stat().st_size < 1000:
        raise ProcessingError("هذا الفيديو لا يحتوي على صوت.")

    # فصل الصوت عن الموسيقى
    run_command([
        sys.executable, "-m", "demucs",
        "--two-stems=vocals",
        "-n", "htdemucs",
        "--device", "cpu",
        "--segment", "3",
        "--shifts", "0",
        "-j", "0",
        "-o", str(output_dir),
        str(audio_path)
    ], timeout=900)

    stems_dir = output_dir / "htdemucs" / "input"

    vocals = stems_dir / "vocals.wav"
    music = stems_dir / "no_vocals.wav"

    if not vocals.exists() or not music.exists():
        raise ProcessingError("فشل فصل الصوت، لم تُنتَج الملفات.")

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

    # تصدير الموسيقى MP3
    music_file = work_dir / "Extracted_Music.mp3"

    run_command([
        "ffmpeg", "-y",
        "-i", str(music),
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        str(music_file)
    ], timeout=120)

    return clean_video, music_file
