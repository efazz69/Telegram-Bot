# Telegram Crypto Store Bot

A complete cryptocurrency store bot for Telegram with user profiles, balance system, and admin management.

## Features
- 👤 User profiles with balance tracking
- 💰 Add balance with multiple cryptocurrencies
- 🛍️ Category and subcategory product organization
- 🤖 Admin commands for product management
- 💱 Real-time crypto price feeds
- 🔒 Secure payment processing

## Setup Instructions

### 1. Prerequisites
- Python 3.8+
- Telegram Bot Token from @BotFather
- Your Telegram User ID

### 2. Local Development
```bash
# Clone and setup
git clone <your-repo>
cd telegram-crypto-bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your BOT_TOKEN and ADMIN_ID

# Run locally
python bot.py