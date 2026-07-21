"""The object-store port and its Cloudflare R2 (S3-compatible) binding.

The service layer depends on the narrow :class:`ObjectStore` interface (``put`` and
``get_url``); production binds :class:`R2ObjectStore` over an injected aioboto3
session while tests substitute an in-memory fake. R2 speaks the S3 API, so the
binding puts objects and mints presigned GET URLs through the standard S3 client.
The client is injected so no live R2 credentials are exercised in CI, and each
operation opens a short-lived client (aioboto3 clients are async context managers)
rather than pinning one for the whole process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import aioboto3

# R2 exposes an S3-compatible API reached at the account endpoint; ``auto`` is R2's
# single pseudo-region (SigV4 requires a region, and R2 ignores which).
_R2_REGION = "auto"
_S3_SERVICE = "s3"
_GET_OBJECT = "get_object"


class ObjectStore(Protocol):
    """Put an object by key, and mint a time-limited URL to read it back."""

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get_url(self, key: str) -> str: ...


class R2ObjectStore:
    """The production store over an injected S3-compatible (aioboto3) session."""

    def __init__(
        self,
        session: aioboto3.Session,
        *,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        presign_ttl_seconds: int,
    ) -> None:
        self._session = session
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._presign_ttl_seconds = presign_ttl_seconds

    def _client(self) -> Any:
        """Open a short-lived S3 client bound to the R2 endpoint and credentials."""
        return self._session.client(
            _S3_SERVICE,
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name=_R2_REGION,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store ``data`` at ``key`` with the given content type (overwrites)."""
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

    async def get_url(self, key: str) -> str:
        """Mint a time-limited presigned GET URL for ``key`` (download / preview-expand)."""
        async with self._client() as client:
            url: str = await client.generate_presigned_url(
                _GET_OBJECT,
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=self._presign_ttl_seconds,
            )
        return url
