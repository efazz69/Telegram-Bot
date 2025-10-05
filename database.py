import json
import os
from datetime import datetime, timedelta

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
        with open(filename, 'r') as f:
            return json.load(f)
    
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