"""
Video Creator
=============
Creates kids YouTube Shorts:
- Reddit Story mode: dramatic story text over Minecraft background with voiceover
- Cartoon mode: simple animated cartoon scene with voiceover

Requirements:
    pip install gtts pillow openai
    FFmpeg required
"""

import os
import random
import subprocess
import tempfile
from pathlib import Path

from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

WORK_DIR = Path(__file__).parent / "clipper_output"
VIDEOS_DIR = WORK_DIR / "created_videos"

# Video dimensions (vertical for Shorts/TikTok)
WIDTH, HEIGHT = 1080, 1920
FPS = 30


def ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "temp").mkdir(exist_ok=True)


def get_client():
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


# ---------------------------------------------------------------------------
# Text to Speech
# ---------------------------------------------------------------------------

def text_to_speech(text: str, output_path: Path):
    """Convert text to speech using Google TTS (free)."""
    tts = gTTS(text=text, lang='en', slow=False)
    tts.save(str(output_path))
    print(f"    Audio saved: {output_path.name}")


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    import json
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


# ---------------------------------------------------------------------------
# Minecraft Style Background
# ---------------------------------------------------------------------------

def draw_minecraft_background(draw: ImageDraw, width: int, height: int):
    """Draw a Minecraft-style pixelated dirt/grass background."""
    block_size = 60

    # Minecraft colour palette
    dirt_colors = [
        (134, 96, 67), (120, 85, 58), (144, 103, 72), (128, 90, 62)
    ]
    grass_colors = [
        (106, 170, 62), (91, 158, 50), (118, 180, 72), (98, 165, 58)
    ]
    stone_colors = [
        (125, 125, 125), (115, 115, 115), (135, 135, 135), (120, 120, 120)
    ]
    sky_colors = [
        (100, 160, 220), (90, 150, 210), (110, 170, 230)
    ]

    sky_height = int(height * 0.55)
    ground_start = int(height * 0.55)
    grass_layer = int(height * 0.60)
    dirt_layer = int(height * 0.75)

    for y in range(0, height, block_size):
        for x in range(0, width, block_size):
            if y < sky_height:
                color = random.choice(sky_colors)
            elif y < grass_layer:
                color = random.choice(grass_colors)
            elif y < dirt_layer:
                color = random.choice(dirt_colors)
            else:
                color = random.choice(stone_colors)

            draw.rectangle([x, y, x + block_size, y + block_size], fill=color)
            # Block border
            draw.rectangle([x, y, x + block_size, y + block_size],
                          outline=(0, 0, 0, 40), width=1)

    # Draw some trees
    for tx in [150, 500, 850]:
        trunk_y = ground_start - block_size
        # Trunk
        draw.rectangle([tx, trunk_y, tx + block_size, ground_start],
                       fill=(101, 67, 33))
        # Leaves
        for lx in range(tx - block_size, tx + block_size * 2, block_size):
            for ly in range(trunk_y - block_size * 3, trunk_y, block_size):
                draw.rectangle([lx, ly, lx + block_size, ly + block_size],
                               fill=(34, 139, 34))

    # Draw clouds
    for cx in [100, 400, 750]:
        for bx in range(cx, cx + block_size * 3, block_size):
            draw.rectangle([bx, 100, bx + block_size, 160], fill=(255, 255, 255))
        for bx in range(cx + block_size // 2, cx + block_size * 2, block_size):
            draw.rectangle([bx, 50, bx + block_size, 110], fill=(255, 255, 255))


def get_font(size: int):
    """Try to load a font, fall back to default."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int, draw: ImageDraw) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Reddit Story Mode
# ---------------------------------------------------------------------------

# Fallback stories when no API key available
# Fallback stories when no API key available
_used_stories = []
_used_cartoons = []


def _pick_unused(items, used):
    """Pick an item not recently used."""
    unused = [i for i in items if i["title"] not in used]
    if not unused:
        used.clear()
        unused = items
    import random as _r
    choice = _r.choice(unused)
    used.append(choice["title"])
    return choice


FALLBACK_STORIES = [
    {
        "title": "My Neighbour Has Been Lying For 3 Years",
        "story": "I need to get this off my chest. For three years my neighbour told everyone on the street he was a retired pilot. He had all the stories. The flights, the countries, the close calls. We all believed him. Then last month his actual brother visited and casually mentioned that Dave had worked in a biscuit factory his entire life. I could not stop thinking about it. Why would someone do that? I finally asked him directly. He just shrugged and said nobody ever talked to him before he started telling pilot stories. I had absolutely nothing to say to that. I still think about it every single day."
    },
    {
        "title": "I Overheard Something I Was Never Meant to Hear",
        "story": "Two weeks ago I was sitting in a cafe doing homework when the two people at the next table started talking quietly. I wasn't trying to listen but they were right there. One of them said they had found the letter. The other one went completely pale. They paid and left immediately without finishing their drinks. I have no idea what letter they meant or who they were. But the look on that person's face has stayed with me. Pure dread. Whatever that letter contained it clearly changed everything. I go back to that cafe every week hoping to see them again. I never have."
    },
    {
        "title": "My Best Friend Has a Secret Identity Online",
        "story": "So I was scrolling through a gaming forum last month when I recognised something. The way this person wrote. The specific phrases they used. The jokes. I know this sounds strange but I was completely certain it was my best friend. The account had thousands of followers and had been posting for four years. My friend has never once mentioned it. I tested it. I sent them a very specific meme that the account would definitely reference. Next day the account posted about it. I still haven't said anything. Part of me doesn't want to ruin it. But I think about it every time we talk."
    },
    {
        "title": "The Package That Was Never Meant for Me",
        "story": "A package arrived at my door six months ago with my address but a name I didn't recognise. I held onto it assuming they'd come for it. Nobody came. I eventually opened it. Inside was a handwritten letter, a key, and a photograph of a house I've never seen. No explanation. No return address. I posted about it online and thousands of people tried to help figure it out. We traced the house to a village four hours away. I drove there last weekend. The house was empty and had been for years. A neighbour told me the person who used to live there had been waiting for that package for a very long time."
    },
    {
        "title": "I Won a Competition I Never Entered",
        "story": "Last year I got a letter saying I had won a national photography competition. There was a cheque inside. The problem is I have never entered a photography competition in my life. I am not a photographer. I barely use my phone camera. I contacted the organisation and they confirmed my name, my address, everything was correct. They sent me the winning entry. It was genuinely beautiful. A photograph of a sunset over a city rooftop. I have no memory of taking it. My phone has no record of it. The competition people said it was submitted eight months ago. To this day I cannot explain it. I have the cheque framed on my wall."
    },
    {
        "title": "My Teacher Knew Something She Shouldn't Have",
        "story": "This happened years ago but I still think about it. I was twelve and having a really hard time at home. I hadn't told anyone. I was good at pretending everything was fine. One afternoon my teacher asked me to stay behind after class. She didn't ask me anything. She just slid a piece of paper across the desk. On it was a phone number and the words you don't have to explain anything. I still don't know how she knew. I never asked. But I used that number and it genuinely changed things for me. Some people just see more than they let on. I think about her all the time."
    },
    {
        "title": "The Person Who Remembers Me But Shouldn't",
        "story": "This is going to sound odd but bear with me. A few months ago a stranger stopped me in a supermarket and said it was so good to see me again and asked how my mum was doing. She clearly knew me well. The warmth in her face was completely real. The problem is I have never seen this woman before in my life. I told her I thought she had the wrong person. She went quiet, looked at me for a long moment, and said very softly, yes. You're right. I'm so sorry. Then she walked away quickly. I stood in that aisle for ten minutes trying to work out what just happened. I still haven't."
    },
]

FALLBACK_CARTOONS = [
    {
        "title": "The Cat Who Wanted to Fly",
        "script": "Once upon a time there was a little orange cat named Marmalade who dreamed of flying through the sky. Every day he would climb to the top of the garden fence and look up at the birds soaring above him. One afternoon he found a big red balloon tied to a post. He grabbed the string and up he went, floating gently over the rooftops. He could see everything from up there. The park, the school, his cosy house. Then slowly he floated back down and landed softly in his garden. He never did learn to fly like a bird. But for one magical afternoon he came pretty close."
    },
    {
        "title": "The Robot Who Learned to Dance",
        "script": "Deep in a busy factory there lived a small robot called Bolt who did the same job every single day. One morning some music started playing from a radio nearby. Bolt had never heard music before. Something strange happened to his circuits. His arms started moving. His legs started tapping. Before he knew it Bolt was dancing right there on the factory floor. All the other robots stopped and stared. Then one by one they started moving too. The whole factory filled with dancing robots. The factory owner came running in to see what was happening. Then he smiled, turned up the radio, and joined in."
    },
    {
        "title": "The Dog Who Stole the Picnic",
        "script": "Max the dog had one mission every Saturday. Find the picnic. The family would pack sandwiches and head to the park and Max would follow close behind pretending to be very well behaved. The moment everyone looked away Max would snatch a sandwich and bolt across the grass with his tail spinning like a helicopter. The kids would chase him laughing and screaming. Max would run in big circles getting slower and slower until finally he flopped down and dropped the sandwich. He never actually ate it. He just loved the chase. Every single week. Same sandwich. Same chase. Same happy ending."
    },
    {
        "title": "The Robot Who Found a Friend",
        "script": "Bolt the robot lived alone in a big empty warehouse. He did his work every day but he was very lonely. One rainy afternoon a small stray cat wandered in through a broken window. Bolt had never seen a cat before. He scanned it carefully and concluded it was a small fluffy robot of unknown origin. He decided to look after it. He built it a little bed from spare parts and programmed himself to dispense cat food every morning. The cat purred and rubbed against his metal legs. Bolt did not know what purring meant but his sensors told him it was a good thing. He was never lonely again."
    },
    {
        "title": "The Cat Who Learned to Share",
        "script": "Marmalade the cat had three toys and she loved all three of them equally. A stuffed mouse, a crinkly ball, and a feather on a stick. One day a new kitten arrived at the house. The kitten had no toys at all. Marmalade watched the kitten sitting alone in the corner looking sad. She thought about it for a very long time. Then she walked over and dropped the crinkly ball at the kitten's feet. The kitten's eyes went wide. They played together all afternoon. That evening Marmalade realised something important. Sharing did not make her toys worth less. It made playing twice as fun."
    },
]


def generate_reddit_story(topic: str = "") -> dict:
    """Generate a dramatic Reddit-style story using GPT-4."""
    try:
        client = get_client()
    except Exception:
        return _pick_unused(FALLBACK_STORIES, _used_stories)

    prompt = f"""Write a short, dramatic Reddit-style story perfect for a YouTube Short or TikTok.
{"Topic: " + topic if topic else "Pick any dramatic topic."}

Requirements:
- 60-90 seconds when read aloud (roughly 150-200 words)
- Start with a hook like "So this actually happened..." or "I can't believe I'm posting this..."
- Dramatic, emotional, relatable
- Kid-friendly (no violence, swearing, or adult content)
- End with a satisfying conclusion or twist
- Write ONLY the story text, no title or labels

Story:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        story = response.choices[0].message.content.strip()

        title_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Write a short catchy YouTube title (max 60 chars) for this story: {story[:200]}. Just the title, nothing else."}],
            max_tokens=30,
        )
        title = title_response.choices[0].message.content.strip().strip('"')
        return {"story": story, "title": title}
    except Exception:
        return _pick_unused(FALLBACK_STORIES, _used_stories)


