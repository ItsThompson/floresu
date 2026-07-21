"""The R2 object-store binding over a fake S3 session (no live credentials).

Exercises :class:`R2ObjectStore` through the injected fake session, asserting it
binds the client to the R2 endpoint, credentials, and pseudo-region, puts the object
with its content type, and presigns a time-limited GET, matching the AC that the R2
client is injected and substituted by a fake in tests.
"""

from __future__ import annotations

import pytest

from floresu.storage.store import R2ObjectStore
from tests.storage_fakes import FakeS3Session


@pytest.fixture
def store_with_session() -> tuple[R2ObjectStore, FakeS3Session]:
    session = FakeS3Session()
    store = R2ObjectStore(
        session,
        bucket="resumes",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        access_key_id="ak",
        secret_access_key="sk",
        presign_ttl_seconds=900,
    )
    return store, session


async def test_put_writes_the_object_with_its_content_type(
    store_with_session: tuple[R2ObjectStore, FakeS3Session],
) -> None:
    store, session = store_with_session
    await store.put("u/1/r/2/rev/1.pdf", b"%PDF-1.7 body", "application/pdf")

    assert session.puts == [
        {
            "Bucket": "resumes",
            "Key": "u/1/r/2/rev/1.pdf",
            "Body": b"%PDF-1.7 body",
            "ContentType": "application/pdf",
        }
    ]
    client_call = session.client_kwargs[0]
    assert client_call["service_name"] == "s3"
    assert client_call["endpoint_url"] == "https://acct.r2.cloudflarestorage.com"
    assert client_call["aws_access_key_id"] == "ak"
    assert client_call["aws_secret_access_key"] == "sk"
    assert client_call["region_name"] == "auto"


async def test_get_url_presigns_a_time_limited_get(
    store_with_session: tuple[R2ObjectStore, FakeS3Session],
) -> None:
    store, session = store_with_session
    url = await store.get_url("u/1/r/2/rev/1.pdf")

    assert url == "https://signed.example/get"
    assert session.presigns == [
        {
            "operation": "get_object",
            "Params": {"Bucket": "resumes", "Key": "u/1/r/2/rev/1.pdf"},
            "ExpiresIn": 900,
        }
    ]
