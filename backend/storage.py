"""Simple local filesystem storage; no MinIO or cloud credentials required."""
from pathlib import Path

class StorageError(Exception):
    pass

class ObjectNotFound(StorageError):
    pass

class ObjectStorage:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parent / 'data' / 'objects'
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        # Prevent path traversal while allowing keys such as originals/id/file.png.
        p = (self.root / key).resolve()
        if p != self.root.resolve() and self.root.resolve() not in p.parents:
            raise StorageError('Invalid storage key.')
        return p

    def ensure_bucket(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key, data, content_type=None):
        try:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except StorageError:
            raise
        except OSError as e:
            raise StorageError('Could not write to local file storage.') from e

    def get_bytes(self, key):
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as e:
            raise ObjectNotFound('Stored file not found.') from e
        except OSError as e:
            raise StorageError('Could not read from local file storage.') from e

    def delete(self, key):
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass

    def ping(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / '.health-check'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False
