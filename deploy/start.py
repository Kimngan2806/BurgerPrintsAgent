"""Run one API worker, standalone Next.js and nginx; stop all if one fails."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def nginx_config(port):
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError('PORT must be between 1024 and 65535')
    return '''
worker_processes 1;
pid /tmp/nginx.pid;
error_log /dev/stderr warn;
events { worker_connections 256; }
http {
    include /etc/nginx/mime.types;
    # Do not log design capability URLs, callbacks, or account data.
    access_log off;
    client_max_body_size 26m;
    client_body_temp_path /tmp/nginx-body;
    proxy_temp_path /tmp/nginx-proxy;
    map $http_upgrade $connection_upgrade { default upgrade; '' close; }
    server {
        listen PORT_PLACEHOLDER;
        server_name _;
        location /api/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 240s;
            proxy_send_timeout 240s;
        }
        location = /health {
            proxy_pass http://127.0.0.1:8000/health;
        }
        location / {
            proxy_pass http://127.0.0.1:3000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_read_timeout 240s;
        }
    }
}
'''.replace('PORT_PLACEHOLDER', str(port))


def main():
    config = Path('/tmp/burgerprints-nginx.conf')
    config.write_text(nginx_config(os.environ.get('PORT', '10000')))
    external_url = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
    if external_url:
        os.environ.setdefault('PUBLIC_FILE_BASE_URL', external_url)
        os.environ.setdefault('CORS_ORIGINS', external_url)
    api_env = dict(os.environ, WEB_CONCURRENCY='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    frontend_env = dict(os.environ, HOSTNAME='127.0.0.1', PORT='3000', NODE_OPTIONS='--max-old-space-size=128')
    if external_url:
        frontend_env['__NEXT_PRIVATE_ORIGIN'] = external_url
    commands = [
        ([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000',
          '--workers', '1', '--no-access-log', '--timeout-graceful-shutdown', '20'], '/app/backend', api_env),
        (['node', 'server.js'], '/app/frontend', frontend_env),
        (['nginx', '-c', str(config), '-g', 'daemon off;'], '/app', dict(os.environ)),
    ]
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    exit_code = 0
    try:
        for command, cwd, env in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env))
        while not stopping:
            failed = [child for child in children if child.poll() is not None]
            if failed:
                exit_code = failed[0].returncode or 1
                break
            time.sleep(.25)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 25
        for child in children:
            try:
                child.wait(timeout=max(.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
