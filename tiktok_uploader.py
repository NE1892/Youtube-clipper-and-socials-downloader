"""
TikTok Uploader
===============
Uses Edge on Windows, Chrome on Mac with your existing TikTok login.
Generates AI captions with fixed hashtags.
"""

import asyncio
import os
import platform
import random
from pathlib import Path

from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).parent / "tiktok_session.json"

# Browser paths per platform
if platform.system() == "Darwin":
    BROWSER_PROFILE = Path.home() / "Library/Application Support/Google/Chrome"
    BROWSER_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    PROFILE_DIR = "TikTokBot"
    SELECT_ALL = "Meta+a"
elif platform.system() == "Windows":
    BROWSER_PROFILE = Path.home() / "AppData/Local/Microsoft/Edge/User Data"
    BROWSER_EXECUTABLE = "C:/Program Files/Microsoft/Edge/Application/msedge.exe"
    PROFILE_DIR = "TikTokBot"
    SELECT_ALL = "Control+a"
else:
    BROWSER_PROFILE = Path.home() / ".config/google-chrome"
    BROWSER_EXECUTABLE = "/usr/bin/google-chrome"
    PROFILE_DIR = "TikTokBot"
    SELECT_ALL = "Control+a"

FIXED_HASHTAGS = "#fyp #foryoupage #trending #viral #story"


def generate_caption(video_title: str, clip_title: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f'Write a short catchy TikTok caption (max 100 characters, no hashtags) for a clip called "{clip_title}" from a video titled "{video_title}". Make it engaging with emojis. Just the caption text, nothing else.'}],
            max_tokens=100,
        )
        return f"{response.choices[0].message.content.strip()}\n\n{FIXED_HASHTAGS}"
    except Exception as e:
        print(f"    Could not generate AI caption: {e}")
        return f"{clip_title}\n\n{FIXED_HASHTAGS}"


async def human_delay(min_ms=800, max_ms=2000):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _upload_single(clip_path: Path, title: str, video_title: str = ""):
    async with async_playwright() as p:

        print(f"    Opening browser ({platform.system()})...")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE),
            executable_path=BROWSER_EXECUTABLE,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                f"--profile-directory={PROFILE_DIR}",
            ],
            viewport={"width": 1280, "height": 800},
        )

        # Close blank pages
        for pg in context.pages:
            if pg.url == "about:blank":
                await pg.close()

        page = await context.new_page()
        await page.wait_for_timeout(2000)

        print("    Going to TikTok upload page...")
        await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded", timeout=30000)
        await human_delay(3000, 5000)

        # Wait for login if needed
        if "login" in page.url:
            print("\n    Not logged in — please log in manually in the browser window...")
            await page.wait_for_url(
                lambda url: "tiktok.com" in url and "login" not in url,
                timeout=180000
            )
            await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded")
            await human_delay(3000, 5000)

        # Find file input with retries
        print("    Waiting for upload area to load...")
        file_input = None
        for attempt in range(3):
            for frame in [page] + list(page.frames):
                try:
                    fi = await frame.query_selector('input[type="file"]')
                    if fi:
                        file_input = fi
                        break
                except Exception:
                    continue
            if file_input:
                break
            print(f"    Waiting... (attempt {attempt+1}/3)")
            await human_delay(3000, 5000)

        if not file_input:
            await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded")
            await human_delay(5000, 7000)
            for frame in [page] + list(page.frames):
                try:
                    fi = await frame.query_selector('input[type="file"]')
                    if fi:
                        file_input = fi
                        break
                except Exception:
                    continue

        if not file_input:
            raise Exception("Could not find file upload input")

        print(f"    Selecting file: {clip_path.name}")
        await file_input.set_input_files(str(clip_path))
        print("    File selected, waiting for video to process...")
        await human_delay(4000, 6000)

        # Find caption box
        caption_selectors = ['[data-text="true"]', '.public-DraftEditor-content', '[contenteditable="true"]']
        caption_box = None
        for selector in caption_selectors:
            try:
                await page.wait_for_selector(selector, timeout=60000)
                caption_box = await page.query_selector(selector)
                if caption_box:
                    break
            except Exception:
                continue

        if not caption_box:
            for frame in page.frames:
                for selector in caption_selectors:
                    try:
                        caption_box = await frame.query_selector(selector)
                        if caption_box:
                            break
                    except Exception:
                        continue
                if caption_box:
                    break

        if caption_box:
            caption_text = generate_caption(video_title or title, title)
            hashtags = FIXED_HASHTAGS.split()

            await caption_box.click()
            await human_delay(500, 1000)
            # Clear existing text (Control+a on Windows, Meta+a on Mac)
            await page.keyboard.press(SELECT_ALL)
            await human_delay(300, 500)
            await page.keyboard.press("Delete")
            await human_delay(300, 500)

            # Type each hashtag and click suggestion
            for hashtag in hashtags:
                tag = hashtag.lstrip("#")
                await page.keyboard.type(f"#{tag}")
                await human_delay(1000, 2000)
                try:
                    suggestion = page.locator(f"[data-e2e='search-suggest-item']:first-child, .tt-suggest-item:first-child, div[class*='suggest'] >> text=#{tag}").first
                    await suggestion.wait_for(state="visible", timeout=3000)
                    await suggestion.click()
                    print(f"    Clicked hashtag: #{tag}")
                except Exception:
                    await page.keyboard.press("Space")
                await human_delay(500, 800)

            print("    Hashtags typed.")

        await human_delay(2000, 3000)
        print("    Waiting for video to finish processing...")
        await human_delay(5000, 8000)

        # Click Post with retries
        posted = False
        post_selectors = ["button:has-text('Post')", "button:has-text('Upload')", "[data-e2e='upload-btn']", ".btn-post"]

        for attempt in range(5):
            for frame in [page] + list(page.frames):
                for selector in post_selectors:
                    try:
                        btn = frame.locator(selector)
                        if await btn.count() > 0:
                            await btn.last.scroll_into_view_if_needed()
                            await human_delay(800, 1500)
                            await btn.last.click()
                            posted = True
                            print("    Posted to TikTok!")
                            break
                    except Exception:
                        continue
                if posted:
                    break
            if posted:
                break
            print(f"    Post button not found, waiting... (attempt {attempt+1}/5)")
            await human_delay(3000, 5000)

        if not posted:
            print("    Could not find Post button — please click it manually.")
            await page.wait_for_timeout(30000)

        await human_delay(4000, 6000)
        await context.close()


def upload_to_tiktok(clip_path: Path, title: str, video_title: str = ""):
    print(f"\n[TikTok] Uploading: {clip_path.name}")
    try:
        asyncio.run(_upload_single(clip_path, title, video_title))
        return True
    except Exception as e:
        print(f"    TikTok upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False