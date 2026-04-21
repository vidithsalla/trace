from typing import BinaryIO

import boto3

from app.core.config import settings


class StorageService:
    def __init__(self) -> None:
        self.client = None

    def _ensure_bucket(self) -> None:
        if self.client is None:
            return
        buckets = {bucket["Name"] for bucket in self.client.list_buckets().get("Buckets", [])}
        if settings.minio_bucket not in buckets:
            self.client.create_bucket(Bucket=settings.minio_bucket)

    def _get_client(self):
        if self.client is None:
            self.client = boto3.client(
                "s3",
                endpoint_url=f"http://{settings.minio_endpoint}",
                aws_access_key_id=settings.minio_access_key,
                aws_secret_access_key=settings.minio_secret_key,
            )
            self._ensure_bucket()
        return self.client

    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str) -> str:
        client = self._get_client()
        fileobj.seek(0)
        client.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=fileobj,
            ContentType=content_type,
        )
        return key

    def get_object_bytes(self, key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(Bucket=settings.minio_bucket, Key=key)
        with response["Body"] as body:
            return body.read()

    def object_exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=settings.minio_bucket, Key=key)
        except Exception:
            return False
        return True

    def delete_object(self, key: str) -> None:
        client = self._get_client()
        client.delete_object(Bucket=settings.minio_bucket, Key=key)


storage_service = StorageService()
