import discord
from discord.ext import commands
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CATEGORY_ID = int(os.getenv("TICKETS_CATEGORY_ID", "0"))
LOGS_CHANNEL_ID = 1558332887000948757

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# user_id -> {channel_id, opened_at, member, messages, mods}
open_tickets = {}
maintenance = False


def now() -> datetime:
    return datetime.now(timezone.utc)


def fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y à %H:%M:%S UTC")


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if maintenance:
        if isinstance(message.channel, discord.DMChannel):
            await message.author.send("🔧 Le support est actuellement en maintenance. Reviens plus tard !")
        else:
            await bot.process_commands(message)  # laisser passer !maintenance uniquement
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

    # Ticket déjà ouvert → relay + log message
    if user_id in open_tickets:
        channel = guild.get_channel(open_tickets[user_id]["channel_id"])
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

            open_tickets[user_id]["messages"].append({
                "time": now(),
                "author": str(message.author),
                "role": "Membre",
                "content": message.content or "[fichier joint]",
            })
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

    opened_at = now()
    open_tickets[user_id] = {
        "channel_id": channel.id,
        "opened_at": opened_at,
        "member": str(message.author),
        "member_id": user_id,
        "messages": [{
            "time": opened_at,
            "author": str(message.author),
            "role": "Membre",
            "content": message.content or "[fichier joint]",
        }],
        "mods": set(),
    }

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

    await channel.send("@here", embed=embed)
    await message.author.send(
        "✅ Ton message a bien été reçu ! Un membre du staff va te répondre dès que possible. 🙏"
    )


async def handle_ticket_reply(message):
    user_id = next(
        (uid for uid, data in open_tickets.items() if data["channel_id"] == message.channel.id),
        None,
    )
    if user_id is None:
        return
    if message.content.startswith("!"):
        return

    # Log le modo
    open_tickets[user_id]["mods"].add(str(message.author))
    open_tickets[user_id]["messages"].append({
        "time": now(),
        "author": str(message.author),
        "role": "Staff",
        "content": message.content or "[fichier joint]",
    })

    try:
        await message.delete()
    except discord.Forbidden:
        pass

    user = bot.get_user(user_id)
    if not user:
        return

    try:
        embed = discord.Embed(
            description=message.content or "*[fichier joint]*",
            color=0x57F287,
        )
        embed.set_author(name="Support", icon_url=bot.user.display_avatar.url)
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        await user.send(embed=embed)
    except discord.Forbidden:
        await message.channel.send("⚠️ Impossible d'envoyer le DM (DMs fermés).")


def build_transcript(data: dict, closed_at: datetime, closed_by: str) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("              TRANSCRIPT DE TICKET")
    lines.append("=" * 60)
    lines.append(f"  Membre       : {data['member']} (ID: {data['member_id']})")
    lines.append(f"  Ouvert le    : {fmt(data['opened_at'])}")
    lines.append(f"  Fermé le     : {fmt(closed_at)}")
    lines.append(f"  Fermé par    : {closed_by}")
    mods = ", ".join(data["mods"]) if data["mods"] else "Aucun"
    lines.append(f"  Staff actif  : {mods}")
    lines.append(f"  Messages     : {len(data['messages'])}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("─── MESSAGES ───────────────────────────────────────────")
    lines.append("")

    for msg in data["messages"]:
        lines.append(f"[{fmt(msg['time'])}] [{msg['role']}] {msg['author']}")
        lines.append(f"  → {msg['content']}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("               FIN DU TRANSCRIPT")
    lines.append("=" * 60)
    return "\n".join(lines)


CLOSING_FRAMES = [
    "🔒 Fermeture du ticket dans **5**... ⏳",
    "🔒 Fermeture du ticket dans **4**... ⌛",
    "🔒 Fermeture du ticket dans **3**... ⏳",
    "🔒 Fermeture du ticket dans **2**... ⌛",
    "🔒 Fermeture du ticket dans **1**... ⏳",
    "💥 Fermeture en cours... 🔐",
    "🗑️ Suppression du salon... 🚨",
]


@bot.command(name="maintenance")
@commands.has_permissions(administrator=True)
async def toggle_maintenance(ctx):
    global maintenance
    maintenance = not maintenance
    if maintenance:
        await bot.change_presence(
            status=discord.Status.do_not_disturb,
            activity=discord.Game("🔧 Maintenance en cours")
        )
        await ctx.send("🔧 Maintenance **activée** — le bot ne répond plus aux DMs.")
    else:
        await bot.change_presence(
            status=discord.Status.online,
            activity=None
        )
        await ctx.send("✅ Maintenance **désactivée** — le bot est de retour.")


@bot.command(name="fermer")
@commands.has_permissions(administrator=True)
async def fermer(ctx):
    user_id = next(
        (uid for uid, data in open_tickets.items() if data["channel_id"] == ctx.channel.id),
        None,
    )
    if user_id is None:
        await ctx.send("❌ Ce channel n'est pas un ticket.")
        return

    data = open_tickets.pop(user_id)
    closed_at = now()

    # Notifier le membre
    user = bot.get_user(user_id)
    if user:
        try:
            await user.send(
                "🔒 Ton ticket a été **fermé** par le staff.\n"
                "➡️ N'hésite pas à revenir si tu as besoin d'aide ! 👋"
            )
        except discord.Forbidden:
            pass

    # Animation fermeture
    msg = await ctx.send(CLOSING_FRAMES[0])
    for frame in CLOSING_FRAMES[1:]:
        await asyncio.sleep(1)
        await msg.edit(content=frame)

    # Envoyer le transcript dans le salon de logs
    logs_channel = ctx.guild.get_channel(LOGS_CHANNEL_ID)
    if logs_channel:
        transcript = build_transcript(data, closed_at, str(ctx.author))
        file_bytes = transcript.encode("utf-8")
        file = discord.File(
            fp=__import__("io").BytesIO(file_bytes),
            filename=f"transcript-{data['member'].replace('#', '')}-{closed_at.strftime('%Y%m%d-%H%M%S')}.txt",
        )

        embed = discord.Embed(
            title="📋 Ticket fermé",
            color=0xFF4444,
        )
        embed.add_field(name="👤 Membre", value=f"{data['member']}\n`{data['member_id']}`", inline=True)
        embed.add_field(name="🛡️ Fermé par", value=str(ctx.author), inline=True)
        embed.add_field(
            name="🕐 Durée",
            value=f"Ouvert: {fmt(data['opened_at'])}\nFermé: {fmt(closed_at)}",
            inline=False,
        )
        mods = ", ".join(data["mods"]) if data["mods"] else "Aucun"
        embed.add_field(name="👥 Staff ayant répondu", value=mods, inline=False)
        embed.add_field(name="💬 Messages", value=str(len(data["messages"])), inline=True)
        embed.set_footer(text="Transcript joint en fichier ↓")

        await logs_channel.send(embed=embed, file=file)

    await asyncio.sleep(1)
    await ctx.channel.delete()


bot.run(TOKEN)
