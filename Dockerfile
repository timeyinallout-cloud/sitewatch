FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml .
COPY sitewatch/ sitewatch/
RUN pip install --no-cache-dir -e ".[web]"

# The local fallback path (sitewatch.web.local_ops, used only when GitHub
# Actions can't be reached -- see sweep_ops.py) needs its own Chromium.
# `--with-deps` installs the apt packages Chromium needs; running it here
# as root during build means the non-root runtime user never needs to.
RUN playwright install --with-deps chromium

COPY sites.toml .

RUN mkdir -p /data \
    && adduser --system --group --no-create-home app \
    && chown -R app:app /data
VOLUME ["/data"]

EXPOSE 8000
USER app
# Playwright looks for its browser download under $HOME by default; the
# non-root user has no home directory (adduser --no-create-home), so this
# must point at the same path used during the root install above -- same
# class of bug as MatchScout's soccerdata/HOME issue, fixed proactively here.
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
CMD ["uvicorn", "sitewatch.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
