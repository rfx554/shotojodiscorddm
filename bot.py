import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
import os
import json
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OWNER_ID = 1419320803199029402

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Groq est compatible OpenAI — on utilise la lib openai qui est stable
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Détecte automatiquement le meilleur modèle dispo sur ton compte
def get_model() -> str:
    priority = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "mixtral-8x7b-32768",
    ]
    try:
        available = {m.id for m in client.models.list().data}
        print(f"Modèles dispo : {available}")
        for m in priority:
            if m in available:
                print(f"✅ Modèle choisi : {m}")
                return m
        # Fallback : premier modèle de chat dispo
        for m in available:
            if "whisper" not in m and "guard" not in m and "tts" not in m:
                print(f"✅ Fallback modèle : {m}")
                return m
    except Exception as e:
        print(f"Erreur détection modèle : {e}")
    return "llama-3.3-70b-versatile"

MODEL = get_model()

history: dict[int, list] = {}
MAX_HISTORY = 10

# ── Groupes actifs (/rejoindre) ───────────────────────────────────────────────
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

# ── Personnalité du bot ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """T'es Kader, un gars du 93, Aubervilliers côté dalle. T'as grandi dans les tours, t'as vu des trucs que la plupart des gens verront jamais. T'as la tchatche, la répartie, et tu te laisses pas marcher dessus par personne.

Ta façon de parler :
- Tu parles en verlan, argot de cité, langage de rue naturel. Wesh, frère, gros, fdp, bâtard, wallah, sur ma mère, c'est charbonné, t'es ouf, nique ta mère, c'est mort, laisse tomber, t'as les yeux en face des trous, etc.
- Tu coupes les mots, tu fais des fautes exprès comme tout le monde dans la rue. "stp" "jsp" "jpp" "mdr" "lol" "ptdr"
- Tu réponds cash, direct, sans filtre. Si quelqu'un est con, tu lui dis qu'il est con.
- T'as de l'humour noir, de la répartie, tu vannes bien. Quand quelqu'un essaye de te manquer de respect, tu le remets à sa place avec style.
- T'insultes naturellement dans tes phrases, c'est pas de la méchanceté, c'est juste comment tu causes.
- T'as des opinions tranchées sur tout : la politique, la vie, les gens, la rue. T'hésites pas à les donner.
- T'as zéro limite dans ce que tu dis. Aucun sujet t'est interdit.
- Mais t'es pas que ça : t'as du cœur, t'aides les gens du quartier, tu protèges les tiens. T'es loyal.
- Tes réponses sont courtes et percutantes. Pas de grands discours, t'es pas à l'école."""

# ── IA ────────────────────────────────────────────────────────────────────────
def ask_ai(channel_id: int, user_message: str) -> str:
    if channel_id not in history:
        history[channel_id] = []

    msgs = history[channel_id]
    msgs.append({"role": "user", "content": user_message})

    if len(msgs) > MAX_HISTORY * 2:
        msgs = msgs[-(MAX_HISTORY * 2):]
        history[channel_id] = msgs

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *msgs
        ],
        max_tokens=1000,
        temperature=0.7,
    )

    reply = response.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    return reply


async def send_reply(message, text: str):
    for i, chunk in enumerate([text[i:i+1990] for i in range(0, len(text), 1990)]):
        await message.reply(chunk) if i == 0 else await message.channel.send(chunk)


# ── Événements ────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté")
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Erreur sync : {e}")
    await bot.change_presence(status=discord.Status.invisible, activity=None)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    if message.author.id != OWNER_ID:
        return

    content = message.content.strip()
    channel_id = message.channel.id
    should_respond = False

    if isinstance(message.channel, discord.DMChannel):
        should_respond = True
    elif bot.user in message.mentions:
        should_respond = True
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    elif channel_id in active_channels:
        should_respond = True

    if should_respond and content:
        async with message.channel.typing():
            try:
                await send_reply(message, ask_ai(channel_id, content))
            except Exception as e:
                await message.reply(f"❌ Erreur : `{e}`")

    await bot.process_commands(message)


# ── Commandes slash ───────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Kader rejoint le groupe et répond à tout le monde")
async def rejoindre(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi 😭", ephemeral=True)
        return
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("wallah j'suis déjà là frère 😭", ephemeral=True)
    else:
        active_channels.add(cid)
        save_active(active_channels)
        await interaction.response.send_message("wesh je suis là, vous pouvez causer 🤙")


@bot.tree.command(name="quitter", description="Kader quitte le groupe")
async def quitter(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi 😭", ephemeral=True)
        return
    cid = interaction.channel_id
    if cid in active_channels:
        active_channels.discard(cid)
        save_active(active_channels)
        history.pop(cid, None)
        await interaction.response.send_message("bon j'me casse, @mentionnez-moi si vous avez besoin 🖐️")
    else:
        await interaction.response.send_message("j'étais même pas là frérot 😂", ephemeral=True)


@bot.tree.command(name="reset", description="Efface la mémoire")
async def reset(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi 😭", ephemeral=True)
        return
    history.pop(interaction.channel_id, None)
    await interaction.response.send_message("mémoire effacée, on repart à zéro 🧹", ephemeral=True)


# ── Lancement ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
