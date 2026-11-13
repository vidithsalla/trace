from io import BytesIO

import pytest

from app.core.config import Settings, UnsafeConfigurationError, assert_safe_for_environment
from app.services.storage import FilesystemStorage, StorageKeyError


@pytest.mark.parametrize(
    "key",
    ["../etc/passwd", "a/../../b", "/abs/path", "a//b", "", "a/", ".hidden", "a/\x00b"],
)
def test_filesystem_storage_rejects_unsafe_keys(tmp_path, key):
    storage = FilesystemStorage(str(tmp_path))
    with pytest.raises(StorageKeyError):
        storage.upload_fileobj(key, BytesIO(b"x"), "text/plain")
    assert storage.object_exists(key) is False


def test_filesystem_storage_round_trip_is_atomic(tmp_path):
    storage = FilesystemStorage(str(tmp_path))
    key = "matters/m1/documents/d1/file.txt"
    storage.upload_fileobj(key, BytesIO(b"hello"), "text/plain")
    assert storage.object_exists(key)
    assert storage.get_object_bytes(key) == b"hello"
    assert not any(p.name.startswith(".tmp-") for p in tmp_path.rglob("*"))
    storage.delete_object(key)
    assert not storage.object_exists(key)


def test_unsafe_config_blocked_outside_development():
    with pytest.raises(UnsafeConfigurationError):
        assert_safe_for_environment(Settings(env="production", secret_key="change-me"))
    with pytest.raises(UnsafeConfigurationError):
        assert_safe_for_environment(
            Settings(env="production", secret_key="x" * 40, allow_insecure_demo_login=True)
        )
    assert_safe_for_environment(
        Settings(env="production", secret_key="x" * 40, allow_insecure_demo_login=False)
    )
    assert_safe_for_environment(Settings(env="development"))
