import os
import discord
from discord.ext import commands
import aiosqlite

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB = "ecopay.db"

# ---------------- F1 CAP LIMIT ----------------
CAP_LIMIT = 215_000_000


# ---------------- DATABASE ----------------
async def setup_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER,
            account_name TEXT,
            budget INTEGER,
            external INTEGER,
            is_f1 INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0
        )
        """)
        await db.commit()


# ---------------- READY ----------------
@bot.event
async def on_ready():
    await setup_db()

    # IMPORTANT FIX: proper sync timing
    await bot.wait_until_ready()
    await bot.tree.sync()

    print(f"Logged in as {bot.user}")


# ---------------- CREATE ACC ----------------
@bot.tree.command(name="createacc")
async def createacc(interaction: discord.Interaction, name: str):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM accounts WHERE user_id=? AND is_f1=0",
            (interaction.user.id,)
        )
        count = (await cursor.fetchone())[0]

        if count >= 3:
            await interaction.response.send_message("❌ Max 3 normal accounts reached!")
            return

        await db.execute(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
            (interaction.user.id, name, 0, 0, 0, 0)
        )
        await db.commit()

    await interaction.response.send_message(f"✅ Account '{name}' created!")


# ---------------- CREATE F1 ----------------
@bot.tree.command(name="createf1")
async def createf1(interaction: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE user_id=? AND is_f1=1",
            (interaction.user.id,)
        )
        if await cursor.fetchone():
            await interaction.response.send_message("❌ F1 Account already exists!")
            return

        await db.execute(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
            (interaction.user.id, "F1 Account", 0, 0, 1, 0)
        )
        await db.commit()

    await interaction.response.send_message("🏎 F1 Account created!")


# ---------------- BALANCE ----------------
@bot.tree.command(name="balance")
async def balance(interaction: discord.Interaction):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT account_name, budget, external FROM accounts WHERE user_id=?",
            (interaction.user.id,)
        )
        data = await cursor.fetchall()

    if not data:
        await interaction.response.send_message("❌ No accounts found.")
        return

    msg = "💰 **Your Accounts:**\n\n"
    for name, budget, external in data:
        msg += f"**{name}** → Budget: ${budget} | External: ${external}\n"

    await interaction.response.send_message(msg)


# ---------------- DEPOSIT ----------------
@bot.tree.command(name="deposit")
async def deposit(interaction: discord.Interaction, account: str, amount: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT budget, external, is_f1 FROM accounts WHERE user_id=? AND account_name=?",
            (interaction.user.id, account)
        )
        data = await cursor.fetchone()

        if not data:
            await interaction.response.send_message("❌ Account not found.")
            return

        budget, external, is_f1 = data

        if is_f1 and budget + amount >= CAP_LIMIT:
            await interaction.response.send_message("❌ F1 cap reached.")
            return

        if external < amount:
            await interaction.response.send_message("❌ Not enough money.")
            return

        await db.execute(
            "UPDATE accounts SET budget=?, external=? WHERE user_id=? AND account_name=?",
            (budget + amount, external - amount, interaction.user.id, account)
        )
        await db.commit()

    await interaction.response.send_message("✅ Deposited!")


# ---------------- WITHDRAW ----------------
@bot.tree.command(name="withdraw")
async def withdraw(interaction: discord.Interaction, account: str, amount: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT budget, external FROM accounts WHERE user_id=? AND account_name=?",
            (interaction.user.id, account)
        )
        data = await cursor.fetchone()

        if not data:
            await interaction.response.send_message("❌ Account not found.")
            return

        budget, external = data

        if budget < amount:
            await interaction.response.send_message("❌ Not enough budget.")
            return

        await db.execute(
            "UPDATE accounts SET budget=?, external=? WHERE user_id=? AND account_name=?",
            (budget - amount, external + amount, interaction.user.id, account)
        )
        await db.commit()

    await interaction.response.send_message("💸 Withdraw complete")


# ---------------- TRANSFER ----------------
@bot.tree.command(name="transfer")
async def transfer(interaction: discord.Interaction, account: str, user: discord.User, amount: int):
    async with aiosqlite.connect(DB) as db:

        sender = await db.execute(
            "SELECT external FROM accounts WHERE user_id=? AND account_name=?",
            (interaction.user.id, account)
        )
        sender = await sender.fetchone()

        receiver = await db.execute(
            "SELECT account_name, external FROM accounts WHERE user_id=? LIMIT 1",
            (user.id,)
        )
        receiver = await receiver.fetchone()

        if not sender or not receiver:
            await interaction.response.send_message("❌ Account not found.")
            return

        sender_ext = sender[0]
        recv_name, recv_ext = receiver

        if sender_ext < amount:
            await interaction.response.send_message("❌ Not enough money.")
            return

        await db.execute(
            "UPDATE accounts SET external=? WHERE user_id=? AND account_name=?",
            (sender_ext - amount, interaction.user.id, account)
        )

        await db.execute(
            "UPDATE accounts SET external=? WHERE user_id=? AND account_name=?",
            (recv_ext + amount, user.id, recv_name)
        )

        await db.commit()

    await interaction.response.send_message("🔁 Transfer complete")


# ---------------- UPGRADE SYSTEM ----------------
UPGRADE_DATA = {
    1: {"value": 0.6, "cost": 5_000_000},
    2: {"value": 1.2, "cost": 9_500_000},
    3: {"value": 1.8, "cost": 16_000_000}
}


@bot.tree.command(name="upgrade")
async def upgrade(interaction: discord.Interaction, level: int):
    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute(
            "SELECT budget FROM accounts WHERE user_id=? AND is_f1=1",
            (interaction.user.id,)
        )
        data = await cursor.fetchone()

        if not data:
            await interaction.response.send_message("❌ No F1 account found.")
            return

        budget = data[0]

        if level not in UPGRADE_DATA:
            await interaction.response.send_message("❌ Invalid level.")
            return

        cost = UPGRADE_DATA[level]["cost"]
        value = UPGRADE_DATA[level]["value"]

        if budget < cost:
            await interaction.response.send_message("❌ Not enough money.")
            return

        await db.execute("""
            UPDATE accounts
            SET budget = budget - ?,
                level = ?
            WHERE user_id=? AND is_f1=1
        """, (cost, level, interaction.user.id))

        await db.commit()

    await interaction.response.send_message(
        f"🏎 Upgrade Level {level} applied (+{value})"
    )


# ---------------- RUN ----------------
bot.run(os.getenv("TOKEN"))