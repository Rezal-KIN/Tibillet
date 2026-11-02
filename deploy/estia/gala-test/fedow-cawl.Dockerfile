# Exact native image already used by the VM; no upstream version change.
FROM tibillet/fedow@sha256:06724f74667cc348b2083d2f1951affb26d1a94452392922029db3e4b48e1bac
COPY patch-fedow-cawl.py /tmp/patch-fedow-cawl.py
RUN python /tmp/patch-fedow-cawl.py
