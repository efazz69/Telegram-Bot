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
ADMIN_ID = os.getenv("ADMIN_ID", "7091475665")
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
# Admin Commands
# ---------------------------
async def is_admin(user_id):
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
            subcategories = [s for s in data['subcategories'] if s['category_id'] == category['id']]
            if subcategories:
                for sub in subcategories:
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

# ... [KEEP ALL YOUR EXISTING USER COMMANDS AND HANDLERS FROM THE PREVIOUS FIX] ...
# The rest of your existing code for start, profile, balance, services, about, orders, button_handler, etc.
# Make sure to keep all the user command functions from the previous fix

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

# ... [REST OF YOUR EXISTING USER COMMANDS - profile, balance, services, about, orders, etc.] ...
# ... [REST OF YOUR EXISTING BUTTON HANDLERS AND MESSAGE HANDLERS] ...

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

# ... [REST OF YOUR FLASK ROUTES AND WEBHOOK CODE] ...

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Crypto Bot",
        "message": "🤖 Flask server is running successfully with Admin Commands!",
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
    except Exception as e:
        logger.error(f"Failed to set webhook automatically: {e}")
        print(f"❌ Webhook setup failed: {e}")

    print("🤖 Bot starting with Admin Commands enabled...")
    app.run(host='0.0.0.0', port=5000)
