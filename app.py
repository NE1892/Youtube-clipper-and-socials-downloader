"""
YouTube Auto-Clipper — Web App
Run: python3 app.py  then open http://localhost:5000
"""

import os
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import yt_clipper as yc
from tiktok_uploader import upload_to_tiktok

app = Flask(__name__)
jobs = {}


def run_job(job_id, channel_url, max_videos, use_ai, clips_per_video, clip_length, video_url=None, mode="channel", upload_tiktok=False):

    def log(msg, progress=None):
        jobs[job_id]["log"].append(msg)
        if progress is not None:
            jobs[job_id]["progress"] = progress

    try:
        yc.ensure_dirs()
        jobs[job_id]["clips"] = []
        yc.CLIPS_PER_VIDEO = clips_per_video
        yc.CLIP_LENGTH_MINUTES = clip_length

        # Auto-detect: if the URL contains /watch?v= treat as single video
        url = video_url or channel_url
        if mode == "video" or "watch?v=" in url or "youtu.be/" in url:
            log("Fetching video info…", 5)
            import yt_dlp
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

        for idx, video in enumerate(videos):
            base = int((idx / len(videos)) * 85)

            log(f"Downloading: {video['title']}…", base + 10)
            video_path = yc.download_video(video)

            log("Fetching captions…", base + 40)
            transcript = yc.get_transcript(video)

            if use_ai and transcript:
                log("Asking GPT-4 for highlights…", base + 55)
                transcript_text = yc.transcript_to_text(transcript)
                clips = yc.ask_gpt_for_highlights(video["title"], transcript_text)
            else:
                log("Picking random clip points…", base + 55)
                duration = yc.get_video_duration(video_path)
                clips = yc.pick_clips_randomly(duration, video["title"])

            log(f"Cutting {len(clips)} clips…", base + 70)
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
                    if success:
                        log(f"✓ Uploaded to TikTok: {clip_info['title']}")
                    else:
                        log(f"✗ TikTok upload failed: {clip_info['title']}")

        jobs[job_id]["status"] = "done"
        log(f"All done! {len(jobs[job_id]['clips'])} clips ready.", 100)

    except Exception as e:
        import traceback
        jobs[job_id]["status"] = "error"
        log(f"Error: {e}")
        print(traceback.format_exc())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    data = request.json
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "running", "log": [], "progress": 0, "clips": []}

    threading.Thread(
        target=run_job,
        args=(job_id, data.get("channel_url", ""), int(data.get("max_videos", 1)),
              data.get("use_ai", False), int(data.get("clips_per_video", 3)),
              float(data.get("clip_length", 5)), data.get("video_url", ""), data.get("mode", "channel"),
              data.get("upload_tiktok", False)),
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


if __name__ == "__main__":
    import webbrowser, time
    yc.ensure_dirs()
    print("\n🎬 YouTube Auto-Clipper")
    print("Opening http://localhost:5000 …\n")
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open("http://localhost:5000")), daemon=True).start()
    app.run(debug=False, port=5000)