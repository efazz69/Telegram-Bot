import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import asyncio

from config import BOT_TOKEN, CRYPTO_NETWORKS
from database import Database
from payment_handler import PaymentHandler
from user_manager import UserManager
from admin_commands import AdminCommands

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Initialize components
db = Database()
payment_handler = PaymentHandler()
user_manager = UserManager()

class CryptoStoreBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.load_products()
        # Initialize admin commands
        self.admin_commands = AdminCommands(self.application)
        # Start background tasks
        self.background_tasks = set()
    
    def load_products(self):
        with open('products.json', 'r') as f:
            data = json.load(f)
            self.products = data.get('products', [])
            self.categories = data.get('categories', [])
            self.subcategories = data.get('subcategories', [])
    
    def setup_handlers(self):
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("profile", self.show_profile))
        self.application.add_handler(CommandHandler("balance", self.add_balance))
        self.application.add_handler(CommandHandler("services", self.show_services))
        self.application.add_handler(CommandHandler("about", self.show_about))
        self.application.add_handler(CommandHandler("orders", self.show_orders))
        
        # Message handlers for balance amount input
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_balance_input))
        
        # Callback query handlers
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_background_tasks(self):
        """Start background tasks for payment checking and cleanup"""
        task = asyncio.create_task(self.periodic_cleanup())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
    
    async def periodic_cleanup(self):
        """Periodically clean up expired orders"""
        while True:
            try:
                cleaned_count = db.cleanup_expired_orders()
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} expired orders")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(300)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        # Create user if not exists
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
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        user_data = user_manager.get_user(user.id)
        
        if not user_data:
            user_data = user_manager.create_user(user.id, user.username, user.first_name)
        
        # Format registration date
        reg_date = datetime.fromisoformat(user_data['registration_date']).strftime("%Y-%m-%d %H:%M")
        
        # Format first top-up date
        if user_data['first_topup_date']:
            topup_date = datetime.fromisoformat(user_data['first_topup_date']).strftime("%Y-%m-%d %H:%M")
        else:
            topup_date = "Not yet"
        
        profile_text = f"""
👤 **Profile Information**

🆔 **User ID:** `{user_data['user_id']}`
💼 **Current Balance:** `${user_data['balance']:.2f}`
📅 **Registration:** {reg_date}
💰 **First Top-up:** {topup_date}
📊 **Total Deposited:** `${user_data['total_deposited']:.2f}`
📦 **Total Orders:** {user_data['total_orders']}
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("📦 My Orders", callback_data="my_orders")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def add_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        user_manager.update_user_activity(user.id)
        
        balance_text = """
💰 **Add Balance**

Please enter the amount in USD you want to add to your balance.

💡 **Minimum deposit:** $1.00
💡 **Maximum deposit:** $1000.00

Type the amount below:
        """
        
        # Store that we're waiting for balance input
        context.user_data['waiting_for_balance'] = True
        
        await update.message.reply_text(balance_text, parse_mode='Markdown')
    
    async def handle_balance_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        
        # Check if we're waiting for balance input
        if not context.user_data.get('waiting_for_balance'):
            return
        
        try:
            amount = float(update.message.text)
            
            # Validate amount
            if amount < 1.0:
                await update.message.reply_text("❌ Minimum deposit is $1.00. Please enter a higher amount:")
                return
            elif amount > 1000.0:
                await update.message.reply_text("❌ Maximum deposit is $1000.00. Please enter a lower amount:")
                return
            
            # Clear the waiting flag
            context.user_data['waiting_for_balance'] = False
            
            # Store the amount for crypto selection
            context.user_data['deposit_amount'] = amount
            
            # Show crypto options
            await self.show_crypto_options(update, context, amount)
            
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number (e.g., 50.00):")
    
    async def show_crypto_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE, amount):
        """Show cryptocurrency options for deposit"""
        
        # Calculate crypto amounts for each currency
        crypto_options = []
        for crypto in ['USDT_BEP20', 'BTC', 'LTC']:
            crypto_amount, current_rate = payment_handler.get_crypto_amount(amount, crypto)
            crypto_options.append((crypto, crypto_amount, current_rate))
        
        options_text = f"""
