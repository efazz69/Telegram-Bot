import json
import os
from datetime import datetime

class UserManager:
    def __init__(self):
        self.users_file = 'users.json'
        self._init_file()
    
    def _init_file(self):
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump({}, f)
    
    def _read_users(self):
        with open(self.users_file, 'r') as f:
            return json.load(f)
    
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
        users[user_id_str]['total_deposited'] += max(0, amount)
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