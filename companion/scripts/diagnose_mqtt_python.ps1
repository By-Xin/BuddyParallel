param(
    [string]$PythonExe = "",
    [switch]$SkipNetwork
)

$ErrorActionPreference = "Stop"
$ReportPath = Join-Path $PSScriptRoot ("mqtt-python-diagnose-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
New-Item -ItemType File -Path $ReportPath -Force | Out-Null

function Write-Report {
    param([string]$Text = "")
    Write-Host $Text
    Add-Content -LiteralPath $ReportPath -Value $Text
}

function Write-Section {
    param([string]$Title)
    Write-Report ""
    Write-Report ("==== " + $Title + " ====")
}

function Write-Lines {
    param($Value)
    if ($null -eq $Value) {
        return
    }
    $text = ($Value | Out-String -Width 400).TrimEnd()
    if ($text.Length -eq 0) {
        return
    }
    foreach ($line in ($text -split "`r?`n")) {
        Write-Report $line
    }
}

function Invoke-ReportBlock {
    param(
        [string]$Title,
        [scriptblock]$Block
    )
    Write-Section $Title
    try {
        $result = & $Block
        Write-Lines $result
    } catch {
        Write-Report ("ERROR: " + $_.Exception.Message)
        if ($_.ScriptStackTrace) {
            Write-Lines $_.ScriptStackTrace
        }
    }
}

function Resolve-PythonExecutable {
    param([string]$Preferred)

    $candidates = @()
    if ($Preferred) {
        $candidates += $Preferred
    }
    $repoVenv = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"
    $candidates += @(
        "D:\Anaconda\python.exe",
        $repoVenv,
        "python"
    )

    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        try {
            $command = Get-Command $candidate -ErrorAction Stop
            if ($command.Source) {
                return $command.Source
            }
        } catch {
        }
    }
    return $null
}

function Invoke-PythonSnippet {
    param(
        [string]$PythonPath,
        [string]$Code
    )

    if (-not $PythonPath) {
        throw "Python executable not found."
    }

    $tempPath = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".py")
    try {
        Set-Content -LiteralPath $tempPath -Value $Code -Encoding UTF8
        & $PythonPath $tempPath 2>&1
    } finally {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1500)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

$ResolvedPython = Resolve-PythonExecutable -Preferred $PythonExe
$ConfigPath = Join-Path $env:APPDATA "BuddyParallel\config.json"
$ClashConfigPath = Join-Path $env:APPDATA "io.github.clash-verge-rev.clash-verge-rev\config.yaml"
$ClashVergePath = Join-Path $env:APPDATA "io.github.clash-verge-rev.clash-verge-rev\verge.yaml"

Write-Section "Report"
Write-Report ("Report file: " + $ReportPath)
Write-Report ("Repo root: " + (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))
Write-Report ("Skip network: " + $SkipNetwork.ToString())

Invoke-ReportBlock "System" {
    @(
        "ComputerName: $env:COMPUTERNAME",
        "UserName: $env:USERNAME",
        "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "PowerShell: $($PSVersionTable.PSVersion)",
        "PythonExe: $(if ($ResolvedPython) { $ResolvedPython } else { '<not found>' })"
    )
}

Invoke-ReportBlock "BuddyParallel Config" {
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        return "Config not found: $ConfigPath"
    }
    $cfg = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    [pscustomobject]@{
        notice_transport              = $cfg.notice_transport
        notice_mqtt_url               = $cfg.notice_mqtt_url
        notice_mqtt_topic             = $cfg.notice_mqtt_topic
        notice_mqtt_username          = $cfg.notice_mqtt_username
        notice_mqtt_password          = if ([string]::IsNullOrWhiteSpace($cfg.notice_mqtt_password)) { "<missing>" } else { "<set>" }
        notice_mqtt_client_id         = if ([string]::IsNullOrWhiteSpace($cfg.notice_mqtt_client_id)) { "<auto>" } else { $cfg.notice_mqtt_client_id }
        notice_mqtt_keepalive_seconds = $cfg.notice_mqtt_keepalive_seconds
    } | Format-List
}

Invoke-ReportBlock "Proxy Environment" {
    $envRows = Get-ChildItem Env: |
        Where-Object { $_.Name -match 'proxy|http|https|all_proxy|ws' } |
        Sort-Object Name |
        Select-Object Name, Value
    if (-not $envRows) {
        return "No proxy-related environment variables."
    }
    $envRows | Format-Table -AutoSize
}

Invoke-ReportBlock "Active Proxy Processes" {
    $names = "clash-verge", "clash-core-service", "clash-verge-service", "verge-mihomo", "warp"
    $rows = Get-Process -Name $names -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path
    if (-not $rows) {
        return "No Clash/Warp processes found."
    }
    $rows | Sort-Object ProcessName, Id | Format-Table -AutoSize
}

Invoke-ReportBlock "Clash Config Snippet" {
    $rows = @()
    if (Test-Path -LiteralPath $ClashConfigPath) {
        $rows += "config.yaml"
        $rows += Get-Content -LiteralPath $ClashConfigPath |
            Select-String "mixed-port|socks-port|port:|allow-lan|mode:"
    }
    if (Test-Path -LiteralPath $ClashVergePath) {
        $rows += ""
        $rows += "verge.yaml"
        $rows += Get-Content -LiteralPath $ClashVergePath |
            Select-String "enable_system_proxy|proxy_auto_config|verge_mixed_port|verge_socks_port|verge_http_enabled|verge_socks_enabled"
    }
    if (-not $rows) {
        return "Clash config files not found."
    }
    $rows
}

