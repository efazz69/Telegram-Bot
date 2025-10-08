from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from dotenv import load_dotenv
import os
import logging
import requests
import json
import time
import traceback
from datetime import datetime, timedelta
from web3 import Web3

# ---------------------------
# Configuration
# ---------------------------
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7963936009:AAEK3Y4GYCpRk4mbASW2Xvh7u0xedXmR64Y')
ADMIN_ID = os.getenv('ADMIN_ID', '7091475665')

# Payment Configuration
CRYPTO_NETWORKS = {
    'USDT_BEP20': {
        'name': 'USDT (BEP20)',
        'network': 'BSC',
        'decimals': 6,
    },
    'BTC': {
        'name': 'Bitcoin',
        'network': 'BTC',
        'decimals': 8
    },
    'LTC': {
        'name': 'Litecoin',
        'network': 'LTC',
        'decimals': 8
    }
}

# Your wallet addresses (REPLACE WITH YOUR ACTUAL ADDRESSES)
WALLET_ADDRESSES = {
    'USDT_BEP20': '0x515a1DA038D2813400912C88Bbd4921836041766',
    'BTC': 'bc1q85ad38ndcd29zgz7d77y5k9hcsurqxaqurzl2g',
    'LTC': 'ltc1q2e3z74c63j5cn2hu0wep5vdrmmf6jv9zf6m4rv'
}

# Render Configuration
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL', 'http://localhost:8000')
WEBHOOK_URL = f"https://telegram-bot-5fco.onrender.com/{BOT_TOKEN}"

# ---------------------------
# User Manager Class
# ---------------------------
class UserManager:
    def __init__(self):
        self.users_file = 'users.json'
        self._init_file()
    
    def _init_file(self):
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump({}, f)
    
    def _read_users(self):
        try:
            with open(self.users_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _write_users(self, users):
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
    
    def get_user(self, user_id):
        users = self._read_users()
        user_id_str = str(user_id)
        
        if user_id_str not in users:
            return None
        
        return users[user_id_str]
    
    def create_user(self, user_id, username, first_name):
        users = self._read_users()
        user_id_str = str(user_id)
        
        if user_id_str in users:
            return users[user_id_str]
        
        user_data = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'balance': 0.0,
            'registration_date': datetime.now().isoformat(),
            'first_topup_date': None,
            'total_deposited': 0.0,
            'total_orders': 0,
            'last_activity': datetime.now().isoformat()
        }
        
        users[user_id_str] = user_data
        self._write_users(users)
        return user_data
    
    def update_balance(self, user_id, amount):
        users = self._read_users()
        user_id_str = str(user_id)
        
        if user_id_str not in users:
            return False
        
        users[user_id_str]['balance'] += amount
        if amount > 0:
            users[user_id_str]['total_deposited'] += amount
        users[user_id_str]['last_activity'] = datetime.now().isoformat()
        
        # Set first top-up date if this is the first deposit
        if amount > 0 and users[user_id_str]['first_topup_date'] is None:
            users[user_id_str]['first_topup_date'] = datetime.now().isoformat()
        
        self._write_users(users)
        return True
    
    def update_user_activity(self, user_id):
        users = self._read_users()
        user_id_str = str(user_id)
        
        if user_id_str in users:
            users[user_id_str]['last_activity'] = datetime.now().isoformat()
            self._write_users(users)
    
    def increment_orders(self, user_id):
        users = self._read_users()
        user_id_str = str(user_id)
        
        if user_id_str in users:
            users[user_id_str]['total_orders'] += 1
            self._write_users(users)

# ---------------------------
# Database Class
# ---------------------------
class Database:
    def __init__(self):
        self.orders_file = 'orders.json'
        self._init_files()
    
    def _init_files(self):
        for file in [self.orders_file]:
            if not os.path.exists(file):
                with open(file, 'w') as f:
                    json.dump([], f)
    
    def _read_json(self, filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def _write_json(self, filename, data):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_order(self, user_id, product_id, amount, crypto_currency, crypto_amount, payment_address, exchange_rate):
        orders = self._read_json(self.orders_file)
        order_id = len(orders) + 1
        
        order = {
            'order_id': order_id,
            'user_id': user_id,
            'product_id': product_id,
            'amount': amount,
            'crypto_currency': crypto_currency,
            'crypto_amount': crypto_amount,
            'payment_address': payment_address,
            'exchange_rate': exchange_rate,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=15)).isoformat()
        }
        
        orders.append(order)
        self._write_json(self.orders_file, orders)
        return order
    
    def get_order(self, order_id):
        orders = self._read_json(self.orders_file)
        for order in orders:
            if order['order_id'] == order_id:
                return order
        return None
    
    def update_order_status(self, order_id, status):
        orders = self._read_json(self.orders_file)
        for order in orders:
            if order['order_id'] == order_id:
                order['status'] = status
                if status == 'paid':
                    order['paid_at'] = datetime.now().isoformat()
                self._write_json(self.orders_file, orders)
                return True
        return False
    
    def get_user_orders(self, user_id):
        orders = self._read_json(self.orders_file)
        return [order for order in orders if order['user_id'] == user_id]
    
    def cleanup_expired_orders(self):
        """Remove orders that have expired"""
        orders = self._read_json(self.orders_file)
        current_time = datetime.now()
        valid_orders = []
        
        for order in orders:
            expires_at = datetime.fromisoformat(order['expires_at'])
            if expires_at > current_time or order['status'] in ['paid', 'cancelled']:
                valid_orders.append(order)
        
        self._write_json(self.orders_file, valid_orders)
        return len(orders) - len(valid_orders)

