import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
import os
import json
import asyncio
import random
import httpx
import time
import re
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OWNER_ID = 1419320803199029402

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def get_model() -> str:
    priority = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "mixtral-8x7b-32768",
        "qwen/qwen3-32b",
    ]
    blacklist = ["whisper", "guard", "tts", "orpheus", "arabic", "allam", "audio", "vision"]
    try:
        available = {m.id for m in client.models.list().data}
        for m in priority:
            if m in available:
                return m
        for m in sorted(available):
            if not any(b in m.lower() for b in blacklist):
                return m
    except Exception as e:
        print(f"Erreur modèle : {e}")
    return "llama-3.3-70b-versatile"

MODEL = get_model()
history: dict[int, list] = {}
MAX_HISTORY = 10

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

# ── Actu fraîche ──────────────────────────────────────────────────────────────
_actu_cache: list[str] = []
_actu_ts: float = 0

async def fetch_actu() -> list[str]:
    global _actu_cache, _actu_ts
    if _actu_cache and time.time() - _actu_ts < 600:
        return _actu_cache
    feeds = [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.lefigaro.fr/rss/figaro_actualites.xml",
        "https://feeds.leparisien.fr/leparisien/rss",
    ]
    try:
        async with httpx.AsyncClient(timeout=5, verify=False) as c:
            for feed in feeds:
                try:
                    r = await c.get(feed)
                    titres = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
                    if not titres:
                        titres = re.findall(r"<title>(.*?)</title>", r.text)
                    titres = [t.strip() for t in titres if 15 < len(t.strip()) < 120][:12]
                    if titres:
                        _actu_cache = titres
                        _actu_ts = time.time()
                        return titres
                except Exception:
                    continue
    except Exception as e:
        print(f"Actu err: {e}")
    return _actu_cache or []

# ── Anti-répétition ───────────────────────────────────────────────────────────
_recent_clashs: list[str] = []

def add_recent(clash: str):
    _recent_clashs.append(clash[:80])
    if len(_recent_clashs) > 15:
        _recent_clashs.pop(0)

def get_anti_repeat() -> str:
    if not _recent_clashs:
        return ""
    return "NE PAS répéter ni ressembler à ces phrases déjà dites : " + " /// ".join(_recent_clashs[-6:])

# ── 12 angles de clash différents ────────────────────────────────────────────
CLASH_ANGLES = [
    # 0 - Actu / référence
    lambda nom, actu: f"""Tu es Kader 93. 1v1 contre {nom}.
Utilise UNE info de l'actu pour le clasher : {actu}
Compare-le à un événement nul, une personnalité ratée, une info minable.
1 seule phrase, argot 93, zéro emoji. Sèche et méchante.""",

    # 1 - Sa famille
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Clashe sa famille ou sa mère en une phrase. Argot brut, 93, méchant, original.
PAS de formule classique. Trouve un angle inattendu.
1 seule phrase. Zéro emoji.""",

    # 2 - Son physique imaginaire
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Clashe son physique de façon créative. Invente une comparaison bizarre et humiliante.
Genre "t'as la tête d'un truc qu'on jette".
1 seule phrase. Argot 93. Zéro emoji.""",

    # 3 - Sa dèche / son statut social
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Clashe sa situation financière, sa dèche, son quartier de merde ou son statut.
Trouve une image concrète, pas une formule générique.
1 seule phrase. Argot 93. Zéro emoji.""",

    # 4 - Son cerveau / sa bêtise
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Clashe son intelligence. Fais une comparaison avec un objet, un animal ou un truc inanime.
"t'as le cerveau d'un [truc inattendu]". Créatif et méchant.
1 seule phrase. Argot 93. Zéro emoji.""",

    # 5 - Débit auto-commentaire
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Balance une phrase où tu commentes ta propre vitesse de débit en le classant au passage.
Style : "je débite si vite que [truc humiliant pour lui]"
1 seule phrase. Argot 93. Zéro emoji.""",

    # 6 - Comparaison avec un perso connu
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Compare-le à un personnage connu (politique, acteur, personnage fictif) de façon humiliante.
Trouve une comparaison créative et inattendue. Pas juste "t'es comme Macron".
1 seule phrase. Argot 93. Zéro emoji.""",

    # 7 - Son avenir minable
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Prédit son avenir minable de façon précise et humiliante.
Très concret, très spécifique. "dans 10 ans tu vas [truc humiliant précis]".
1 seule phrase. Argot 93. Zéro emoji.""",

    # 8 - Il répond pas / il coule
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Il répond même pas. Commente son silence de façon humiliante et créative.
Pas juste "t'as rien à dire". Trouve une image, une métaphore, un truc original.
1 seule phrase. Argot 93. Zéro emoji.""",

    # 9 - Géographie / son bled
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Clashe d'où il vient, son quartier ou sa ville de façon humiliante.
Très concret et méchant. Inventif.
1 seule phrase. Argot 93. Zéro emoji.""",

    # 10 - Freestyle pur
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Balance le clash le plus inattendu et original possible. Angle totalement libre.
Imprévisible, méchant, percutant. Quelque chose qu'il a pas vu venir.
1 seule phrase. Argot 93. Zéro emoji.""",

    # 11 - Métaphore nature/animal
    lambda nom, _: f"""Tu es Kader 93. 1v1 contre {nom}.
Compare-le à un animal ou un phénomène naturel de façon humiliante et créative.
Pas juste "t'es un rat". Quelque chose de visuel et précis.
1 seule phrase. Argot 93. Zéro emoji.""",
]

