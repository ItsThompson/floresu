# syntax=docker/dockerfile:1

# =============================================================================
# Floresu Grafana image: stock Grafana OSS with the datasource + dashboards
# provisioning baked in at build time.
#
# Baking provisioning into a first-party image (rather than bind-mounting) keeps
# the box-less deploy invariant: over an SSH Docker Context a bind mount resolves
# on the daemon host (the VPS, which has no checkout). The image ships with the
# Prometheus datasource and the Floresu overview dashboard already provisioned;
# nothing lands on the box.
#
# Grafana is provisioned but NON-GATING (spec §12): dashboards are optional and
# never a release gate. The admin password is supplied at runtime via
# GF_SECURITY_ADMIN_PASSWORD (a GitHub secret at deploy; the stock default for
# local dev).
# =============================================================================

FROM grafana/grafana-oss:11.4.0

# Provisioning: the Prometheus datasource and the dashboard provider that loads
# every JSON under /var/lib/grafana/dashboards.
COPY provisioning/ /etc/grafana/provisioning/
COPY dashboards/ /var/lib/grafana/dashboards/

# Anonymous, read-only viewing so the dashboards are usable without a login on
# the internal network; editing still requires the admin credentials.
ENV GF_AUTH_ANONYMOUS_ENABLED=true \
    GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
    GF_USERS_DEFAULT_THEME=light

EXPOSE 3000
