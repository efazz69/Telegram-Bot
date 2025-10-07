from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from dotenv import load_dotenv
import os

# Load environment variables (BOT_TOKEN, etc.)
load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ---------------------------
# Telegram Bot Handlers
# ---------------------------
def start(update, context):
    update.message.reply_text("👋 Hello! Your Telegram Crypto Bot is active.")

def help_command(update, context):
    update.message.reply_text("Use /start to begin using this bot.")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))

# ---------------------------
# Flask Routes
# ---------------------------
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Bot web server is running and webhook is active."
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates"""
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# ---------------------------
# Startup
# ---------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
