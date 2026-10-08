# Native TiBillet image; database and transaction code remain native.
FROM tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.source="https://github.com/Rezal-KIN/Tibillet" \
      org.opencontainers.image.revision=$SOURCE_COMMIT \
      org.opencontainers.image.base.name="tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83"
COPY --chown=fedow:fedow deploy/Fedow/settings.py /home/fedow/Fedow/fedowallet_django/settings.py
COPY --chown=fedow:fedow deploy/source/admin-templates/admin/base_site.html /home/fedow/Fedow/source_templates/admin/base_site.html
RUN python3 -m compileall -q fedowallet_django/settings.py
