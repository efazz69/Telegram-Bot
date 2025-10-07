from flask import Flask, jsonify
import os
import subprocess
import sys

app = Flask(__name__)

# Global variable to track bot process
bot_process = None

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Bot web server is running. Visit /start-bot to start the Telegram bot."
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot_running": bot_process is not None})

@app.route('/start-bot')
def start_bot():
    global bot_process
    
    if bot_process is not None:
        return jsonify({"status": "already_running", "message": "Bot is already running"})
    
    try:
        # Start bot in a separate process
        bot_process = subprocess.Popen([sys.executable, 'bot.py'], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE,
                                      text=True)
        return jsonify({"status": "started", "message": "Bot started successfully"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop-bot')
def stop_bot():
    global bot_process
    
    if bot_process is None:
        return jsonify({"status": "not_running", "message": "Bot is not running"})
    
    try:
        bot_process.terminate()
        bot_process.wait(timeout=5)
        bot_process = None
        return jsonify({"status": "stopped", "message": "Bot stopped successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