def create_reddit_story_video(story: str, title: str, output_path: Path):
    """Create a Reddit story video with Minecraft background and text overlay."""
    temp_dir = WORK_DIR / "temp"
    audio_path = temp_dir / "story_audio.mp3"
    frames_dir = temp_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Generate audio
    print("    Generating voiceover...")
    text_to_speech(story, audio_path)
    duration = get_audio_duration(audio_path)
    total_frames = int(duration * FPS)

    # Split story into chunks for display
    words = story.split()
    words_per_chunk = 8
    chunks = [" ".join(words[i:i+words_per_chunk])
              for i in range(0, len(words), words_per_chunk)]
    frames_per_chunk = max(1, total_frames // len(chunks))

    print(f"    Generating {total_frames} frames...")

    font_title = get_font(52)
    font_story = get_font(44)
    font_small = get_font(32)

    # Generate a consistent background seed
    random.seed(42)
    bg_image = Image.new("RGB", (WIDTH, HEIGHT))
    bg_draw = ImageDraw.Draw(bg_image)
    draw_minecraft_background(bg_draw, WIDTH, HEIGHT)

    for frame_num in range(total_frames):
        img = bg_image.copy()
        draw = ImageDraw.Draw(img)

        # Semi-transparent story box
        box_x, box_y = 40, HEIGHT // 3
        box_w, box_h = WIDTH - 80, HEIGHT // 2
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                               fill=(0, 0, 0, 180))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Title at top
        title_lines = wrap_text(title, font_title, WIDTH - 80, draw)
        ty = 80
        for line in title_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            tx = (WIDTH - (bbox[2] - bbox[0])) // 2
            # Shadow
            draw.text((tx + 3, ty + 3), line, font=font_title, fill=(0, 0, 0))
            draw.text((tx, ty), line, font=font_title, fill=(255, 220, 50))
            ty += bbox[3] - bbox[1] + 10

        # Current story chunk
        chunk_idx = min(frame_num // frames_per_chunk, len(chunks) - 1)
        current_text = chunks[chunk_idx]
        lines = wrap_text(current_text, font_story, WIDTH - 120, draw)

        text_y = box_y + 30
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_story)
            tx = (WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((tx + 2, text_y + 2), line, font=font_story, fill=(0, 0, 0))
            draw.text((tx, text_y), line, font=font_story, fill=(255, 255, 255))
            text_y += bbox[3] - bbox[1] + 12

        # Progress bar
        progress = frame_num / total_frames
        bar_y = HEIGHT - 60
        draw.rectangle([40, bar_y, WIDTH - 40, bar_y + 12], fill=(60, 60, 60))
        draw.rectangle([40, bar_y, int(40 + (WIDTH - 80) * progress), bar_y + 12],
                      fill=(255, 50, 50))

        frame_path = frames_dir / f"frame_{frame_num:05d}.png"
        img.save(str(frame_path))

        if frame_num % 30 == 0:
            print(f"    Frame {frame_num}/{total_frames}...")

    # Combine frames and audio with FFmpeg
    print("    Combining frames and audio...")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path)
    ], capture_output=True)

    # Cleanup frames
    import shutil
    shutil.rmtree(str(frames_dir), ignore_errors=True)
    audio_path.unlink(missing_ok=True)
    print(f"    ✓ Video saved: {output_path.name}")


