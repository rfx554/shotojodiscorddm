import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("MTU1ODMyNzU4ODcxMDEyMTU1NA.GBu4SO.X8h2lQjHsozbVnANUPtCL6xvU8pNn3iTpMADVs")
GUILD_ID = int(os.getenv("1556027569600471054"))
CATEGORY_ID = int(os.getenv("1556136510292623380", "0"))

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# user_id -> channel_id
open_tickets = {}


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        await handle_dm(message)
    else:
        await handle_ticket_reply(message)
        await bot.process_commands(message)


async def handle_dm(message):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    user_id = message.author.id

    # Ticket déjà ouvert → relay
    if user_id in open_tickets:
        channel = guild.get_channel(open_tickets[user_id])
        if channel:
            embed = discord.Embed(
                description=message.content or "*[fichier joint]*",
                color=0x5865F2,
            )
            embed.set_author(
                name=str(message.author),
                icon_url=message.author.display_avatar.url,
            )
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            await channel.send(embed=embed)
        return

    # Nouveau ticket
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )

    category = guild.get_channel(CATEGORY_ID) if CATEGORY_ID else None
    channel_name = f"ticket-{message.author.name}".lower()[:32]

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=f"{message.author} | {user_id}",
    )
    open_tickets[user_id] = channel.id

    embed = discord.Embed(
        title="📩 Nouveau ticket",
        description=message.content or "*[fichier joint]*",
        color=0x5865F2,
    )
    embed.set_author(
        name=f"{message.author} ({user_id})",
        icon_url=message.author.display_avatar.url,
    )
    embed.set_footer(text="Répondez ici · !fermer pour clore le ticket")
    if message.attachments:
        embed.set_image(url=message.attachments[0].url)

    await channel.send(embed=embed)
    await message.author.send(
        "✅ Ton message a été reçu ! Un admin va te répondre dès que possible."
    )


async def handle_ticket_reply(message):
    user_id = next(
        (uid for uid, cid in open_tickets.items() if cid == message.channel.id), None
    )
    if user_id is None:
        return
    if message.content.startswith("!"):
        return

    user = bot.get_user(user_id)
    if not user:
        return

    try:
        embed = discord.Embed(
            description=message.content or "*[fichier joint]*",
            color=0x57F287,
        )
        embed.set_author(
            name=f"Support — {message.author.display_name}",
            icon_url=message.author.display_avatar.url,
        )
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        await user.send(embed=embed)
    except discord.Forbidden:
        await message.channel.send("⚠️ Impossible d'envoyer le DM (DMs fermés).")


@bot.command(name="fermer")
@commands.has_permissions(administrator=True)
async def fermer(ctx):
    user_id = next(
        (uid for uid, cid in open_tickets.items() if cid == ctx.channel.id), None
    )
    if user_id is None:
        await ctx.send("❌ Ce channel n'est pas un ticket.")
        return

    user = bot.get_user(user_id)
    if user:
        try:
            await user.send("🔒 Ton ticket a été fermé. Reviens si besoin !")
        except discord.Forbidden:
            pass

    del open_tickets[user_id]
    await ctx.send("✅ Ticket fermé. Suppression dans 5 secondes...")
    await asyncio.sleep(5)
    await ctx.channel.delete()


bot.run(TOKEN)
