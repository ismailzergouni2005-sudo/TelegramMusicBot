import subprocess
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

    # Extract audio from video
    run_command([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        str(audio_path)
    ])

    # Separate voice and music using Demucs
    run_command([
        "python", "-m", "demucs",
        "--two-stems=vocals",
        "-n", "htdemucs",
        "--device", "cpu",
        "-o", str(output_dir),
        str(audio_path)
    ])

    stems_dir = output_dir / "htdemucs" / "input"

    vocals = stems_dir / "vocals.wav"
    music = stems_dir / "no_vocals.wav"

    if not vocals.exists() or not music.exists():
        raise FileNotFoundError("Separated audio files not found")

    # Create video with voice only
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

    # Export extracted music as MP3
    music_file = work_dir / "Extracted_Music.mp3"

    run_command([
        "ffmpeg", "-y",
        "-i", str(music),
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        str(music_file)
    ])

    return clean_video, music_file
