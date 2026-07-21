"""In-memory object-store double and a fake S3 session for the R2 binding tests.

:class:`FakeObjectStore` is the store substituted in unit, API, and integration
tests (per the testing strategy: R2 is always faked, no live credentials). The
:class:`FakeS3Session` pair stands in for aioboto3 at the true external boundary so
:class:`~floresu.storage.store.R2ObjectStore` can be exercised without a live bucket.
"""

from __future__ import annotations

from typing import Any


class FakeObjectStore:
    """Records puts in memory and mints a deterministic fake URL per key."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get_url(self, key: str) -> str:
        return f"https://fake-r2.local/{key}?signed=1"


class FakeS3Client:
    """A fake aioboto3 S3 client (async context manager) recording the S3 calls."""

    def __init__(self, session: FakeS3Session) -> None:
        self._session = session

    async def __aenter__(self) -> FakeS3Client:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def put_object(self, **kwargs: Any) -> None:
        self._session.puts.append(kwargs)

    async def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self._session.presigns.append({"operation": operation, **kwargs})
        return "https://signed.example/get"


class FakeS3Session:
    """A fake aioboto3 session whose ``client`` returns a recording S3 client."""

    def __init__(self) -> None:
        self.client_kwargs: list[dict[str, Any]] = []
        self.puts: list[dict[str, Any]] = []
        self.presigns: list[dict[str, Any]] = []

    def client(self, service_name: str, **kwargs: Any) -> FakeS3Client:
        self.client_kwargs.append({"service_name": service_name, **kwargs})
        return FakeS3Client(self)
