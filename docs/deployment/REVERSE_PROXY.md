# Emsalist Reverse Proxy Configuration

Emsalist is designed to run behind a reverse proxy (nginx, Caddy, cloud load balancer).

## Nginx Example

```nginx
upstream emsalist_api {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/example.com.crt;
    ssl_certificate_key /etc/ssl/example.com.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Request size limit (must match app max_upload_size_bytes)
    client_max_body_size 16m;

    # Timeouts
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;

    location / {
        proxy_pass http://emsalist_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

## HTTPS Termination

- HTTPS is terminated at the reverse proxy, not in the application
- The app sets `Strict-Transport-Security` header (proxy should also set it)
- `--proxy-headers` flag enables the app to trust `X-Forwarded-*` headers
- Configure `ALLOWED_HOSTS` to match your domain(s)

## Rate Limiting

- Application provides in-memory rate limiting (60 req/60s for non-localhost clients)
- For production, rate limiting should also be configured at the reverse proxy level
- Recommended nginx rate limiting:
  ```nginx
  limit_req_zone $binary_remote_addr zone=api:10m rate=120r/m;
  limit_req zone=api burst=20 nodelay;
  ```

## Trusted Proxy Range

The application trusts `X-Forwarded-*` headers when `--proxy-headers` is enabled.
In production, ensure only the reverse proxy can send these headers.
Use firewall rules or network policies to restrict direct access to the app container.

## WebSocket Support

Emsalist does not currently use WebSockets.
If added in future, ensure the proxy supports WebSocket upgrade.

## Streaming Uploads

File uploads use streaming (`Transfer-Encoding: chunked` via multipart).
Ensure proxy timeouts allow for uploads up to `max_upload_size_bytes` (default 15 MB).