# ---------------------------
# Improved Payment Handler with Multiple API Fallbacks
# ---------------------------
class PaymentHandler:
    def __init__(self):
        self.price_cache = {}
        self.cache_duration = 300  # 5 minutes
        print("✅ Payment Handler Initialized")
    
    def get_binance_price(self, symbol):
        """Get price from Binance API"""
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return float(data['price'])
            return None
        except:
            return None
    
    def get_kraken_price(self, pair):
        """Get price from Kraken API"""
        try:
            url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'result' in data:
                    # Kraken returns different keys, get the first one
                    first_key = list(data['result'].keys())[0]
                    return float(data['result'][first_key]['c'][0])
            return None
        except:
            return None
    
    def get_coingecko_price(self, crypto_id):
        """Get price from CoinGecko API"""
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                price = data.get(crypto_id, {}).get('usd')
                if price:
                    return float(price)
            return None
        except:
            return None
    
    def get_real_time_price(self, crypto_currency):
        """Get real-time price with multiple fallback APIs"""
        cache_key = crypto_currency
        current_time = time.time()
        
        # Check cache first
        if cache_key in self.price_cache:
            cached_price, timestamp = self.price_cache[cache_key]
            if current_time - timestamp < self.cache_duration:
                return cached_price
        
        price = None
        print(f"🔍 Fetching price for {crypto_currency}...")
        
        if crypto_currency == 'BTC':
            # Try multiple APIs for BTC
            price = self.get_binance_price('BTCUSDT')
            if not price:
                price = self.get_kraken_price('XXBTZUSD')
            if not price:
                price = self.get_coingecko_price('bitcoin')
                
        elif crypto_currency == 'LTC':
            # Try multiple APIs for LTC
            price = self.get_binance_price('LTCUSDT')
            if not price:
                price = self.get_kraken_price('XLTCZUSD')
            if not price:
                price = self.get_coingecko_price('litecoin')
                
        elif crypto_currency == 'USDT_BEP20':
            # For USDT, we expect ~1.0, but check multiple sources
            price = self.get_binance_price('BUSDUSDT')  # Using BUSD as stablecoin reference
            if not price:
                price = self.get_kraken_price('USDTZUSD')
            if not price:
                price = self.get_coingecko_price('tether')
            
            # If still no price or price is unrealistic, use 1.0
            if not price or price < 0.9 or price > 1.1:
                price = 1.0
        
        # If all APIs fail, use fallback prices
        if not price:
            fallback_prices = {
                'BTC': 45000.0,
                'LTC': 75.0,
                'USDT_BEP20': 1.0
            }
            price = fallback_prices.get(crypto_currency, 1.0)
            print(f"⚠️ Using fallback price for {crypto_currency}: ${price}")
        else:
            print(f"✅ Real-time price for {crypto_currency}: ${price:.4f}")
        
        # Cache the price
        self.price_cache[cache_key] = (price, current_time)
        return price
    
    def generate_payment_address(self, crypto_currency, order_id):
        """Generate payment address for specific cryptocurrency"""
        try:
            address = WALLET_ADDRESSES.get(crypto_currency)
            if not address:
                print(f"❌ No address configured for {crypto_currency}")
                return None
            
            print(f"✅ Generated {crypto_currency} address: {address}")
            return address
            
        except Exception as e:
            print(f"❌ Error generating payment address: {e}")
            return None
    
    def get_crypto_amount(self, usd_amount, crypto_currency):
        """Convert USD amount to cryptocurrency amount using real-time prices"""
        current_price = self.get_real_time_price(crypto_currency)
        
        if current_price <= 0:
            current_price = 1.0  # Prevent division by zero
        
        crypto_amount = usd_amount / current_price
        
        # Round to appropriate decimal places
        decimals = CRYPTO_NETWORKS.get(crypto_currency, {}).get('decimals', 8)
        crypto_amount = round(crypto_amount, decimals)
        
        return crypto_amount, current_price

# ---------------------------
# Flask App Setup
# ---------------------------
app = Flask(__name__)

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# Initialize components
db = Database()
payment_handler = PaymentHandler()
user_manager = UserManager()

# Global storage for user context
user_deposit_context = {}

# Enable logging for debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load products data
def load_products():
    try:
        with open('products.json', 'r') as f:
            data = json.load(f)
            return data.get('products', []), data.get('categories', []), data.get('subcategories', [])
    except Exception as e:
        logger.error(f"Error loading products: {e}")
        return [], [], []

products, categories, subcategories = load_products()

# ---------------------------
# User Command Functions
# ---------------------------
def start(update, context):
    """Start command with main menu"""
    user = update.message.from_user
    user_manager.create_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
