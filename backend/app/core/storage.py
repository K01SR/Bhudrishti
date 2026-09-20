import os
import io
import hashlib
from typing import Optional, Tuple
from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class SpatialStorageService:
    def __init__(self):
        self.client: Optional[Minio] = None
        self.bucket = settings.MINIO_BUCKET_NAME
        self.local_fallback_path = settings.LOCAL_STORAGE_PATH
        os.makedirs(self.local_fallback_path, exist_ok=True)
        self._init_client()

    def _init_client(self):
        try:
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ROOT_USER,
                secret_key=settings.MINIO_ROOT_PASSWORD,
                secure=settings.MINIO_USE_SSL,
            )
            # Ensure bucket exists
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except Exception as e:
            # Fallback to local storage if MinIO is not immediately available
            self.client = None

    def put_file(
        self,
        object_name: str,
        data_bytes: bytes,
        content_type: str = "application/octet-stream",
    ) -> Tuple[str, str, int]:
        """
        Stores file and returns (storage_key, sha256_hash, file_size).
        """
        file_size = len(data_bytes)
        file_hash = hashlib.sha256(data_bytes).hexdigest()

        if self.client:
            try:
                self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    data=io.BytesIO(data_bytes),
                    length=file_size,
                    content_type=content_type,
                )
                return object_name, file_hash, file_size
            except Exception:
                pass

        # Local storage fallback
        dest_path = os.path.join(self.local_fallback_path, object_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data_bytes)
        return object_name, file_hash, file_size

    def get_file(self, object_name: str) -> Optional[bytes]:
        """Retrieves raw bytes for object."""
        if self.client:
            try:
                response = self.client.get_object(self.bucket, object_name)
                return response.read()
            except Exception:
                pass

        dest_path = os.path.join(self.local_fallback_path, object_name)
        if os.path.exists(dest_path):
            with open(dest_path, "rb") as f:
                return f.read()
        return None


storage_service = SpatialStorageService()
