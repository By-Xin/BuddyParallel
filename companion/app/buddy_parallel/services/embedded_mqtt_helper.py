from __future__ import annotations


def build_helper_html(api_base_url: str) -> str:
    api_base = api_base_url.rstrip("/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BuddyParallel MQTT Bridge</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      padding: 20px;
      background: #0f1720;
      color: #e2e8f0;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
    }}
  </style>
</head>
<body>
  <pre id="status">Starting BuddyParallel MQTT notice bridge...</pre>
  <script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
  <script>
    (() => {{
      const API_BASE = {api_base!r};
      const statusEl = document.getElementById("status");
      let config = null;
      let client = null;
      let lastStatusKey = "";

      function render(text) {{
        statusEl.textContent = text;
      }}

      async function postJson(path, payload) {{
        const response = await fetch(API_BASE + path, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          cache: "no-store",
          body: JSON.stringify(payload),
        }});
        if (!response.ok) {{
          throw new Error("bridge POST " + path + " failed with " + response.status);
        }}
        return response.json().catch(() => ({{ ok: true }}));
      }}

      async function reportStatus({{ connected = false, error = "", summary = "" }}) {{
        const trimmedError = String(error || "").slice(0, 160);
        const trimmedSummary = String(summary || "").slice(0, 40);
        const key = JSON.stringify([connected, trimmedError, trimmedSummary]);
        render(trimmedError || trimmedSummary || (connected ? "MQTT connected" : "MQTT idle"));
        if (key === lastStatusKey) {{
          return;
        }}
        lastStatusKey = key;
        try {{
          await postJson("/bridge/mqtt-status", {{
            connected,
            last_error: trimmedError,
            last_message_summary: trimmedSummary,
          }});
        }} catch (_) {{
        }}
      }}

      async function loadConfig() {{
        const response = await fetch(API_BASE + "/bridge/mqtt-config", {{ cache: "no-store" }});
        if (!response.ok) {{
          throw new Error("helper config request failed with " + response.status);
        }}
        const payload = await response.json();
        if (!payload.ok) {{
          throw new Error(payload.error || "helper config unavailable");
        }}
        config = {{
          url: payload.url,
          topic: payload.topic,
          username: payload.username || "",
          password: payload.password || "",
          clientId: payload.clientId || "",
          keepaliveSeconds: payload.keepaliveSeconds || 60,
        }};
      }}

      async function forwardNotice(topic, message, packet) {{
        let payload = null;
        try {{
          payload = JSON.parse(String(message));
        }} catch (_) {{
          await reportStatus({{
            connected: true,
            error: "Ignored non-JSON MQTT payload",
          }});
          return;
        }}
        if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {{
          await reportStatus({{
            connected: true,
            error: "Ignored MQTT payload with unsupported type",
          }});
          return;
        }}
        try {{
          await postJson("/bridge/mqtt-notice", {{
            topic,
            retain: Boolean(packet && packet.retain),
            payload,
          }});
        }} catch (error) {{
          await reportStatus({{
            connected: false,
            error: String(error),
          }});
        }}
      }}

      async function boot() {{
        try {{
          await loadConfig();
          if (!window.mqtt || typeof window.mqtt.connect !== "function") {{
            throw new Error("mqtt.js failed to load");
          }}
          await reportStatus({{
            connected: false,
            summary: "Connecting MQTT bridge...",
          }});

          // Stay intentionally close to the user's proven mqtt.js browser test.
          client = window.mqtt.connect(config.url, {{
            username: config.username,
            password: config.password,
            protocolVersion: 4,
            keepalive: Number(config.keepaliveSeconds || 60),
            reconnectPeriod: 2000,
            clientId: config.clientId || undefined,
          }});

          client.on("connect", () => {{
            reportStatus({{
              connected: true,
              summary: "MQTT connected",
            }});
            client.subscribe(config.topic, (error) => {{
              if (error) {{
                reportStatus({{
                  connected: false,
                  error: "Subscribe failed: " + error.message,
                }});
                return;
              }}
              reportStatus({{
                connected: true,
                summary: "Subscribed " + String(config.topic || "").slice(0, 28),
              }});
            }});
          }});

          client.on("reconnect", () => {{
            reportStatus({{
              connected: false,
              summary: "Reconnecting MQTT bridge...",
            }});
          }});

          client.on("close", () => {{
            reportStatus({{
              connected: false,
              error: "MQTT websocket closed",
            }});
          }});

          client.on("offline", () => {{
            reportStatus({{
              connected: false,
              error: "MQTT bridge offline",
            }});
          }});

          client.on("error", (error) => {{
            reportStatus({{
              connected: false,
              error: "MQTT error: " + (error && error.message ? error.message : String(error)),
            }});
          }});

          client.on("packetsend", (packet) => {{
            const cmd = packet && packet.cmd ? String(packet.cmd) : "";
            if (cmd === "connect") {{
              reportStatus({{
                connected: false,
                summary: "Sent MQTT CONNECT",
              }});
            }} else if (cmd === "subscribe") {{
              reportStatus({{
                connected: false,
                summary: "Sent MQTT SUBSCRIBE",
              }});
            }}
          }});

          client.on("packetreceive", (packet) => {{
            const cmd = packet && packet.cmd ? String(packet.cmd) : "";
            if (cmd === "connack") {{
              const code = packet && typeof packet.returnCode !== "undefined" ? packet.returnCode : "?";
              reportStatus({{
                connected: false,
                summary: "Received CONNACK " + code,
              }});
            }} else if (cmd === "suback") {{
              reportStatus({{
                connected: true,
                summary: "Received SUBACK",
              }});
            }}
          }});

          client.on("message", (topic, message, packet) => {{
            forwardNotice(topic, message.toString(), packet);
          }});

          window.addEventListener("beforeunload", () => {{
            try {{
              client.end(true);
            }} catch (_) {{
            }}
          }});
        }} catch (error) {{
          await reportStatus({{
            connected: false,
            error: String(error),
          }});
          setTimeout(boot, 3000);
        }}
      }}

      boot();
    }})();
  </script>
</body>
</html>
""".strip()
