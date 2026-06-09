"""
TikTok Uploader
===============
Uses your real Chrome browser with your existing TikTok login.
Generates AI captions with fixed hashtags.
"""

import asyncio
import os
import random
from pathlib import Path

from playwright.async_api import async_playwright

CHROME_PROFILE = Path.home() / "Library/Application Support/Google/Chrome/TikTokBot"
CHROME_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FIXED_HASHTAGS = "#fyp #foryoupage #viral #trending #TikTok"


def generate_caption(video_title: str, clip_title: str) -> str:
    """Use GPT-4 to write a catchy TikTok caption."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f'Write a short catchy TikTok caption (max 100 characters, no hashtags) for a clip called "{clip_title}" from a video titled "{video_title}". Make it engaging with emojis. Just the caption text, nothing else.'}],
            max_tokens=100,
        )
        caption = response.choices[0].message.content.strip()
        return f"{caption}\n\n{FIXED_HASHTAGS}"
    except Exception as e:
        print(f"    Could not generate AI caption: {e}")
        return f"{clip_title}\n\n{FIXED_HASHTAGS}"


async def human_delay(min_ms=800, max_ms=2000):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _upload_single(clip_path: Path, title: str, video_title: str = ""):
    async with async_playwright() as p:

        print("    Opening your Chrome browser with existing TikTok session...")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE),
            executable_path=CHROME_EXECUTABLE,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--profile-directory=TikTokBot",
            ],
            viewport={"width": 1280, "height": 800},
        )

        # Close any blank pages
        for pg in context.pages:
            if pg.url == "about:blank":
                await pg.close()

        page = await context.new_page()
        await page.wait_for_timeout(2000)

        print("    Going to TikTok upload page...")
        await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded", timeout=30000)
        await human_delay(3000, 5000)

        # If not logged in, wait for manual login
        if "login" in page.url:
            print("\n    Not logged into TikTok in Chrome.")
            print("    Please log in manually in the browser window, then wait...")
            await page.wait_for_url(
                lambda url: "tiktok.com" in url and "login" not in url,
                timeout=180000
            )
            await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded")
            await human_delay(3000, 5000)

        # Find file input with retries
        print(f"    Waiting for upload area to load...")
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
            print(f"    File input not found yet, waiting... (attempt {attempt+1}/3)")
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

        # Wait for caption field
        caption_selectors = [
            '[data-text="true"]',
            '.public-DraftEditor-content',
            '[contenteditable="true"]',
        ]
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
            # Split into main caption and hashtags
            parts = caption_text.split("\n\n")
            main_caption = parts[0]
            hashtags = FIXED_HASHTAGS.split() if len(parts) < 2 else parts[1].split()

            print(f"    Caption: {main_caption[:80]}...")
            await caption_box.click()
            await human_delay(500, 1000)
            await page.keyboard.press("Meta+a")
            await human_delay(300, 500)

            # Type each hashtag and click the first suggestion
            for hashtag in hashtags:
                tag = hashtag.lstrip("#")
                await page.keyboard.type(f"#{tag}")
                await human_delay(1000, 2000)

                # Wait for dropdown and click first suggestion
                try:
                    suggestion = page.locator(f"[data-e2e='search-suggest-item']:first-child, .tt-suggest-item:first-child, div[class*='suggest'] >> text=#{tag}").first
                    await suggestion.wait_for(state="visible", timeout=3000)
                    await suggestion.click()
                    print(f"    Clicked hashtag: #{tag}")
                except Exception:
                    # If no dropdown, just press space to move on
                    await page.keyboard.press("Space")

                await human_delay(500, 800)

            print("    Caption and hashtags typed.")

        await human_delay(2000, 3000)

        # Wait for video to finish processing
        print("    Waiting for video to finish processing...")
        await human_delay(5000, 8000)

        # Click Post with retries
        posted = False
        post_selectors = [
            "button:has-text('Post')",
            "button:has-text('Upload')",
            "[data-e2e='upload-btn']",
            ".btn-post",
            "button.submit",
        ]

        for attempt in range(5):
            for frame in [page] + list(page.frames):
                for selector in post_selectors:
                    try:
                        btn = frame.locator(selector)
                        count = await btn.count()
                        if count > 0:
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
            print(f"    Post button not found yet, waiting... (attempt {attempt+1}/5)")
            await human_delay(3000, 5000)

        if not posted:
            print("    Could not find Post button — please click it manually in the browser.")
            await page.wait_for_timeout(30000)

        await human_delay(4000, 6000)
        await context.close()


def upload_to_tiktok(clip_path: Path, title: str, video_title: str = ""):
    """Upload a clip to TikTok using your real Chrome browser."""
    print(f"\n[TikTok] Uploading: {clip_path.name}")
    try:
        asyncio.run(_upload_single(clip_path, title, video_title))
        return True
    except Exception as e:
        print(f"    TikTok upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def clear_tiktok_session():
    """Force fresh login by clearing the profile copy."""
    import shutil
    if CHROME_PROFILE.exists():
        shutil.rmtree(CHROME_PROFILE)
        print("TikTok profile cleared.")