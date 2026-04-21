# Azure + Discord VM Operations Bot

A Python Discord bot that bridges **Discord slash commands** with **Azure VM lifecycle operations**.  
It is designed for lightweight remote operations: checking VM state, starting compute, posting periodic status, and running controlled shutdown actions through Discord.

## What this project focuses on

### 1. Azure Integration
- Authenticates with Azure using a Service Principal (OAuth2 client credentials flow).
- Calls Azure Compute REST endpoints to:
  - read VM power status (`instanceView`)
  - start VM
  - deallocate VM
- Uses environment-driven Azure configuration for tenant, app, subscription, resource group, and VM targeting.

### 2. Discord Integration
- Uses `discord.py` app commands (slash commands) for operational control.
- Exposes command-based workflows such as:
  - `/ping`
  - `/server status`
  - `/server start`
- Publishes automated status updates to a fixed Discord message (edited in-place).
- Supports background loops for periodic monitoring and auto-actions.

---

## Architecture at a glance

1. Discord interaction triggers command handlers in `bot.py`.
2. Handlers call Azure helpers to read or mutate VM state.
3. Scheduled loops periodically:
   - update status embeds in Discord,
   - evaluate runtime activity and execute shutdown flow when conditions are met.
4. SSH-based commands are used for guest-level service control before VM deallocation.

---

## Prerequisites

- Python 3.10+
- Azure subscription with a target VM
- Azure AD App Registration / Service Principal with rights to manage that VM
- Discord application + bot token with slash command permissions in your server

Install dependencies:

```powershell
pip install discord.py requests python-dotenv mcstatus
```

---

## Configuration

Copy `sampleenv.txt` to `.env` and fill values:

```powershell
Copy-Item sampleenv.txt .env
```

### Required environment variables

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Discord bot token |
| `TENANT_ID` | Azure tenant ID |
| `CLIENT_ID` | Service Principal (App Registration) client ID |
| `CLIENT_SECRET` | Service Principal client secret |
| `SUBSCRIPTION_ID` | Azure subscription ID |
| `RESOURCE_GROUP` | VM resource group name |
| `VM_NAME` | VM name to control |
| `MC_SERVER_IP` | Service endpoint IP/domain queried for availability |
| `MC_SERVER_PORT` | Service endpoint port |
| `SHUTDOWN_CHECK_INTERVAL` | Minutes between inactivity checks |
| `MESSAGE_CHANNEL` | Channel ID for operational notifications |
| `STATUS_CHECK_INTERVAL` | Minutes between status refreshes |
| `STATUS_CHANNEL` | Channel ID containing status message |
| `STATUS_MSG_ID` | Existing message ID to edit for status updates |
| `SSH_KEY` | Path to private key used for SSH |
| `SSH_HOST` | SSH target (`user@host`) |

> Note: `AZURE_TOKEN_ID` exists in `sampleenv.txt` but is not currently used in `bot.py`.

---

## Azure setup notes

1. Create an App Registration and client secret.
2. Grant the Service Principal permissions to operate the VM (at least read instance status and start/deallocate actions).
3. Ensure your VM and resource identifiers in `.env` exactly match Azure resource names.

---

## Discord setup notes

1. Create a Discord bot in the Developer Portal.
2. Enable required bot scopes/permissions for slash commands and channel messaging.
3. Invite the bot to your server.
4. Capture channel IDs and status message ID:
   - Enable Developer Mode in Discord.
   - Right-click channels/messages to copy IDs.

---

## Run the bot

```powershell
python bot.py
```

On startup, the bot syncs slash commands and begins scheduled status updates.

---

## Operational behavior

- VM state is treated as the primary source of truth for command decisions.
- Status is communicated via embed updates to a single tracked message.
- Auto-shutdown logic waits for inactivity, performs guest service stop, then deallocates the VM.

---

## Security guidance

- Never commit `.env` or private SSH keys.
- Rotate `CLIENT_SECRET` and `BOT_TOKEN` if exposed.
- Use least-privilege Azure roles for the Service Principal.
