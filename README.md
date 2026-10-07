# OpenCode Render Relay 🚀

A lightweight, zero-dependency Node.js edge relay designed to run on **[Render](https://render.com)** (or any cloud container) as a reliable proxy for OpenCode Zen.

## Features

- **100% Free** on Render's free tier (750 instance hours / month).
- **Runs on AWS Infrastructure:** Never triggers Cloudflare-to-Cloudflare loop limits (Error 1000).
- **Full Streaming Support:** Real-time Server-Sent Events (SSE) streaming pass-through for model outputs.
- **Header & Client Authentication:** Supports optional `RELAY_TOKEN` Bearer authentication.
- **Universal Routing:**
  - Supports `pi-bansos` relay headers (`x-relay-target` / `x-relay-path`).
  - Supports path-based API forwarding (`/v1/chat/completions`, `/v1/responses`).
- **OpenCode Fingerprinting:** Enforces valid OpenCode client User-Agents to prevent free-tier blocks.

## Deployment on Render

1. Fork or push this repository to your GitHub account.
2. In the **[Render Dashboard](https://dashboard.render.com)**, click **New +** $\rightarrow$ **Web Service**.
3. Select this repository.
4. Configure:
   - **Environment:** `Node`
   - **Build Command:** *(leave empty or `npm install`)*
   - **Start Command:** `node index.js`
   - **Instance Type:** `Free`
5. *(Optional)* Under **Environment Variables**, set:
   - `RELAY_TOKEN`: A secret password of your choice (e.g. `my-relay-token`).
6. Click **Deploy Web Service**.

Your service will be live at:
`https://<your-service-name>.onrender.com`

## Usage with `omp` / `pi-bansos`

Update `~/.omp/agent/pi-bansos-relay-state.json`:

```json
{
  "enabled": true,
  "url": "https://<your-service-name>.onrender.com"
}
```

Or toggle live in the TUI:
```text
/bansos url https://<your-service-name>.onrender.com
/bansos on
```
