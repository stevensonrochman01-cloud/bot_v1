# Telegram Scheduler Bot

A Telegram bot for scheduling future messages, adapted for Railway as an always-on worker.

## How This Version Works

Railway can keep a Python process running continuously, so this version uses:

- Telegram polling for incoming bot messages
- APScheduler for in-process scheduled delivery
- Postgres or SQLite for persistent scheduled jobs
- Automatic job reload from the database after restarts

This is a much better fit for a scheduler bot than serverless cron limits.

## Features

- `/start` and `/help`
- `/schedule` multi-step scheduling flow
- `/list` to view pending messages
- `/delete <id>` to delete a pending message
- `/cancel` to stop the current scheduling flow
- SQLite support for local development
- Postgres support for Railway production

## Project Structure

```text
.
|-- .env
|-- .env.example
|-- .gitignore
|-- Procfile
|-- README.md
|-- requirements.txt
|-- run.py
`-- src/
    `-- telegram_scheduler_bot/
        |-- __init__.py
        |-- bot.py
        |-- config.py
        `-- storage.py
```

## Local Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Confirm `.env` has your bot token.
4. Start the bot:

```bash
python run.py
```

## Required Environment Variables

- `BOT_TOKEN`
- `TIMEZONE`
- `DATABASE_URL`

Example local SQLite setup:

```env
BOT_TOKEN=your_telegram_bot_token_here
TIMEZONE=UTC
DATABASE_URL=sqlite:///data/scheduled_messages.db
```

Example Railway Postgres setup:

```env
BOT_TOKEN=your_telegram_bot_token_here
TIMEZONE=UTC
DATABASE_URL=postgresql://username:password@host:5432/postgres
```

## Telegram Commands

- `/start`
- `/help`
- `/schedule`
- `/list`
- `/delete <id>`
- `/cancel`

## Schedule Flow

1. Send `/schedule`
2. Send the message text
3. Send the date/time in this format:

```text
YYYY-MM-DD HH:MM
```

Example:

```text
2026-06-07 18:30
```

The bot interprets time using `TIMEZONE`.

## Railway Deployment

1. Push the project to GitHub.
2. In Railway, create a new project from your GitHub repo.
3. Add environment variables:
   - `BOT_TOKEN`
   - `TIMEZONE`
   - `DATABASE_URL`
4. If you are using Supabase Postgres, paste that connection string into `DATABASE_URL`.
5. Set the start command to:

```bash
python run.py
```

6. Deploy the service.

Railway will keep the process running, and the bot will poll Telegram directly, so you do not need webhooks, `APP_URL`, or cron setup.

## Notes

- The bot can only message chats where it has already been started or added.
- Pending scheduled messages are reloaded from the database after restart.
- If the app is offline during a scheduled send time, missed messages are currently marked as failed on restart rather than sent late.
