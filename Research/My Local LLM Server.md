---
title: Local LLM Server Runbook
aliases:
  - HP Laptop AI Server
  - Local Qwen Server
tags:
  - local-ai
  - llama-cpp
  - homelab
  - runbook
  - obsidian
updated: 2026-07-16
---

# Local LLM Server Runbook

This is the operating manual for the local LLM server running on the HP laptop. It explains what the server does and provides the commands needed to use, check, start, stop, restart, monitor, secure, and troubleshoot it from both the server and a separate client computer.

The live service is a native Windows `llama.cpp` server. It runs the Qwen2.5 1.5B Instruct model entirely on the CPU and exposes an OpenAI-compatible HTTP API to devices on the trusted home LAN.

> [!IMPORTANT]
> In this document, **server** means the HP laptop running the model. **Client** means the separate computer or application sending API requests.

> [!WARNING]
> This service uses unencrypted HTTP and is intended only for the trusted local network. Never forward port `8000` through the router. Secure access away from home is not currently configured by this deployment.

> [!DANGER]
> Do not paste the real API key into this README or any synced Obsidian note. The key is stored on the server and can be retrieved with a command in this runbook.

## Runbook map

- [[#Quick reference|Quick reference]] - the base URL, model, port, files, and current host address.
- [[#Required server hardening checkpoint|Required hardening]] - fix firewall scope and keep the laptop awake.
- [[#Fastest daily check|Fastest daily check]] - confirm the server and client can reach the model.
- [[#Server-side operations|Server-side operations]] - start, stop, restart, credentials, logs, startup, and local tests.
- [[#Server network and firewall|Server network and firewall]] - LAN address, listener, DHCP, and firewall checks.
- [[#Client-side operations|Client-side operations]] - PowerShell, curl, Python, Postman, and Obsidian configuration.
- [[#API reference|API reference]] - supported endpoints and request fields.
- [[#Troubleshooting|Troubleshooting]] - symptom-based checks and corrections.
- [[#Maintenance|Maintenance]] - versions, updates, resources, and disk checks.

## Quick reference

| Item | Current value |
|---|---|
| Server | HP laptop running Windows |
| LAN address | `192.168.1.66` - DHCP-assigned and may change |
| OpenAI API base | `http://192.168.1.66:8000/v1` |
| Local API base on server | `http://127.0.0.1:8000/v1` |
| Health endpoint | `http://192.168.1.66:8000/health` |
| Chat endpoint | `http://192.168.1.66:8000/v1/chat/completions` |
| Model name | `qwen2.5-1.5b-instruct` |
| Authentication | `Authorization: Bearer <API_KEY>` |
| Port | TCP `8000` |
| Runtime | Native `llama.cpp` / `llama-server.exe` |
| Model file | `models\qwen2.5-1.5b-instruct-q4_k_m.gguf` |
| Startup script | `scripts\start_llama_windows.ps1` |
| Runtime log | `%LOCALAPPDATA%\LocalAIServer\logs\server.log` |
| Automatic start | Runs only after this Windows user signs in; not at the pre-login boot screen |
| Firewall status | Narrow LAN rule exists; two broad `llama-server.exe` rules still need to be disabled |
| Power status | AC lid-close sleep and timed hibernation still need to be disabled for unattended use |

The LAN API base is valid only while the server still has `192.168.1.66`. Use the IP-discovery command below if a client suddenly cannot connect.

## What this server does

```text
Client application
        |
        | OpenAI-compatible HTTP + Bearer API key
        v
Windows TCP 8000 on the HP laptop
        |
        v
llama.cpp, CPU only, one generation at a time
        |
        v
Qwen2.5 1.5B Instruct Q4_K_M
```

The current live server supports:

- OpenAI-compatible chat completions.
- Normal and streamed responses.
- Model discovery through `/v1/models`.
- Health checks through `/health`.
- API-key protection for generation requests.
- LAN access from another computer.
- Automatic launch after Windows sign-in.

The repository also contains FastAPI, Qdrant, embedding, and RAG development code. That stack is **not currently running**. Therefore, the live service does not currently provide:

- `/ready`
- `/generate`
- `/documents/ingest`
- `/retrieve`
- `/rag/query`
- Qdrant-backed storage or document ingestion

Use `/v1/chat/completions` for the currently deployed service.

## Required server hardening checkpoint

Complete this once before relying on the server from another computer. The current Windows state still has a Public Wi-Fi profile, two broad auto-generated `llama-server.exe` firewall rules, AC lid-close sleep, and an AC hibernation timeout.

Open PowerShell **as Administrator** on the HP server and run:

```powershell
$RuleName = "Local AI API TCP 8000 (LAN only)"

# Treat the current home Wi-Fi as a trusted Private network.
Set-NetConnectionProfile `
  -InterfaceAlias "Wi-Fi" `
  -NetworkCategory Private

# Disable both broad Windows-generated llama-server TCP/UDP rules.
Get-NetFirewallRule `
  -DisplayName "llama-server.exe" `
  -ErrorAction SilentlyContinue |
  Disable-NetFirewallRule

# Replace the narrow rule with a Private-profile, LAN-source-only rule.
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule

New-NetFirewallRule `
  -DisplayName $RuleName `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8000 `
  -Profile Private `
  -InterfaceAlias "Wi-Fi" `
  -RemoteAddress "192.168.1.0/24"

# Keep the server awake while connected to AC power.
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```

Verify the result:

```powershell
Get-NetConnectionProfile -InterfaceAlias "Wi-Fi" |
  Select-Object InterfaceAlias, Name, NetworkCategory

Get-NetFirewallRule `
  -DisplayName "llama-server.exe", "Local AI API TCP 8000 (LAN only)" |
  Select-Object DisplayName, Enabled, Direction, Action, Profile

powercfg /query SCHEME_CURRENT SUB_SLEEP
powercfg /qh SCHEME_CURRENT SUB_BUTTONS LIDACTION
```

Expected checkpoint:

- Wi-Fi category is `Private`.
- Both broad `llama-server.exe` rules show `Enabled: False`.
- `Local AI API TCP 8000 (LAN only)` shows `Enabled: True` and `Profile: Private`.
- AC sleep, AC hibernation, and AC lid-close action are all disabled or set to `Do nothing`.

> [!IMPORTANT]
> The automatic launcher still requires this Windows user to sign in after a reboot. Until a pre-login service is configured, a rebooted laptop is not remotely available from the client before sign-in.

## Fastest daily check

### Run on the server in PowerShell

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
```

Expected health response:

```json
{
  "status": "ok"
}
```

### Run on the client in PowerShell

```powershell
$ServerIP = "192.168.1.66"
Test-NetConnection -ComputerName $ServerIP -Port 8000
Invoke-RestMethod -Uri "http://$($ServerIP):8000/health" -TimeoutSec 10
```

`TcpTestSucceeded` should be `True`, and the health response should contain `status: ok`.

## Server-side operations

Run the commands in this section on the HP server using Windows PowerShell.

### Set the project location

```powershell
$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
Set-Location -LiteralPath $ProjectRoot
```

If the project is moved, update `$ProjectRoot` and recreate the Startup shortcut described later.

### Find the current LAN IP and API base

```powershell
$Lan = Get-NetIPConfiguration |
  Where-Object {
    $_.NetAdapter.Status -eq "Up" -and
    $_.IPv4DefaultGateway -and
    $_.IPv4Address.IPAddress -notlike "169.254.*"
  } |
  Select-Object -First 1

$Lan | Select-Object InterfaceAlias,
  @{Name="IPv4"; Expression={$_.IPv4Address.IPAddress}},
  @{Name="PrefixLength"; Expression={$_.IPv4Address.PrefixLength}},
  @{Name="Gateway"; Expression={$_.IPv4DefaultGateway.NextHop}}

$LanIP = $Lan.IPv4Address.IPAddress
"API base: http://$($LanIP):8000/v1"
```

The expected address is currently `192.168.1.66/24`. If it changes, update the API base on every client.

### Load or copy the current API key

The key is stored in the Windows user environment under `LOCAL_AI_API_KEY`.

```powershell
$ApiKey = [Environment]::GetEnvironmentVariable("LOCAL_AI_API_KEY", "User")

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  throw "LOCAL_AI_API_KEY is missing."
}

"API key loaded. Length: $($ApiKey.Length) characters"
```

To copy it to the Windows clipboard for transfer to a trusted client:

```powershell
$ApiKey | Set-Clipboard
```

> [!WARNING]
> Clipboard contents can be read by other applications. Paste the key only into the intended client, then copy harmless text over it. Do not print it during screen sharing.

### Check whether the server is running

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue |
  Select-Object Id, StartTime, CPU,
    @{Name="MemoryMB"; Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}}

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, OwningProcess

Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
```

A healthy server has all three signs:

1. A `llama-server` process exists.
2. A listener exists on `0.0.0.0:8000`.
3. `/health` returns `status: ok`.

### Start the server in the background

```powershell
$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
$StartScript = Join-Path $ProjectRoot "scripts\start_llama_windows.ps1"
$Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

Start-Process -FilePath "powershell.exe" `
  -ArgumentList $Arguments `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Hidden
```

Wait approximately 5-15 seconds for the model to load, then check `/health`.

The startup script safely exits without starting a second model if something is already listening on port `8000`.

### Start visibly for troubleshooting

Use this when the hidden start does not work. The terminal remains attached to the server and displays startup errors. Press `Ctrl+C` to stop it.

```powershell
$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
Set-Location -LiteralPath $ProjectRoot

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\scripts\start_llama_windows.ps1"
```

### Stop the server

This stops only a `llama-server` process that owns port `8000`.

```powershell
$Listeners = @(
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
)

if ($Listeners.Count -eq 0) {
  "The server is already stopped."
} else {
  $ServerPids = $Listeners | Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($ServerPid in $ServerPids) {
    $Process = Get-Process -Id $ServerPid -ErrorAction Stop

    if ($Process.ProcessName -ne "llama-server") {
      throw "Port 8000 belongs to $($Process.ProcessName), not llama-server."
    }

    Stop-Process -Id $ServerPid
    "Stopped llama-server process $ServerPid."
  }
}
```

### Restart the server

Use the stop command above, wait two seconds, then run:

```powershell
Start-Sleep -Seconds 2

$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
$StartScript = Join-Path $ProjectRoot "scripts\start_llama_windows.ps1"
$Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

Start-Process -FilePath "powershell.exe" `
  -ArgumentList $Arguments `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Hidden

Start-Sleep -Seconds 8
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
```

Restart after changing the API key, model, port, thread count, or startup script.

### Verify automatic startup

The current deployment uses a shortcut in the signed-in user's Windows Startup folder:

```powershell
$StartupShortcut = Join-Path `
  ([Environment]::GetFolderPath("Startup")) `
  "Local AI LLM Server.lnk"

Test-Path -LiteralPath $StartupShortcut
Get-Item -LiteralPath $StartupShortcut -ErrorAction SilentlyContinue
```

Expected result: `True`.

The server starts after this Windows user signs in. It does not start at the lock screen before sign-in.

To recreate the shortcut if it is missing or the project was moved:

```powershell
$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
$StartScript = Join-Path $ProjectRoot "scripts\start_llama_windows.ps1"
$StartupShortcut = Join-Path `
  ([Environment]::GetFolderPath("Startup")) `
  "Local AI LLM Server.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($StartupShortcut)
$Shortcut.TargetPath = Join-Path $PSHOME "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Start the local authenticated llama.cpp API server"
$Shortcut.Save()
```

To disable automatic startup without deleting the shortcut:

```powershell
$StartupFolder = [Environment]::GetFolderPath("Startup")

Rename-Item `
  -LiteralPath (Join-Path $StartupFolder "Local AI LLM Server.lnk") `
  -NewName "Local AI LLM Server.lnk.disabled"
```

To enable it again:

```powershell
$StartupFolder = [Environment]::GetFolderPath("Startup")

Rename-Item `
  -LiteralPath (Join-Path $StartupFolder "Local AI LLM Server.lnk.disabled") `
  -NewName "Local AI LLM Server.lnk"
```

Disabling automatic startup does not stop a server that is already running. Use the stop command separately.

### Keep the server awake while plugged in

The model becomes unreachable whenever Windows sleeps or hibernates. Run the following from an Administrator PowerShell session to disable AC sleep, disable AC hibernation, and make closing the lid do nothing while connected to power:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```

Verify the active settings:

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP
powercfg /qh SCHEME_CURRENT SUB_BUTTONS LIDACTION
```

These commands do not change the battery/DC settings. Keep the laptop plugged in and on a hard, ventilated surface. Do not close the lid if doing so obstructs airflow or causes unsafe temperatures.

### View live logs

Follow the log continuously:

```powershell
Get-Content "$env:LOCALAPPDATA\LocalAIServer\logs\server.log" `
  -Tail 100 -Wait
```

Show only the most recent entries and return to the prompt:

```powershell
Get-Content "$env:LOCALAPPDATA\LocalAIServer\logs\server.log" -Tail 100
```

The current log records model startup, inference tasks, token counts, latency, generation speed, cancellations, warnings, and errors. At normal verbosity it does not store complete incoming prompts or JSON request bodies.

### Verify the loaded model

```powershell
$ApiKey = [Environment]::GetEnvironmentVariable("LOCAL_AI_API_KEY", "User")

(Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/v1/models" `
  -Headers @{Authorization = "Bearer $ApiKey"} `
  -TimeoutSec 10).data |
  Select-Object id, owned_by
```

Expected model ID:

```text
qwen2.5-1.5b-instruct
```

### Run a small local completion test

```powershell
$ApiKey = [Environment]::GetEnvironmentVariable("LOCAL_AI_API_KEY", "User")

$Payload = @{
  model = "qwen2.5-1.5b-instruct"
  messages = @(
    @{role = "user"; content = "Reply with exactly: LOCAL AI READY"}
  )
  temperature = 0
  max_tokens = 16
  stream = $false
} | ConvertTo-Json -Depth 6

$Response = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/v1/chat/completions" `
  -Headers @{Authorization = "Bearer $ApiKey"} `
  -ContentType "application/json" `
  -Body $Payload `
  -TimeoutSec 120

$Response.choices[0].message.content
```

Expected response: `LOCAL AI READY`.

### Verify the model file and checksum

```powershell
$ModelFile = "C:\Users\hp\OneDrive\Desktop\New folder\models\qwen2.5-1.5b-instruct-q4_k_m.gguf"

Get-Item -LiteralPath $ModelFile |
  Select-Object FullName, Length, LastWriteTime

Get-FileHash -LiteralPath $ModelFile -Algorithm SHA256
```

Expected size and checksum:

```text
Size:   1117320736 bytes
SHA256: 6A1A2EB6D15622BF3C96857206351BA97E1AF16C30D7A74EE38970E434E9407E
```

> [!WARNING]
> The model currently lives inside a OneDrive-managed folder. Mark the GGUF as **Always keep on this device** so Files On-Demand cannot evict it and model loading is not interrupted by synchronization.

Pin the model from PowerShell:

```powershell
attrib.exe +P -U "$ModelFile"
```

You can also right-click the model in File Explorer and select **Always keep on this device**.

### Rotate the API key

Rotate the key if it is exposed or shared with an untrusted person. This command creates a new 64-character key, stores it in the Windows user environment, and copies it to the clipboard.

```powershell
$Bytes = New-Object byte[] 32
$Generator = [Security.Cryptography.RandomNumberGenerator]::Create()

try {
  $Generator.GetBytes($Bytes)
} finally {
  $Generator.Dispose()
}

$NewApiKey = -join ($Bytes | ForEach-Object { $_.ToString("x2") })

[Environment]::SetEnvironmentVariable(
  "LOCAL_AI_API_KEY",
  $NewApiKey,
  "User"
)

$NewApiKey | Set-Clipboard
"New API key stored and copied to the clipboard. Restart the server now."
```

The running server continues using the old key until it is restarted. Update every client with the new key after the restart.

After saving the new key in a password manager and updating the clients, clear the temporary clipboard and variable:

```powershell
"clipboard cleared" | Set-Clipboard
Remove-Variable NewApiKey, Bytes -ErrorAction SilentlyContinue
```

## Server network and firewall

### Check the listener

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 |
  Select-Object LocalAddress, LocalPort, OwningProcess,
    @{Name="ProcessName"; Expression={(Get-Process -Id $_.OwningProcess).ProcessName}}
```

Expected result: `llama-server` listening on `0.0.0.0:8000`.

### Check the LAN-only firewall rule

> [!WARNING]
> Before the required hardening checkpoint is completed, Windows has two enabled Public-profile rules named `llama-server.exe` that allow TCP and UDP from any remote address. The deployment is not fully LAN-restricted until those rules are disabled and the narrow rule is limited to the Private profile.

```powershell
$RuleName = "Local AI API TCP 8000 (LAN only)"
$Rule = Get-NetFirewallRule `
  -PolicyStore ActiveStore `
  -DisplayName $RuleName `
  -ErrorAction Stop
$Port = $Rule | Get-NetFirewallPortFilter
$Scope = $Rule | Get-NetFirewallAddressFilter

$Rule | Format-List DisplayName, Enabled, Direction, Action, Profile
$Port | Format-List Protocol, LocalPort
$Scope | Format-List RemoteAddress
```

Expected values:

- Enabled: `True`
- Direction: `Inbound`
- Action: `Allow`
- Profile: `Private`
- Protocol: `TCP`
- Local port: `8000`
- Remote address: `192.168.1.0/255.255.255.0`, equivalent to `192.168.1.0/24`

If the rule is missing or wrong, open PowerShell **as Administrator** and run:

```powershell
$RuleName = "Local AI API TCP 8000 (LAN only)"

Set-NetConnectionProfile `
  -InterfaceAlias "Wi-Fi" `
  -NetworkCategory Private

Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule

New-NetFirewallRule `
  -DisplayName $RuleName `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8000 `
  -Profile Private `
  -InterfaceAlias "Wi-Fi" `
  -RemoteAddress "192.168.1.0/24"
```

Inspect the two broad application rules currently created by Windows:

```powershell
Get-NetFirewallRule -DisplayName "llama-server.exe" -ErrorAction SilentlyContinue |
  Format-List DisplayName, Enabled, Direction, Action, Profile
```

The narrow TCP 8000 rule is sufficient. Open PowerShell **as Administrator** and disable both broad rules:

```powershell
Get-NetFirewallRule -DisplayName "llama-server.exe" -ErrorAction SilentlyContinue |
  Disable-NetFirewallRule
```

Verify that the broad rules are disabled and the narrow rule remains enabled:

```powershell
Get-NetFirewallRule `
  -DisplayName "llama-server.exe", "Local AI API TCP 8000 (LAN only)" |
  Select-Object DisplayName, Enabled, Direction, Action, Profile
```

> [!WARNING]
> After the two broad rules are disabled, a home-LAN change away from `192.168.1.0/24` should fail closed. Change the narrow rule's `RemoteAddress` only to the new trusted LAN range; never set it to `Any`.

### Check whether the IP is assigned by DHCP

```powershell
$Lan = Get-NetIPConfiguration |
  Where-Object {
    $_.NetAdapter.Status -eq "Up" -and
    $_.IPv4DefaultGateway -and
    $_.IPv4Address.IPAddress -notlike "169.254.*"
  } |
  Select-Object -First 1

$Lan.IPv4Address |
  Select-Object IPAddress, PrefixLength, PrefixOrigin, AddressState

Get-NetAdapter -InterfaceIndex $Lan.InterfaceIndex |
  Select-Object Name, InterfaceDescription, MacAddress, Status, LinkSpeed
```

`PrefixOrigin: Dhcp` means the IP can change. Use the displayed Wi-Fi MAC address to create a DHCP reservation in the home router for `192.168.1.66`. A router reservation is safer than inventing a manual static Windows address.

## Client-side operations

Run this section on the separate computer that will use the model.

### Values required by any application

Configure an application as follows:

| Application field | Value |
|---|---|
| Provider/API type | OpenAI-compatible or Custom OpenAI |
| Base URL | `http://192.168.1.66:8000/v1` |
| API key | Retrieve from the server; do not use a placeholder |
| Model | `qwen2.5-1.5b-instruct` |
| Authentication | Bearer token |

If an application asks for the full chat URL instead of a base URL, use:

```text
http://192.168.1.66:8000/v1/chat/completions
```

Do not enter Markdown syntax such as `[http://...](http://...)` into a URL field.

### Prepare a Windows PowerShell client session

```powershell
$ServerIP = "192.168.1.66"
$ApiBase = "http://$($ServerIP):8000/v1"
$Model = "qwen2.5-1.5b-instruct"

$SecureApiKey = Read-Host "Paste the API key" -AsSecureString
$ApiKey = [Net.NetworkCredential]::new("unused", $SecureApiKey).Password
```

The secure prompt keeps the key out of PowerShell command history.

### Test network access from the client

```powershell
Test-NetConnection -ComputerName $ServerIP -Port 8000 |
  Select-Object ComputerName, RemotePort, SourceAddress, TcpTestSucceeded

Invoke-RestMethod `
  -Uri "http://$($ServerIP):8000/health" `
  -TimeoutSec 10
```

If this fails, do not troubleshoot the model yet. First check power, Windows sign-in, Wi-Fi, the current server IP, port `8000`, and the firewall.

### List available models from the client

```powershell
(Invoke-RestMethod `
  -Uri "$ApiBase/models" `
  -Headers @{Authorization = "Bearer $ApiKey"} `
  -TimeoutSec 10).data |
  Select-Object id, owned_by
```

### Send a chat request with PowerShell

This method constructs JSON safely and avoids shell-quoting errors.

```powershell
$Payload = @{
  model = $Model
  messages = @(
    @{
      role = "system"
      content = "You are a helpful and technically accurate assistant."
    },
    @{
      role = "user"
      content = "Explain retrieval-augmented generation in two sentences."
    }
  )
  temperature = 0.2
  max_tokens = 160
  stream = $false
} | ConvertTo-Json -Depth 6

$Response = Invoke-RestMethod `
  -Method Post `
  -Uri "$ApiBase/chat/completions" `
  -Headers @{Authorization = "Bearer $ApiKey"} `
  -ContentType "application/json" `
  -Body $Payload `
  -TimeoutSec 180

$Response.choices[0].message.content
```

### Send the same request with curl on Windows

Use `curl.exe`, `POST`, a plain URL, PowerShell backticks, and pipe the JSON here-string through standard input. This avoids Windows PowerShell splitting a multiline body into separate command arguments.

```powershell
$Body = @'
{
  "model": "qwen2.5-1.5b-instruct",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful and technically accurate assistant."
    },
    {
      "role": "user",
      "content": "Explain retrieval-augmented generation in two sentences."
    }
  ],
  "temperature": 0.2,
  "max_tokens": 160,
  "stream": false
}
'@

$Body | curl.exe --silent --show-error --request POST `
  "$ApiBase/chat/completions" `
  --header "Authorization: Bearer $ApiKey" `
  --header "Content-Type: application/json" `
  --data-binary "@-"
```

### Stream a response with curl on Windows

```powershell
$StreamingBody = @'
{
  "model": "qwen2.5-1.5b-instruct",
  "messages": [
    {
      "role": "user",
      "content": "Give me five concise study tips."
    }
  ],
  "temperature": 0.3,
  "max_tokens": 160,
  "stream": true
}
'@

$StreamingBody | curl.exe --no-buffer --silent --show-error --request POST `
  "$ApiBase/chat/completions" `
  --header "Authorization: Bearer $ApiKey" `
  --header "Content-Type: application/json" `
  --data-binary "@-"
```

Streaming returns Server-Sent Events. The final line is normally `data: [DONE]`.

### Send a request from Bash, Linux, macOS, or Git Bash

```bash
API_BASE='http://192.168.1.66:8000/v1'
MODEL='qwen2.5-1.5b-instruct'
read -rsp 'API key: ' API_KEY
echo

curl --silent --show-error --request POST \
  "$API_BASE/chat/completions" \
  --header "Authorization: Bearer $API_KEY" \
  --header 'Content-Type: application/json' \
  --data-raw "{
    \"model\": \"$MODEL\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"Explain semantic search in two sentences.\"
      }
    ],
    \"temperature\": 0.2,
    \"max_tokens\": 160,
    \"stream\": false
  }"

unset API_KEY
```

In Bash, line continuation is a backslash (`\`). In PowerShell, it is a backtick (`` ` ``). Do not mix them.

### Use the Python OpenAI client

Install the client package on the client computer:

```powershell
py -m pip install --upgrade openai
```

Set temporary environment variables for the current PowerShell window:

```powershell
$env:LOCAL_AI_API_BASE = "http://192.168.1.66:8000/v1"
$env:LOCAL_AI_API_KEY = $ApiKey
$env:LOCAL_AI_MODEL = "qwen2.5-1.5b-instruct"
```

Python example:

```python
import os

from openai import OpenAI


client = OpenAI(
    base_url=os.environ["LOCAL_AI_API_BASE"],
    api_key=os.environ["LOCAL_AI_API_KEY"],
)

response = client.chat.completions.create(
    model=os.environ.get("LOCAL_AI_MODEL", "qwen2.5-1.5b-instruct"),
    messages=[
        {"role": "system", "content": "Answer clearly and concisely."},
        {"role": "user", "content": "What is a vector database?"},
    ],
    temperature=0.2,
    max_tokens=160,
)

print(response.choices[0].message.content)
```

Save the code as `local_ai_test.py`, then run:

```powershell
py .\local_ai_test.py
```

### Configure Postman or an Obsidian AI plugin

For Postman:

1. Method: `POST`
2. URL: `http://192.168.1.66:8000/v1/chat/completions`
3. Authorization type: Bearer Token
4. Token: the API key retrieved from the server
5. Header: `Content-Type: application/json`
6. Body: raw JSON using the same structure as the curl example

For an Obsidian plugin that supports custom OpenAI-compatible providers:

1. Select `OpenAI-compatible`, `Custom OpenAI`, or equivalent.
2. Set the base URL to `http://192.168.1.66:8000/v1`.
3. Set the model to `qwen2.5-1.5b-instruct`.
4. Paste the API key into the plugin's secret/API-key field.
5. Do not put the key directly in a note or template.

Plugin field names vary, but the three values remain the same: base URL, API key, and model.

### Clear secrets from the client PowerShell session

```powershell
Remove-Variable ApiKey, SecureApiKey -ErrorAction SilentlyContinue
Remove-Item Env:LOCAL_AI_API_KEY -ErrorAction SilentlyContinue
```

Closing the PowerShell window also removes ordinary session variables.

## API reference

### `GET /health`

Purpose: confirms that `llama-server` is running and the model has loaded.

Authentication: not required.

### `GET /v1/models`

Purpose: returns the model IDs advertised by the server.

Expected model: `qwen2.5-1.5b-instruct`.

Authentication: the current `llama.cpp` build exposes this discovery endpoint publicly. The examples still send the Bearer header for consistent client configuration. Generation remains API-key protected.

### `POST /v1/chat/completions`

Purpose: accepts OpenAI-style chat messages and generates a response.

Authentication:

```text
Authorization: Bearer <API_KEY>
```

Common request fields:

| Field | Meaning | Recommended starting value |
|---|---|---:|
| `model` | Model alias | `qwen2.5-1.5b-instruct` |
| `messages` | System/user/assistant conversation | Required |
| `temperature` | Randomness | `0.2` for factual work, `0.7` for creative work |
| `max_tokens` | Maximum generated tokens | `128`-`256` for normal use |
| `stream` | Stream tokens as they are generated | `false` initially |

The server accepts one generation at a time. A second request waits until the current request finishes.

## Runtime configuration

The current startup script configures:

| Setting | Value | Reason |
|---|---:|---|
| CPU threads | `3` | Leaves one logical thread for Windows |
| Parallel slots | `1` | Best fit for the two-core CPU |
| Context size | `4096` tokens | Controls memory and prompt cost |
| Batch size | `128` | Conservative prompt processing |
| Micro-batch size | `64` | Limits temporary memory pressure |
| GPU layers | `0` | CPU-only operation |
| Device | `none` | Prevents GPU/Vulkan offload |
| Web UI | Disabled | Reduces unnecessary LAN exposure |
| Slot endpoint | Disabled | Reduces unnecessary LAN exposure |

Change these values only in `scripts\start_llama_windows.ps1`, then restart and test the server.

Observed performance is approximately 7-10 generated tokens per second, depending on prompt size, output length, Windows load, and temperature. A 512-token answer may take around one minute.

## Troubleshooting

### Client cannot reach the server

On the client:

```powershell
Test-NetConnection 192.168.1.66 -Port 8000
```

On the server:

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
Invoke-RestMethod http://127.0.0.1:8000/health
```

Likely causes:

- The server laptop is powered off, asleep, or not signed in.
- The model server is stopped.
- The DHCP address changed.
- The devices are on different or guest Wi-Fi networks.
- Wireless client isolation is enabled in the router.
- The firewall scope does not match the current LAN.

### Port 8000 is already occupied

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  ForEach-Object {
    Get-Process -Id $_.OwningProcess
  }
```

If the process is `llama-server`, the server is already running. Do not start another copy. If it is another application, stop or reconfigure that application before starting this server.

### Health works but chat returns `401`

The API key is wrong, missing, or was rotated.

On the server, load the current value again:

```powershell
$ApiKey = [Environment]::GetEnvironmentVariable("LOCAL_AI_API_KEY", "User")
"Key length: $($ApiKey.Length)"
```

The client must send:

```text
Authorization: Bearer <CURRENT_API_KEY>
```

Restart the server after changing the stored key.

### Request returns `404` or `405`

Check all of the following:

- Use `POST`, not `GET`.
- Use `/v1/chat/completions`.
- Use the plain URL, without Markdown brackets or parentheses.
- Use model `qwen2.5-1.5b-instruct`.

Correct URL:

```text
http://192.168.1.66:8000/v1/chat/completions
```

### Request returns a JSON parse error

The body was damaged by shell quoting. Common causes include:

- Using Bash backslashes in Windows PowerShell.
- Using PowerShell backticks in Bash.
- Copying smart quotes from formatted text.
- Sending `GET` with a body instead of `POST`.
- Passing a Markdown-formatted URL.

Use the PowerShell `ConvertTo-Json` example in this README. It avoids manual JSON escaping.

### The hidden start does nothing

Run the startup script visibly:

```powershell
Set-Location "C:\Users\hp\OneDrive\Desktop\New folder"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\scripts\start_llama_windows.ps1"
```

It will report a missing executable, model file, API key, or other startup error. Also inspect:

```powershell
Get-Content "$env:LOCALAPPDATA\LocalAIServer\logs\server.log" -Tail 100
```

### The response is very slow

This is CPU-only inference on a two-core processor. To reduce latency:

- Use `max_tokens` between `64` and `256`.
- Keep prompts and conversation history concise.
- Send only one request at a time.
- Use streaming so text appears as it is generated.
- Keep the laptop on a hard, ventilated surface.
- Close unnecessary applications on the server.

### The IP address changed

Run the LAN discovery command on the server, then update the client's base URL. If the new address remains inside `192.168.1.0/24`, the existing firewall scope should still work.

Create a DHCP reservation in the router for the server's Wi-Fi MAC address to prevent repeated changes.

### Server stopped after a reboot

The Startup shortcut runs only after the Windows user signs in. Sign in, wait approximately 15 seconds, and check `/health`.

If it still does not start, verify the shortcut and run the startup script visibly.

## Maintenance

### Recovery inventory

This runbook intentionally focuses on operating the existing server rather than recreating it. Keep the following recovery items:

- `README.md` - this runbook.
- `scripts\start_llama_windows.ps1` - the actual runtime configuration.
- `models\qwen2.5-1.5b-instruct-q4_k_m.gguf` - optional to back up because it is 1.1 GB and can be downloaded again; keep its checksum if not backed up.
- The API key - store it in a password manager, never in the Obsidian vault or an unencrypted backup file.
- The Startup shortcut - it can be recreated with the command in this README.
- `%LOCALAPPDATA%\LocalAIServer\logs` - optional diagnostic history, not required to restore service.

There is currently no RAG or vector-database state to back up.

To copy the runbook and startup script to a backup directory:

```powershell
$ProjectRoot = "C:\Users\hp\OneDrive\Desktop\New folder"
$BackupRoot = Read-Host "Enter a trusted backup directory"

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $BackupRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "scripts\start_llama_windows.ps1") -Destination $BackupRoot
```

Copy the GGUF separately only if the backup destination has at least 1.2 GB free space.

### Check disk space and model size

```powershell
Get-PSDrive -Name C |
  Select-Object Used, Free,
    @{Name="FreeGB"; Expression={[math]::Round($_.Free / 1GB, 1)}}

Get-Item "C:\Users\hp\OneDrive\Desktop\New folder\models\qwen2.5-1.5b-instruct-q4_k_m.gguf" |
  Select-Object FullName, Length, LastWriteTime
```

### Check llama.cpp version

```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe" `
  --version
```

### Update llama.cpp deliberately

Stop the server, then:

```powershell
winget upgrade `
  --id ggml.llamacpp `
  --exact `
  --source winget `
  --accept-package-agreements `
  --accept-source-agreements
```

Start the server and repeat the health, model-list, small completion, and firewall-rule checks. A Windows package update may recreate broad application firewall rules. Do not update while a request is running.

### Monitor CPU and memory

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue |
  Select-Object Id, CPU,
    @{Name="MemoryMB"; Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}},
    StartTime
```

Task Manager can also show CPU usage, clock speed, memory, disk activity, and the `llama-server.exe` process. It does not normally show the CPU temperature; use a trusted hardware-monitoring utility if temperature readings are needed.

## Security checklist

- [ ] The two broad `llama-server.exe` Public-profile firewall rules are disabled.
- [ ] The narrow TCP `8000` rule is enabled only for the trusted LAN range.
- [ ] Router port forwarding for port `8000` is disabled.
- [ ] The API key is not stored in README, Obsidian notes, Git, screenshots, or source code.
- [ ] Applications send the key as `Authorization: Bearer ...`.
- [ ] The key is rotated after accidental exposure.
- [ ] The server is not used over public Wi-Fi without an encrypted VPN.
- [ ] The laptop is placed on a hard, ventilated surface.
- [ ] Battery swelling, unusual heat, fan problems, and low disk space are checked regularly.
- [ ] A router DHCP reservation keeps the server address stable.

The API key authenticates clients but does not encrypt traffic. Anyone able to capture traffic on an untrusted network could read the key and prompts.

## Known limitations

- The server is intended for one user and one active generation at a time.
- Qwen2.5 1.5B is a small model with limited reasoning, factual recall, and coding depth.
- CPU inference is much slower than GPU inference.
- Long prompts and outputs increase latency substantially.
- There is one shared API key, without user accounts, quotas, or per-user audit identity.
- Complete request payloads are not logged at normal verbosity.
- There is no active RAG, embedding, vector database, document-ingestion, or retrieval service.
- Automatic startup occurs after Windows sign-in, not before sign-in.
- The LAN address is DHCP-assigned until reserved in the router.

## Upstream references

- [llama.cpp server and OpenAI-compatible API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Qwen2.5 1.5B Instruct GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)
