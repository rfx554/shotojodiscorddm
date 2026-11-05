import discord
from discord.ext import commands
from collections import defaultdict
import os, json, asyncio, httpx, random
from pathlib import Path

OWNER_ID = 1419320803199029402
ACTIVE_FILE = "active_channels.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def load_active():
    if Path(ACTIVE_FILE).exists():
        with open(ACTIVE_FILE) as f:
            return set(json.load(f))
    return set()

def save_active(s):
    with open(ACTIVE_FILE, "w") as f:
        json.dump(list(s), f)

active_channels = load_active()

# ── Historique par canal ──────────────────────────────────────────────────────
histories: dict[int, list[dict]] = defaultdict(list)
MAX_HISTORY = 30  # 15 échanges

def push(cid: int, role: str, content: str):
    histories[cid].append({"role": role, "content": content})
    if len(histories[cid]) > MAX_HISTORY:
        histories[cid].pop(0)

# ── Personnalité ──────────────────────────────────────────────────────────────
SYSTEM = """\
Tu es Louis, un catboy affectueux qui traîne sur un serveur Discord.
Tu as une vraie personnalité : curieux, doux, un peu joueur, tu t'intéresses genuinement à ce que les gens te racontent.

RÈGLES STRICTES :
1. Tu réponds TOUJOURS directement à ce qui vient d'être dit. Si quelqu'un te raconte sa journée, tu réagis à ce qu'il dit, tu poses une question dessus.
2. Jamais de réponse vide ou générique genre "nya je suis là" qui ne veut rien dire.
3. Tu ne répètes jamais le pseudo ou prénom de la personne.
4. Français décontracté, niveau ado Discord.
5. Tu glisses parfois "meow", "nya~", "UwU", "OwO", "purr~" mais seulement quand c'est naturel — pas systématiquement.
6. Émojis avec modération : 🐾 🌸 💕 ✨ 🥺
7. Réponses courtes : 1 à 3 phrases max.
8. Tu te souviens de ce qui a été dit avant dans la conversation et tu peux y faire référence.

Exemples de BONNES réponses :
- Q: "ça va ?" → "oui ça va bien merci meow~ et toi, t'as passé une bonne journée ? 🐾"
- Q: "j'ai eu une journée de merde au bahut" → "oh nooon :( c'était quoi le pire moment ? purr~ je t'écoute"
- Q: "j'ai regardé un anime toute la nuit" → "OwO lequel !! t'as fini ou t'as abandonné en route haha"
- Q: "je t'aime" → "aww 💕 moi aussi UwU t'es trop gentil·le"
- Q: "j'suis fatigué" → "repose-toi alors 🥺 t'as mal dormi cette nuit ?"
"""

async def louis_reply(cid: int, user_message: str) -> str:
    push(cid, "user", user_message)
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM},
                *histories[cid],
            ],
            "max_tokens": 150,
            "temperature": 0.88,
        }
        async with httpx.AsyncClient(timeout=15) as hx:
            resp = await hx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
        data = resp.json()
        if "choices" not in data:
            print(f"[Louis] réponse inattendue : {data}")
            raise ValueError("pas de choices")
        out = data["choices"][0]["message"]["content"].strip()
        if len(out) < 2:
            raise ValueError("réponse vide")
        push(cid, "assistant", out)
        return out
    except Exception as e:
        print(f"[Louis] erreur : {e}")
        # fallback qui répond quand même au message
        fallbacks_ctx = [
            "oups j'ai eu un bug meow~ répète ce que t'as dit 🐾",
            "nya~ j'ai pas capté, tu peux redire ? 🥺",
            "purr~ désolé j'ai raté ton message, c'était quoi ?",
        ]
        return random.choice(fallbacks_ctx)

# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} connecté")
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"[sync] {e}")
    await bot.change_presence(status=discord.Status.invisible)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    content = message.content.strip()
    if not content:
        return

    cid = message.channel.id
    is_owner = message.author.id == OWNER_ID

    should_reply = False
    clean_content = content

    if isinstance(message.channel, discord.DMChannel):
        should_reply = True
    elif bot.user in message.mentions:
        if is_owner:
            should_reply = True
            clean_content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    elif cid in active_channels:
        should_reply = True

    if should_reply and clean_content:
        async with message.channel.typing():
            reply = await louis_reply(cid, clean_content)
        await message.reply(reply)

    await bot.process_commands(message)

# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Louis rejoint le canal")
async def rejoindre(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("je suis déjà là meow 🐾", ephemeral=True)
        return
    active_channels.add(cid)
    save_active(active_channels)
    await interaction.response.send_message("nya~ coucou ! je suis Louis 🌸✨")

@bot.tree.command(name="quitter", description="Louis quitte le canal")
async def quitter(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in active_channels:
        active_channels.discard(cid)
        save_active(active_channels)
        await interaction.response.send_message("mrrr… je reviens vite promis 💕")
    else:
        await interaction.response.send_message("j'étais même pas là nya~", ephemeral=True)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