💰 **Deposit: ${amount:.2f}**

Select your payment method:

"""
        for crypto, crypto_amount, rate in crypto_options:
            network_info = CRYPTO_NETWORKS[crypto]
            if crypto == 'USDT_BEP20':
                options_text += f"• **{network_info['name']}:** {crypto_amount:.2f} USDT\n"
            else:
                options_text += f"• **{network_info['name']}:** {crypto_amount:.6f}\n"
        
        options_text += f"\n💱 **Current Rates:**\n"
        for crypto, crypto_amount, rate in crypto_options:
            if crypto != 'USDT_BEP20':
                options_text += f"• 1 {crypto} = ${rate:,.2f}\n"
        
        keyboard = []
        for crypto, crypto_amount, rate in crypto_options:
            network_info = CRYPTO_NETWORKS[crypto]
            keyboard.append([
                InlineKeyboardButton(
                    f"{network_info['name']} - {crypto_amount:.6f}",
                    callback_data=f"deposit_{crypto}_{amount}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="add_balance")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(options_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def process_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE, crypto_currency, usd_amount):
        """Process deposit and show payment instructions"""
        query = update.callback_query
        user = query.from_user
        
        # Calculate crypto amount
        crypto_amount, exchange_rate = payment_handler.get_crypto_amount(usd_amount, crypto_currency)
        
        # Generate payment address
        payment_address = payment_handler.generate_payment_address(crypto_currency, f"deposit_{user.id}")
        
        # Create deposit order
        order = db.create_order(
            user_id=user.id,
            product_id=0,  # 0 for deposits
            amount=usd_amount,
            crypto_currency=crypto_currency,
            crypto_amount=crypto_amount,
            payment_address=payment_address,
            exchange_rate=exchange_rate
        )
        
        # Prepare payment instructions
        network_info = CRYPTO_NETWORKS[crypto_currency]
        
        payment_text = f"""
💰 **Deposit Instructions**

💵 Amount: **${usd_amount:.2f}**
💎 Crypto: **{crypto_amount:.6f} {network_info['name']}**
🌐 Network: {network_info['network']}
💰 Exchange Rate: 1 {crypto_currency} = ${exchange_rate:,.2f}

📬 Send EXACTLY **{crypto_amount:.6f} {network_info['name']}** to:

`{payment_address}`

⏰ **Important:**
• Send only {network_info['name']} on {network_info['network']} network
• Send exact amount: {crypto_amount:.6f}
• ⚠️ Price locked for 15 minutes only
• Balance will be updated automatically after payment

🔄 The bot will automatically check for your payment every 5 minutes.

