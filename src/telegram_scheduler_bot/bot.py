from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import get_settings
from .storage import MessageStorage


ASK_MESSAGE, ASK_DATETIME = range(2)
UTC = timezone.utc

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

settings = get_settings()
local_tz = ZoneInfo(settings.timezone)
storage = MessageStorage()
scheduler = AsyncIOScheduler(timezone=local_tz)


def format_local_time(dt_utc: datetime) -> str:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return dt_utc.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")


async def send_scheduled_message(
    application: Application,
    message_id: int,
    chat_id: int,
    message: str,
) -> None:
    try:
        await application.bot.send_message(chat_id=chat_id, text=message)
        storage.update_status(message_id=message_id, status="sent")
        logger.info("Sent scheduled message %s", message_id)
    except Exception:
        storage.update_status(message_id=message_id, status="failed")
        logger.exception("Failed to send scheduled message %s", message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await update.effective_message.reply_text(
        "Hello! I can schedule Telegram messages.\n\n"
        "Commands:\n"
        "/schedule - Create a scheduled message\n"
        "/list - View your pending messages\n"
        "/delete <id> - Delete a pending message\n"
        "/cancel - Cancel the current action\n"
        "/help - Show this help message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Send the message text you want me to schedule."
    )
    return ASK_MESSAGE


async def receive_message_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["message_to_schedule"] = update.effective_message.text
    await update.effective_message.reply_text(
        "Now send the delivery time in this format:\n\n"
        "YYYY-MM-DD HH:MM\n\n"
        f"Timezone: {settings.timezone}"
    )
    return ASK_DATETIME


async def receive_schedule_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    raw_value = update.effective_message.text.strip()
    message = context.user_data.get("message_to_schedule", "").strip()

    if not message:
        await update.effective_message.reply_text(
            "I lost the message text. Please start again with /schedule."
        )
        return ConversationHandler.END

    try:
        scheduled_local = datetime.strptime(raw_value, "%Y-%m-%d %H:%M").replace(
            tzinfo=local_tz
        )
    except ValueError:
        await update.effective_message.reply_text(
            "Invalid date format. Use:\n"
            "YYYY-MM-DD HH:MM"
        )
        return ASK_DATETIME

    now_local = datetime.now(local_tz)
    if scheduled_local <= now_local:
        await update.effective_message.reply_text(
            "Please choose a future date and time."
        )
        return ASK_DATETIME

    scheduled_utc = scheduled_local.astimezone(UTC).replace(tzinfo=None)
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    message_id = storage.create_message(
        chat_id=chat_id,
        user_id=user_id,
        message=message,
        scheduled_time_utc=scheduled_utc,
    )

    scheduler.add_job(
        send_scheduled_message,
        trigger="date",
        run_date=scheduled_local,
        args=[context.application, message_id, chat_id, message],
        id=str(message_id),
        replace_existing=True,
    )

    await update.effective_message.reply_text(
        "Message scheduled successfully.\n\n"
        f"ID: {message_id}\n"
        f"Time: {scheduled_local.strftime('%Y-%m-%d %H:%M')} ({settings.timezone})"
    )
    context.user_data.pop("message_to_schedule", None)
    return ConversationHandler.END


async def list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    rows = storage.list_pending_for_user(user_id=update.effective_user.id)
    if not rows:
        await update.effective_message.reply_text(
            "You have no pending scheduled messages."
        )
        return

    response_lines = ["Your pending scheduled messages:"]
    for row in rows:
        response_lines.append(
            f"ID: {row.id}\n"
            f"Time: {format_local_time(row.scheduled_time_utc)} ({settings.timezone})\n"
            f"Message: {row.message}"
        )

    await update.effective_message.reply_text("\n\n".join(response_lines))


async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /delete <id>")
        return

    try:
        message_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("Message ID must be a number.")
        return

    deleted = storage.delete_pending_message(
        message_id=message_id,
        user_id=update.effective_user.id,
    )
    if not deleted:
        await update.effective_message.reply_text(
            "I could not find a pending message with that ID."
        )
        return

    try:
        scheduler.remove_job(str(message_id))
    except JobLookupError:
        logger.info("Scheduler job %s was already missing during delete.", message_id)

    await update.effective_message.reply_text(
        f"Deleted scheduled message {message_id}."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("message_to_schedule", None)
    await update.effective_message.reply_text("Scheduling cancelled.")
    return ConversationHandler.END


def reload_pending_jobs(application: Application) -> None:
    now_utc = datetime.utcnow().replace(tzinfo=UTC)
    for row in storage.list_all_pending():
        scheduled_utc = row.scheduled_time_utc.replace(tzinfo=UTC)

        if scheduled_utc <= now_utc:
            storage.update_status(message_id=row.id, status="failed")
            continue

        scheduler.add_job(
            send_scheduled_message,
            trigger="date",
            run_date=scheduled_utc.astimezone(local_tz),
            args=[application, row.id, row.chat_id, row.message],
            id=str(row.id),
            replace_existing=True,
        )


def build_application() -> Application:
    if not settings.bot_token:
        raise ValueError("BOT_TOKEN is missing. Add it to your environment or .env file.")

    storage.initialize()
    application = ApplicationBuilder().token(settings.bot_token).build()

    schedule_handler = ConversationHandler(
        entry_points=[CommandHandler("schedule", schedule_start)],
        states={
            ASK_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message_text)
            ],
            ASK_DATETIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_schedule_time)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(schedule_handler)
    application.add_handler(CommandHandler("list", list_messages))
    application.add_handler(CommandHandler("delete", delete_message))
    application.add_handler(CommandHandler("cancel", cancel))

    reload_pending_jobs(application)
    return application


def main() -> None:
    application = build_application()
    scheduler.start()
    logger.info("Bot is running with polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
