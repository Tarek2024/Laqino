FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir cryptography==44.0.0
COPY server.py notif.py account.py market.py market_seed.py gsearch.py products.py rx.py chat.py svc.py overview.py fcm.py lsocial.py bulk_import.py exchange.py setup_initial.py backup_restore.py ./
COPY static ./static
ENV HOST=0.0.0.0 PORT=8000 LAQINO_DB=/data/laqino.db LAQINO_UPLOADS=/data/uploads
VOLUME /data
EXPOSE 8000
RUN useradd -m app && mkdir /data && chown app /data
USER app
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "server.py"]
