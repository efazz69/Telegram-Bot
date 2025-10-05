import json
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from config import ADMIN_ID

logger = logging.getLogger(__name__)

class AdminCommands:
    def __init__(self, application):
        self.application = application
        self.setup_admin_handlers()
    
    def setup_admin_handlers(self):
        """Setup admin-only command handlers"""
        self.application.add_handler(CommandHandler("addproduct", self.add_product))
        self.application.add_handler(CommandHandler("addcategory", self.add_category))
        self.application.add_handler(CommandHandler("addsubcategory", self.add_subcategory))
        self.application.add_handler(CommandHandler("listproducts", self.list_products))
        self.application.add_handler(CommandHandler("listcategories", self.list_categories))
        self.application.add_handler(CommandHandler("listsubcategories", self.list_subcategories))
        self.application.add_handler(CommandHandler("deleteproduct", self.delete_product))
        self.application.add_handler(CommandHandler("deletecategory", self.delete_category))
        self.application.add_handler(CommandHandler("deletesubcategory", self.delete_subcategory))
    
    async def is_admin(self, user_id):
        """Check if user is admin"""
        return str(user_id) == str(ADMIN_ID)
    
    def load_data(self):
        """Load all data from JSON files"""
        with open('products.json', 'r') as f:
            return json.load(f)
    
    def save_data(self, data):
        """Save data to JSON files"""
        with open('products.json', 'w') as f:
            json.dump(data, f, indent=2)
    
    async def add_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new category: /addcategory Name|Description"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Usage: /addcategory Name|Description\n\n"
                "Example: /addcategory 💎 Digital Accounts|Premium digital accounts and subscriptions"
            )
            return
        
        try:
            args = ' '.join(context.args).split('|')
            if len(args) != 2:
                await update.message.reply_text("❌ Invalid format. Use: Name|Description")
                return
            
            name, description = args
            
            data = self.load_data()
            
            # Generate new category ID
            new_id = max([c['id'] for c in data['categories']]) + 1 if data['categories'] else 1
            
            new_category = {
                'id': new_id,
                'name': name.strip(),
                'description': description.strip()
            }
            
            data['categories'].append(new_category)
            self.save_data(data)
            
            await update.message.reply_text(
                f"✅ Category added successfully!\n\n"
                f"🆔 ID: {new_id}\n"
                f"📂 Name: {name}\n"
                f"📝 Description: {description}"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def add_subcategory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new subcategory: /addsubcategory Name|CategoryID|Description"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Usage: /addsubcategory Name|CategoryID|Description\n\n"
                "Example: /addsubcategory Streaming Services|1|Video and music streaming accounts\n\n"
                "Use /listcategories to see available category IDs"
            )
            return
        
        try:
            args = ' '.join(context.args).split('|')
            if len(args) != 3:
                await update.message.reply_text("❌ Invalid format. Use: Name|CategoryID|Description")
                return
            
            name, category_id, description = args
            
            data = self.load_data()
            
            # Check if category exists
            category_exists = any(cat['id'] == int(category_id) for cat in data['categories'])
            if not category_exists:
                await update.message.reply_text(f"❌ Category ID {category_id} not found. Use /listcategories")
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
            self.save_data(data)
            
            await update.message.reply_text(
                f"✅ Subcategory added successfully!\n\n"
                f"🆔 ID: {new_id}\n"
                f"📂 Name: {name}\n"
                f"🏷️ Category ID: {category_id}\n"
                f"📝 Description: {description}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Category ID must be a number")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def add_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a new product: /addproduct Name|Description|Price|CategoryID|SubcategoryID|Feature1,Feature2"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Usage: /addproduct Name|Description|Price|CategoryID|SubcategoryID|Feature1,Feature2\n\n"
                "Example: /addproduct Netflix Premium|4K Ultra HD|5.99|1|1|4K Quality,4 Screens,30 Days Warranty\n\n"
                "Use /listcategories and /listproducts to see IDs"
            )
            return
        
        try:
            args = ' '.join(context.args).split('|')
            if len(args) != 6:
                await update.message.reply_text("❌ Invalid format. Use: Name|Description|Price|CategoryID|SubcategoryID|Features")
                return
            
            name, description, price, category_id, subcategory_id, features = args
            
            data = self.load_data()
            
            # Check if category exists
            category_exists = any(cat['id'] == int(category_id) for cat in data['categories'])
            if not category_exists:
                await update.message.reply_text(f"❌ Category ID {category_id} not found.")
                return
            
            # Check if subcategory exists and belongs to category
            subcategory_exists = any(
                sub['id'] == int(subcategory_id) and sub['category_id'] == int(category_id) 
                for sub in data['subcategories']
            )
            if not subcategory_exists:
                await update.message.reply_text(f"❌ Subcategory ID {subcategory_id} not found or doesn't belong to category {category_id}.")
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
            self.save_data(data)
            
            # Get category and subcategory names for confirmation
            category_name = next((cat['name'] for cat in data['categories'] if cat['id'] == int(category_id)), "Unknown")
            subcategory_name = next((sub['name'] for sub in data['subcategories'] if sub['id'] == int(subcategory_id)), "Unknown")
            
            await update.message.reply_text(
                f"✅ Product added successfully!\n\n"
                f"🆔 ID: {new_id}\n"
                f"📦 Name: {name}\n"
                f"💰 Price: ${float(price):.2f}\n"
                f"📂 Category: {category_name}\n"
                f"📁 Subcategory: {subcategory_name}\n"
                f"⭐ Features: {', '.join(feature_list)}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Price, Category ID and Subcategory ID must be numbers")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def list_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all categories and subcategories: /listcategories"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        try:
            data = self.load_data()
            
            if not data['categories']:
                await update.message.reply_text("📭 No categories available.")
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
            
            await update.message.reply_text(categories_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def list_subcategories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all subcategories: /listsubcategories"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        try:
            data = self.load_data()
            
            if not data['subcategories']:
                await update.message.reply_text("📭 No subcategories available.")
                return
            
            subcategories_text = "📁 **All Subcategories:**\n\n"
            
            for subcategory in data['subcategories']:
                category = next((c for c in data['categories'] if c['id'] == subcategory['category_id']), {"name": "Unknown"})
                subcategories_text += f"📁 **{subcategory['name']}** (ID: {subcategory['id']})\n"
                subcategories_text += f"   🏷️ Category: {category['name']} (ID: {subcategory['category_id']})\n"
                subcategories_text += f"   📝 {subcategory['description']}\n\n"
            
            await update.message.reply_text(subcategories_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def list_products(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all products: /listproducts"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        try:
            data = self.load_data()
            
            if not data['products']:
                await update.message.reply_text("📭 No products available.")
                return
            
            products_text = "📦 **All Products:**\n\n"
            for product in data['products']:
                category = next((c for c in data['categories'] if c['id'] == product['category_id']), {"name": "Unknown"})
                subcategory = next((s for s in data['subcategories'] if s['id'] == product['subcategory_id']), {"name": "Unknown"})
                
                products_text += f"🆔 {product['id']}: {product['name']}\n"
                products_text += f"   💰 ${product['price']} | 📂 {category['name']} | 📁 {subcategory['name']}\n"
                products_text += f"   📝 {product['description']}\n"
                products_text += f"   ⭐ Features: {', '.join(product.get('features', []))}\n\n"
            
            await update.message.reply_text(products_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def delete_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a product: /deleteproduct PRODUCT_ID"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text("📝 Usage: /deleteproduct PRODUCT_ID")
            return
        
        try:
            product_id = int(context.args[0])
            data = self.load_data()
            
            initial_count = len(data['products'])
            data['products'] = [p for p in data['products'] if p['id'] != product_id]
            
            if len(data['products']) == initial_count:
                await update.message.reply_text(f"❌ Product ID {product_id} not found.")
                return
            
            self.save_data(data)
            await update.message.reply_text(f"✅ Product ID {product_id} deleted successfully.")
            
        except ValueError:
            await update.message.reply_text("❌ Product ID must be a number")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def delete_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a category and its subcategories/products: /deletecategory CATEGORY_ID"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text("📝 Usage: /deletecategory CATEGORY_ID")
            return
        
        try:
            category_id = int(context.args[0])
            data = self.load_data()
            
            # Check if category exists
            category_exists = any(cat['id'] == category_id for cat in data['categories'])
            if not category_exists:
                await update.message.reply_text(f"❌ Category ID {category_id} not found.")
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
            
            self.save_data(data)
            
            await update.message.reply_text(
                f"✅ Category '{category_name}' (ID: {category_id}) deleted successfully.\n\n"
                f"🗑️ Also deleted:\n"
                f"• {len(subcategories_deleted)} subcategories\n"
                f"• {len(products_deleted)} products"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Category ID must be a number")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def delete_subcategory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a subcategory and its products: /deletesubcategory SUBCATEGORY_ID"""
        user_id = update.message.from_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            await update.message.reply_text("📝 Usage: /deletesubcategory SUBCATEGORY_ID")
            return
        
        try:
            subcategory_id = int(context.args[0])
            data = self.load_data()
            
            # Check if subcategory exists
            subcategory_exists = any(sub['id'] == subcategory_id for sub in data['subcategories'])
            if not subcategory_exists:
                await update.message.reply_text(f"❌ Subcategory ID {subcategory_id} not found.")
                return
            
            # Get subcategory name and category info for confirmation
            subcategory = next((sub for sub in data['subcategories'] if sub['id'] == subcategory_id), None)
            category_name = next((cat['name'] for cat in data['categories'] if cat['id'] == subcategory['category_id']), "Unknown")
            
            # Delete subcategory
            data['subcategories'] = [s for s in data['subcategories'] if s['id'] != subcategory_id]
            
            # Delete related products
            products_deleted = [p for p in data['products'] if p['subcategory_id'] == subcategory_id]
            data['products'] = [p for p in data['products'] if p['subcategory_id'] != subcategory_id]
            
            self.save_data(data)
            
            await update.message.reply_text(
                f"✅ Subcategory '{subcategory['name']}' (ID: {subcategory_id}) deleted successfully.\n\n"
                f"📂 Category: {category_name}\n"
                f"🗑️ Also deleted: {len(products_deleted)} products"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Subcategory ID must be a number")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")