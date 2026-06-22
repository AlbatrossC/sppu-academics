import threading
import time

class AllKeysExhaustedError(Exception):
    pass

class KeyManager:
    def __init__(self, api_keys: list[str], cooldown_duration: int = 60):
        if not api_keys:
            raise ValueError("At least one API key is required.")
        self.api_keys = {key: 0.0 for key in api_keys}
        self.cooldown_duration = cooldown_duration
        self.lock = threading.Lock()

    def get_available_key(self) -> str:
        with self.lock:
            now = time.time()
            all_cooling_down = True
            
            for key, cooldown_until in self.api_keys.items():
                if now >= cooldown_until:
                    # Found an available key
                    all_cooling_down = False
                    return key
            
            if all_cooling_down:
                raise AllKeysExhaustedError("All API keys have hit their rate limits and are currently in cooldown.")

    def set_cooldown(self, key: str):
        with self.lock:
            self.api_keys[key] = time.time() + self.cooldown_duration
