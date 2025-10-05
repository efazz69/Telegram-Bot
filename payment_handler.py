import json
import requests
from web3 import Web3
from datetime import datetime, timedelta
import time
import random
from config import CRYPTO_NETWORKS, BLOCKCHAIN_APIS

class PaymentHandler:
    def __init__(self):
        try:
            self.bsc_web3 = Web3(Web3.HTTPProvider(BLOCKCHAIN_APIS['BSC']))
            print("✅ Connected to BSC network")
        except:
            print("❌ Could not connect to BSC network")
            self.bsc_web3 = None
        
        self.price_cache = {}
        self.cache_duration = 300  # 5 minutes
    
    def get_real_time_price(self, crypto_currency):
        """Get real-time cryptocurrency price from Binance API"""
        try:
            # Check if we have a valid cached price
            cache_key = crypto_currency
            if cache_key in self.price_cache:
                cached_price, timestamp = self.price_cache[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    return cached_price
            
            # Binance API for price
            symbols = {
                'BTC': 'BTCUSDT',
                'LTC': 'LTCUSDT',
                'USDT_BEP20': 'USDTUSDT'
            }
            
            symbol = symbols.get(crypto_currency)
            if not symbol:
                return self.get_fallback_price(crypto_currency)
            
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                price = float(data['price'])
                
                # Cache the price
                self.price_cache[cache_key] = (price, time.time())
                return price
            else:
                return self.get_fallback_price(crypto_currency)
                
        except Exception as e:
            print(f"Price fetch error for {crypto_currency}: {e}")
            return self.get_fallback_price(crypto_currency)
    
    def get_fallback_price(self, crypto_currency):
        """Fallback prices if API fails"""
        fallback_prices = {
            'BTC': 45000.0,
            'LTC': 75.0,
            'USDT_BEP20': 1.0
        }
        return fallback_prices.get(crypto_currency, 1.0)
    
    def generate_payment_address(self, crypto_currency, order_id):
        """Generate payment address for specific cryptocurrency"""
        # 🚨 REPLACE THESE WITH YOUR ACTUAL WALLET ADDRESSES 🚨
        addresses = {
            'USDT_BEP20': '0x515a1DA038D2813400912C88Bbd4921836041766',
            'BTC': 'bc1q85ad38ndcd29zgz7d77y5k9hcsurqxaqurzl2g',
            'LTC': 'ltc1q2e3z74c63j5cn2hu0wep5vdrmmf6jv9zf6m4rv'
        }
        
        return addresses.get(crypto_currency)
    
    def check_btc_payment(self, address, expected_amount):
        """Check BTC payments using blockchain API"""
        try:
            url = f"{BLOCKCHAIN_APIS['BTC']}address/{address}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total_received = data.get('chain_stats', {}).get('funded_txo_sum', 0) / 100000000
                return total_received >= expected_amount
        except Exception as e:
            print(f"BTC check error: {e}")
        return False
    
    def check_ltc_payment(self, address, expected_amount):
        """Check LTC payments using blockchain API"""
        try:
            url = f"{BLOCKCHAIN_APIS['LTC']}addrs/{address}/balance"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total_received = data.get('total_received', 0) / 100000000
                return total_received >= expected_amount
        except Exception as e:
            print(f"LTC check error: {e}")
        return False
    
    def check_usdt_bep20_payment(self, address, expected_amount):
        """Check USDT BEP20 payments"""
        try:
            # USDT BEP20 contract ABI (simplified)
            usdt_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            usdt_contract = self.bsc_web3.eth.contract(
                address=Web3.to_checksum_address(CRYPTO_NETWORKS['USDT_BEP20']['usdt_contract']),
                abi=usdt_abi
            )
            
            balance = usdt_contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
            usdt_balance = balance / 10**18
            return usdt_balance >= expected_amount
        except Exception as e:
            print(f"USDT check error: {e}")
        return False
    
    def check_payment(self, crypto_currency, address, expected_amount):
        """Check payment for specific cryptocurrency"""
        checkers = {
            'BTC': self.check_btc_payment,
            'LTC': self.check_ltc_payment,
            'USDT_BEP20': self.check_usdt_bep20_payment
        }
        
        checker = checkers.get(crypto_currency)
        if checker:
            return checker(address, expected_amount)
        return False
    
    def get_crypto_amount(self, usd_amount, crypto_currency):
        """Convert USD amount to cryptocurrency amount using real-time prices"""
        current_price = self.get_real_time_price(crypto_currency)
        crypto_amount = usd_amount / current_price
        
        # Round to appropriate decimal places
        if crypto_currency == 'BTC':
            crypto_amount = round(crypto_amount, 6)
        elif crypto_currency == 'LTC':
            crypto_amount = round(crypto_amount, 4)
        else:
            crypto_amount = round(crypto_amount, 2)
        
        return crypto_amount, current_price