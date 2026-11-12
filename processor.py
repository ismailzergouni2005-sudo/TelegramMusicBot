import sys
import subprocess
import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
from pathlib import Path



def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-3000:])

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
    ])

    # فصل الصوت عن الموسيقى
    run_command([
        sys.executable, "-m", "demucs",
        "--two-stems=vocals",
        "-n", "htdemucs",
        "--device", "cpu",
        "--segment", "6",
        "-j", "1",
        "-o", str(output_dir),
        str(audio_path)
    ])

    stems_dir = output_dir / "htdemucs" / "input"

    vocals = stems_dir / "vocals.wav"
    music = stems_dir / "no_vocals.wav"

    if not vocals.exists() or not music.exists():
        raise FileNotFoundError("Separated audio files not found")

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
    ])

    # تصدير الموسيقى MP3
    music_file = work_dir / "Extracted_Music.mp3"

    run_command([
        "ffmpeg", "-y",
        "-i", str(music),
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        str(music_file)
    ])

    return clean_video, music_file
