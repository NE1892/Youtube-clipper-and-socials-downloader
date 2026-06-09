# YouTube Auto-Clipper 🎬

Paste a YouTube channel URL → get highlight clips → download them.

## First-time setup (any machine)

1. **Clone the repo**
   ```bash
   git clone https://github.com/YOUR_USERNAME/yt-clipper
   cd yt-clipper
   ```

2. **Add your OpenAI API key** (only needed for AI mode)
   ```bash
   cp .env.example .env
   # Edit .env and paste your key
   ```

3. **Double-click `Start.command`**
   - First run installs all dependencies automatically
   - Browser opens at http://localhost:5000

## Every run after that

Just double-click **`Start.command`**.

## Usage

1. Paste a YouTube channel URL
2. Choose how many videos to process and clip settings
3. Toggle AI on (GPT-4 picks best moments) or off (random clips)
4. Hit **Start Clipping**
5. Download your clips when done

## Uploading to GitHub

1. Create a new repo at https://github.com/new
2. Run:
   ```bash
   git init
   git add .
   git commit -m "first commit"
   git remote add origin https://github.com/YOUR_USERNAME/yt-clipper.git
   git push -u origin main
   ```

On a new machine, just `git clone` and double-click `Start.command`.

## Notes

- Clips are saved to `clipper_output/clips/`
- Downloaded videos are cached in `clipper_output/downloads/`
- The `.env` file is gitignored so your API key stays private
