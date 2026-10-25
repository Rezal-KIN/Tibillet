# Native TiBillet image; database and transaction code remain native.
FROM tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.source="https://github.com/Rezal-KIN/Tibillet" \
      org.opencontainers.image.revision=$SOURCE_COMMIT \
      org.opencontainers.image.base.name="tibillet/fedow@sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83"
COPY --chown=fedow:fedow deploy/Fedow/settings.py /home/fedow/Fedow/fedowallet_django/settings.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/__init__.py /home/fedow/Fedow/cawl_fedow/__init__.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/apps.py /home/fedow/Fedow/cawl_fedow/apps.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/management/__init__.py /home/fedow/Fedow/cawl_fedow/management/__init__.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/management/commands/__init__.py /home/fedow/Fedow/cawl_fedow/management/commands/__init__.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/management/commands/install.py /home/fedow/Fedow/cawl_fedow/management/commands/install.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/management/commands/reconcile_cawl_wallet_refunds.py /home/fedow/Fedow/cawl_fedow/management/commands/reconcile_cawl_wallet_refunds.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/migrations/0001_initial.py /home/fedow/Fedow/cawl_fedow/migrations/0001_initial.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/migrations/0002_walletrefundrequest_walletrefund_and_more.py /home/fedow/Fedow/cawl_fedow/migrations/0002_walletrefundrequest_walletrefund_and_more.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/migrations/__init__.py /home/fedow/Fedow/cawl_fedow/migrations/__init__.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/models.py /home/fedow/Fedow/cawl_fedow/models.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/services.py /home/fedow/Fedow/cawl_fedow/services.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/refunds.py /home/fedow/Fedow/cawl_fedow/refunds.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/tests.py /home/fedow/Fedow/cawl_fedow/tests.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/test_wallet_refunds.py /home/fedow/Fedow/cawl_fedow/test_wallet_refunds.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/urls.py /home/fedow/Fedow/cawl_fedow/urls.py
COPY --chown=fedow:fedow deploy/Fedow/cawl_fedow/views.py /home/fedow/Fedow/cawl_fedow/views.py
COPY --chown=fedow:fedow payment_providers/__init__.py /home/fedow/Fedow/payment_providers/__init__.py
COPY --chown=fedow:fedow payment_providers/cawl.py /home/fedow/Fedow/payment_providers/cawl.py
RUN poetry run pip install --no-cache-dir onlinepayments-sdk-python3==10.2.0
COPY --chown=fedow:fedow deploy/source/admin-templates/admin/base_site.html /home/fedow/Fedow/source_templates/admin/base_site.html
RUN python3 -m compileall -q fedowallet_django/settings.py