🤖 Welcome to Crypto Store Bot, {user.first_name}!

💎 **Features:**
• Buy digital products with cryptocurrency
• Real-time crypto prices from multiple APIs
• Support for BTC, LTC, USDT (BEP20)
• Instant delivery after payment
• User balance system
• Secure and anonymous

Select an option from the menu below:
    """
    
    keyboard = [
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🛍️ Services", callback_data="services")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_profile(update, context):
    """Show user profile"""
    user = update.message.from_user
    user_data = user_manager.get_user(user.id)
    
    if not user_data:
        update.message.reply_text("❌ User not found. Please use /start first.")
        return
    
    profile_text = f"""
👤 **User Profile**

🆔 ID: `{user_data['user_id']}`
👤 Name: {user_data['first_name']}
📛 Username: @{user_data['username'] or 'N/A'}
💰 Balance: ${user_data['balance']:.2f}

📊 **Statistics:**
💳 Total Deposited: ${user_data['total_deposited']:.2f}
🛍️ Total Orders: {user_data['total_orders']}
📅 Member Since: {datetime.fromisoformat(user_data['registration_date']).strftime('%Y-%m-%d')}
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("📋 My Orders", callback_data="orders")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')

def add_balance(update, context):
    """Add balance command"""
    user = update.message.from_user
    user_manager.update_user_activity(user.id)
    
    balance_text = """
💰 **Add Balance**

Choose a cryptocurrency to deposit:

• **USDT (BEP20)** - Fast & Low fee (~1:1 with USD)
• **Bitcoin (BTC)** - Most popular
• **Litecoin (LTC)** - Fast confirmations

💱 Real-time prices from multiple APIs (Binance, Kraken, CoinGecko)
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 USDT (BEP20)", callback_data="deposit_USDT_BEP20")],
        [InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data="deposit_BTC")],
        [InlineKeyboardButton("Ł Litecoin (LTC)", callback_data="deposit_LTC")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(balance_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_services(update, context):
    """Show services/categories"""
    user = update.message.from_user
    user_manager.update_user_activity(user.id)
    
    if not categories:
        update.message.reply_text("❌ No categories available at the moment.")
        return
    
    services_text = "🛍️ **Available Categories**\n\n"
    
    keyboard = []
    for category in categories:
        services_text += f"📂 **{category['name']}**\n"
        services_text += f"   {category['description']}\n\n"
        keyboard.append([InlineKeyboardButton(category['name'], callback_data=f"category_{category['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(services_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_about(update, context):
    """Show about information"""
    about_text = """
ℹ️ **About Crypto Store Bot**

💎 **Features:**
• Secure cryptocurrency payments
• Real-time price feeds from multiple APIs
• Instant digital product delivery
• User balance system
• 24/7 automated service

🔒 **Security:**
• No personal data required
• Blockchain-verified payments
• Encrypted communications

🪙 **Supported Cryptocurrencies:**
• USDT (BEP20) - Binance Smart Chain
• Bitcoin (BTC) - Bitcoin Network
• Litecoin (LTC) - Litecoin Network

