from dataclasses import dataclass
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
BASE_DIR = Path(__file__).resolve().parent
@dataclass
class Config:
    database_path: str = str(BASE_DIR / 'data' / 'pipeline.db')
    storage_path: str = str(BASE_DIR / 'data' / 'objects')
    max_upload_mb: int = 10
    allowed_origins: tuple = ('http://localhost:5173', 'http://127.0.0.1:5173')
    flask_host: str = '127.0.0.1'
    flask_port: int = 5000
    flask_debug: bool = False
    max_attempts: int = 3
    retry_backoff_seconds: float = 5.0
    poll_interval_seconds: float = 1.0
    visibility_timeout_seconds: int = 300
    worker_artificial_delay_seconds: float = 0.0
    @property
    def max_upload_bytes(self): return self.max_upload_mb * 1024 * 1024
    @classmethod
    def from_env(cls):
        if load_dotenv: load_dotenv(BASE_DIR / '.env')
        e = os.environ
        db = e.get('DATABASE_PATH', 'data/pipeline.db')
        storage = e.get('STORAGE_PATH', 'data/objects')
        if not os.path.isabs(db): db = str(BASE_DIR / db)
        if not os.path.isabs(storage): storage = str(BASE_DIR / storage)
        origins = tuple(x.strip() for x in e.get('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip())
        boolean = lambda key, default=False: e.get(key, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')
        return cls(database_path=db, storage_path=storage, max_upload_mb=int(e.get('MAX_UPLOAD_MB', '10')), allowed_origins=origins, flask_host=e.get('FLASK_HOST', '127.0.0.1'), flask_port=int(e.get('FLASK_PORT', '5000')), flask_debug=boolean('FLASK_DEBUG'), max_attempts=int(e.get('MAX_ATTEMPTS', '3')), retry_backoff_seconds=float(e.get('RETRY_BACKOFF_SECONDS', '5')), poll_interval_seconds=float(e.get('POLL_INTERVAL_SECONDS', '1')), visibility_timeout_seconds=int(e.get('VISIBILITY_TIMEOUT_SECONDS', '300')), worker_artificial_delay_seconds=float(e.get('WORKER_ARTIFICIAL_DELAY_SECONDS', '0')))
