"""
YouTube Auto-Clipper
====================
Downloads the full video, gets captions, uses GPT-4 or random selection to
pick highlights, cuts clips with FFmpeg, then deletes the source video.

Requirements:
    pip install yt-dlp openai youtube-transcript-api google-api-python-client
    google-auth-oauthlib google-auth-httplib2
    FFmpeg: https://ffmpeg.org/download.html
"""

import json
import os
import random
import re
import subprocess
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "your-openai-api-key-here")
YOUTUBE_CLIENT_SECRETS = os.environ.get("YOUTUBE_CLIENT_SECRETS", str(Path(__file__).parent / "client_secrets.json"))
WORK_DIR = Path(os.environ.get("WORK_DIR", str(Path(__file__).parent / "clipper_output")))
CLIPS_PER_VIDEO = int(os.environ.get("CLIPS_PER_VIDEO", "3"))
CLIP_LENGTH_MINUTES = float(os.environ.get("CLIP_LENGTH_MINUTES", "5"))
PROCESSED_LOG = WORK_DIR / "processed_videos.json"
UPLOAD_PRIVACY = os.environ.get("UPLOAD_PRIVACY", "private")


def ensure_dirs():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "downloads").mkdir(exist_ok=True)
    (WORK_DIR / "clips").mkdir(exist_ok=True)


def load_processed() -> set:
    if PROCESSED_LOG.exists():
        return set(json.loads(PROCESSED_LOG.read_text()))
    return set()


def save_processed(ids: set):
    PROCESSED_LOG.write_text(json.dumps(list(ids), indent=2))


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ---------------------------------------------------------------------------
# Step 1 — Fetch video list from channel
# ---------------------------------------------------------------------------

def get_channel_videos(channel_url: str, max_videos: int = 5) -> list[dict]:
    print(f"\n[1/4] Fetching latest {max_videos} videos from {channel_url}")

    if not channel_url.endswith("/videos"):
        channel_url = channel_url.rstrip("/") + "/videos"

    ydl_opts = {"quiet": True, "extract_flat": True, "playlistend": max_videos}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    entries = info.get("entries", [])
    if entries and entries[0].get("_type") == "playlist":
        entries = entries[0].get("entries", [])

    videos = []
    for entry in entries:
        if entry and entry.get("id"):
            videos.append({
                "id": entry["id"],
                "title": entry.get("title", "Untitled"),
                "url": f"https://www.youtube.com/watch?v={entry['id']}",
            })
        if len(videos) >= max_videos:
            break

    print(f"    Found {len(videos)} videos.")
    return videos


# ---------------------------------------------------------------------------
# Step 2 — Download full video
# ---------------------------------------------------------------------------

def download_video(video: dict) -> Path:
    out_dir = WORK_DIR / "downloads"
    out_template = str(out_dir / f"{video['id']}.%(ext)s")
    print(f"\n[2/4] Downloading: {video['title']}")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": out_template,
        "quiet": False,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video["url"]])

    matches = list(out_dir.glob(f"{video['id']}.*"))
    if not matches:
        raise FileNotFoundError(f"Download failed for {video['id']}")
    return matches[0]


# ---------------------------------------------------------------------------
# Step 3 — Get transcript
# ---------------------------------------------------------------------------

def get_transcript(video: dict) -> list[dict]:
    print(f"\n[3/4] Fetching captions for: {video['title']}")
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video["id"])
        transcript = [{"start": s.start, "duration": s.duration, "text": s.text} for s in fetched]
        print(f"    Got {len(transcript)} caption segments.")
        return transcript
    except Exception:
        print("    No captions available — will use random clips.")
        return []


def transcript_to_text(transcript: list[dict]) -> str:
    lines = []
    for seg in transcript:
        start = seg["start"]
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = start % 60
        ts = f"{h:02d}:{m:02d}:{s:05.2f}"
        lines.append(f"[{ts}] {seg['text'].strip()}")
    return "\n".join(lines)


def get_video_duration(video_path: Path) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


# ---------------------------------------------------------------------------
# Step 4a — Ask GPT-4 to pick highlights
# ---------------------------------------------------------------------------

def ask_gpt_for_highlights(video_title: str, transcript_text: str) -> list[dict]:
    from openai import OpenAI
    print(f"\n[4/4] Asking GPT-4 to find {CLIPS_PER_VIDEO} highlight clips…")

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""You are an expert YouTube video editor. I have a transcript of a video titled:
"{video_title}"

Identify the {CLIPS_PER_VIDEO} most engaging, self-contained highlight moments for standalone clips. Each clip should be approximately {CLIP_LENGTH_MINUTES} minutes long.

Look for:
- The most interesting, informative, or entertaining segments
- Moments with a clear beginning and end
- High-energy or emotionally compelling sections
- Segments that make sense without watching the full video

Transcript:
{transcript_text}

