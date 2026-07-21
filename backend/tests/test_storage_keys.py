"""The persisted-PDF object-key scheme."""

from __future__ import annotations

from floresu.storage.keys import revision_pdf_key


def test_key_is_namespaced_by_user_resume_and_revision() -> None:
    assert revision_pdf_key(7, 42, 3) == "u/7/r/42/rev/3.pdf"


def test_re_exporting_the_same_revision_yields_the_same_key() -> None:
    assert revision_pdf_key(1, 2, 5) == revision_pdf_key(1, 2, 5)


def test_different_revisions_get_distinct_keys() -> None:
    assert revision_pdf_key(1, 2, 1) != revision_pdf_key(1, 2, 2)


def test_different_users_and_resumes_get_distinct_keys() -> None:
    assert revision_pdf_key(1, 2, 1) != revision_pdf_key(9, 2, 1)
    assert revision_pdf_key(1, 2, 1) != revision_pdf_key(1, 9, 1)
