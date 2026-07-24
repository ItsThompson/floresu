"""The shared router block both composition roots mount.

Both apps mount the same eleven product routers (sources, worklog, bullets,
skills, variants, resume render/revision/finalize, jobapps, resumes, search) and
differ only on four axes: the identity resolver, the write actor, the resume edit
channel, and the search embedding provider. This builder takes those four as
parameters and returns the routers in mount order, so the wiring lives in one
place and each app declares only its own out-of-block routers.

The render module and R2 object store are process-wide and identical across the
two apps, so the builder constructs them from settings rather than taking them as
axes.

Wiring only: this composes existing routers and providers; it holds no request
logic of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.jobapps.router import create_jobapps_router
from floresu.jobapps.wiring import build_jobapps_service_provider
from floresu.library.router import create_bullets_router
from floresu.library.wiring import build_bullet_service_provider
from floresu.profile.router import create_sources_router
from floresu.profile.skills.router import create_skills_router
from floresu.profile.skills.wiring import build_skill_service_provider
from floresu.profile.variants.router import create_variants_router
from floresu.profile.variants.wiring import build_variant_service_provider
from floresu.profile.wiring import build_source_service_provider
from floresu.rendering.wiring import build_render_module
from floresu.resumes.finalize_router import create_resume_finalize_router
from floresu.resumes.finalize_wiring import build_resume_finalize_service_provider
from floresu.resumes.render_router import create_resume_render_router
from floresu.resumes.render_wiring import build_resume_render_service_provider
from floresu.resumes.revision_router import create_resume_revision_router
from floresu.resumes.revision_wiring import build_resume_revision_service_provider
from floresu.resumes.router import create_resumes_router
from floresu.resumes.wiring import build_resume_service_provider
from floresu.search.router import create_search_router
from floresu.search.wiring import build_search_service_provider
from floresu.storage.wiring import build_object_store
from floresu.worklog.router import create_worklog_router
from floresu.worklog.wiring import build_worklog_service_provider

if TYPE_CHECKING:
    from fastapi import APIRouter

    from floresu.core.providers import ActorResolver, Identity
    from floresu.core.settings import AppSettings
    from floresu.embedding.provider import EmbeddingProvider
    from floresu.resumes.cow import EditChannel


def build_shared_router_block(
    settings: AppSettings,
    *,
    identity: Identity,
    actor: ActorResolver,
    channel: EditChannel,
    search_provider: EmbeddingProvider,
) -> list[APIRouter]:
    """Build the eleven routers both apps share, in mount order.

    The four axes the two apps differ on are injected: ``identity`` resolves the
    caller at the trust boundary, ``actor`` stamps write provenance, ``channel``
    is the resume edit channel, and ``search_provider`` embeds the search query.
    The render module and object store are identical across apps, so they are
    built here from ``settings`` rather than injected.
    """
    render_module = build_render_module()
    object_store = build_object_store(settings)
    return [
        create_sources_router(build_source_service_provider(), identity=identity, actor=actor),
        create_worklog_router(build_worklog_service_provider(), identity=identity, actor=actor),
        create_bullets_router(build_bullet_service_provider(), identity=identity, actor=actor),
        create_skills_router(build_skill_service_provider(), identity=identity, actor=actor),
        create_variants_router(build_variant_service_provider(), identity=identity, actor=actor),
        # Render mounts before the resumes router so GET /resumes/templates matches
        # ahead of GET /resumes/{resume_id}.
        create_resume_render_router(
            build_resume_render_service_provider(render_module, object_store),
            identity=identity,
            actor=actor,
        ),
        create_resume_revision_router(
            build_resume_revision_service_provider(object_store), identity=identity
        ),
        create_resume_finalize_router(
            build_resume_finalize_service_provider(render_module, object_store),
            identity=identity,
            actor=actor,
        ),
        create_jobapps_router(
            build_jobapps_service_provider(render_module, object_store),
            identity=identity,
            actor=actor,
        ),
        create_resumes_router(
            build_resume_service_provider(),
            identity=identity,
            actor=actor,
            channel=channel,
        ),
        create_search_router(build_search_service_provider(search_provider), identity=identity),
    ]
