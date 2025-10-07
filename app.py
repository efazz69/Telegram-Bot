from flask import Flask, jsonify
import os
import threading
import asyncio
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store bot instance globally
bot_instance = None
bot_thread = None

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Bot is running in the background"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot_running": bot_instance is not None})

@app.route('/start-bot')
def start_bot():
    global bot_instance, bot_thread
    
    if bot_instance is not None:
        return jsonify({"status": "already_running", "message": "Bot is already running"})
    
    try:
        # Import and start the bot in a separate thread
        from bot import CryptoStoreBot, BOT_TOKEN
        
        if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE' or not BOT_TOKEN:
            return jsonify({"status": "error", "message": "BOT_TOKEN not set"})
        
        def run_bot():
            global bot_instance
            try:
                bot_instance = CryptoStoreBot()
                print("🤖 Starting Telegram bot...")
                bot_instance.application.run_polling()
            except Exception as e:
                print(f"❌ Bot error: {e}")
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
        return jsonify({"status": "started", "message": "Bot started successfully"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop-bot')
def stop_bot():
    global bot_instance, bot_thread
    
    if bot_instance is None:
        return jsonify({"status": "not_running", "message": "Bot is not running"})
    
    try:
        bot_instance.application.stop()
        bot_instance = None
        bot_thread = None
        return jsonify({"status": "stopped", "message": "Bot stopped successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    # Auto-start bot when running locally
    if os.environ.get('RENDER') != 'true':
        from bot import CryptoStoreBot, BOT_TOKEN
        if BOT_TOKEN and BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE':
            bot = CryptoStoreBot()
            bot.application.run_polling()
        else:
            print("❌ BOT_TOKEN not set. Starting web server only.")
            app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        # On Render, just start the web server
        app.run(host='0.0.0.0', port=5000, debug=False)