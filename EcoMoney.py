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


    bot.loop.create_task(leaderboard_loop())

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



@bot.tree.command(name="setleaderboardchannel")
async def setleaderboardchannel(interaction: discord.Interaction, channel: discord.TextChannel):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return

    await set_setting("leaderboard_channel", channel.id)

    await interaction.response.send_message(
        f"📊 Leaderboard set to {channel.mention}"
    )


# ---------------- NEXT COMMANDS ----------------


@bot.tree.command(name="transactions")
async def transactions(interaction: discord.Interaction, user: discord.User):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("""
            SELECT action, account, amount
            FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 10
        """, (user.id,))

        data = await cursor.fetchall()

    if not data:
        await interaction.response.send_message("❌ No transactions found.")
        return

    msg = f"📜 **Last Transactions for {user.name}**\n\n"

    for action, account, amount in data:
        msg += f"**{action}** | {account} | ${amount}\n"

    await interaction.response.send_message(msg)


#---------------- Add & Deduct Function --------------------------------#

@bot.tree.command(name="add")
async def add(interaction: discord.Interaction, user: discord.User, account: str, amount: int):

    owner_role = await get_setting("owner_role")
    admin_role = await get_setting("admin_role")

    user_roles = [role.id for role in interaction.user.roles]

    if not any(r in user_roles for r in [int(owner_role), int(admin_role)]):
        await interaction.response.send_message("❌ Admin & Owner only.")
        return

    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            UPDATE accounts
            SET external = external + ?
            WHERE user_id=? AND account_name=?
        """, (amount, user.id, account))

        await db.commit()

    await interaction.response.send_message(
        f"➕ Added ${amount} to {user.name}'s account `{account}`"
    )


@bot.tree.command(name="deduct")
async def deduct(interaction: discord.Interaction, user: discord.User, account: str, amount: int):

    owner_role = await get_setting("owner_role")
    admin_role = await get_setting("admin_role")

    user_roles = [role.id for role in interaction.user.roles]

    if not any(r in user_roles for r in [int(owner_role), int(admin_role)]):
        await interaction.response.send_message("❌ Admin & Owner only.")
        return

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute("""
            SELECT external FROM accounts
            WHERE user_id=? AND account_name=?
        """, (user.id, account))

        data = await cursor.fetchone()

        if not data:
            await interaction.response.send_message("❌ Account not found.")
            return

        current = data[0]

        if current < amount:
            await interaction.response.send_message("❌ Not enough balance.")
            return

        await db.execute("""
            UPDATE accounts
            SET external = external - ?
            WHERE user_id=? AND account_name=?
        """, (amount, user.id, account))

        await db.commit()

    await interaction.response.send_message(
        f"➖ Removed ${amount} from {user.name}'s account `{account}`"
    )

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

async def leaderboard_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():

        channel_id = await get_setting("leaderboard_channel")
        if not channel_id:
            await asyncio.sleep(10)
            continue

        channel = bot.get_channel(int(channel_id))
        if not channel:
            await asyncio.sleep(10)
            continue

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute("""
                SELECT user_id, SUM(budget)
                FROM accounts
                GROUP BY user_id
                ORDER BY SUM(budget) DESC
                LIMIT 10
            """)
            all_data = await cursor.fetchall()

            cursor = await db.execute("""
                SELECT user_id, SUM(budget)
                FROM accounts
                WHERE is_f1=1
                GROUP BY user_id
                ORDER BY SUM(budget) DESC
                LIMIT 10
            """)
            f1_data = await cursor.fetchall()

        msg = "🏆 LIVE LEADERBOARD 🏆\n\n"

        msg += "ALL PLAYERS\n"
        for i, (uid, total) in enumerate(all_data, 1):
            try:
                user = await bot.fetch_user(uid)
                name = user.name
            except:
                name = "Unknown"
            msg += f"{i}. {name} — ${total or 0:,}\n"

        msg += "\nF1 PLAYERS\n"
        for i, (uid, total) in enumerate(f1_data, 1):
            try:
                user = await bot.fetch_user(uid)
                name = user.name
            except:
                name = "Unknown"
            msg += f"{i}. {name} — ${total or 0:,}\n"

        message_id = await get_setting("leaderboard_message")

        try:
            if not message_id:
                message = await channel.send(msg)
                await set_setting("leaderboard_message", message.id)
            else:
                message = await channel.fetch_message(int(message_id))
                await message.edit(content=msg)
        except:
            message = await channel.send(msg)
            await set_setting("leaderboard_message", message.id)

        await asyncio.sleep(30)

# ---------------- RUN ----------------
bot.run(os.getenv("TOKEN"))