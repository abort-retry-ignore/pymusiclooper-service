# pymusiclooper-service

A minimal Docker HTTP service wrapping [pymusiclooper](https://github.com/arkrow/PyMusicLooper).

Accepts a raw audio file upload, detects seamless loop points, and returns them as JSON. Intended as a sidecar for applications that need loop detection without bundling the heavy Python/LLVM dependency stack.

## API

### `GET /health`
Returns `{"ok": true}` when the service is ready.

### `POST /detect-loop`
- **Body**: raw audio file bytes (`Content-Type: application/octet-stream`)
- **200**: `{"loop_start": <samples>, "loop_end": <samples>}`
- **404**: `{"error": "no loop detected"}` — file is valid but no loop was found
- **500**: `{"error": "<message>"}` — unexpected failure

Loop points are returned in **samples**. Divide by the file's sample rate to get seconds.

## Usage

### Build

```bash
docker build -t pymusiclooper:local .
```

### Run standalone

```bash
docker compose up
# or
docker run -p 7070:7070 pymusiclooper:local
```

### Use from another compose project

```yaml
services:
  pymusiclooper:
    image: pymusiclooper:local
    ports:
      - "7070:7070"
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:7070/health')\""]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

Set `PYMUSICLOOPER_URL=http://pymusiclooper:7070` in your app container and POST audio bytes to `/detect-loop`.

## Configuration

| Env var               | Default | Description          |
|-----------------------|---------|----------------------|
| `PYMUSICLOOPER_PORT`  | `7070`  | Port to listen on    |
