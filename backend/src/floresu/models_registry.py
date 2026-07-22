"""Import every domain's ORM models so their tables attach to the shared
``Base.metadata``.

Importing this module for its side effects guarantees the full schema is
registered in the current process. Both ASGI apps and the Alembic environment
import it, so no process ever runs with a *partial* metadata. A partial metadata
is not a silent problem: a cross-table foreign key (e.g. ``worklog_entries.user_id
-> users.id``) whose target table's model was never imported raises
``NoReferencedTableError`` at query time, so an app that mounts a domain's routes
must also have that domain's referenced tables registered.

Add a domain's model module here as it lands; ``tests/test_models_registry.py``
asserts the referenced tables resolve.
"""

from __future__ import annotations

from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.audit import models as _audit_models  # noqa: F401
from floresu.embedding import models as _embedding_models  # noqa: F401
from floresu.library import models as _library_models  # noqa: F401
from floresu.oauth import models as _oauth_models  # noqa: F401
from floresu.profile import models as _profile_models  # noqa: F401
from floresu.profile.skills import models as _skill_models  # noqa: F401
from floresu.profile.variants import models as _variant_models  # noqa: F401
from floresu.resumes import models as _resume_models  # noqa: F401
from floresu.worklog import models as _worklog_models  # noqa: F401
