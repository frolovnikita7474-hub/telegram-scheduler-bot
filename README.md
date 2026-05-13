# Telegram Bot — Delayed Publishing

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Create `.env` file:
```
BOT_TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
CHANNEL_ID=channel_id
```

Or set environment variables on your hosting platform.

## Run locally

```bash
python bot.py
```

Or double-click `run.bat`

## Deploy to Render

1. Push code to GitHub
2. Go to [render.com](https://render.com) → "New" → "Blueprint"
3. Connect your GitHub repo
4. Set environment variables:
   - `BOT_TOKEN`
   - `ADMIN_ID`
   - `CHANNEL_ID`
5. Deploy — bot will run 24/7 for free