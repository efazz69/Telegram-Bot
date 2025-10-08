import os
import logging
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from telegram.constants import ParseMode
from flask import Flask, request, jsonify
import threading
import time

# Initialize Flask app for webhook
app = Flask(__name__)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7963936009:AAEK3Y4GYCpRk4mbASW2Xvh7u0xedXmR64Y')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://your-app-name.onrender.com')
ADMIN_IDS = [123456789]  # Replace with your admin user IDs

# Conversation states
DEPOSIT_AMOUNT, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS, ADMIN_ACTION = range(4)

# Database setup
def init_db():
    conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0.0,
            total_deposited REAL DEFAULT 0.0,
            total_withdrawn REAL DEFAULT 0.0,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            currency TEXT,
            network TEXT,
            address TEXT,
            tx_hash TEXT,
            status TEXT DEFAULT 'pending',
            confirmed_blocks INTEGER DEFAULT 0,
            required_blocks INTEGER DEFAULT 12,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Crypto addresses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crypto_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT,
            network TEXT,
            address TEXT UNIQUE,
            private_key TEXT,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Insert default settings
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) 
        VALUES 
        ('min_deposit', '10'),
        ('min_withdrawal', '5'),
        ('withdrawal_fee', '0.5'),
        ('admin_chat_id', '123456789')
    ''')
    
    # Insert sample crypto addresses if not exists
    cursor.execute('''
        INSERT OR IGNORE INTO crypto_addresses (currency, network, address) 
        VALUES 
        ('USDT', 'BEP20', '0x515a1DA038D2813400912C88Bbd4921836041766'),
        ('USDT', 'ERC20', '0x89205A3A3b2A69De6Dbf7f01ED13B2108B2c43e7'),
        ('BTC', 'BTC', '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'),
        ('ETH', 'ERC20', '0x742d35Cc6634C0532925a3b844Bc454e4438f44e')
    ''')
    
    # Create admin user
    for admin_id in ADMIN_IDS:
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, is_admin)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, 'admin', 'Admin', True))
    
    conn.commit()
    conn.close()

init_db()

# Database helper functions
def get_db_connection():
    conn = sqlite3.connect('crypto_bot.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_user(user_id):
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE user_id = ?', (user_id,)
    ).fetchone()
    conn.close()
    return user

def create_user(user_id, username, first_name):
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if amount > 0:
        cursor.execute(
            'UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?',
            (amount, amount, user_id)
        )
    else:
        cursor.execute(
            'UPDATE users SET balance = balance + ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?',
            (amount, abs(amount), user_id)
        )
    
    conn.commit()
    conn.close()

def add_transaction(user_id, transaction_type, amount, currency, network=None, address=None, status='pending'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO transactions (user_id, type, amount, currency, network, address, status) 
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (user_id, transaction_type, amount, currency, network, address, status)
    )
    transaction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return transaction_id

def get_transaction(transaction_id):
    conn = get_db_connection()
    transaction = conn.execute(
        'SELECT * FROM transactions WHERE id = ?', (transaction_id,)
    ).fetchone()
    conn.close()
    return transaction

def update_transaction_status(transaction_id, status, tx_hash=None):
    conn = get_db_connection()
    conn.execute(
        'UPDATE transactions SET status = ?, tx_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (status, tx_hash, transaction_id)
    )
    conn.commit()
    conn.close()

def get_crypto_address(currency, network):
    conn = get_db_connection()
    address = conn.execute(
        'SELECT address FROM crypto_addresses WHERE currency = ? AND network = ? AND is_active = TRUE',
        (currency, network)
    ).fetchone()
    conn.close()
    return address['address'] if address else None

def get_setting(key):
    conn = get_db_connection()
    setting = conn.execute(
        'SELECT value FROM settings WHERE key = ?', (key,)
    ).fetchone()
    conn.close()
    return setting['value'] if setting else None

def get_all_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return users

def get_pending_transactions():
    conn = get_db_connection()
    transactions = conn.execute(
        'SELECT * FROM transactions WHERE status = "pending"'
    ).fetchall()
    conn.close()
    return transactions

# Price fetching with multiple fallbacks
def get_crypto_price(currency_pair):
    try:
        # Try Binance first
        if currency_pair == 'USDTUSDT':
            return 1.0
        
        response = requests.get(
            f'https://api.binance.com/api/v3/ticker/price?symbol={currency_pair}',
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
    except Exception as e:
        logger.warning(f"Binance API failed: {str(e)}")
    
    try:
        # Fallback to CoinGecko
        if currency_pair == 'BTCUSDT':
            coin_id = 'bitcoin'
        elif currency_pair == 'ETHUSDT':
            coin_id = 'ethereum'
        else:
            return None
            
        response = requests.get(
            f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd',
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data[coin_id]['usd']
    except Exception as e:
        logger.warning(f"CoinGecko API failed: {str(e)}")
    
    return None

# Improved message sending with proper formatting
def send_safe_message(context, chat_id, text, reply_markup=None, parse_mode=ParseMode.HTML):
    try:
        # Split long messages
        if len(text) > 4096:
            parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for part in parts[:-1]:
                context.bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
            text = parts[-1]
        
        context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        try:
            context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=None,
                disable_web_page_preview=True
            )
        except Exception as fallback_error:
            logger.error(f"Fallback message also failed: {str(fallback_error)}")

# Command handlers
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
👋 Welcome <b>{user.first_name}</b> to Crypto Payment Bot!

💼 <b>Available Commands:</b>
/balance - Check your balance
/deposit - Add funds to your account
/withdraw - Withdraw funds
/history - View transaction history
/help - Get help

💰 <b>Supported Cryptocurrencies:</b>
• USDT (BEP20/ERC20)
• Bitcoin (BTC)
• Ethereum (ETH)

This bot allows you to deposit and withdraw cryptocurrencies securely.
    """
    
    send_safe_message(context, update.effective_chat.id, welcome_text)

def balance(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    if user:
        balance_text = f"""
💰 <b>Your Balance</b>

💵 <b>Available:</b> ${user['balance']:.2f} USD
📥 <b>Total Deposited:</b> ${user['total_deposited']:.2f} USD
📤 <b>Total Withdrawn:</b> ${user['total_withdrawn']:.2f} USD

Use /deposit to add funds or /withdraw to withdraw funds.
        """
        send_safe_message(context, update.effective_chat.id, balance_text)
    else:
        update.message.reply_text("❌ User not found. Please use /start to initialize your account.")

def deposit(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("USDT (BEP20)", callback_data='deposit_USDT_BEP20')],
        [InlineKeyboardButton("USDT (ERC20)", callback_data='deposit_USDT_ERC20')],
        [InlineKeyboardButton("BTC", callback_data='deposit_BTC_BTC')],
        [InlineKeyboardButton("ETH", callback_data='deposit_ETH_ERC20')],
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    min_deposit = get_setting('min_deposit') or '10'
    
    deposit_text = f"""
💸 <b>Deposit Funds</b>

Please select the cryptocurrency you want to deposit:

• <b>USDT (BEP20)</b> - Lower fees, faster
• <b>USDT (ERC20)</b> - Ethereum network
• <b>BTC</b> - Bitcoin
• <b>ETH</b> - Ethereum

⚠️ <b>Important:</b> Only send the selected cryptocurrency on the correct network!
💰 <b>Minimum deposit:</b> ${min_deposit} USD
    """
    
    send_safe_message(context, update.effective_chat.id, deposit_text, reply_markup=reply_markup)
    return DEPOSIT_AMOUNT

def withdraw(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    if not user or user['balance'] <= 0:
        update.message.reply_text("❌ Insufficient balance or user not found.")
        return ConversationHandler.END
    
    min_withdrawal = float(get_setting('min_withdrawal') or '5')
    withdrawal_fee = float(get_setting('withdrawal_fee') or '0.5')
    
    if user['balance'] < min_withdrawal:
        update.message.reply_text(f"❌ Minimum withdrawal amount is ${min_withdrawal:.2f}")
        return ConversationHandler.END
    
    context.user_data['withdrawal_fee'] = withdrawal_fee
    
    update.message.reply_text(
        f"💵 <b>Withdrawal Request</b>\n\n"
        f"Please enter the amount in USD you want to withdraw:\n"
        f"• Minimum: ${min_withdrawal:.2f}\n"
        f"• Fee: ${withdrawal_fee:.2f}\n"
        f"• Available: ${user['balance']:.2f}",
        parse_mode=ParseMode.HTML
    )
    return WITHDRAW_AMOUNT

def history(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = get_db_connection()
    transactions = conn.execute(
        'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
        (user_id,)
    ).fetchall()
    conn.close()
    
    if not transactions:
        update.message.reply_text("📝 No transactions found.")
        return
    
    history_text = "📊 <b>Last 10 Transactions</b>\n\n"
    for tx in transactions:
        emoji = "⬇️" if tx['type'] == 'deposit' else "⬆️"
        status_emoji = "✅" if tx['status'] == 'completed' else "⏳" if tx['status'] == 'pending' else "❌"
        history_text += f"{emoji} <b>{tx['type'].title()}</b> - ${tx['amount']:.2f} {tx['currency']} {status_emoji}\n"
        history_text += f"🕒 {tx['created_at']}\n"
        if tx['tx_hash']:
            history_text += f"🔗 {tx['tx_hash'][:20]}...\n"
        history_text += "\n"
    
    send_safe_message(context, update.effective_chat.id, history_text)

def stats(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    if not user or not user['is_admin']:
        update.message.reply_text("❌ Access denied.")
        return
    
    conn = get_db_connection()
    
    # Total statistics
    total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    total_balance = conn.execute('SELECT SUM(balance) as total FROM users').fetchone()['total'] or 0
    total_deposits = conn.execute('SELECT SUM(amount) as total FROM transactions WHERE type = "deposit" AND status = "completed"').fetchone()['total'] or 0
    total_withdrawals = conn.execute('SELECT SUM(amount) as total FROM transactions WHERE type = "withdrawal" AND status = "completed"').fetchone()['total'] or 0
    pending_deposits = conn.execute('SELECT COUNT(*) as count FROM transactions WHERE type = "deposit" AND status = "pending"').fetchone()['count']
    pending_withdrawals = conn.execute('SELECT COUNT(*) as count FROM transactions WHERE type = "withdrawal" AND status = "pending"').fetchone()['count']
    
    conn.close()
    
    stats_text = f"""
📈 <b>Bot Statistics</b>

👥 <b>Total Users:</b> {total_users}
💰 <b>Total Balance:</b> ${total_balance:.2f}
📥 <b>Total Deposits:</b> ${total_deposits:.2f}
📤 <b>Total Withdrawals:</b> ${total_withdrawals:.2f}
⏳ <b>Pending Deposits:</b> {pending_deposits}
⏳ <b>Pending Withdrawals:</b> {pending_withdrawals}
    """
    
    send_safe_message(context, update.effective_chat.id, stats_text)

def help_command(update: Update, context: CallbackContext):
    help_text = """
🆘 <b>Help Guide</b>

<b>Commands:</b>
/start - Initialize your account
/balance - Check your balance  
/deposit - Add funds via cryptocurrency
/withdraw - Withdraw funds to your wallet
/history - View transaction history
/help - This help message

<b>Supported Cryptocurrencies:</b>
• USDT (BEP20/ERC20)
• Bitcoin (BTC)
• Ethereum (ETH)

<b>Deposit Process:</b>
1. Use /deposit and select currency
2. Enter USD amount
3. Send exact crypto amount to provided address
4. Wait for confirmation

<b>Withdrawal Process:</b>
1. Use /withdraw and enter amount
2. Provide your wallet address
3. Wait for processing

<b>Need Assistance?</b>
Contact support if you encounter any issues.
    """
    
    send_safe_message(context, update.effective_chat.id, help_text)

# Callback query handler
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'cancel':
        query.edit_message_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    if data.startswith('deposit_'):
        _, currency, network = data.split('_')
        
        context.user_data['deposit_currency'] = currency
        context.user_data['deposit_network'] = network
        
        # Get current price
        price_symbol = f"{currency}USDT" if currency != 'USDT' else 'USDT'
        price = get_crypto_price(price_symbol)
        price_info = f" (≈ ${price:.4f})" if price and currency != 'USDT' else ""
        
        min_deposit = get_setting('min_deposit') or '10'
        
        query.edit_message_text(
            f"💵 <b>Deposit {currency} ({network})</b>{price_info}\n\n"
            f"Please enter the amount in USD you want to deposit:\n"
            f"• Minimum: ${min_deposit}",
            parse_mode=ParseMode.HTML
        )
        return DEPOSIT_AMOUNT

# Message handler for deposit amount
def handle_deposit_amount(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        amount = float(text)
        min_deposit = float(get_setting('min_deposit') or '10')
        
        if amount < min_deposit:
            update.message.reply_text(f"❌ Minimum deposit amount is ${min_deposit:.2f}")
            return DEPOSIT_AMOUNT
        
        currency = context.user_data.get('deposit_currency')
        network = context.user_data.get('deposit_network')
        
        if not currency or not network:
            update.message.reply_text("❌ Error: Please start over with /deposit")
            return ConversationHandler.END
        
        # Get crypto address
        address = get_crypto_address(currency, network)
        if not address:
            update.message.reply_text("❌ Error: Address not available. Please try another currency.")
            return ConversationHandler.END
        
        # Get current price for the selected cryptocurrency
        price_symbol = f"{currency}USDT" if currency != 'USDT' else 'USDT'
        price = get_crypto_price(price_symbol)
        
        if currency == 'USDT':
            crypto_amount = amount
        elif price:
            crypto_amount = amount / price
        else:
            update.message.reply_text("❌ Error: Could not fetch current price. Please try again.")
            return ConversationHandler.END
        
        # Format crypto amount appropriately
        if currency in ['BTC', 'ETH']:
            crypto_amount = Decimal(str(crypto_amount)).quantize(Decimal('0.00000000'), rounding=ROUND_DOWN)
        else:
            crypto_amount = Decimal(str(crypto_amount)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        
        # Add transaction to database
        transaction_id = add_transaction(
            user_id=user_id,
            transaction_type='deposit',
            amount=amount,
            currency=currency,
            network=network,
            address=address,
            status='pending'
        )
        
        # Create deposit instructions
        instructions = f"""
💸 <b>Deposit Instructions</b>

• <b>Network:</b> {network}
• <b>Amount:</b> ${amount:.2f} USD
• <b>Equivalent {currency}:</b> {crypto_amount:.8f if currency in ['BTC', 'ETH'] else crypto_amount:.2f}
• <b>Address:</b> <code>{address}</code>
• <b>Transaction ID:</b> #{transaction_id}

Please send exactly <b>{crypto_amount:.8f if currency in ['BTC', 'ETH'] else crypto_amount:.2f} {currency}</b> to the address above.

⚠️ <b>Important:</b>
• Send only {currency} on the {network} network
• Do not send any other currency or from other networks
• Transactions may take 5-30 minutes to confirm

After sending, your balance will be updated automatically.

🔗 <b>Address:</b> <code>{address}</code>
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ I Have Sent", callback_data=f'confirm_sent_{transaction_id}')],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        send_safe_message(
            context,
            update.effective_chat.id,
            instructions,
            reply_markup=reply_markup
        )
        
        # Notify admin
        admin_chat_id = get_setting('admin_chat_id')
        if admin_chat_id:
            admin_text = f"""
🆕 <b>New Deposit Request</b>

👤 User: {update.effective_user.first_name} (@{update.effective_user.username})
💰 Amount: ${amount:.2f} USD
💱 Currency: {currency} ({network})
📋 TX ID: #{transaction_id}
            """
            send_safe_message(context, admin_chat_id, admin_text)
        
        # Clear the state
        context.user_data.pop('deposit_currency', None)
        context.user_data.pop('deposit_network', None)
        return ConversationHandler.END
    
    except ValueError:
        update.message.reply_text("❌ Please enter a valid number.")
        return DEPOSIT_AMOUNT
    except Exception as e:
        logger.error(f"Error processing deposit amount: {str(e)}")
        update.message.reply_text("❌ An error occurred while processing your deposit. Please try again.")
        return ConversationHandler.END

# Message handler for withdrawal amount
def handle_withdrawal_amount(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        amount = float(text)
        user = get_user(user_id)
        withdrawal_fee = context.user_data.get('withdrawal_fee', 0.5)
        min_withdrawal = float(get_setting('min_withdrawal') or '5')
        
        if amount < min_withdrawal:
            update.message.reply_text(f"❌ Minimum withdrawal amount is ${min_withdrawal:.2f}")
            return WITHDRAW_AMOUNT
        
        total_amount = amount + withdrawal_fee
        
        if total_amount > user['balance']:
            update.message.reply_text(f"❌ Insufficient balance. Withdrawal amount + fee (${withdrawal_fee:.2f}) = ${total_amount:.2f}")
            return WITHDRAW_AMOUNT
        
        context.user_data['withdrawal_amount'] = amount
        context.user_data['withdrawal_total'] = total_amount
        
        update.message.reply_text(
            f"💳 <b>Withdrawal: ${amount:.2f}</b>\n\n"
            f"• Amount: ${amount:.2f}\n"
            f"• Fee: ${withdrawal_fee:.2f}\n"
            f"• Total: ${total_amount:.2f}\n\n"
            "Please enter your cryptocurrency wallet address:",
            parse_mode=ParseMode.HTML
        )
        return WITHDRAW_ADDRESS
    
    except ValueError:
        update.message.reply_text("❌ Please enter a valid number.")
        return WITHDRAW_AMOUNT
    except Exception as e:
        logger.error(f"Error processing withdrawal amount: {str(e)}")
        update.message.reply_text("❌ An error occurred while processing your withdrawal. Please try again.")
        return ConversationHandler.END

# Message handler for withdrawal address
def handle_withdrawal_address(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    address = update.message.text.strip()
    amount = context.user_data.get('withdrawal_amount')
    total_amount = context.user_data.get('withdrawal_total')
    
    if not amount or not total_amount:
        update.message.reply_text("❌ Error: Please start over with /withdraw")
        return ConversationHandler.END
    
    # Basic address validation
    if len(address) < 10:
        update.message.reply_text("❌ Please enter a valid wallet address.")
        return WITHDRAW_ADDRESS
    
    try:
        # Add withdrawal transaction
        transaction_id = add_transaction(
            user_id=user_id,
            transaction_type='withdrawal',
            amount=amount,
            currency='USD',
            address=address,
            status='pending'
        )
        
        # Update balance
        update_balance(user_id, -total_amount)
        
        withdrawal_text = f"""
✅ <b>Withdrawal Request Submitted</b>

• <b>Amount:</b> ${amount:.2f}
• <b>Fee:</b> ${context.user_data.get('withdrawal_fee', 0.5):.2f}
• <b>Total Deducted:</b> ${total_amount:.2f}
• <b>Address:</b> <code>{address}</code>
• <b>Status:</b> Pending
• <b>Transaction ID:</b> #{transaction_id}

Your withdrawal has been processed and the funds have been deducted from your balance. 
The transaction will be completed shortly.

We'll notify you once it's sent.
        """
        
        send_safe_message(
            context,
            update.effective_chat.id,
            withdrawal_text
        )
        
        # Notify admin
        admin_chat_id = get_setting('admin_chat_id')
        if admin_chat_id:
            admin_text = f"""
🆕 <b>New Withdrawal Request</b>

👤 User: {update.effective_user.first_name} (@{update.effective_user.username})
💰 Amount: ${amount:.2f} USD
💸 Fee: ${context.user_data.get('withdrawal_fee', 0.5):.2f} USD
🏦 Total: ${total_amount:.2f} USD
🔗 Address: <code>{address}</code>
📋 TX ID: #{transaction_id}
            """
            send_safe_message(context, admin_chat_id, admin_text)
        
        # Clear withdrawal data
        context.user_data.pop('withdrawal_amount', None)
        context.user_data.pop('withdrawal_total', None)
        context.user_data.pop('withdrawal_fee', None)
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Error processing withdrawal address: {str(e)}")
        update.message.reply_text("❌ An error occurred while processing your withdrawal. Please try again.")
        return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

# Error handler
def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_chat:
        send_safe_message(
            context,
            update.effective_chat.id,
            "❌ An unexpected error occurred. Please try again later."
        )

# Background task for checking transactions (simplified)
def check_pending_transactions(context: CallbackContext):
    try:
        pending_txs = get_pending_transactions()
        for tx in pending_txs:
            # In a real implementation, you would check blockchain for confirmations
            # This is a simplified version
            if tx['type'] == 'deposit':
                # Simulate deposit confirmation after 1 minute
                created_time = datetime.strptime(tx['created_at'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() - created_time > timedelta(minutes=1):
                    update_transaction_status(tx['id'], 'completed')
                    update_balance(tx['user_id'], tx['amount'])
                    
                    # Notify user
                    user = get_user(tx['user_id'])
                    if user:
                        notification_text = f"""
✅ <b>Deposit Confirmed</b>

Your deposit of ${tx['amount']:.2f} has been confirmed and added to your balance.

💰 <b>New Balance:</b> ${user['balance']:.2f} USD
                        """
                        send_safe_message(context, tx['user_id'], notification_text)
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}")

# Flask routes for webhook
@app.route('/')
def index():
    return "Crypto Payment Bot is running!"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(), updater.bot)
    dispatcher.process_update(update)
    return 'OK'

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# Initialize bot
def main():
    global updater, dispatcher
    
    # Create Updater and Dispatcher
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # Conversation handler for deposit
    deposit_conv = ConversationHandler(
        entry_points=[CommandHandler('deposit', deposit)],
        states={
            DEPOSIT_AMOUNT: [
                CallbackQueryHandler(button_handler, pattern='^deposit_'),
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_deposit_amount)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')]
    )
    
    # Conversation handler for withdrawal
    withdrawal_conv = ConversationHandler(
        entry_points=[CommandHandler('withdraw', withdraw)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_withdrawal_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_withdrawal_address)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("balance", balance))
    dispatcher.add_handler(deposit_conv)
    dispatcher.add_handler(withdrawal_conv)
    dispatcher.add_handler(CommandHandler("history", history))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CommandHandler("help", help_command))
    
    dispatcher.add_handler(CallbackQueryHandler(button_handler, pattern='^(deposit_|confirm_sent_|cancel)'))
    
    dispatcher.add_error_handler(error_handler)
    
    # Add background job for checking transactions
    job_queue = updater.job_queue
    job_queue.run_repeating(check_pending_transactions, interval=60, first=10)
    
    # Set webhook on Render
    try:
        updater.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info(f"Webhook set to: {WEBHOOK_URL}/{BOT_TOKEN}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {str(e)}")
    
    logger.info("Bot started with webhook")
    
    # Start Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()
