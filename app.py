from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram.error import BadRequest
from dotenv import load_dotenv
import os
import logging
import requests
import json
import time
import traceback
from datetime import datetime
import random
import re
from web3 import Web3 # Kept for context

# ---------------------------
# Configuration
# ---------------------------
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7963936009:AAEK3Y4GYCpRk4mbASW2Xvh7u0xedXmR64Y')
# ADMIN_ID is read as a string from environment variables
ADMIN_ID = os.getenv('ADMIN_ID', '7091475665') 
# IMPORTANT: Replace this with your actual Render URL base
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-render-app-name.onrender.com/webhook') 

# API Configuration
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3/simple/price"

# Payment Configuration
CRYPTO_NETWORKS = {
    'USDT_BEP20': {
        'name': 'USDT (BEP20)',
        'network': 'BSC',
        'decimals': 6,
        'coingecko_id': 'tether',
        'symbol': 'USDT'
    },
    'BTC': {
        'name': 'Bitcoin',
        'network': 'BTC',
        'decimals': 8,
        'coingecko_id': 'bitcoin',
        'symbol': 'BTC'
    },
    'LTC': {
        'name': 'Litecoin',
        'network': 'LTC',
        'decimals': 8,
        'coingecko_id': 'litecoin',
        'symbol': 'LTC'
    }
}

# Your wallet addresses (REPLACE WITH YOUR ACTUAL ADDRESSES)
WALLET_ADDRESSES = {
    'USDT_BEP20': '0x515a1DA038D2813400912C88Bbd4921836041766', 
    'BTC': 'bc1q...BTC_ADDRESS_HERE',
    'LTC': 'ltc1q...LTC_ADDRESS_HERE'
}

# ---------------------------
# State and Database (Mocked for in-memory state)
# ---------------------------
# {chat_id: {'step': 'awaiting_usd_amount', 'currency_key': 'USDT_BEP20', 'usd_amount': None, 'time': datetime}}
user_deposits = {} 
# {chat_id: {'USD': 0.0, 'last_update': datetime}}
user_balances = {} 

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# Price Retrieval Function
# ---------------------------
def get_crypto_price(currency_key):
    """
    Fetches the current price of a cryptocurrency in USD using CoinGecko.
    Returns: {'price': float} or None on failure.
    """
    if currency_key not in CRYPTO_NETWORKS:
        logger.error(f"Unknown currency key: {currency_key}")
        return None

    coingecko_id = CRYPTO_NETWORKS[currency_key]['coingecko_id']
    url = f"{COINGECKO_API_BASE}?ids={coingecko_id}&vs_currencies=usd"
    
    logger.info(f"🔍 Fetching price for {currency_key}...")
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        if coingecko_id in data and 'usd' in data[coingecko_id]:
            price = data[coingecko_id]['usd']
            if isinstance(price, (int, float)) and price > 0:
                logger.info(f"✅ Real-time price for {currency_key}: ${price:.4f}")
                return {'price': float(price)}
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to fetch price for {currency_key} from CoinGecko: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during price fetch for {currency_key}: {e}")
        return None
    
    return None

# ---------------------------
# Telegram Handlers
# ---------------------------