# ---------------------------------------------------------------------------
# Cartoon Mode
# ---------------------------------------------------------------------------

def generate_cartoon_script(topic: str = "") -> dict:
    """Generate a simple cartoon scene script."""
    try:
        client = get_client()
    except Exception:
        return _pick_unused(FALLBACK_CARTOONS, _used_cartoons)
    prompt = f"""Write a short, fun kids cartoon script.
{"Topic: " + topic if topic else "Pick a fun topic for young children."}

Requirements:
- 30-45 seconds when read aloud (roughly 80-100 words)
- Simple, funny, educational
- 1-2 characters max (e.g. a cat and a dog, a robot, a friendly dinosaur)
- Kid-friendly, positive message
- Write as a narrator describing the scene
- No dialogue tags, just flowing narration

Script:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        script = response.choices[0].message.content.strip()
        title_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Write a fun kids YouTube Short title (max 50 chars) for: {script[:150]}. Just the title."}],
            max_tokens=20,
        )
        title = title_response.choices[0].message.content.strip().strip('"')
        return {"script": script, "title": title}
    except Exception:
        return _pick_unused(FALLBACK_CARTOONS, _used_cartoons)


def draw_cartoon_scene(draw: ImageDraw, frame_num: int, total_frames: int,
                       character: str = "cat"):
    """Draw a simple animated cartoon scene."""
    # Sky gradient background
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(135 + (255 - 135) * ratio * 0.3)
        g = int(206 + (255 - 206) * ratio * 0.1)
        b = int(235 + (200 - 235) * ratio * 0.2)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    # Ground
    draw.rectangle([0, HEIGHT - 300, WIDTH, HEIGHT], fill=(76, 153, 0))
    draw.rectangle([0, HEIGHT - 320, WIDTH, HEIGHT - 300], fill=(101, 178, 22))

    # Sun
    sun_x = 150 + int(50 * abs((frame_num / total_frames) - 0.5))
    draw.ellipse([sun_x - 60, 80, sun_x + 60, 200], fill=(255, 220, 50))
    # Sun rays
    for angle in range(0, 360, 45):
        import math
        rx = sun_x + int(80 * math.cos(math.radians(angle)))
        ry = 140 + int(80 * math.sin(math.radians(angle)))
        draw.line([(sun_x, 140), (rx, ry)], fill=(255, 200, 0), width=4)

    # Clouds
    for cx in [300, 700]:
        cloud_x = cx + int(20 * (frame_num / total_frames))
        for bx in range(cloud_x, cloud_x + 180, 40):
            draw.ellipse([bx, 220, bx + 80, 290], fill=(255, 255, 255))
        for bx in range(cloud_x + 20, cloud_x + 160, 40):
            draw.ellipse([bx, 200, bx + 80, 270], fill=(255, 255, 255))

    # Trees
    for tx in [100, 880]:
        draw.rectangle([tx, HEIGHT - 500, tx + 40, HEIGHT - 300], fill=(101, 67, 33))
        draw.ellipse([tx - 60, HEIGHT - 620, tx + 100, HEIGHT - 460], fill=(34, 139, 34))
        draw.ellipse([tx - 40, HEIGHT - 650, tx + 80, HEIGHT - 500], fill=(50, 160, 50))

    # Flowers
    for fx in range(200, 900, 120):
        fy = HEIGHT - 310
        colors = [(255, 100, 100), (255, 200, 0), (200, 100, 255), (100, 200, 255)]
        fc = colors[(fx // 120) % len(colors)]
        draw.ellipse([fx - 15, fy - 15, fx + 15, fy + 15], fill=fc)
        draw.ellipse([fx - 8, fy - 8, fx + 8, fy + 8], fill=(255, 255, 0))

    # Animated character
    bounce = int(15 * abs((frame_num % 20) / 10 - 1))
    char_x = int(WIDTH * 0.4 + 100 * (frame_num / total_frames))
    char_y = HEIGHT - 380 - bounce

    if character == "cat":
        _draw_cat(draw, char_x, char_y, frame_num)
    elif character == "dog":
        _draw_dog(draw, char_x, char_y, frame_num)
    else:
        _draw_robot(draw, char_x, char_y, frame_num)


def _draw_cat(draw, x, y, frame):
    # Body
    draw.ellipse([x - 50, y, x + 50, y + 80], fill=(255, 165, 0))
    # Head
    draw.ellipse([x - 40, y - 70, x + 40, y + 10], fill=(255, 165, 0))
    # Ears
    draw.polygon([(x - 35, y - 65), (x - 55, y - 100), (x - 15, y - 80)], fill=(255, 140, 0))
    draw.polygon([(x + 35, y - 65), (x + 55, y - 100), (x + 15, y - 80)], fill=(255, 140, 0))
    # Eyes
    blink = frame % 40 > 38
    if blink:
        draw.line([(x - 20, y - 40), (x - 5, y - 40)], fill=(0, 0, 0), width=3)
        draw.line([(x + 5, y - 40), (x + 20, y - 40)], fill=(0, 0, 0), width=3)
    else:
        draw.ellipse([x - 22, y - 48, x - 6, y - 32], fill=(50, 200, 50))
        draw.ellipse([x + 6, y - 48, x + 22, y - 32], fill=(50, 200, 50))
        draw.ellipse([x - 17, y - 44, x - 9, y - 36], fill=(0, 0, 0))
        draw.ellipse([x + 9, y - 44, x + 17, y - 36], fill=(0, 0, 0))
    # Nose
    draw.polygon([(x, y - 25), (x - 8, y - 18), (x + 8, y - 18)], fill=(255, 100, 100))
    # Smile
    draw.arc([x - 15, y - 22, x + 15, y - 5], start=0, end=180, fill=(100, 50, 0), width=3)
    # Tail
    wave = int(20 * abs((frame % 20) / 10 - 1))
    draw.arc([x + 30, y + 20, x + 90, y + 80 + wave], start=270, end=90, fill=(255, 140, 0), width=8)
    # Legs
    draw.rectangle([x - 35, y + 65, x - 15, y + 110], fill=(255, 140, 0))
    draw.rectangle([x + 15, y + 65, x + 35, y + 110], fill=(255, 140, 0))


def _draw_dog(draw, x, y, frame):
    # Body
    draw.ellipse([x - 55, y, x + 55, y + 85], fill=(180, 120, 60))
    # Head
    draw.ellipse([x - 45, y - 75, x + 45, y + 5], fill=(180, 120, 60))
    # Floppy ears
    draw.ellipse([x - 65, y - 55, x - 20, y + 20], fill=(150, 90, 40))
    draw.ellipse([x + 20, y - 55, x + 65, y + 20], fill=(150, 90, 40))
    # Eyes
    draw.ellipse([x - 22, y - 48, x - 6, y - 32], fill=(80, 50, 20))
    draw.ellipse([x + 6, y - 48, x + 22, y - 32], fill=(80, 50, 20))
    # Nose
    draw.ellipse([x - 14, y - 22, x + 14, y - 8], fill=(60, 40, 20))
    # Smile
    draw.arc([x - 18, y - 18, x + 18, y - 2], start=0, end=180, fill=(100, 50, 0), width=3)
    # Tongue
    draw.ellipse([x - 8, y - 8, x + 8, y + 10], fill=(255, 100, 100))
    # Tail wag
    wave = int(30 * abs((frame % 15) / 7.5 - 1))
    draw.arc([x + 35, y - 10, x + 95, y + 50], start=270 - wave, end=90 - wave,
             fill=(150, 90, 40), width=8)
    # Legs
    draw.rectangle([x - 40, y + 68, x - 18, y + 115], fill=(150, 90, 40))
    draw.rectangle([x + 18, y + 68, x + 40, y + 115], fill=(150, 90, 40))


def _draw_robot(draw, x, y, frame):
    # Body
    draw.rectangle([x - 45, y, x + 45, y + 90], fill=(100, 100, 200))
    draw.rectangle([x - 40, y + 5, x + 40, y + 85], fill=(120, 120, 220))
    # Head
    draw.rectangle([x - 38, y - 70, x + 38, y + 5], fill=(100, 100, 200))
    # Eyes — blinking LED
    blink = frame % 30 > 28
    eye_color = (255, 50, 50) if blink else (50, 255, 50)
    draw.ellipse([x - 28, y - 55, x - 8, y - 35], fill=eye_color)
    draw.ellipse([x + 8, y - 55, x + 28, y - 35], fill=eye_color)
    # Mouth — scrolling
    scroll = (frame // 5) % 3
    mouth_text = ["^_^", "-_-", "o_o"][scroll]
    # Antenna
    antenna_wave = int(10 * abs((frame % 20) / 10 - 1))
    draw.line([(x, y - 70), (x + antenna_wave, y - 110)], fill=(150, 150, 200), width=4)
    draw.ellipse([x + antenna_wave - 8, y - 120, x + antenna_wave + 8, y - 104],
                 fill=(255, 50, 50))
    # Arms
    arm_angle = int(20 * abs((frame % 20) / 10 - 1))
    draw.rectangle([x - 75, y + 5 + arm_angle, x - 45, y + 35 + arm_angle],
                   fill=(80, 80, 180))
    draw.rectangle([x + 45, y + 5 - arm_angle, x + 75, y + 35 - arm_angle],
                   fill=(80, 80, 180))
    # Legs
    draw.rectangle([x - 35, y + 85, x - 10, y + 130], fill=(80, 80, 180))
    draw.rectangle([x + 10, y + 85, x + 35, y + 130], fill=(80, 80, 180))


def create_cartoon_video(script: str, title: str, output_path: Path, character: str = "cat"):
    """Create an animated cartoon video."""
    temp_dir = WORK_DIR / "temp"
    audio_path = temp_dir / "cartoon_audio.mp3"
    frames_dir = temp_dir / "cartoon_frames"
    frames_dir.mkdir(exist_ok=True)

    print("    Generating voiceover...")
    text_to_speech(script, audio_path)
    duration = get_audio_duration(audio_path)
    total_frames = int(duration * FPS)

    words = script.split()
    words_per_chunk = 6
    chunks = [" ".join(words[i:i+words_per_chunk])
              for i in range(0, len(words), words_per_chunk)]
    frames_per_chunk = max(1, total_frames // len(chunks))

    font_title = get_font(48)
    font_text = get_font(40)

    print(f"    Generating {total_frames} cartoon frames...")

    for frame_num in range(total_frames):
        img = Image.new("RGB", (WIDTH, HEIGHT), (135, 206, 235))
        draw = ImageDraw.Draw(img)
        draw_cartoon_scene(draw, frame_num, total_frames, character)

        # Title banner at top
        banner_h = 130
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.rectangle([0, 0, WIDTH, banner_h], fill=(0, 0, 0, 160))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        title_lines = wrap_text(title, font_title, WIDTH - 60, draw)
        ty = 20
        for line in title_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            tx = (WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((tx + 2, ty + 2), line, font=font_title, fill=(0, 0, 0))
            draw.text((tx, ty), line, font=font_title, fill=(255, 220, 50))
            ty += bbox[3] - bbox[1] + 8

        # Subtitle text at bottom
        chunk_idx = min(frame_num // frames_per_chunk, len(chunks) - 1)
        current_text = chunks[chunk_idx]

        sub_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        sub_draw = ImageDraw.Draw(sub_overlay)
        sub_draw.rectangle([0, HEIGHT - 220, WIDTH, HEIGHT - 40], fill=(0, 0, 0, 160))
        img = Image.alpha_composite(img.convert("RGBA"), sub_overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        lines = wrap_text(current_text, font_text, WIDTH - 80, draw)
        text_y = HEIGHT - 200
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_text)
            tx = (WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((tx + 2, text_y + 2), line, font=font_text, fill=(0, 0, 0))
            draw.text((tx, text_y), line, font=font_text, fill=(255, 255, 255))
            text_y += bbox[3] - bbox[1] + 10

        frame_path = frames_dir / f"frame_{frame_num:05d}.png"
        img.save(str(frame_path))

        if frame_num % 30 == 0:
            print(f"    Frame {frame_num}/{total_frames}...")

    print("    Combining frames and audio...")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path)
    ], capture_output=True)

    import shutil
    shutil.rmtree(str(frames_dir), ignore_errors=True)
    audio_path.unlink(missing_ok=True)
    print(f"    ✓ Video saved: {output_path.name}")


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def create_reddit_story(topic: str = "") -> dict:
    ensure_dirs()
    print(f"\n[Creator] Generating Reddit story...")
    data = generate_reddit_story(topic)
    print(f"    Title: {data['title']}")
    safe_title = "".join(c for c in data["title"] if c.isalnum() or c in " -_")[:40]
    output_path = VIDEOS_DIR / f"reddit_{safe_title.replace(' ', '_')}.mp4"
    create_reddit_story_video(data["story"], data["title"], output_path)
    return {"path": output_path, "title": data["title"], "script": data["story"]}


def create_cartoon(topic: str = "", character: str = "cat") -> dict:
    ensure_dirs()
    print(f"\n[Creator] Generating cartoon...")
    data = generate_cartoon_script(topic)
    print(f"    Title: {data['title']}")
    safe_title = "".join(c for c in data["title"] if c.isalnum() or c in " -_")[:40]
    output_path = VIDEOS_DIR / f"cartoon_{safe_title.replace(' ', '_')}.mp4"
    create_cartoon_video(data["script"], data["title"], output_path, character)
    return {"path": output_path, "title": data["title"], "script": data["script"]}