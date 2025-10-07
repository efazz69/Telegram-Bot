from flask import Flask, request, jsonify
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from dotenv import load_dotenv
import os
import logging
import requests
import json
from datetime import datetime

# Import your existing modules
from config import BOT_TOKEN, ADMIN_ID
from user_manager import UserManager
from database import Database
from payment_handler import PaymentHandler

# ---------------------------
# Setup
# ---------------------------
load_dotenv()
app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "7963936009:AAEK3Y4GYCpRk4mbASW2Xvh7u0xedXmR64Y")
WEBHOOK_URL = f"https://telegram-bot-5fco.onrender.com/{BOT_TOKEN}"

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# Initialize components
db = Database()
payment_handler = PaymentHandler()
user_manager = UserManager()

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
# Telegram Handlers
# ---------------------------
def start(update, context):
    """Start command with main menu"""
    user = update.message.from_user
    user_manager.create_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
🤖 Welcome to Crypto Store Bot, {user.first_name}!

💎 **Features:**
• Buy digital products with cryptocurrency
• Real-time crypto prices from Binance
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

• **USDT (BEP20)** - Fast & Low fee
• **Bitcoin (BTC)** - Most popular
• **Litecoin (LTC)** - Fast confirmations

💱 Prices update in real-time from Binance.
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
• Real-time price feeds from Binance
• Instant digital product delivery
• User balance system
• 24/7 automated service

🔒 **Security:**
• No personal data required
• Blockchain-verified payments
• Encrypted communications

🪙 **Supported Cryptocurrencies:**
• USDT (BEP20)
• Bitcoin (BTC)
• Litecoin (LTC)

📞 **Support:**
Contact @YourSupportHandle for assistance.
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
            
    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        query.edit_message_text("❌ An error occurred. Please try again.")

def start_callback(query):
    """Start menu for callback queries"""
    user = query.from_user
    
    welcome_text = f"""
🤖 Welcome to Crypto Store Bot, {user.first_name}!

💎 **Features:**
• Buy digital products with cryptocurrency
• Real-time crypto prices from Binance
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

• **USDT (BEP20)** - Fast & Low fee
• **Bitcoin (BTC)** - Most popular
• **Litecoin (LTC)** - Fast confirmations

💱 Prices update in real-time from Binance.
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
• Real-time price feeds from Binance
• Instant digital product delivery
• User balance system
• 24/7 automated service

🔒 **Security:**
• No personal data required
• Blockchain-verified payments
• Encrypted communications

🪙 **Supported Cryptocurrencies:**
• USDT (BEP20)
• Bitcoin (BTC)
• Litecoin (LTC)

📞 **Support:**
Contact @YourSupportHandle for assistance.
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
    
    deposit_text = f"""
💰 **Add Balance with {crypto_currency}**

Please enter the amount in USD you want to deposit:

💡 Example: `50` for $50.00

💰 Your current balance: ${user_manager.get_user(user.id)['balance']:.2f}
    """
    
    # Store the selected crypto in user data for the next message
    context = query.message._bot_data
    if 'user_data' not in context:
        context['user_data'] = {}
    context['user_data'][user.id] = {'awaiting_deposit_amount': crypto_currency}
    
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
    text = update.message.text
    
    # Check if we're expecting a deposit amount from this user
    user_context = context.bot_data.get('user_data', {}).get(user.id, {})
    
    if 'awaiting_deposit_amount' in user_context:
        crypto_currency = user_context['awaiting_deposit_amount']
        
        try:
            usd_amount = float(text)
            if usd_amount <= 0:
                update.message.reply_text("❌ Please enter a positive amount.")
                return
            
            # Clear the awaiting state
            if user.id in context.bot_data.get('user_data', {}):
                del context.bot_data['user_data'][user.id]
            
            # Generate payment information
            crypto_amount, current_price = payment_handler.get_crypto_amount(usd_amount, crypto_currency)
            payment_address = payment_handler.generate_payment_address(crypto_currency, f"deposit_{user.id}")
            
            payment_text = f"""
💰 **Deposit Instructions - {crypto_currency}**

💵 **Amount:** ${usd_amount:.2f} USD
🪙 **To Pay:** {crypto_amount:.6f} {crypto_currency}
💱 **Exchange Rate:** 1 {crypto_currency} = ${current_price:.2f} USD

📍 **Send to this address:**
`{payment_address}`

⏰ **Expires in:** 15 minutes
🔍 **Network:** {crypto_currency.replace('_', ' ')}

⚠️ **Important:**
• Send exactly {crypto_amount:.6f} {crypto_currency}
• Only send {crypto_currency} to this address
• Payment will be auto-confirmed
            """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_deposit_{crypto_currency}_{usd_amount}")],
                [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except ValueError:
            update.message.reply_text("❌ Please enter a valid number (e.g., 50 or 25.50)")
    else:
        # Default response for other text messages
        update.message.reply_text("💡 Use the menu buttons or commands to navigate the bot.")

# Setup command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("profile", show_profile))
dispatcher.add_handler(CommandHandler("balance", add_balance))
dispatcher.add_handler(CommandHandler("services", show_services))
dispatcher.add_handler(CommandHandler("about", show_about))
dispatcher.add_handler(CommandHandler("orders", show_orders))

# Setup callback query handler
dispatcher.add_handler(CallbackQueryHandler(button_handler))

# Setup message handler for text input
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_message))

# ---------------------------
# Flask Routes
# ---------------------------
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Flask server is running successfully with full menu system!",
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
    # Automatically set webhook on startup
    try:
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
        logger.info(f"Webhook setup: {response.json()}")
        print("✅ Webhook set successfully!")
        print(f"🌐 Webhook URL: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Failed to set webhook automatically: {e}")
        print(f"❌ Webhook setup failed: {e}")

    print("🤖 Bot starting with full menu system...")
    app.run(host='0.0.0.0', port=5000)
