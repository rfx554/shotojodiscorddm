import discord
from discord import app_commands
from discord.ext import commands
from groq import Groq
import os
import json
from pathlib import Path

# ── Setup ─────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"  # Gratuit et très bon

# ── Salons actifs (persistés dans un fichier) ─────────────────────────────────
ACTIVE_FILE = "active_channels.json"

def load_active():
    if Path(ACTIVE_FILE).exists():
        with open(ACTIVE_FILE) as f:
            return set(json.load(f))
    return set()

def save_active(channels):
    with open(ACTIVE_FILE, "w") as f:
        json.dump(list(channels), f)

active_channels = load_active()

# Mémoire courte par salon (10 derniers échanges)
history: dict[int, list] = {}
MAX_HISTORY = 10

# ── Fonction IA ───────────────────────────────────────────────────────────────
def ask_groq(channel_id: int, user_message: str, username: str) -> str:
    if channel_id not in history:
        history[channel_id] = []

    msgs = history[channel_id]
    msgs.append({"role": "user", "content": f"{username}: {user_message}"})

    # Garder seulement les derniers messages
    if len(msgs) > MAX_HISTORY * 2:
        msgs = msgs[-(MAX_HISTORY * 2):]
        history[channel_id] = msgs

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un assistant IA sympa sur Discord. "
                    "Réponds de façon naturelle et concise. "
                    "Tu peux utiliser des emojis avec modération. "
                    "N'invente pas d'informations."
                )
            },
            *msgs
        ],
        max_tokens=1000,
        temperature=0.7,
    )

    reply = response.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    return reply


async def send_reply(message, text: str):
    """Envoie la réponse en découpant si > 2000 caractères."""
    chunks = [text[i:i+1990] for i in range(0, len(text), 1990)]
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk)
        else:
            await message.channel.send(chunk)


# ── Événements ────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"⚡ {len(synced)} commande(s) slash synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="/rejoindre | @mention"
        )
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    channel_id = message.channel.id
    content = message.content.strip()
    username = message.author.display_name
    should_respond = False

    # DM → toujours répondre
    if isinstance(message.channel, discord.DMChannel):
        should_respond = True

    # Mentionné → répondre
    elif bot.user in message.mentions:
        should_respond = True
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

    # Salon actif via /rejoindre → répondre à tout le monde
    elif channel_id in active_channels:
        should_respond = True

    if should_respond and content:
        async with message.channel.typing():
            try:
                reply = ask_groq(channel_id, content, username)
                await send_reply(message, reply)
            except Exception as e:
                await message.reply(f"❌ Erreur : `{e}`")

    await bot.process_commands(message)


# ── Commandes Slash ───────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Le bot rejoint et répond à tous les messages du salon")
async def rejoindre(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("✅ Je suis déjà actif ici !", ephemeral=True)
    else:
        active_channels.add(cid)
        save_active(active_channels)
        await interaction.response.send_message(
            f"👋 J'ai rejoint **#{interaction.channel.name}** !\n"
            "Je réponds maintenant à tous les messages ici.\n"
            "Tape `/quitter` pour que j'arrête."
        )


@bot.tree.command(name="quitter", description="Le bot arrête de répondre automatiquement dans ce salon")
async def quitter(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in active_channels:
        active_channels.discard(cid)
        save_active(active_channels)
        history.pop(cid, None)
        await interaction.response.send_message(
            f"👋 J'ai quitté **#{interaction.channel.name}**.\n"
            "Mentionne-moi avec `@` pour continuer à me parler !"
        )
    else:
        await interaction.response.send_message("Je n'étais pas actif ici.", ephemeral=True)


@bot.tree.command(name="effacer", description="Efface la mémoire de conversation dans ce salon")
async def effacer(interaction: discord.Interaction):
    history.pop(interaction.channel_id, None)
    await interaction.response.send_message("🧹 Mémoire effacée !", ephemeral=True)


@bot.tree.command(name="statut", description="Affiche l'état du bot dans ce salon")
async def statut(interaction: discord.Interaction):
    cid = interaction.channel_id
    actif = "✅ Actif (répond à tout le monde)" if cid in active_channels else "💤 En veille (mention uniquement)"
    msgs = len(history.get(cid, [])) // 2
    await interaction.response.send_message(
        f"**Statut :** {actif}\n**Messages en mémoire :** {msgs}",
        ephemeral=True
    )


# ── Lancement ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.getenv("DISCORD_TOKEN"):
        raise ValueError("❌ DISCORD_TOKEN manquant !")
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("❌ GROQ_API_KEY manquant !")
    bot.run(os.getenv("DISCORD_TOKEN"))
