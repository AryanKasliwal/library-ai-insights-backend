import os
import time
import threading

CACHE_TTL_SECONDS = 86400  # 24 hours

# Tracks {file_path: timestamp_when_downloaded}
_cache_registry: dict = {}
_lock = threading.Lock()


def register_file(file_path: str):
    """Register a file as cached with current timestamp."""
    with _lock:
        _cache_registry[file_path] = time.time()


def cleanup_expired():
    """Delete files that have been cached longer than TTL."""
    now = time.time()
    with _lock:
        expired = [
            path for path, ts in _cache_registry.items()
            if now - ts > CACHE_TTL_SECONDS
        ]
    for path in expired:
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"🗑️ Cache expired, deleted: {path}")
        except Exception as e:
            print(f"⚠️ Failed to delete {path}: {e}")
        with _lock:
            _cache_registry.pop(path, None)


def start_cleanup_scheduler():
    """Run cleanup every hour in a background thread."""
    def _loop():
        while True:
            time.sleep(3600)  # check every hour
            cleanup_expired()

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    print("🧹 Cache cleanup scheduler started.")