⚠️ **DO NOT SEND OTHER CURRENCIES - THEY WILL BE LOST**
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_payment_{order['order_id']}")],
            [InlineKeyboardButton("💰 Add More Balance", callback_data="add_balance")],
            [InlineKeyboardButton("👤 Profile", callback_data="profile")],
            [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show services/categories"""
        try:
            if not self.categories:
                await update.message.reply_text("📭 No services available yet. Check back later!")
                return
            
            keyboard = []
            for category in self.categories:
                keyboard.append([
                    InlineKeyboardButton(
                        category['name'],
                        callback_data=f"category_{category['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🛍️ **Our Services**\n\nSelect a category to browse products:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text("❌ Error loading services.")
    
    async def show_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        about_text = """
ℹ️ **About Us**

🤖 **Crypto Store Bot**
Your trusted partner for digital products and services.

💎 **What we offer:**
• High-quality digital products
• Secure cryptocurrency payments
• Instant delivery after payment
• 24/7 customer support

🔒 **Security Features:**
• Blockchain-based payments
• Secure wallet integration
• Encrypted transactions
• Anonymous purchasing

🌐 **Supported Cryptocurrencies:**
• Bitcoin (BTC)
• Litecoin (LTC)
• USDT (BEP20)

⏰ **Delivery:**
• Instant automated delivery
• 24/7 availability
• No delays

📞 **Support:**
Telegram: @your_support_username
Email: support@yourdomain.com

Thank you for choosing our service! 🚀
        """
        
        keyboard = [
            [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(about_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.from_user.id
        orders = db.get_user_orders(user_id)
        
        if not orders:
            await update.message.reply_text("📭 You don't have any orders yet.")
            return
        
        text = "📦 **Your Orders:**\n\n"
        for order in orders[:10]:
            if order['product_id'] == 0:
                # Deposit order
                product_name = "💰 Balance Deposit"
            else:
                product = next((p for p in self.products if p['id'] == order['product_id']), None)
                product_name = product['name'] if product else "Unknown Product"
            
            status_emoji = "✅" if order['status'] == 'paid' else "⏳" if order['status'] == 'pending' else "❌"
            expires_at = datetime.fromisoformat(order['expires_at'])
            time_left = expires_at - datetime.now()
            minutes_left = max(0, int(time_left.total_seconds() / 60))
            
            text += f"{status_emoji} Order #{order['order_id']}\n"
            text += f"Product: {product_name}\n"
            text += f"Amount: {order['crypto_amount']} {order['crypto_currency']}\n"
            text += f"Status: {order['status'].title()}\n"
            if order['status'] == 'pending':
                text += f"⏰ Expires in: {minutes_left} minutes\n"
            text += f"Date: {order['created_at'][:10]}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        # Update user activity
        user_manager.update_user_activity(user_id)
        
        if data == "main_menu":
            await self.start_callback(query)
        elif data == "profile":
            await self.show_profile_callback(query)
        elif data == "add_balance":
            await self.add_balance_callback(query)
        elif data == "services":
            await self.show_services_callback(query)
        elif data == "about":
            await self.show_about_callback(query)
        elif data == "my_orders":
            await self.show_orders_callback(query, user_id)
        elif data.startswith("deposit_"):
            parts = data.split("_")
            crypto_currency = parts[1]
            usd_amount = float(parts[2])
            await self.process_deposit(query, context, crypto_currency, usd_amount)
        elif data.startswith("category_"):
            category_id = int(data.split("_")[1])
            await self.show_category(query, category_id)
        elif data.startswith("subcategory_"):
            subcategory_id = int(data.split("_")[1])
            await self.show_subcategory(query, subcategory_id)
        elif data.startswith("product_"):
            product_id = int(data.split("_")[1])
            await self.show_product_detail(query, product_id)
        elif data.startswith("select_crypto_"):
            parts = data.split("_")
            product_id = int(parts[2])
            crypto_currency = parts[3]
            await self.create_product_order(query, user_id, product_id, crypto_currency)
        elif data.startswith("check_payment_"):
            order_id = int(data.split("_")[2])
            await self.check_payment_status(query, order_id)
    
    # Callback methods for button handlers
    async def start_callback(self, query):
        user = query.from_user
        welcome_text = f"""
🤖 Welcome to Crypto Store Bot, {user.first_name}!

Select an option from the menu below:
        """
        
        keyboard = [
            [InlineKeyboardButton("👤 Profile", callback_data="profile")],
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("🛍️ Services", callback_data="services")],
            [InlineKeyboardButton("ℹ️ About", callback_data="about")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_profile_callback(self, query):
        user = query.from_user
        user_data = user_manager.get_user(user.id)
        
        if not user_data:
            user_data = user_manager.create_user(user.id, user.username, user.first_name)
        
        reg_date = datetime.fromisoformat(user_data['registration_date']).strftime("%Y-%m-%d %H:%M")
        
        if user_data['first_topup_date']:
            topup_date = datetime.fromisoformat(user_data['first_topup_date']).strftime("%Y-%m-%d %H:%M")
        else:
            topup_date = "Not yet"
        
        profile_text = f"""
👤 **Profile Information**

🆔 **User ID:** `{user_data['user_id']}`
💼 **Current Balance:** `${user_data['balance']:.2f}`
📅 **Registration:** {reg_date}
💰 **First Top-up:** {topup_date}
📊 **Total Deposited:** `${user_data['total_deposited']:.2f}`
📦 **Total Orders:** {user_data['total_orders']}
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("📦 My Orders", callback_data="my_orders")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def add_balance_callback(self, query):
        balance_text = """
💰 **Add Balance**

Please enter the amount in USD you want to add to your balance.

💡 **Minimum deposit:** $1.00
💡 **Maximum deposit:** $1000.00

Type the amount below:
        """
        
        # We can't get text input from callback, so show current options
        keyboard = [
            [InlineKeyboardButton("$10", callback_data="quick_deposit_10")],
            [InlineKeyboardButton("$25", callback_data="quick_deposit_25")],
            [InlineKeyboardButton("$50", callback_data="quick_deposit_50")],
            [InlineKeyboardButton("$100", callback_data="quick_deposit_100")],
            [InlineKeyboardButton("Custom Amount", callback_data="custom_deposit")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(balance_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_services_callback(self, query):
        try:
            if not self.categories:
                await query.edit_message_text("📭 No services available yet. Check back later!")
                return
            
            keyboard = []
            for category in self.categories:
                keyboard.append([
                    InlineKeyboardButton(
                        category['name'],
                        callback_data=f"category_{category['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🛍️ **Our Services**\n\nSelect a category to browse products:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await query.edit_message_text("❌ Error loading services.")
    
    async def show_about_callback(self, query):
        about_text = """
ℹ️ **About Us**

🤖 **Crypto Store Bot**
Your trusted partner for digital products and services.

📞 **Support:** @your_support_username
📧 **Email:** support@yourdomain.com

Thank you for choosing our service! 🚀
        """
        
        keyboard = [
            [InlineKeyboardButton("🛍️ Browse Services", callback_data="services")],
            [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(about_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_orders_callback(self, query, user_id):
        orders = db.get_user_orders(user_id)
        
        if not orders:
            await query.edit_message_text("📭 You don't have any orders yet.")
            return
        
        text = "📦 **Your Orders:**\n\n"
        for order in orders[:5]:
            if order['product_id'] == 0:
                product_name = "💰 Balance Deposit"
            else:
                product = next((p for p in self.products if p['id'] == order['product_id']), None)
                product_name = product['name'] if product else "Unknown Product"
            
            status_emoji = "✅" if order['status'] == 'paid' else "⏳" if order['status'] == 'pending' else "❌"
            
            text += f"{status_emoji} Order #{order['order_id']}\n"
            text += f"Product: {product_name}\n"
            text += f"Status: {order['status'].title()}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="profile")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Category and product browsing methods
    async def show_category(self, query, category_id):
        """Show subcategories in a category"""
        try:
            category = next((c for c in self.categories if c['id'] == category_id), None)
            if not category:
                await query.edit_message_text("❌ Category not found.")
                return
            
            subcategories = [s for s in self.subcategories if s['category_id'] == category_id]
            products = [p for p in self.products if p['category_id'] == category_id]
            
            keyboard = []
            
            # Add subcategory buttons
            for subcategory in subcategories:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📁 {subcategory['name']}",
                        callback_data=f"subcategory_{subcategory['id']}"
                    )
                ])
            
            # Add direct product buttons for products without subcategories
            products_without_subcat = [p for p in products if not any(s['id'] == p['subcategory_id'] for s in subcategories)]
            for product in products_without_subcat:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📦 {product['name']} - ${product['price']}",
                        callback_data=f"product_{product['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data="services")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"📂 **{category['name']}**\n\n{category['description']}\n\n"
            if subcategories:
                text += "Select a subcategory or product:"
            else:
                text += "Available products:"
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            await query.edit_message_text("❌ Error loading category.")
    
    async def show_subcategory(self, query, subcategory_id):
        """Show products in a subcategory"""
        try:
            subcategory = next((s for s in self.subcategories if s['id'] == subcategory_id), None)
            if not subcategory:
                await query.edit_message_text("❌ Subcategory not found.")
                return
            
            category = next((c for c in self.categories if c['id'] == subcategory['category_id']), None)
            products = [p for p in self.products if p['subcategory_id'] == subcategory_id]
            
            if not products:
                await query.edit_message_text("📭 No products available in this subcategory yet.")
                return
            
            keyboard = []
            for product in products:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📦 {product['name']} - ${product['price']}",
                        callback_data=f"product_{product['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Back to Category", callback_data=f"category_{subcategory['category_id']}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"📁 **{subcategory['name']}**\n"
            if category:
                text += f"📂 Category: {category['name']}\n\n"
            text += f"{subcategory['description']}\n\n"
            text += "Available products:"
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            await query.edit_message_text("❌ Error loading subcategory.")
    
    async def show_product_detail(self, query, product_id):
        product = next((p for p in self.products if p['id'] == product_id), None)
        if not product:
            await query.edit_message_text("❌ Product not found.")
            return
        
        category = next((c for c in self.categories if c['id'] == product['category_id']), None)
        subcategory = next((s for s in self.subcategories if s['id'] == product['subcategory_id']), None)
        
        # Show current prices for this product
        price_info = "💱 **Current Rates for this Product:**\n"
        for crypto in ['USDT_BEP20', 'BTC', 'LTC']:
            try:
                crypto_amount, current_price = payment_handler.get_crypto_amount(product['price'], crypto)
                if crypto == 'USDT_BEP20':
                    price_info += f"• {crypto}: {crypto_amount} USDT\n"
                else:
                    price_info += f"• {crypto}: {crypto_amount:.6f}\n"
            except Exception as e:
                price_info += f"• {crypto}: Rate unavailable\n"
        
        text = f"""
🛍️ **{product['name']}**

📝 Description: {product['description']}
💰 Price: ${product['price']}
📂 Category: {category['name'] if category else 'N/A'}
📁 Subcategory: {subcategory['name'] if subcategory else 'N/A'}
⭐ Features: {', '.join(product.get('features', []))}

{price_info}

⏰ **Price Lock:** When you select a payment method, the rate will be locked for 15 minutes.

Select payment method:
        """
        
        keyboard = [
            [
                InlineKeyboardButton("₿ Bitcoin", callback_data=f"select_crypto_{product_id}_BTC"),
                InlineKeyboardButton("Ł Litecoin", callback_data=f"select_crypto_{product_id}_LTC")
            ],
            [
                InlineKeyboardButton("💎 USDT (BEP20)", callback_data=f"select_crypto_{product_id}_USDT_BEP20")
            ],
            [InlineKeyboardButton("📊 Refresh Prices", callback_data=f"product_{product_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"category_{product['category_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def show_payment_options(self, query, product_id):
        """Show payment options for a product"""
        await self.show_product_detail(query, product_id)
    
    async def create_product_order(self, query, user_id, product_id, crypto_currency):
        product = next((p for p in self.products if p['id'] == product_id), None)
        if not product:
            await query.edit_message_text("❌ Product not found.")
            return
        
        # Calculate crypto amount with current rate
        crypto_amount, exchange_rate = payment_handler.get_crypto_amount(product['price'], crypto_currency)
        
        # Generate payment address
        payment_address = payment_handler.generate_payment_address(crypto_currency, f"{user_id}_{product_id}")
        
        # Create order with locked rate
        order = db.create_order(user_id, product_id, product['price'], crypto_currency, crypto_amount, payment_address, exchange_rate)
        
        # Prepare payment instructions
        network_info = CRYPTO_NETWORKS[crypto_currency]
        
        payment_text = f"""
💰 **Payment Instructions**

🛍️ Product: {product['name']}
💵 Amount: **{crypto_amount} {network_info['name']}**
💸 USD Value: ${product['price']}
🌐 Network: {network_info['network']}
💰 Exchange Rate: 1 {crypto_currency} = ${exchange_rate:,.2f}

📬 Send EXACTLY **{crypto_amount} {network_info['name']}** to:

`{payment_address}`

⏰ **Important:**
• Send only {network_info['name']} on {network_info['network']} network
• Send exact amount: {crypto_amount}
• ⚠️ Price locked for 15 minutes only
• After payment, your product will be delivered automatically

🔄 The bot will automatically check for your payment every 5 minutes.

⚠️ **DO NOT SEND OTHER CURRENCIES - THEY WILL BE LOST**
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Check Payment Now", callback_data=f"check_payment_{order['order_id']}")],
            [InlineKeyboardButton("📊 Check New Prices", callback_data=f"product_{product_id}")],
            [InlineKeyboardButton("📦 My Orders", callback_data="my_orders")],
            [InlineKeyboardButton("🛍️ Continue Shopping", callback_data="services")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def check_payment_status(self, query, order_id):
        order = db.get_order(order_id)
        if not order:
            await query.answer("Order not found!", show_alert=True)
            return
        
        if order['status'] == 'paid':
            await query.answer("✅ Payment already confirmed!", show_alert=True)
            return
        
        # Check if order expired
        expires_at = datetime.fromisoformat(order['expires_at'])
        if datetime.now() > expires_at:
            db.update_order_status(order_id, 'expired')
            await query.answer("❌ Order expired! Please create a new order.", show_alert=True)
            return
        
        # Check payment
        is_paid = payment_handler.check_payment(
            order['crypto_currency'],
            order['payment_address'],
            order['crypto_amount']
        )
        
        if is_paid:
            db.update_order_status(order_id, 'paid')
            
            # Update user balance for deposits
            if order['product_id'] == 0:
                user_manager.update_balance(order['user_id'], order['amount'])
                await query.answer("✅ Payment confirmed! Your balance has been updated.", show_alert=True)
            else:
                user_manager.increment_orders(order['user_id'])
                await query.answer("✅ Payment confirmed! Your product has been delivered.", show_alert=True)
            
            # Send confirmation message
            if order['product_id'] == 0:
                confirmation_text = f"""
🎉 **Deposit Confirmed!**

✅ Your payment has been verified successfully.

💰 **Amount Added:** ${order['amount']:.2f}
💎 Paid: {order['crypto_amount']} {order['crypto_currency']}

Your balance has been updated. Thank you!
                """
            else:
                product = next((p for p in self.products if p['id'] == order['product_id']), None)
                product_name = product['name'] if product else "Product"
                confirmation_text = f"""
🎉 **Payment Confirmed!**

✅ Your payment has been verified successfully.

📦 **Product Delivered:** {product_name}
💰 Amount Paid: {order['crypto_amount']} {order['crypto_currency']}

Thank you for your purchase!
                """
            
            await query.message.reply_text(confirmation_text, parse_mode='Markdown')
        else:
            time_left = expires_at - datetime.now()
            minutes_left = max(0, int(time_left.total_seconds() / 60))
            await query.answer(f"⏳ Payment not received yet. {minutes_left} minutes remaining.", show_alert=True)

def main():
    # Check if token is set
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Please set your BOT_TOKEN in config.py or environment variables")
        return
    
    bot = CryptoStoreBot()
    
    # Start background tasks
    asyncio.run(bot.start_background_tasks())
    
    # Start the Bot
    print("🤖 Bot is running...")
    bot.application.run_polling()

if __name__ == '__main__':
    main()