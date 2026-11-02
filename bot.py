import discord
from discord import app_commands
from discord.ext import commands
from groq import Groq
import os

# ── Config ────────────────────────────────────────────────────────────────────
OWNER_ID = 1419320803199029402  # Seul utilisateur auquel le bot répond
MODEL    = "gemma2-9b-it"       # Modèle Groq gratuit et stable

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

history: dict[int, list] = {}
MAX_HISTORY = 10

# ── IA ────────────────────────────────────────────────────────────────────────
def ask_groq(channel_id: int, user_message: str) -> str:
    if channel_id not in history:
        history[channel_id] = []

    msgs = history[channel_id]
    msgs.append({"role": "user", "content": user_message})

    if len(msgs) > MAX_HISTORY * 2:
        msgs = msgs[-(MAX_HISTORY * 2):]
        history[channel_id] = msgs

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "Tu es un assistant IA sympa. Réponds de façon naturelle et concise. Tu peux utiliser des emojis avec modération."
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
        print(f"⚡ {len(synced)} commande(s) synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    # Aucun statut affiché
    await bot.change_presence(status=discord.Status.invisible, activity=None)


@bot.event
async def on_message(message: discord.Message):
    # Ignorer le bot lui-même
    if message.author == bot.user:
        return

    # Ignorer tout le monde sauf le owner
    if message.author.id != OWNER_ID:
        return

    content = message.content.strip()
    channel_id = message.channel.id
    should_respond = False

    # DM → toujours répondre (si c'est le owner)
    if isinstance(message.channel, discord.DMChannel):
        should_respond = True

    # Dans un serveur → seulement si le bot est mentionné
    elif bot.user in message.mentions:
        should_respond = True
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

    if should_respond and content:
        async with message.channel.typing():
            try:
                reply = ask_groq(channel_id, content)
                await send_reply(message, reply)
            except Exception as e:
                await message.reply(f"❌ Erreur : `{e}`")

    await bot.process_commands(message)


# ── Commande pour effacer la mémoire ─────────────────────────────────────────
@bot.tree.command(name="effacer", description="Efface la mémoire de conversation")
async def effacer(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
        return
    history.pop(interaction.channel_id, None)
    await interaction.response.send_message("🧹 Mémoire effacée !", ephemeral=True)


# ── Lancement ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.getenv("DISCORD_TOKEN"):
        raise ValueError("❌ DISCORD_TOKEN manquant !")
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("❌ GROQ_API_KEY manquant !")
    bot.run(os.getenv("DISCORD_TOKEN"))
