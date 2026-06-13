import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from dotenv import load_dotenv

load_dotenv()

TARGET_CHANNEL_ID = 1512835652788686999
GUILD_ID = 1489929216299630753


intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    status=discord.Status.online,
)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name} (ID: {bot.user.id})")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)          # copies global commands to guild
        synced = await bot.tree.sync(guild=guild)     # instant sync (no 1hr wait)
        print(f"🔄 Synced {len(synced)} slash command(s) to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


@bot.tree.command(name="speed", description="Train your speed stats and earn XP")

@app_commands.checks.cooldown(1, 72000)
async def speed(interaction: discord.Interaction):
    breakthrough = random.randint(1, 100) <= 20

    log_channel = bot.get_channel(TARGET_CHANNEL_ID)  # set this to your private channel ID
    if log_channel:
        result = "BREAKTHROUGH 🥳" if breakthrough else "normal"
        await log_channel.send(f"📋 {interaction.user} used /speed — result: {result}")

    if breakthrough:
        await interaction.response.send_message(
            "Good job, get your 2 XP points!\n\n🥳 BREAKTHROUGH 🥳! You've just won 25 XP!!!",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message("Good job, get your 2 XP points!", ephemeral=True)

@bot.tree.command(name="risk", description="Train your risk stats and earn XP")

@app_commands.checks.cooldown(1, 72000)
async def risk(interaction: discord.Interaction):
    breakthrough = random.randint(1, 100) <= 20

    log_channel = bot.get_channel(TARGET_CHANNEL_ID)  # set this to your private channel ID
    if log_channel:
        result = "BREAKTHROUGH 🥳" if breakthrough else "normal"
        await log_channel.send(f"📋 {interaction.user} used /risk — result: {result}")

    if breakthrough:
        await interaction.response.send_message(
            "Good job, get your 2 XP points!\n\n🥳 BREAKTHROUGH 🥳! You've just won 25 XP!!!",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message("Good job, get your 2 XP points!", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):

    if isinstance(error, app_commands.CommandOnCooldown):
        hours, remainder = divmod(int(error.retry_after), 3600)
        minutes = remainder // 60
        await interaction.response.send_message(
            f"⏳ You're on cooldown! Try again in **{hours}h {minutes}m**.",
            ephemeral=True,
        )
    else:
        print(f"❌ Command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong. Please try again.", ephemeral=True
            )

bot.run("TOKEN")