def start(update: Update, context):
    """Sends the initial menu message."""
    chat_id = update.effective_chat.id
    first_name = update.effective_user.first_name

    welcome_message = f"👋 Hello, **{first_name}**! Welcome to the Balance Top-up Bot.\n\n" \
                      f"Your current balance is: **${user_balances.get(chat_id, {}).get('USD', 0.0):.2f}**"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Balance", callback_data='menu_deposit')],
        [InlineKeyboardButton("💰 View Balance", callback_data='menu_balance')],
        [InlineKeyboardButton("📝 Contact Admin", url=f"tg://user?id={ADMIN_ID}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Use Markdown for message formatting
    update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

def handle_menu_callback(update: Update, context):
    """Handles all menu button clicks."""
    query = update.callback_query
    query.answer()
    
    data = query.data
    chat_id = query.message.chat_id
    
    if data == 'menu_deposit':
        start_deposit_flow(query.message, context)
    elif data == 'menu_balance':
        balance = user_balances.get(chat_id, {}).get('USD', 0.0)
        query.message.edit_text(
            f"💰 Your current balance is: **${balance:.2f}**",
            parse_mode='Markdown'
        )
    elif data.startswith('deposit_'):
        handle_deposit_selection(query.message, context, data.split('_')[1])
    elif data == 'back_to_main':
        # Re-use start logic to send the main menu
        start_message = f"👋 Welcome back! Your current balance is: **${user_balances.get(chat_id, {}).get('USD', 0.0):.2f}**"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Balance", callback_data='menu_deposit')],
            [InlineKeyboardButton("💰 View Balance", callback_data='menu_balance')],
            [InlineKeyboardButton("📝 Contact Admin", url=f"tg://user?id={ADMIN_ID}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            query.message.edit_text(start_message, reply_markup=reply_markup, parse_mode='Markdown')
        except BadRequest as e:
            if 'Message is not modified' in str(e):
                return
            logger.error(f"Error editing message in back_to_main: {e}")
            query.message.reply_text(start_message, reply_markup=reply_markup, parse_mode='Markdown')


def start_deposit_flow(message, context):
    """Prompts the user to select a crypto network."""
    keyboard = [
        [InlineKeyboardButton(CRYPTO_NETWORKS[key]['name'], callback_data=f'deposit_{key}')]
        for key in CRYPTO_NETWORKS
    ]
    keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        message.edit_text(
            "Please select the cryptocurrency you wish to use for deposit:", 
            reply_markup=reply_markup
        )
    except BadRequest as e:
        if 'Message is not modified' in str(e):
            return
        logger.error(f"Error editing message in start_deposit_flow: {e}")
        message.reply_text("Please select the cryptocurrency you wish to use for deposit:", reply_markup=reply_markup)


def handle_deposit_selection(message, context, currency_key):
    """Stores the chosen currency and prompts for USD amount."""
    chat_id = message.chat_id
    
    # 1. Update state
    user_deposits[chat_id] = {
        'step': 'awaiting_usd_amount',
        'currency_key': currency_key,
        'time': datetime.now()
    }
    
    network_name = CRYPTO_NETWORKS[currency_key]['name']
    
    # 2. Ask for amount
    try:
        message.edit_text(
            f"You selected **{network_name}**.\n\nPlease reply with the **exact USD amount** you wish to deposit (e.g., `50.00`).",
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if 'Message is not modified' not in str(e):
            logger.error(f"Error editing message in handle_deposit_selection: {e}")
            message.reply_text(
                f"You selected **{network_name}**.\n\nPlease reply with the **exact USD amount** you wish to deposit (e.g., `50.00`).",
                parse_mode='Markdown'
            )


def handle_deposit_amount(update: Update, context):
    """
    Handles the user's message containing the USD amount.
    FIXED: Added robust input validation and fixed the Telegram parsing error.
    """
    chat_id = update.effective_chat.id
    
    if chat_id not in user_deposits or user_deposits[chat_id].get('step') != 'awaiting_usd_amount':
        # Ignore messages not part of the deposit flow
        return

    text = update.message.text
    currency_key = user_deposits[chat_id]['currency_key']
    
    # --- FIX 1: Robust Input Validation ---
    try:
        usd_amount = float(text)
        if usd_amount <= 0:
            raise ValueError("Amount must be positive.")
    except ValueError:
        user_deposits.pop(chat_id, None) # Clear state on invalid input
        update.message.reply_text(
            "❌ Invalid amount. Please enter a valid positive number for the USD amount (e.g., `50.00`).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Start New Deposit", callback_data='menu_deposit')]])
        )
        return

    # Store the valid amount
    user_deposits[chat_id]['usd_amount'] = usd_amount
    
    # --- FIX 2: General Exception Handling ---
    try:
        # 1. Get current price
        price_data = get_crypto_price(currency_key)
        if not price_data or not price_data.get('price'):
            raise Exception("Failed to retrieve current crypto price. The price API might be down.")

        price = price_data['price']
        
        # 2. Calculate required crypto amount
        crypto_amount = usd_amount / price
        
        # 3. Get network details
        network_info = CRYPTO_NETWORKS[currency_key]
        wallet_address = WALLET_ADDRESSES[currency_key]
        
        crypto_symbol = network_info['symbol']
        network_name = network_info['name']

        # Format crypto amount
        crypto_amount_str = f"{crypto_amount:.8f}".rstrip('0').rstrip('.')
        
        # --- FIX 3: Safe Message Construction (Addressing the Parse Entities Error) ---
        # We use HTML and the <pre> tag to safely display the wallet address.
        
        confirmation_message = (
            f"✅ <b>Deposit Confirmation</b>\n\n"
            f"You are depositing: <b>${usd_amount:.2f} USD</b>\n"
            f"Required {crypto_symbol} amount: <b>{crypto_amount_str} {crypto_symbol}</b>\n"
            f"(Rate: 1 {crypto_symbol} = ${price:.4f} USD)\n\n"
            
            f"<b>1. Send the EXACT amount to this address:</b>\n"
            f"Network: <b>{network_name}</b>\n"
            f"Address: <pre>{wallet_address}</pre>\n\n" # <--- This is the key fix
            f"<b>2. Click 'I have paid' below once the transaction is sent.</b>\n"
            f"<b>3. Contact the admin if you have any issues!</b>"
        )
        
        keyboard = [
            # Passing amount for confirmation handler
            [InlineKeyboardButton("💰 I have paid", callback_data=f'paid_{currency_key}_{usd_amount:.2f}')], 
            [InlineKeyboardButton("« Cancel Deposit", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            confirmation_message, 
            reply_markup=reply_markup,
            parse_mode='HTML' # <-- Explicitly use HTML
        )
        
        logger.info(f"✅ Generated deposit for {chat_id}: {usd_amount} USD = {crypto_amount_str} {crypto_symbol}")

    except Exception as e:
        logger.error(f"❌ Error processing deposit amount for {chat_id}: {traceback.format_exc()}")
        
        # Clean up the state so user can start over
        user_deposits.pop(chat_id, None)

        update.message.reply_text(
            "❌ An error occurred while processing your deposit. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Main Menu", callback_data='back_to_main')]])
        )
        return

