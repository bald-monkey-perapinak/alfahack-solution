FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.12
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN groupadd -g 10001 app && useradd -u 10001 -g app -m app
COPY --chown=app:app backend ./backend
COPY --chown=app:app ml/src ./ml/src
COPY --chown=app:app ml/__init__.py ./ml/__init__.py
COPY --chown=app:app data/samples ./data/samples
COPY ml/data.zip /tmp/organizer-data.zip
RUN python -m backend.package_organizer_data && rm /tmp/organizer-data.zip && mkdir -p runtime contracts && chown -R app:app runtime contracts ml/data
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