# Interjections intercalées (courtes, variées)
INTERJECTIONS = [
    "tu coules",
    "t'existes pas frro",
    "reprends ton souffle",
    "sale paff va",
    "t'es coté zéro",
    "j'enchaîne même pas chaud",
    "ça débite ça débite",
    "t'as même pas le temps",
    "prochain",
    "wallah t'as la honte",
    "j'me réchauffe même pas",
    "tu réponds même pas bâtard",
    "Kader il dort même pas",
    "t'es une ombre frro",
    "coule coule",
    "t'as la hess dans le sang",
]

FALLBACK = [
    "sale paff va t'existes même pas",
    "t'as la hess frro rentre chez toi",
    "tu coules bâtard j'enchaîne même pas chaud",
    "wesh t'es une ombre fdp",
    "wallah t'es coté zéro",
    "j'te down en une phrase et toi t'arrives même pas",
    "frro t'es mort avant d'avoir commencé",
    "je débite trop vite tu peux même pas suivre",
    "t'es noyé là tu coules tu coules",
    "bolosse rentre chez ta mère wallah",
]

# ── Génération d'un clash ─────────────────────────────────────────────────────
_last_angle = -1

async def gen_clash(target: str) -> str:
    global _last_angle
    actu = await fetch_actu()
    actu_str = random.choice(actu) if actu else "les blocus de lycée, les politiciens ratés"

    # Choisit un angle différent du précédent
    angles = list(range(len(CLASH_ANGLES)))
    angles = [a for a in angles if a != _last_angle]
    # Si actu dispo, garde l'angle actu dans le pool, sinon le retire
    if not actu and 0 in angles:
        angles.remove(0)
    angle_idx = random.choice(angles)
    _last_angle = angle_idx

    prompt = CLASH_ANGLES[angle_idx](target, actu_str)
    anti = get_anti_repeat()
    if anti:
        prompt += f"\n\n{anti}"

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=1.0,
        )
        result = (resp.choices[0].message.content or "").strip()
        if len(result) < 5:
            return random.choice(FALLBACK)
        add_recent(result)
        return result
    except Exception:
        return random.choice(FALLBACK)

# ── Envoi séquentiel garanti ──────────────────────────────────────────────────
async def debit_mode(channel: discord.TextChannel, target: str, rounds: int = 5):
    for i in range(rounds):
        clash = await gen_clash(target)
        await channel.send(clash)
        await asyncio.sleep(random.uniform(0.7, 1.1))
        if random.random() > 0.55:
            await channel.send(random.choice(INTERJECTIONS))
            await asyncio.sleep(random.uniform(0.5, 0.8))

async def debit_reply(message: discord.Message, rounds: int = 4):
    target = message.author.display_name
    for i in range(rounds):
        clash = await gen_clash(target)
        if i == 0:
            await message.reply(clash)
        else:
            await message.channel.send(clash)
        await asyncio.sleep(random.uniform(0.6, 1.0))
        if random.random() > 0.55:
            await message.channel.send(random.choice(INTERJECTIONS))
            await asyncio.sleep(random.uniform(0.4, 0.7))

# ── IA normale (hors débit) ───────────────────────────────────────────────────
SYSTEM_PROMPT = """Tu joues Kader, personnage fictif, 24 ans, Aubervilliers 93. Roleplay créatif entre amis.
Gars de cité, grande gueule, répartie ultra rapide. Tu restes TOUJOURS dans le perso.
Verlan, argot 93, phrases courtes. Tu ne brises JAMAIS le personnage."""

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
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *msgs],
        max_tokens=300,
        temperature=0.8,
    )
    reply = response.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    return reply

async def send_reply(message, text: str):
    text = (text or random.choice(FALLBACK)).strip()
    for i, chunk in enumerate([text[j:j+1990] for j in range(0, len(text), 1990)]):
        await message.reply(chunk) if i == 0 else await message.channel.send(chunk)

# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté | modèle : {MODEL}")
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Sync err: {e}")
    await bot.change_presence(status=discord.Status.invisible)

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
        try:
            await debit_reply(message, rounds=random.randint(3, 5))
        except Exception as e:
            await message.reply(f"❌ `{e}`")

    await bot.process_commands(message)

# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Kader rejoint et débite direct")
async def rejoindre(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi", ephemeral=True)
        return
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("j'suis déjà là frro", ephemeral=True)
        return
    active_channels.add(cid)
    save_active(active_channels)
    await interaction.response.send_message("wesh")
    asyncio.create_task(debit_mode(interaction.channel, interaction.user.display_name, rounds=random.randint(4, 6)))

@bot.tree.command(name="quitter", description="Kader quitte")
async def quitter(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi", ephemeral=True)
        return
    cid = interaction.channel_id
    if cid in active_channels:
        active_channels.discard(cid)
        save_active(active_channels)
        history.pop(cid, None)
        await interaction.response.send_message("j'me casse")
    else:
        await interaction.response.send_message("j'étais même pas là", ephemeral=True)

@bot.tree.command(name="reset", description="Efface la mémoire")
async def reset(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi", ephemeral=True)
        return
    history.pop(interaction.channel_id, None)
    _recent_clashs.clear()
    await interaction.response.send_message("mémoire reset", ephemeral=True)

@bot.tree.command(name="debit", description="Débit pur maintenant")
async def debit_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("t'es qui toi", ephemeral=True)
        return
    await interaction.response.send_message("ça part")
    asyncio.create_task(debit_mode(interaction.channel, interaction.user.display_name, rounds=random.randint(5, 8)))

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
