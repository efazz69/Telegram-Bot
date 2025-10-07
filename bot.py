import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
from datetime import datetime
import asyncio
import threading

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
        self.updater = Updater(token=BOT_TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.setup_handlers()
        self.load_products()
        # Initialize admin commands
        self.admin_commands = AdminCommands(self.dispatcher)
        
    def load_products(self):
        with open('products.json', 'r') as f:
            data = json.load(f)
            self.products = data.get('products', [])
            self.categories = data.get('categories', [])
            self.subcategories = data.get('subcategories', [])
    
    def setup_handlers(self):
        # Command handlers
        self.dispatcher.add_handler(CommandHandler("start", self.start))
        self.dispatcher.add_handler(CommandHandler("profile", self.show_profile))
        self.dispatcher.add_handler(CommandHandler("balance", self.add_balance))
        self.dispatcher.add_handler(CommandHandler("services", self.show_services))
        self.dispatcher.add_handler(CommandHandler("about", self.show_about))
        self.dispatcher.add_handler(CommandHandler("orders", self.show_orders))
        
        # Message handlers for balance amount input
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_balance_input))
        
        # Callback query handlers
        self.dispatcher.add_handler(CallbackQueryHandler(self.button_handler))
    
    def start_polling(self):
        """Start the bot"""
        print("🤖 Bot is starting...")
        self.updater.start_polling()
        print("✅ Bot is now running!")
        self.updater.idle()
    
    # ... [KEEP ALL YOUR EXISTING METHODS AS THEY ARE, but change ContextTypes.DEFAULT_TYPE to CallbackContext]
    # Just change the parameter types in all methods:
    
    async def start(self, update: Update, context: CallbackContext):
        # Your existing start method code here
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
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # ... [CONTINUE WITH ALL YOUR OTHER METHODS, changing ContextTypes.DEFAULT_TYPE to CallbackContext]
    
    # For callback methods, change the signature to:
    async def button_handler(self, update: Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        # Update user activity
        user_manager.update_user_activity(user_id)
        
        # Your existing button handler logic here...
        if data == "main_menu":
            await self.start_callback(query)
        elif data == "profile":
            await self.show_profile_callback(query)
        # ... [rest of your button handler code]

    # ... [ALL YOUR OTHER METHODS REMAIN THE SAME, JUST UPDATE THE PARAMETER TYPES]

def main():
    # Check if token is set
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE' or not BOT_TOKEN:
        print("❌ Please set your BOT_TOKEN in environment variables")
        return
    
    bot = CryptoStoreBot()
    
    # Start the Bot
    print("🤖 Bot is running...")
    bot.start_polling()

if __name__ == '__main__':
    main()