Respond ONLY with a valid JSON array (no markdown). Format:
[
  {{
    "start_seconds": 123.4,
    "end_seconds": 423.4,
    "title": "Short catchy title",
    "reason": "One sentence why this is engaging"
  }}
]"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    clips = json.loads(raw)
    print(f"    GPT-4 identified {len(clips)} clips:")
    for i, c in enumerate(clips, 1):
        print(f"      {i}. {c['title']} ({c['start_seconds']:.0f}s – {c['end_seconds']:.0f}s)")
    return clips


# ---------------------------------------------------------------------------
# Step 4b — Random clip fallback
# ---------------------------------------------------------------------------

def pick_clips_randomly(duration: float, video_title: str) -> list[dict]:
    print(f"\n[4/4] Picking {CLIPS_PER_VIDEO} random clips from {duration:.0f}s video…")
    clip_duration = CLIP_LENGTH_MINUTES * 60
    usable = duration - clip_duration

    if usable <= 0:
        return [{"start_seconds": 0, "end_seconds": duration,
                 "title": "Full video", "reason": "Video shorter than clip length"}]

    pool = list(range(0, int(usable), 10))
    random.shuffle(pool)
    clips, used = [], []
    for start in pool:
        if any(abs(start - u) < clip_duration for u in used):
            continue
        used.append(start)
        end = min(start + clip_duration, duration)
        i = len(clips) + 1
        clips.append({"start_seconds": float(start), "end_seconds": round(end, 1),
                      "title": f"Clip {i}", "reason": "Random selection"})
        print(f"      {i}. Clip {i} ({start:.0f}s – {end:.0f}s)")
        if len(clips) >= CLIPS_PER_VIDEO:
            break

    clips.sort(key=lambda c: c["start_seconds"])
    return clips


# ---------------------------------------------------------------------------
# Step 5 — Cut clips with FFmpeg, then delete source
# ---------------------------------------------------------------------------

def cut_clips(video_path: Path, clips: list[dict], video_id: str) -> list[tuple]:
    print(f"\nCutting {len(clips)} clips…")
    clips_dir = WORK_DIR / "clips"
    out_paths = []

    for i, clip in enumerate(clips, 1):
        safe_title = re.sub(r"[^\w\s-]", "", clip["title"])[:50].strip().replace(" ", "_")
        out_path = clips_dir / f"{video_id}_clip{i}_{safe_title}.mp4"

        start = format_timestamp(clip["start_seconds"])
        duration = clip["end_seconds"] - clip["start_seconds"]

        cmd = [
            "ffmpeg", "-y",
            "-ss", start,
            "-i", str(video_path),
            "-t", str(duration),
            "-c", "copy",
            str(out_path),
        ]

        print(f"    Cutting clip {i}: {clip['title']}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    WARNING: FFmpeg error:\n{result.stderr[-300:]}")
        else:
            out_paths.append((out_path, clip))
            print(f"    ✓ Saved: {out_path.name}")

    # Delete the source video to free up disk space
    print(f"\n    Deleting source video to free disk space…")
    video_path.unlink(missing_ok=True)
    print(f"    ✓ Deleted: {video_path.name}")

    return out_paths


# ---------------------------------------------------------------------------
# Upload to YouTube
# ---------------------------------------------------------------------------

def get_youtube_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token_path = WORK_DIR / "youtube_token.json"
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, scopes)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_clip(youtube, clip_path: Path, clip_info: dict, source_title: str):
    from googleapiclient.http import MediaFileUpload

    title = f"{source_title} #shorts #YouTubeShorts #clip"[:100]
    body = {
        "snippet": {"title": title, "description": clip_info.get("reason", ""),
                    "tags": ["highlight", "clip"], "categoryId": "22"},
        "status": {"privacyStatus": UPLOAD_PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(clip_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"      Upload progress: {int(status.progress() * 100)}%")
    print(f"    ✓ Uploaded! Video ID: {response['id']}")
    return response["id"]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_video(video: dict, youtube=None, no_ai: bool = False):
    print(f"\n{'='*60}\nProcessing: {video['title']}\n{'='*60}")

    # Download full video
    video_path = download_video(video)

    # Get transcript
    transcript = get_transcript(video)

    # Pick clips
    if no_ai or not transcript:
        duration = get_video_duration(video_path)
        clips = pick_clips_randomly(duration, video["title"])
    else:
        transcript_text = transcript_to_text(transcript)
        clips = ask_gpt_for_highlights(video["title"], transcript_text)

    # Cut clips and delete source
    clip_files = cut_clips(video_path, clips, video["id"])

    # Upload if configured
    if youtube and clip_files:
        print(f"\nUploading {len(clip_files)} clips to YouTube…")
        for clip_path, clip_info in clip_files:
            upload_clip(youtube, clip_path, clip_info, video["title"])
    else:
        print(f"\nClips saved to: {WORK_DIR / 'clips'}")

    print(f"\n✓ Done: {video['title']}")
    return clip_files