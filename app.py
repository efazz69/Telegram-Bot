from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from dotenv import load_dotenv
import os
import logging
import requests

# ---------------------------
# Setup
# ---------------------------
load_dotenv()
app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = f"https://telegram-bot-5fco.onrender.com/{BOT_TOKEN}"

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Enable logging for debugging (Render logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------
# Telegram Handlers
# ---------------------------
def start(update, context):
    update.message.reply_text("👋 Hello! Your Telegram Crypto Bot is active and running on Render.")

def help_command(update, context):
    update.message.reply_text("🧠 Available commands:\n/start — Start the bot\n/help — Show this message")

def echo(update, context):
    """Echo any text message"""
    update.message.reply_text(f"🪙 You said: {update.message.text}")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# ---------------------------
# Flask Routes
# ---------------------------
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Flask server is running successfully!",
        "webhook_url": WEBHOOK_URL
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Receive Telegram updates"""
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})

@app.route('/setwebhook')
def set_webhook():
    """Manually trigger setting the webhook"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}"
    response = requests.get(url)
    return jsonify(response.json())

@app.route('/deletewebhook')
def delete_webhook():
    """Delete webhook if needed"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    response = requests.get(url)
    return jsonify(response.json())

# ---------------------------
# Startup
# ---------------------------
if __name__ == '__main__':
    # Automatically set webhook on startup (useful for Render)
    try:
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
        logger.info(f"Webhook setup: {response.json()}")
    except Exception as e:
        logger.error(f"Failed to set webhook automatically: {e}")

    app.run(host='0.0.0.0', port=5000)
