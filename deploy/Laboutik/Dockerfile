# Native TiBillet image; only the audited Gala source files are changed.
FROM tibillet/laboutik@sha256:012f3f1a14b532766f6faa9b6dc55ce53b0f2e65de7035066b96e86b30c006e9
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.source="https://github.com/Rezal-KIN/Tibillet" \
      org.opencontainers.image.revision=$SOURCE_COMMIT \
      org.opencontainers.image.base.name="tibillet/laboutik@sha256:012f3f1a14b532766f6faa9b6dc55ce53b0f2e65de7035066b96e86b30c006e9"
COPY --chown=tibillet:tibillet deploy/Laboutik/views.py /DjangoFiles/webview/views.py
COPY --chown=tibillet:tibillet deploy/Laboutik/validators.py /DjangoFiles/webview/validators.py
COPY --chown=tibillet:tibillet deploy/Laboutik/install.py /DjangoFiles/administration/management/commands/install.py
COPY --chown=tibillet:tibillet deploy/Laboutik/settings.py /DjangoFiles/Cashless/settings.py
COPY --chown=tibillet:tibillet deploy/Laboutik/source_templates/login.html /DjangoFiles/webview/templates/login.html
COPY --chown=tibillet:tibillet deploy/Laboutik/source_templates/kiosk_base.html /DjangoFiles/htmxview/templates/kiosk/base.html
COPY --chown=tibillet:tibillet deploy/Laboutik/source_templates/infos.html /DjangoFiles/htmxview/templates/appsettings/infos.html
COPY --chown=tibillet:tibillet deploy/source/admin-templates/admin/base_site.html /DjangoFiles/source_templates/admin/base_site.html
RUN python3 -m compileall -q webview/views.py webview/validators.py administration/management/commands/install.py Cashless/settings.py
