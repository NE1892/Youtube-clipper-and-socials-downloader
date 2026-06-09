"""
YouTube/TikTok Auto-Clipper — Web App
Run: python3 app.py  then open http://localhost:5000
"""

import os
import threading
import uuid
from pathlib import Path

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_file

import yt_clipper as yc
from tiktok_uploader import upload_to_tiktok

app = Flask(__name__)
jobs = {}

SECRETS_FILE = Path(__file__).parent / "client_secrets.json"


def is_tiktok_url(url):
    return "tiktok.com" in url or "vm.tiktok.com" in url


def is_video_url(url):
    return "watch?v=" in url or "youtu.be/" in url or "tiktok.com" in url or "vm.tiktok.com" in url


def run_job(job_id, url, max_videos, use_ai, clips_per_video, clip_length, upload_tiktok=False, upload_youtube=False):

    def log(msg, progress=None):
        jobs[job_id]["log"].append(msg)
        if progress is not None:
            jobs[job_id]["progress"] = progress

    try:
        yc.ensure_dirs()
        jobs[job_id]["clips"] = []
        yc.CLIPS_PER_VIDEO = clips_per_video
        yc.CLIP_LENGTH_MINUTES = clip_length

        # Detect URL type and get video list
        if is_video_url(url):
            log("Fetching video info…", 5)
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            videos = [{"id": info["id"], "title": info.get("title", "Untitled"), "url": url}]
        else:
            log("Fetching videos from channel…", 5)
            videos = yc.get_channel_videos(url, max_videos)

        if not videos:
            jobs[job_id]["status"] = "error"
            log("No videos found.")
            return

        # Set up YouTube uploader if needed
        youtube = None
        if upload_youtube and SECRETS_FILE.exists():
            log("Authenticating with YouTube…", 8)
            try:
                youtube = yc.get_youtube_service()
            except Exception as e:
                log(f"YouTube auth failed: {e}")

        for idx, video in enumerate(videos):
            base = int((idx / len(videos)) * 85)

            log(f"Downloading: {video['title']}…", base + 10)
            video_path = yc.download_video(video)

            # Only fetch transcript for YouTube videos (TikTok won't have captions)
            transcript = []
            if not is_tiktok_url(video["url"]):
                log("Fetching captions…", base + 35)
                transcript = yc.get_transcript(video)

            if use_ai and transcript:
                log("Asking GPT-4 for highlights…", base + 50)
                transcript_text = yc.transcript_to_text(transcript)
                clips = yc.ask_gpt_for_highlights(video["title"], transcript_text)
            else:
                log("Picking random clip points…", base + 50)
                duration = yc.get_video_duration(video_path)
                clips = yc.pick_clips_randomly(duration, video["title"])

            log(f"Cutting {len(clips)} clips…", base + 65)
            clip_files = yc.cut_clips(video_path, clips, video["id"])

            for clip_path, clip_info in clip_files:
                jobs[job_id]["clips"].append({
                    "filename": clip_path.name,
                    "title": clip_info["title"],
                    "reason": clip_info.get("reason", ""),
                    "start": clip_info["start_seconds"],
                    "end": clip_info["end_seconds"],
                })
                log(f"✓ Ready: {clip_info['title']}")

                if upload_tiktok:
                    log(f"Uploading to TikTok: {clip_info['title']}…")
                    success = upload_to_tiktok(clip_path, clip_info["title"], video["title"])
                    log(f"{'✓ Uploaded to TikTok' if success else '✗ TikTok upload failed'}: {clip_info['title']}")

                if upload_youtube and youtube:
                    log(f"Uploading to YouTube: {clip_info['title']}…")
                    try:
                        import subprocess
                        yt_clip_path = clip_path
                        duration = clip_info["end_seconds"] - clip_info["start_seconds"]
                        short_path = clip_path.parent / (clip_path.stem + "_yt_short.mp4")

                        # Convert to vertical 9:16 (1080x1920) and cap at 59 seconds
                        # Uses padding to add black bars if video is horizontal
                        t = min(duration, 59)
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(clip_path),
                            "-t", str(t),
                            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                            "-c:a", "aac", "-b:a", "128k",
                            str(short_path)
                        ], capture_output=True)

                        if short_path.exists():
                            yt_clip_path = short_path

                        yc.upload_clip(youtube, yt_clip_path, clip_info, video["title"])
                        log(f"✓ Uploaded to YouTube: {clip_info['title']}")
                    except Exception as e:
                        log(f"✗ YouTube upload failed: {e}")

        jobs[job_id]["status"] = "done"
        log(f"All done! {len(jobs[job_id]['clips'])} clips ready.", 100)

    except Exception as e:
        import traceback
        jobs[job_id]["status"] = "error"
        log(f"Error: {e}")
        print(traceback.format_exc())


@app.route("/")
def index():
    youtube_ready = SECRETS_FILE.exists()
    return render_template("index.html", youtube_ready=youtube_ready)


@app.route("/start", methods=["POST"])
def start():
    data = request.json
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "running", "log": [], "progress": 0, "clips": []}

    threading.Thread(
        target=run_job,
        args=(
            job_id,
            data.get("url", ""),
            int(data.get("max_videos", 1)),
            data.get("use_ai", False),
            int(data.get("clips_per_video", 3)),
            float(data.get("clip_length", 5)),
            data.get("upload_tiktok", False),
            data.get("upload_youtube", False),
        ),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<filename>")
def download(filename):
    file_path = yc.WORK_DIR / "clips" / filename
    if not file_path.exists():
        return "File not found", 404
    return send_file(str(file_path), as_attachment=True)


# ---------------------------------------------------------------------------
# Downloader routes
# ---------------------------------------------------------------------------

download_jobs = {}


def run_download(job_id, url):
    import yt_dlp
    out_dir = yc.WORK_DIR / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = int((downloaded / total) * 90)
                download_jobs[job_id]["progress"] = pct
                download_jobs[job_id]["message"] = f"Downloading… {pct}%"
        elif d["status"] == "finished":
            download_jobs[job_id]["progress"] = 95
            download_jobs[job_id]["message"] = "Processing…"

    try:
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "progress_hooks": [progress_hook],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            filename = ydl.prepare_filename(info)
            # Ensure .mp4 extension
            from pathlib import Path as P
            filename = str(P(filename).with_suffix(".mp4"))

        download_jobs[job_id]["status"] = "done"
        download_jobs[job_id]["progress"] = 100
        download_jobs[job_id]["message"] = "Done!"
        download_jobs[job_id]["title"] = title
        download_jobs[job_id]["filename"] = Path(filename).name

    except Exception as e:
        download_jobs[job_id]["status"] = "error"
        download_jobs[job_id]["message"] = str(e)


@app.route("/downloader")
def downloader():
    return render_template("downloader.html")


@app.route("/download-video", methods=["POST"])
def download_video_route():
    data = request.json
    job_id = str(uuid.uuid4())[:8]
    download_jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting…", "title": "", "filename": ""}

    threading.Thread(target=run_download, args=(job_id, data["url"]), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/download-status/<job_id>")
def download_status(job_id):
    job = download_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/get-video/<filename>")
def get_video(filename):
    file_path = yc.WORK_DIR / "downloads" / filename
    if not file_path.exists():
        return "File not found", 404
    return send_file(str(file_path), as_attachment=True)


if __name__ == "__main__":
    import webbrowser, time
    yc.ensure_dirs()
    print("\n🎬 Auto-Clipper")
    print("Opening http://localhost:5000 …\n")
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open("http://localhost:5000")), daemon=True).start()
    app.run(debug=False, port=5000)