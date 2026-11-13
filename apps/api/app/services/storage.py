"""Object storage for uploaded documents and generated exports.

Default backend is the local filesystem (a Docker volume shared by api and worker), so a
self-hosted install needs no object-storage service. An S3-compatible backend remains
available with ``TRACE_STORAGE_BACKEND=s3``.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,511}$")


class StorageKeyError(ValueError):
    pass


def validate_key(key: str) -> str:
    """Reject keys that could escape the storage root or are otherwise malformed."""
    if not _KEY_PATTERN.match(key) or ".." in key.split("/") or "//" in key or key.endswith("/"):
        raise StorageKeyError("invalid storage key")
    return key


class FilesystemStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if self.root not in path.parents:
            raise StorageKeyError("invalid storage key")
        return path

    def ping(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not os.access(self.root, os.W_OK):
            raise RuntimeError("storage root is not writable")

    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fileobj.seek(0)
        # Write to a temp file then rename, so readers never observe a partial object.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                while chunk := fileobj.read(1024 * 1024):
                    handle.write(chunk)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return key

    def get_object_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def object_exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except StorageKeyError:
            return False

    def delete_object(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self) -> None:
        self.client = None

    def _get_client(self):
        if self.client is None:
            import boto3

            self.client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
            )
        return self.client

    def ping(self) -> None:
        self._get_client().head_bucket(Bucket=settings.s3_bucket)

    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str) -> str:
        fileobj.seek(0)
        self._get_client().put_object(
            Bucket=settings.s3_bucket, Key=validate_key(key), Body=fileobj, ContentType=content_type
        )
        return key

    def get_object_bytes(self, key: str) -> bytes:
        response = self._get_client().get_object(Bucket=settings.s3_bucket, Key=validate_key(key))
        with response["Body"] as body:
            return body.read()

    def object_exists(self, key: str) -> bool:
        try:
            self._get_client().head_object(Bucket=settings.s3_bucket, Key=validate_key(key))
        except Exception:
            return False
        return True

    def delete_object(self, key: str) -> None:
        self._get_client().delete_object(Bucket=settings.s3_bucket, Key=validate_key(key))


def _build_storage() -> FilesystemStorage | S3Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return FilesystemStorage(settings.storage_root)


storage_service = _build_storage()