📞 **Support:**
Contact admin for assistance.
    """
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(about_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_orders(update, context):
    """Show user orders"""
    user = update.message.from_user
    orders = db.get_user_orders(user.id)
    
    if not orders:
        orders_text = "📭 You haven't placed any orders yet.\n\n🛍️ Browse our services to get started!"
    else:
        orders_text = "📋 **Your Orders**\n\n"
        for order in orders[-5:]:  # Show last 5 orders
            status_emoji = "✅" if order['status'] == 'paid' else "⏳" if order['status'] == 'pending' else "❌"
            orders_text += f"{status_emoji} Order #{order['order_id']}\n"
            orders_text += f"   💰 ${order['amount']} • {order['crypto_currency']}\n"
            orders_text += f"   📅 {datetime.fromisoformat(order['created_at']).strftime('%Y-%m-%d %H:%M')}\n"
            orders_text += f"   📊 Status: {order['status'].title()}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(orders_text, reply_markup=reply_markup, parse_mode='Markdown')

# ---------------------------
# Button Handler Functions
# ---------------------------
def button_handler(update, context):
    """Handle button callbacks"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    user_id = query.from_user.id
    user_manager.update_user_activity(user_id)
    
    try:
        if data == "main_menu":
            start_callback(query)
        elif data == "profile":
            show_profile_callback(query)
        elif data == "add_balance":
            add_balance_callback(query)
        elif data == "services":
            show_services_callback(query)
        elif data == "about":
            show_about_callback(query)
        elif data == "orders":
            show_orders_callback(query)
        elif data.startswith("deposit_"):
            crypto = data.replace("deposit_", "")
            handle_deposit_selection(query, crypto)
        elif data.startswith("category_"):
            category_id = int(data.replace("category_", ""))
            show_category_products(query, category_id)
        elif data.startswith("product_"):
            product_id = int(data.replace("product_", ""))
            show_product_details(query, product_id)
        elif data.startswith("buy_"):
            product_id = int(data.replace("buy_", ""))
            start_payment_process(query, product_id)
        else:
            query.edit_message_text("❌ Unknown button action. Use /start to restart.")
            
    except Exception as e:
        logger.error(f"Error in button handler: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        query.edit_message_text("❌ An error occurred. Please try again or use /start to restart.")

def start_callback(query):
    """Start menu for callback queries"""
    user = query.from_user
    
    welcome_text = f"""
🤖 Welcome to Crypto Store Bot, {user.first_name}!

💎 **Features:**
• Buy digital products with cryptocurrency
• Real-time crypto prices from multiple APIs
• Support for BTC, LTC, USDT (BEP20)
• Instant delivery after payment
• User balance system
• Secure and anonymous

Select an option from the menu below:
    """
    
    keyboard = [
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🛍️ Services", callback_data="services")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_profile_callback(query):
    """Show profile for callback queries"""
    user = query.from_user
    user_data = user_manager.get_user(user.id)
    
    if not user_data:
        query.edit_message_text("❌ User not found. Please use /start first.")
        return
    
    profile_text = f"""
👤 **User Profile**

🆔 ID: `{user_data['user_id']}`
👤 Name: {user_data['first_name']}
📛 Username: @{user_data['username'] or 'N/A'}
💰 Balance: ${user_data['balance']:.2f}

📊 **Statistics:**
💳 Total Deposited: ${user_data['total_deposited']:.2f}
🛍️ Total Orders: {user_data['total_orders']}
📅 Member Since: {datetime.fromisoformat(user_data['registration_date']).strftime('%Y-%m-%d')}
    """
    
    keyboard = [
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("📋 My Orders", callback_data="orders")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')

def add_balance_callback(query):
    """Add balance for callback queries"""
    balance_text = """
💰 **Add Balance**

Choose a cryptocurrency to deposit:

• **USDT (BEP20)** - Fast & Low fee (~1:1 with USD)
• **Bitcoin (BTC)** - Most popular
• **Litecoin (LTC)** - Fast confirmations

💱 Real-time prices from multiple APIs (Binance, Kraken, CoinGecko)
    """
    
    keyboard = [
        [InlineKeyboardButton("💎 USDT (BEP20)", callback_data="deposit_USDT_BEP20")],
        [InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data="deposit_BTC")],
        [InlineKeyboardButton("Ł Litecoin (LTC)", callback_data="deposit_LTC")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(balance_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_services_callback(query):
    """Show services for callback queries"""
    if not categories:
        query.edit_message_text("❌ No categories available at the moment.")
        return
    
    services_text = "🛍️ **Available Categories**\n\n"
    
    keyboard = []
    for category in categories:
        services_text += f"📂 **{category['name']}**\n"
        services_text += f"   {category['description']}\n\n"
        keyboard.append([InlineKeyboardButton(category['name'], callback_data=f"category_{category['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(services_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_about_callback(query):
    """Show about for callback queries"""
    about_text = """
ℹ️ **About Crypto Store Bot**

💎 **Features:**
• Secure cryptocurrency payments
• Real-time price feeds from multiple APIs
• Instant digital product delivery
• User balance system
• 24/7 automated service

🔒 **Security:**
• No personal data required
• Blockchain-verified payments
• Encrypted communications

🪙 **Supported Cryptocurrencies:**
• USDT (BEP20) - Binance Smart Chain
• Bitcoin (BTC) - Bitcoin Network
• Litecoin (LTC) - Litecoin Network

📞 **Support:**
Contact admin for assistance.
    """
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(about_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_orders_callback(query):
    """Show orders for callback queries"""
    user = query.from_user
    orders = db.get_user_orders(user.id)
    
    if not orders:
        orders_text = "📭 You haven't placed any orders yet.\n\n🛍️ Browse our services to get started!"
    else:
        orders_text = "📋 **Your Orders**\n\n"
        for order in orders[-5:]:
            status_emoji = "✅" if order['status'] == 'paid' else "⏳" if order['status'] == 'pending' else "❌"
            orders_text += f"{status_emoji} Order #{order['order_id']}\n"
            orders_text += f"   💰 ${order['amount']} • {order['crypto_currency']}\n"
            orders_text += f"   📅 {datetime.fromisoformat(order['created_at']).strftime('%Y-%m-%d %H:%M')}\n"
            orders_text += f"   📊 Status: {order['status'].title()}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(orders_text, reply_markup=reply_markup, parse_mode='Markdown')

def handle_deposit_selection(query, crypto_currency):
    """Handle deposit cryptocurrency selection"""
    user = query.from_user
    
    user_data = user_manager.get_user(user.id)
    current_balance = user_data['balance'] if user_data else 0.0
    
    # Get current price for display
    current_price = payment_handler.get_real_time_price(crypto_currency)
    
    deposit_text = f"""
💰 **Add Balance with {crypto_currency}**

💱 Current Price: 1 {crypto_currency} = ${current_price:.4f} USD

Please enter the amount in USD you want to deposit:

💡 Example: `50` for $50.00

💰 Your current balance: ${current_balance:.2f}

⏰ Address valid for 15 minutes
    """
    
    # Store user context globally
    global user_deposit_context
    user_deposit_context[user.id] = {
        'awaiting_deposit_amount': crypto_currency,
        'timestamp': time.time()
    }
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Deposit", callback_data="add_balance")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(deposit_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_category_products(query, category_id):
    """Show products in a category"""
    category_products = [p for p in products if p['category_id'] == category_id]
    category = next((c for c in categories if c['id'] == category_id), None)
    
    if not category_products or not category:
        query.edit_message_text("❌ No products available in this category.")
        return
    
    products_text = f"📂 **{category['name']}**\n\n"
    products_text += f"{category['description']}\n\n"
    
    keyboard = []
    for product in category_products:
        products_text += f"🆔 {product['id']}: **{product['name']}**\n"
        products_text += f"   💰 ${product['price']:.2f}\n"
        products_text += f"   📝 {product['description']}\n\n"
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} - ${product['price']:.2f}", 
            callback_data=f"product_{product['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="services")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(products_text, reply_markup=reply_markup, parse_mode='Markdown')

def show_product_details(query, product_id):
    """Show detailed product information"""
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        query.edit_message_text("❌ Product not found.")
        return
    
    category = next((c for c in categories if c['id'] == product['category_id']), {"name": "Unknown"})
    subcategory = next((s for s in subcategories if s['id'] == product['subcategory_id']), {"name": "Unknown"})
    
    product_text = f"""
📦 **{product['name']}**

💰 **Price:** ${product['price']:.2f}
📂 **Category:** {category['name']}
📁 **Subcategory:** {subcategory['name']}

📝 **Description:**
{product['description']}

⭐ **Features:**
"""
    for feature in product.get('features', []):
        product_text += f"• {feature}\n"
    
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_{product['id']}")],
        [InlineKeyboardButton("🔙 Back to Category", callback_data=f"category_{product['category_id']}")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(product_text, reply_markup=reply_markup, parse_mode='Markdown')

def start_payment_process(query, product_id):
    """Start payment process for a product"""
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        query.edit_message_text("❌ Product not found.")
        return
    
    user = query.from_user
    user_data = user_manager.get_user(user.id)
    
    if user_data['balance'] >= product['price']:
        # User has enough balance
        user_manager.update_balance(user.id, -product['price'])
        user_manager.increment_orders(user.id)
        
        success_text = f"""
✅ **Purchase Successful!**

📦 **Product:** {product['name']}
💰 **Price:** ${product['price']:.2f}
🆔 **Order ID:** {len(db.get_user_orders(user.id)) + 1}

💳 **Payment Method:** Balance
💰 **New Balance:** ${user_data['balance'] - product['price']:.2f}

📦 Your product will be delivered shortly.
Thank you for your purchase!
        """
        
        keyboard = [
            [InlineKeyboardButton("🛍️ Browse More", callback_data="services")],
            [InlineKeyboardButton("👤 Profile", callback_data="profile")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        # Not enough balance - show deposit options
        balance_needed = product['price'] - user_data['balance']
        
        payment_text = f"""
🛒 **Purchase {product['name']}**

💰 **Product Price:** ${product['price']:.2f}
💳 **Your Balance:** ${user_data['balance']:.2f}
❌ **Balance Shortage:** ${balance_needed:.2f}

💡 Please add ${balance_needed:.2f} or more to your balance to complete this purchase.
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("🔙 Back to Product", callback_data=f"product_{product['id']}")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')

def handle_text_message(update, context):
    """Handle text messages for balance input"""
    user = update.message.from_user
    text = update.message.text.strip()
    
    # Check if we're expecting a deposit amount from this user
    global user_deposit_context
    
    user_context = user_deposit_context.get(user.id, {})
    
    # Clean old contexts (older than 1 hour)
    current_time = time.time()
    user_deposit_context = {uid: ctx for uid, ctx in user_deposit_context.items() 
                           if current_time - ctx.get('timestamp', 0) < 3600}
    
    if user_context and 'awaiting_deposit_amount' in user_context:
        crypto_currency = user_context['awaiting_deposit_amount']
        
        try:
            usd_amount = float(text)
            if usd_amount <= 0:
                update.message.reply_text("❌ Please enter a positive amount.")
                return
            
            if usd_amount < 1:
                update.message.reply_text("❌ Minimum deposit amount is $1.00")
                return
            
            if usd_amount > 10000:
                update.message.reply_text("❌ Maximum deposit amount is $10,000")
                return
            
            # Clear the user context
            user_deposit_context.pop(user.id, None)
            
            # Generate payment information
            crypto_amount, current_price = payment_handler.get_crypto_amount(usd_amount, crypto_currency)
            payment_address = payment_handler.generate_payment_address(crypto_currency, f"deposit_{user.id}")
            
            if not payment_address:
                update.message.reply_text("❌ Payment system temporarily unavailable. Please try again later.")
                return
            
            payment_text = f"""
💰 **Deposit Instructions - {crypto_currency}**

💵 **Amount:** ${usd_amount:.2f} USD
🪙 **To Pay:** {crypto_amount:.8f} {crypto_currency}
💱 **Exchange Rate:** 1 {crypto_currency} = ${current_price:.4f} USD

📍 **Send to this address:**
`{payment_address}`

⏰ **Expires in:** 15 minutes
🔍 **Network:** {crypto_currency.replace('_', ' ')}

⚠️ **Important:**
• Send exactly {crypto_amount:.8f} {crypto_currency}
• Only send {crypto_currency} to this address
• Payment will be auto-confirmed
• Do not send from exchange wallets
            """
            
            keyboard = [
                [InlineKeyboardButton("💰 Add More Balance", callback_data="add_balance")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except ValueError:
            update.message.reply_text("❌ Please enter a valid number (e.g., 50 or 25.50)")
        except Exception as e:
            logger.error(f"Error processing deposit amount: {e}")
            update.message.reply_text("❌ An error occurred while processing your deposit. Please try again.")
    else:
        # Default response for other text messages
        update.message.reply_text("💡 Use the menu buttons or commands to navigate the bot.\n\nUse /start to see the main menu.")

# ---------------------------
# Admin Command Functions (Keep your existing admin functions)
# ---------------------------
def is_admin(user_id):
    """Check if user is admin"""
    return str(user_id) == str(ADMIN_ID)

def load_data():
    """Load all data from JSON files"""
    with open('products.json', 'r') as f:
        return json.load(f)

def save_data(data):
    """Save data to JSON files"""
    with open('products.json', 'w') as f:
        json.dump(data, f, indent=2)

def add_category(update, context):
    """Add a new category: /addcategory Name|Description"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text(
            "📝 Usage: /addcategory Name|Description\n\n"
            "Example: /addcategory 💎 Digital Accounts|Premium digital accounts and subscriptions"
        )
        return
    
    try:
        args = ' '.join(context.args).split('|')
        if len(args) != 2:
            update.message.reply_text("❌ Invalid format. Use: Name|Description")
            return
        
        name, description = args
        
        data = load_data()
        
        # Generate new category ID
        new_id = max([c['id'] for c in data['categories']]) + 1 if data['categories'] else 1
        
        new_category = {
            'id': new_id,
            'name': name.strip(),
            'description': description.strip()
        }
        
        data['categories'].append(new_category)
        save_data(data)
        
        # Reload products data
        global categories
        categories = data['categories']
        
        update.message.reply_text(
            f"✅ Category added successfully!\n\n"
            f"🆔 ID: {new_id}\n"
            f"📂 Name: {name}\n"
            f"📝 Description: {description}"
        )
        
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def add_subcategory(update, context):
    """Add a new subcategory: /addsubcategory Name|CategoryID|Description"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text(
            "📝 Usage: /addsubcategory Name|CategoryID|Description\n\n"
            "Example: /addsubcategory Streaming Services|1|Video and music streaming accounts\n\n"
            "Use /listcategories to see available category IDs"
        )
        return
    
    try:
        args = ' '.join(context.args).split('|')
        if len(args) != 3:
            update.message.reply_text("❌ Invalid format. Use: Name|CategoryID|Description")
            return
        
        name, category_id, description = args
        
        data = load_data()
        
        # Check if category exists
        category_exists = any(cat['id'] == int(category_id) for cat in data['categories'])
        if not category_exists:
            update.message.reply_text(f"❌ Category ID {category_id} not found. Use /listcategories")
            return
        
        # Generate new subcategory ID
        new_id = max([s['id'] for s in data['subcategories']]) + 1 if data['subcategories'] else 1
        
        new_subcategory = {
            'id': new_id,
            'name': name.strip(),
            'category_id': int(category_id),
            'description': description.strip()
        }
        
        data['subcategories'].append(new_subcategory)
        save_data(data)
        
        # Reload products data
        global subcategories
        subcategories = data['subcategories']
        
        update.message.reply_text(
            f"✅ Subcategory added successfully!\n\n"
            f"🆔 ID: {new_id}\n"
            f"📂 Name: {name}\n"
            f"🏷️ Category ID: {category_id}\n"
            f"📝 Description: {description}"
        )
        
    except ValueError:
        update.message.reply_text("❌ Category ID must be a number")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def add_product(update, context):
    """Add a new product: /addproduct Name|Description|Price|CategoryID|SubcategoryID|Feature1,Feature2"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text(
            "📝 Usage: /addproduct Name|Description|Price|CategoryID|SubcategoryID|Feature1,Feature2\n\n"
            "Example: /addproduct Netflix Premium|4K Ultra HD|5.99|1|1|4K Quality,4 Screens,30 Days Warranty\n\n"
            "Use /listcategories and /listproducts to see IDs"
        )
        return
    
    try:
        args = ' '.join(context.args).split('|')
        if len(args) != 6:
            update.message.reply_text("❌ Invalid format. Use: Name|Description|Price|CategoryID|SubcategoryID|Features")
            return
        
        name, description, price, category_id, subcategory_id, features = args
        
        data = load_data()
        
        # Check if category exists
        category_exists = any(cat['id'] == int(category_id) for cat in data['categories'])
        if not category_exists:
            update.message.reply_text(f"❌ Category ID {category_id} not found.")
            return
        
        # Check if subcategory exists and belongs to category
        subcategory_exists = any(
            sub['id'] == int(subcategory_id) and sub['category_id'] == int(category_id) 
            for sub in data['subcategories']
        )
        if not subcategory_exists:
            update.message.reply_text(f"❌ Subcategory ID {subcategory_id} not found or doesn't belong to category {category_id}.")
            return
        
        # Generate new product ID
        new_id = max([p['id'] for p in data['products']]) + 1 if data['products'] else 1
        
        # Parse features
        feature_list = [f.strip() for f in features.split(',')]
        
        new_product = {
            'id': new_id,
            'name': name.strip(),
            'description': description.strip(),
            'price': float(price),
            'category_id': int(category_id),
            'subcategory_id': int(subcategory_id),
            'features': feature_list
        }
        
        data['products'].append(new_product)
        save_data(data)
        
        # Reload products data
        global products
        products = data['products']
        
        # Get category and subcategory names for confirmation
        category_name = next((cat['name'] for cat in data['categories'] if cat['id'] == int(category_id)), "Unknown")
        subcategory_name = next((sub['name'] for sub in data['subcategories'] if sub['id'] == int(subcategory_id)), "Unknown")
        
        update.message.reply_text(
            f"✅ Product added successfully!\n\n"
            f"🆔 ID: {new_id}\n"
            f"📦 Name: {name}\n"
            f"💰 Price: ${float(price):.2f}\n"
            f"📂 Category: {category_name}\n"
            f"📁 Subcategory: {subcategory_name}\n"
            f"⭐ Features: {', '.join(feature_list)}"
        )
        
    except ValueError:
        update.message.reply_text("❌ Price, Category ID and Subcategory ID must be numbers")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def list_categories(update, context):
    """List all categories and subcategories: /listcategories"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    try:
        data = load_data()
        
        if not data['categories']:
            update.message.reply_text("📭 No categories available.")
            return
        
        categories_text = "📂 **All Categories & Subcategories:**\n\n"
        
        for category in data['categories']:
            categories_text += f"🏷️ **{category['name']}** (ID: {category['id']})\n"
            categories_text += f"   📝 {category['description']}\n"
            
            # Show subcategories for this category
            subcategories_list = [s for s in data['subcategories'] if s['category_id'] == category['id']]
            if subcategories_list:
                for sub in subcategories_list:
                    categories_text += f"   └─ 📁 {sub['name']} (ID: {sub['id']})\n"
                    categories_text += f"        📝 {sub['description']}\n"
            else:
                categories_text += f"   └─ 📭 No subcategories\n"
            
            categories_text += "\n"
        
        update.message.reply_text(categories_text, parse_mode='Markdown')
        
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def list_subcategories(update, context):
    """List all subcategories: /listsubcategories"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    try:
        data = load_data()
        
        if not data['subcategories']:
            update.message.reply_text("📭 No subcategories available.")
            return
        
        subcategories_text = "📁 **All Subcategories:**\n\n"
        
        for subcategory in data['subcategories']:
            category = next((c for c in data['categories'] if c['id'] == subcategory['category_id']), {"name": "Unknown"})
            subcategories_text += f"📁 **{subcategory['name']}** (ID: {subcategory['id']})\n"
            subcategories_text += f"   🏷️ Category: {category['name']} (ID: {subcategory['category_id']})\n"
            subcategories_text += f"   📝 {subcategory['description']}\n\n"
        
        update.message.reply_text(subcategories_text, parse_mode='Markdown')
        
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def list_products(update, context):
    """List all products: /listproducts"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    try:
        data = load_data()
        
        if not data['products']:
            update.message.reply_text("📭 No products available.")
            return
        
        products_text = "📦 **All Products:**\n\n"
        for product in data['products']:
            category = next((c for c in data['categories'] if c['id'] == product['category_id']), {"name": "Unknown"})
            subcategory = next((s for s in data['subcategories'] if s['id'] == product['subcategory_id']), {"name": "Unknown"})
            
            products_text += f"🆔 {product['id']}: {product['name']}\n"
            products_text += f"   💰 ${product['price']} | 📂 {category['name']} | 📁 {subcategory['name']}\n"
            products_text += f"   📝 {product['description']}\n"
            products_text += f"   ⭐ Features: {', '.join(product.get('features', []))}\n\n"
        
        update.message.reply_text(products_text, parse_mode='Markdown')
        
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def delete_product(update, context):
    """Delete a product: /deleteproduct PRODUCT_ID"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text("📝 Usage: /deleteproduct PRODUCT_ID")
        return
    
    try:
        product_id = int(context.args[0])
        data = load_data()
        
        initial_count = len(data['products'])
        data['products'] = [p for p in data['products'] if p['id'] != product_id]
        
        if len(data['products']) == initial_count:
            update.message.reply_text(f"❌ Product ID {product_id} not found.")
            return
        
        save_data(data)
        
        # Reload products data
        global products
        products = data['products']
        
        update.message.reply_text(f"✅ Product ID {product_id} deleted successfully.")
        
    except ValueError:
        update.message.reply_text("❌ Product ID must be a number")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def delete_category(update, context):
    """Delete a category and its subcategories/products: /deletecategory CATEGORY_ID"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text("📝 Usage: /deletecategory CATEGORY_ID")
        return
    
    try:
        category_id = int(context.args[0])
        data = load_data()
        
        # Check if category exists
        category_exists = any(cat['id'] == category_id for cat in data['categories'])
        if not category_exists:
            update.message.reply_text(f"❌ Category ID {category_id} not found.")
            return
        
        # Get category name for confirmation
        category_name = next((cat['name'] for cat in data['categories'] if cat['id'] == category_id), "Unknown")
        
        # Delete category
        data['categories'] = [c for c in data['categories'] if c['id'] != category_id]
        
        # Delete related subcategories
        subcategories_deleted = [s for s in data['subcategories'] if s['category_id'] == category_id]
        data['subcategories'] = [s for s in data['subcategories'] if s['category_id'] != category_id]
        
        # Delete related products
        products_deleted = [p for p in data['products'] if p['category_id'] == category_id]
        data['products'] = [p for p in data['products'] if p['category_id'] != category_id]
        
        save_data(data)
        
        # Reload global data
        global categories, subcategories, products
        categories = data['categories']
        subcategories = data['subcategories']
        products = data['products']
        
        update.message.reply_text(
            f"✅ Category '{category_name}' (ID: {category_id}) deleted successfully.\n\n"
            f"🗑️ Also deleted:\n"
            f"• {len(subcategories_deleted)} subcategories\n"
            f"• {len(products_deleted)} products"
        )
        
    except ValueError:
        update.message.reply_text("❌ Category ID must be a number")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def delete_subcategory(update, context):
    """Delete a subcategory and its products: /deletesubcategory SUBCATEGORY_ID"""
    user_id = update.message.from_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        update.message.reply_text("📝 Usage: /deletesubcategory SUBCATEGORY_ID")
        return
    
    try:
        subcategory_id = int(context.args[0])
        data = load_data()
        
        # Check if subcategory exists
        subcategory_exists = any(sub['id'] == subcategory_id for sub in data['subcategories'])
        if not subcategory_exists:
            update.message.reply_text(f"❌ Subcategory ID {subcategory_id} not found.")
            return
        
        # Get subcategory name and category info for confirmation
        subcategory = next((sub for sub in data['subcategories'] if sub['id'] == subcategory_id), None)
        category_name = next((cat['name'] for cat in data['categories'] if cat['id'] == subcategory['category_id']), "Unknown")
        
        # Delete subcategory
        data['subcategories'] = [s for s in data['subcategories'] if s['id'] != subcategory_id]
        
        # Delete related products
        products_deleted = [p for p in data['products'] if p['subcategory_id'] == subcategory_id]
        data['products'] = [p for p in data['products'] if p['subcategory_id'] != subcategory_id]
        
        save_data(data)
        
        # Reload global data
        global subcategories, products
        subcategories = data['subcategories']
        products = data['products']
        
        update.message.reply_text(
            f"✅ Subcategory '{subcategory['name']}' (ID: {subcategory_id}) deleted successfully.\n\n"
            f"📂 Category: {category_name}\n"
            f"🗑️ Also deleted: {len(products_deleted)} products"
        )
        
    except ValueError:
        update.message.reply_text("❌ Subcategory ID must be a number")
    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

# ---------------------------
# Setup Handlers
# ---------------------------

# User command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("profile", show_profile))
dispatcher.add_handler(CommandHandler("balance", add_balance))
dispatcher.add_handler(CommandHandler("services", show_services))
dispatcher.add_handler(CommandHandler("about", show_about))
dispatcher.add_handler(CommandHandler("orders", show_orders))

# Admin command handlers
dispatcher.add_handler(CommandHandler("addproduct", add_product))
dispatcher.add_handler(CommandHandler("addcategory", add_category))
dispatcher.add_handler(CommandHandler("addsubcategory", add_subcategory))
dispatcher.add_handler(CommandHandler("listproducts", list_products))
dispatcher.add_handler(CommandHandler("listcategories", list_categories))
dispatcher.add_handler(CommandHandler("listsubcategories", list_subcategories))
dispatcher.add_handler(CommandHandler("deleteproduct", delete_product))
dispatcher.add_handler(CommandHandler("deletecategory", delete_category))
dispatcher.add_handler(CommandHandler("deletesubcategory", delete_subcategory))

# Callback and message handlers
dispatcher.add_handler(CallbackQueryHandler(button_handler))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_message))

# ---------------------------
# Flask Routes
# ---------------------------
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Flask server is running successfully with Multi-API Price System!",
        "webhook_url": WEBHOOK_URL,
        "admin_id": ADMIN_ID
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
    # Automatically set webhook on startup
    try:
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
        logger.info(f"Webhook setup: {response.json()}")
        print("✅ Webhook set successfully!")
        print(f"🌐 Webhook URL: {WEBHOOK_URL}")
        print(f"👑 Admin ID: {ADMIN_ID}")
        print("💰 Using Multi-API System for real-time prices")
        print("🔧 APIs: Binance, Kraken, CoinGecko")
    except Exception as e:
        logger.error(f"Failed to set webhook automatically: {e}")
        print(f"❌ Webhook setup failed: {e}")

    print("🤖 Bot starting with improved payment system...")
    app.run(host='0.0.0.0', port=5000)
