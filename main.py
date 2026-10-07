import json
import os
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from curl_cffi import requests

app = FastAPI()

UPSTREAM_HOST = "https://opencode.ai"
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "").strip()
DEFAULT_UA = "opencode/1.18.31 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14"

@app.api_route("/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def relay_all(request: Request, path: str):
    # 1. CORS Preflight
    if request.method == "OPTIONS":
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
            },
        )

    # 2. Health check
    if path in ("", "/") and not request.headers.get("x-relay-target"):
        return JSONResponse({"status": "healthy", "service": "opencode-render-relay-python"})

    # 3. Optional Authentication Check
    if RELAY_TOKEN:
        token = request.headers.get("x-relay-token") or request.headers.get("authorization", "")
        token = token.replace("Bearer ", "").strip()
        if token != RELAY_TOKEN and request.headers.get("x-relay-token") != RELAY_TOKEN:
            return JSONResponse({"error": "Unauthorized access"}, status_code=401)

    # 4. Path mapping (supports pi-bansos relay headers and direct path forwarding)
    relay_path = request.headers.get("x-relay-path")
    if relay_path:
        target_path = relay_path
    elif path.startswith("v1/"):
        target_path = f"/zen/{path}"
    elif path.startswith("zen/"):
        target_path = f"/{path}"
    else:
        target_path = f"/zen/v1/{path}"

    target_url = f"{UPSTREAM_HOST}{target_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # 5. Header sanitization
    headers = {}
    for k, v in request.headers.items():
        kl = k.lower()
        if kl not in ("host", "content-length", "x-relay-token", "x-relay-target", "x-relay-path"):
            headers[k] = v

    headers["host"] = "opencode.ai"
    ua = headers.get("user-agent", "")
    if not ua or not ua.startswith("opencode/"):
        headers["user-agent"] = DEFAULT_UA

    body = await request.body()
    is_stream = (
        "text/event-stream" in headers.get("accept", "")
        or b'"stream":true' in body
        or b'"stream": true' in body
    )

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body if body else None,
            impersonate="chrome124",
            stream=is_stream,
            timeout=300 if is_stream else 60,
        )

        if is_stream:
            def stream_gen():
                for chunk in resp.iter_content(chunk_size=4096):
                    yield chunk

            return StreamingResponse(
                stream_gen(),
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "text/event-stream"),
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
                headers={"Access-Control-Allow-Origin": "*"},
            )
    except Exception as e:
        return JSONResponse({"error": "Upstream connection error", "details": str(e)}, status_code=502)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
