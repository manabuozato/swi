# cache_manager.py

import time
import os
import json

class TimedCache:
    def __init__(self, cache_dir, expiration_time=86400):  # デフォルトは1日
        self.cache_dir = cache_dir
        self.expiration_time = expiration_time
        os.makedirs(cache_dir, exist_ok=True)

    def get(self, key):
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
            if time.time() - data['timestamp'] < self.expiration_time:
                return data['value']
        return None

    def set(self, key, value):
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        data = {
            'timestamp': time.time(),
            'value': value
        }
        with open(file_path, 'w') as f:
            json.dump(data, f)

    def clear_expired(self):
        for filename in os.listdir(self.cache_dir):
            file_path = os.path.join(self.cache_dir, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
            if time.time() - data['timestamp'] > self.expiration_time:
                os.remove(file_path)

# キャッシュインスタンスの作成
cache = TimedCache('cache_directory', 86400 * 7)  # 1週間のキャッシュ