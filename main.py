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
    relay_target = request.headers.get("x-relay-target")
    relay_path = request.headers.get("x-relay-path")
    if relay_target:
        target_url = f"{relay_target.rstrip('/')}{relay_path or '/'}"
    else:
        norm_path = path.strip("/")
        if norm_path in ("response", "responses", "v1/response", "v1/responses"):
            target_path = "/zen/v1/responses"
        elif norm_path in ("chat/completions", "v1/chat/completions"):
            target_path = "/zen/v1/chat/completions"
        elif path.startswith("v1/"):
            target_path = f"/zen/{path}"
        elif path.startswith("zen/"):
            target_path = f"/{path}"
        else:
            target_path = f"/zen/v1/{path}"
        target_url = f"{UPSTREAM_HOST}{target_path}"

    if request.url.query:
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}{request.url.query}"

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

    if "authorization" not in headers:
        headers["authorization"] = "Bearer public"
    if "x-opencode-client" not in headers:
        headers["x-opencode-client"] = "desktop"
    if "x-opencode-session" not in headers:
        import time, random
        now_ms = int(time.time() * 1000)
        val = (~((now_ms * 0x1000) + random.randint(1, 4095))) & 0xFFFFFFFFFFFF
        base62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        rnd = "".join(random.choice(base62) for _ in range(14))
        ses = f"ses_{val:012x}{rnd}"
        headers["x-opencode-session"] = ses
        headers["x-session-affinity"] = ses

    body = await request.body()
    if body and ("/responses" in target_url or "/chat/completions" in target_url):
        try:
            body_json = json.loads(body.decode("utf-8"))
            if "/responses" in target_url:
                body_json["store"] = False
                if "messages" in body_json and "input" not in body_json:
                    inp = []
                    for m in body_json.get("messages", []):
                        c = m.get("content", "")
                        if isinstance(c, list):
                            c = "\n".join(p["text"] if isinstance(p, dict) and "text" in p else str(p) for p in c)
                        inp.append({"type": "message", "role": m.get("role", "user"), "content": c})
                    body_json["input"] = inp
                    del body_json["messages"]
                if isinstance(body_json.get("input"), list):
                    for item in body_json["input"]:
                        if isinstance(item, dict) and isinstance(item.get("content"), list):
                            item["content"] = "\n".join(p["text"] if isinstance(p, dict) and "text" in p else str(p) for p in item["content"])
            body = json.dumps(body_json).encode("utf-8")
            headers["content-length"] = str(len(body))
        except Exception:
            pass

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
