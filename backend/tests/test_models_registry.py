"""The model registry must register every table each foreign key references.

If an app entrypoint imports only some model modules, a cross-table foreign key
(e.g. ``worklog_entries.user_id -> users.id``) whose target table was never
imported raises ``NoReferencedTableError`` at query time. Importing the shared
registry must leave no such dangling reference.
"""

from __future__ import annotations

import floresu.models_registry  # noqa: F401  (registers every domain's models)
from floresu.core.orm import Base


def test_registry_registers_the_account_and_worklog_tables() -> None:
    tables = set(Base.metadata.tables)
    assert "users" in tables
    assert "worklog_entries" in tables


def test_every_foreign_key_target_table_is_registered() -> None:
    tables = set(Base.metadata.tables)
    dangling = [
        (table.name, foreign_key.target_fullname)
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.target_fullname.rsplit(".", 1)[0] not in tables
    ]
    assert dangling == []
