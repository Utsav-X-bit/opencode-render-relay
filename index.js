const http = require("node:http");
const https = require("node:https");

const PORT = process.env.PORT || 10000;
const UPSTREAM_HOST = "opencode.ai";
const RELAY_TOKEN = (process.env.RELAY_TOKEN || "").trim();
const DEFAULT_UA = "opencode/1.18.31 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14";

const server = http.createServer((req, res) => {
  // 1. CORS Preflight
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    });
    res.end();
    return;
  }

  // 2. Health Check
  if (req.url === "/" && req.method === "GET" && !req.headers["x-relay-target"]) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "healthy", service: "opencode-render-relay" }));
    return;
  }

  // 3. Optional Authentication Check (if RELAY_TOKEN is configured)
  if (RELAY_TOKEN) {
    const authHeader = req.headers["x-relay-token"] || req.headers["authorization"] || "";
    const token = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (token !== RELAY_TOKEN && authHeader !== RELAY_TOKEN) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Unauthorized access" }));
      return;
    }
  }

  // 4. Resolve Target URL & Path
  // Supports both pi-bansos relay headers and direct path-based forwarding
  const relayTarget = req.headers["x-relay-target"];
  const relayPath = req.headers["x-relay-path"];

  let targetHost = UPSTREAM_HOST;
  let targetPath = req.url;

  if (relayTarget) {
    try {
      const u = new URL(relayTarget);
      targetHost = u.hostname;
      targetPath = (u.pathname.replace(/\/$/, "") || "") + (relayPath || "/");
    } catch {
      targetPath = relayPath || req.url;
    }
  } else if (targetPath.startsWith("/v1/")) {
    targetPath = `/zen${targetPath}`;
  } else if (!targetPath.startsWith("/zen/")) {
    targetPath = `/zen/v1${targetPath}`;
  }

  // 5. Clean and forward headers
  const headers = { ...req.headers };
  delete headers.host;
  delete headers["content-length"];
  delete headers["x-relay-token"];
  delete headers["x-relay-target"];
  delete headers["x-relay-path"];

  // Enforce authentic OpenCode User-Agent
  const ua = headers["user-agent"] || "";
  if (!ua || ua.includes("urllib") || !ua.startsWith("opencode/")) {
    headers["user-agent"] = DEFAULT_UA;
  }

  // 6. Forward request with streaming pass-through
  const upstreamReq = https.request(
    {
      hostname: targetHost,
      port: 443,
      path: targetPath,
      method: req.method,
      headers: headers,
      timeout: 300000,
    },
    (upstreamRes) => {
      const outHeaders = { ...upstreamRes.headers, "Access-Control-Allow-Origin": "*" };
      res.writeHead(upstreamRes.statusCode || 200, outHeaders);
      upstreamRes.pipe(res);
    }
  );

  upstreamReq.on("error", (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Upstream connection error", details: err.message }));
    }
  });

  req.pipe(upstreamReq);
});

server.listen(PORT, () => {
  console.log(`OpenCode Render Relay listening on port ${PORT}`);
});
