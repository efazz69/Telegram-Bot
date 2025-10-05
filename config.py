import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7963936009:AAEK3Y4GYCpRk4mbASW2Xvh7u0xedXmR64Y')
ADMIN_ID = os.getenv('ADMIN_ID', '7091475665')

# Payment Configuration
CRYPTO_NETWORKS = {
    'USDT_BEP20': {
        'name': 'USDT (BEP20)',
        'network': 'BSC',
        'decimals': 18,
        'usdt_contract': '0x55d398326f99059fF775485246999027B3197955'
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

# Blockchain API Configuration
BLOCKCHAIN_APIS = {
    'BTC': 'https://blockstream.info/api/',
    'LTC': 'https://api.blockcypher.com/v1/ltc/main/',
    'BSC': 'https://bsc-dataseed.binance.org/'
}

# Render Configuration
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL', 'http://localhost:8000')