from datetime import datetime
import discord
import requests
from discord.ext import commands,tasks
import os
import dotenv 
dotenv.load_dotenv()
import asyncio

# Values from .end file
TENANT_ID = os.environ['TENANT_ID']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']
SUBSCRIPTION_ID = os.environ['SUBSCRIPTION_ID']
RESOURCE_GROUP = os.environ['RESOURCE_GROUP']
VM_NAME = os.environ['VM_NAME']

SERVER_IP = os.environ['MC_SERVER_IP']
SERVER_PORT = os.environ['MC_SERVER_PORT']

DISCORD_BOT_TOKEN = os.environ['BOT_TOKEN']

SHUTDOWN_CHECK_INTERVAL = int(os.environ['SHUTDOWN_CHECK_INTERVAL'])
MESSAGE_CHANNEL = int(os.environ['MESSAGE_CHANNEL'])
STATUS_CHECK_INTERVAL = int(os.environ['STATUS_CHECK_INTERVAL'])
STATUS_CHANNEL = int(os.environ['STATUS_CHANNEL'])
STATUS_MSG_ID = int(os.environ['STATUS_MSG_ID'])

SSH_KEY = os.environ['SSH_KEY']
SSH_HOST = os.environ['SSH_HOST']

# Discord Bot Setup

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

# Azure authentication

def get_azure_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    res = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://management.azure.com/.default"
    })
    return res.json()["access_token"]

def azure_request(method, action, token=None):
    token = token or get_azure_token()
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Compute/virtualMachines/{VM_NAME}"
        f"/{action}?api-version=2025-04-01"
    )
    fn = requests.post if method == "POST" else requests.get
    return fn(url, headers={"Authorization": f"Bearer {token}"})

def get_vm_status():
    token = get_azure_token()
    res =azure_request("GET", "instanceView", token).json()
    for s in res.get("statuses", []):
        if s["code"].startswith("PowerState/"):
            return s["code"].replace("PowerState/", "")
    return "Unknown"

def start_vm():
    azure_request("POST", "start")

def deallocate_vm():
    azure_request("POST", "deallocate")

async def azure_command(cmd: str):
    try:
        process = await asyncio.create_subprocess_exec("ssh",
            "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            SSH_HOST,
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        ) 

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        return "timeout"

async def stop_mc_server():
    await azure_command("sudo systemctl stop minecraft")

async def check_minecraft_service():
    return await azure_command("systemctl is-active minecraft")


# Minecraft Helper
def get_player_count():
    try:
        from mcstatus import JavaServer
        server = JavaServer(SERVER_IP, int(SERVER_PORT))
        return server.status().players.online
    except Exception :
        return None
    
# Auto Shutdown after X minutes of inactivity
@tasks.loop(minutes=SHUTDOWN_CHECK_INTERVAL)
async def auto_shutdown():
    vm_status = get_vm_status()
    if vm_status != "running":
        return
    
    player_count = get_player_count()
    if player_count is None:
        print("Failed to get player count. Skipping auto shutdown check.")
        return
    
    print(f"Auto shutdown check: {player_count} player(s) online.")
    
    if player_count == 0:
        channel = bot.get_channel(MESSAGE_CHANNEL)
        if(channel):
            await channel.send("No players online. Auto shutting down the server.")

        await stop_mc_server()

        for _ in range(30):
            await asyncio.sleep(2)
            status=await check_minecraft_service()
            if status != "active":
                break
        deallocate_vm()
    else:
        print(f"{player_count} player(s) online. Server will remain running.")

@tasks.loop(minutes=STATUS_CHECK_INTERVAL)
async def status_update():
    vm_status = get_vm_status()
    embed = discord.Embed(title="Minecraft Server Status", color=0x00ff00 if vm_status == "running" else 0xff0000)
    emoji = {
        "running": "✅",
        "starting": "⏳",
        "deallocating": "🛑",
        "deallocated": "🛑",
        "Unknown": "❓"
    }
    if vm_status == "running":
        players = get_player_count()
        player_info = f"\nConnect to: `{SERVER_IP}:{SERVER_PORT}` with **{players}** player(s) online" if players is not None else ""
        content = f"{emoji[vm_status]} Server is **{vm_status}**!{player_info}"
    else:
        content = f"{emoji[vm_status]} Server is **{vm_status}**."
    embed.description = content
    embed.set_footer(text=f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    channel = bot.get_channel(STATUS_CHANNEL)
    if channel:
        try:
            msg = await channel.fetch_message(STATUS_MSG_ID)
            await msg.edit(embed=embed,content="")
        except Exception as e:
            print(f"Failed to update status message: {e}")

# Slash Commands
@tree.command(name="ping", description="Check bot responsiveness")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(ephemeral=True, embed=discord.Embed(colour=0x00ff00, title="Pong!", description=f"Latency: {bot.latency*1000:.2f}ms"))

server_group = discord.app_commands.Group(name="server", description="Minecraft server control commands")
tree.add_command(server_group)

@server_group.command(name="status", description="Check Minecraft server status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    vm_status = get_vm_status()
    emoji = {
        "running": "✅",
        "starting": "⏳",
        "deallocating": "🛑",
        "deallocated": "🛑",
        "Unknown": "❓"
    }
    if vm_status == "running":
        players = get_player_count()
        if players is None:
            player_info = " but Minecraft server is not responding"
        else:
            player_info = f"\nConnect to: `{SERVER_IP}:{SERVER_PORT}` with **{players}** player(s) online" if players is not None else ""
        
        await interaction.followup.send(f"{emoji[vm_status]} Server is **{vm_status}**!{player_info}")
    else:
        await interaction.followup.send(f"{emoji[vm_status]} Server is **{vm_status}**.")

@server_group.command(name="start", description="Start the Minecraft server")
async def start(interaction: discord.Interaction):
    await interaction.response.defer()

    vm_status = get_vm_status()
    if vm_status in ["starting", "deallocating"]:
        await interaction.followup.send(f"⏳ Server is currently **{vm_status}**. Please wait...")
        return
    
    if vm_status == "running" and get_player_count() is None: 
        await interaction.followup.send(f"Server is already running but minecraft server is not responding.")
        return
    await interaction.followup.send("Starting the server")
    start_vm()

    if not auto_shutdown.is_running():
        auto_shutdown.start()

    for _ in range(30):
        await asyncio.sleep(5)
        if get_player_count() is not None:
            print(f"Server has started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            await interaction.channel.send(f"{interaction.user.mention} ✅ Server is **running**!\nConnect to: `{SERVER_IP}:{SERVER_PORT}`")
            return
    await interaction.channel.send(f"❌ Server failed to start within expected time. Please check Azure portal.")

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

    status_update.start()

    if get_vm_status() == "running" and not auto_shutdown.is_running():
        auto_shutdown.start()

    print("------")
    
bot.run(DISCORD_BOT_TOKEN)