def handle_payment_confirmation(update: Update, context):
    """Handles the 'I have paid' button click."""
    query = update.callback_query
    query.answer()
    
    data_parts = query.data.split('_')
    # data format: paid_USDT_BEP20_50.00
    
    currency_key = data_parts[1]
    usd_amount = float(data_parts[2])
    
    chat_id = query.message.chat_id
    
    # 1. Notify Admin for manual review/automated check
    context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🚨 **NEW PENDING DEPOSIT**\n"
             f"User ID: `{chat_id}`\n"
             f"Username: @{query.from_user.username or 'N/A'}\n"
             f"Amount: **${usd_amount:.2f} USD**\n"
             f"Network: **{CRYPTO_NETWORKS[currency_key]['name']}**\n"
             f"Address: `{WALLET_ADDRESSES[currency_key]}`",
        parse_mode='Markdown'
    )
    
    # 2. Acknowledge user
    query.message.edit_text(
        f"👍 Thank you! Your payment of **${usd_amount:.2f} USD** has been marked for review. We will notify you once the funds are confirmed and added to your balance.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Main Menu", callback_data='back_to_main')]])
    )
    
    # 3. Clean up temporary state
    user_deposits.pop(chat_id, None)
        
# --------------------------
# Flask and Dispatcher Setup
# --------------------------
app = Flask(__name__)
bot = Bot(BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Register Handlers
dispatcher.add_handler(CommandHandler('start', start))
# Handle menu/deposit flow callbacks
dispatcher.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r'^(menu_|back_to_main|deposit_)'))
# Handle 'I have paid' confirmation callback
dispatcher.add_handler(CallbackQueryHandler(handle_payment_confirmation, pattern=r'^paid_'))
# Filters.text ensures we only process text messages that are not commands (for deposit amount)
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_deposit_amount))

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Receive and process Telegram updates."""
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), bot)
            dispatcher.process_update(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True})
    return jsonify({"ok": True})

@app.route('/setwebhook')
def set_webhook():
    """Manually trigger setting the webhook"""
    # Use the /BOT_TOKEN route path for the endpoint
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
    response = requests.get(url)
    return jsonify(response.json())

@app.route('/deletewebhook')
def delete_webhook():
    """Delete webhook if needed"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    response = requests.get(url)
    return jsonify(response.json())

# --------------------------
# Startup
# --------------------------
if __name__ == '__main__':
    print("Starting bot application...")
    print("✅ Payment Handler Initialized")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
