FROM python:3.11-bookworm

RUN mkdir -p /usr/share/man/man1 /usr/share/man/man7 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      postgresql-client \
      nano iputils-ping curl borgbackup cron gettext supervisor \
      libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libdbus-1-3 \
      libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
      libxkbcommon0 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash tibillet
USER tibillet

ENV POETRY_NO_INTERACTION=1

## PYTHON
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/tibillet/.local/bin:$PATH"

COPY --chown=tibillet:tibillet ./ /DjangoFiles
COPY --chown=tibillet:tibillet ./bashrc /home/tibillet/.bashrc

WORKDIR /DjangoFiles

RUN poetry install

CMD ["bash", "/DjangoFiles/start.sh"]

# docker build -t lespass .
# docker tag lespass tibillet/lespass:alpha0.9
# docker push tibillet/lespass:alpha0.9

# If nightly
# docker tag lespass tibillet/lespass:nightly
# docker push lespass tibillet/lespass:nightly

# If LTS
# docker tag lespass tibillet/lespass:latest
# docker push lespass tibillet/lespass:latest