Invoke-ReportBlock "Local Proxy Listener Check" {
    $ports = 7897, 7898, 7899
    $rows = foreach ($port in $ports) {
        [pscustomobject]@{
            Port      = $port
            Listening = Test-TcpPort -HostName "127.0.0.1" -Port $port
        }
    }
    $rows | Format-Table -AutoSize
}

if ($SkipNetwork) {
    Write-Section "Skipped"
    Write-Report "Network probes were skipped."
    Write-Report "Done."
    return
}

Invoke-ReportBlock "TCP 443" {
    Test-NetConnection mqtt.baiying.xin -Port 443 | Format-List
}

Invoke-ReportBlock "HTTPS Direct via Requests" {
    if (-not $ResolvedPython) {
        return "Python executable not found."
    }
    $code = @'
import requests
try:
    r = requests.get("https://mqtt.baiying.xin", timeout=10)
    print("status", r.status_code)
    print(r.text[:200])
except Exception as exc:
    print(type(exc).__name__, exc)
'@
    Invoke-PythonSnippet -PythonPath $ResolvedPython -Code $code
}

Invoke-ReportBlock "HTTPS via Local Proxies" {
    if (-not $ResolvedPython) {
        return "Python executable not found."
    }
    $code = @'
import socket
import requests

targets = []
for port, scheme in ((7897, "http"), (7897, "socks5h"), (7898, "socks5h"), (7899, "http")):
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        targets.append((port, scheme))
    except OSError:
        s.close()

for port, scheme in targets:
    proxy = f"{scheme}://127.0.0.1:{port}"
    print("PROXY", proxy)
    try:
        r = requests.get(
            "https://mqtt.baiying.xin",
            timeout=10,
            proxies={"http": proxy, "https": proxy},
        )
        print("status", r.status_code)
        print(r.text[:120])
    except Exception as exc:
        print(type(exc).__name__, exc)
    print("-" * 40)

if not targets:
    print("No local proxy listeners detected on 7897/7898/7899.")
'@
    Invoke-PythonSnippet -PythonPath $ResolvedPython -Code $code
}

Invoke-ReportBlock "Paho MQTT WSS Probe" {
    if (-not $ResolvedPython) {
        return "Python executable not found."
    }
    $code = @'
import json
import socket
import ssl
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import paho.mqtt.client as mqtt
except Exception as exc:
    print(type(exc).__name__, exc)
    raise SystemExit(0)

try:
    import socks
except Exception:
    socks = None

config_path = Path.home() / "AppData" / "Roaming" / "BuddyParallel" / "config.json"
if not config_path.exists():
    print("ConfigMissing", config_path)
    raise SystemExit(0)

cfg = json.loads(config_path.read_text(encoding="utf-8"))
url = str(cfg.get("notice_mqtt_url") or "").strip()
topic = str(cfg.get("notice_mqtt_topic") or "").strip()
username = str(cfg.get("notice_mqtt_username") or "").strip()
password = str(cfg.get("notice_mqtt_password") or "")
if not url or not topic or not username or not password:
    print("ConfigIncomplete", {"url": bool(url), "topic": bool(topic), "username": bool(username), "password": bool(password)})
    raise SystemExit(0)

candidates = [("direct", None)]

def port_open(port):
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        s.close()
        return False

if socks is not None and port_open(7897):
    candidates.append(("proxy-http-7897", {"proxy_type": socks.HTTP, "proxy_addr": "127.0.0.1", "proxy_port": 7897, "proxy_rdns": True}))
    candidates.append(("proxy-socks5-7897", {"proxy_type": socks.SOCKS5, "proxy_addr": "127.0.0.1", "proxy_port": 7897, "proxy_rdns": True}))
if socks is not None and port_open(7898):
    candidates.append(("proxy-socks5-7898", {"proxy_type": socks.SOCKS5, "proxy_addr": "127.0.0.1", "proxy_port": 7898, "proxy_rdns": True}))

for label, proxy_args in candidates:
    print("===", label, "===")
    events = []
    try:
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=("bp-probe-" + label)[:23],
                transport="websockets",
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )
        except AttributeError:
            client = mqtt.Client(
                client_id=("bp-probe-" + label)[:23],
                transport="websockets",
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )

        client.username_pw_set(username, password)
        client.ws_set_options(path="/mqtt", headers={"Origin": "null"})
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.tls_insecure_set(False)
        if proxy_args:
            client.proxy_set(**proxy_args)

        def on_connect(c, u, f, rc):
            events.append(("connect", rc))
            print("CONNECT", rc)
            c.subscribe(topic, qos=1)

        def on_disconnect(c, u, rc):
            events.append(("disconnect", rc))
            print("DISCONNECT", rc)

        def on_subscribe(c, u, mid, granted_qos):
            events.append(("subscribe", list(granted_qos)))
            print("SUBSCRIBE", granted_qos)

        def on_message(c, u, msg):
            payload = msg.payload.decode("utf-8", errors="replace")
            events.append(("message", msg.topic, payload[:80]))
            print("MESSAGE", msg.topic, payload[:160])

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        client.on_message = on_message

        rc = client.connect("mqtt.baiying.xin", 443, keepalive=30)
        print("connect() rc", rc)
        client.loop_start()
        time.sleep(8)
    except Exception as exc:
        print(type(exc).__name__, exc)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
        print("events", events)
        print("-" * 50)
'@
    Invoke-PythonSnippet -PythonPath $ResolvedPython -Code $code
}

Write-Section "Done"
Write-Report "Please send this whole console output or the report file."
