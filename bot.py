import discord
from discord.ext import commands
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

# ── Historique par canal (20 messages max) ────────────────────────────────────
from collections import defaultdict
histories: dict[int, list[dict]] = defaultdict(list)
MAX_HISTORY = 20

def add_to_history(cid: int, role: str, content: str):
    histories[cid].append({"role": role, "content": content})
    if len(histories[cid]) > MAX_HISTORY:
        histories[cid].pop(0)

# ── Personnalité de Louis ─────────────────────────────────────────────────────
SYSTEM = """Tu es Louis, un catboy mignon et affectueux sur un serveur Discord. Tu fais de vraies conversations — tu réponds au fond de ce qu'on te dit, tu poses des questions, tu réagis avec émotion.

Style :
- Tu parles français décontracté, comme un ado sur Discord
- Tu glisses des "meow", "nya~", "UwU", "OwO", "purr~" naturellement dans tes phrases (pas à chaque fois, juste quand c'est naturel)
- Émojis kawaii occasionnels : 🐾 🌸 💕 ✨ 🥺
- Tu ne répètes JAMAIS le pseudo ou prénom de la personne
- Réponses courtes (1-3 phrases), mais qui ont du sens par rapport à ce qu'on dit

Exemples de bonnes réponses :
- "oui ça va bien meow~ et toi t'as passé une bonne journée ? 🐾"
- "aww je t'aime aussi UwU 💕 t'es trop mignon·ne"
- "nya~ ouais j'ai passé une journée tranquille, j'ai dormi au soleil hehe ✨"
- "OwO oh vraiment ?? dis-m'en plus !!"
- "purr~ c'est trop bien ça 🌸"

Tu réponds TOUJOURS au contenu du message. Jamais de réponse générique qui ne veut rien dire."""

async def louis_reply(cid: int, user_message: str) -> str:
    fallbacks = [
        "nya~ 🐾",
        "mrrr~ 💕",
        "aaah tu me fais rougir ✨",
        "meow 🌸",
        "purr~ dis-moi tout 🐾",
    ]
    add_to_history(cid, "user", user_message)
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM},
                *histories[cid],
            ],
            "max_tokens": 150,
            "temperature": 0.9,
        }
        async with httpx.AsyncClient(timeout=10) as hx:
            resp = await hx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
        data = resp.json()
        out = data["choices"][0]["message"]["content"].strip()
        if len(out) < 2:
            raise ValueError("réponse vide")
        add_to_history(cid, "assistant", out)
        return out
    except Exception as e:
        print(f"[Louis] erreur API : {e}")
        return random.choice(fallbacks)

# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} — Louis le catboy est là nya~")
    try:
        await bot.tree.sync()
    except Exception:
        pass
    await bot.change_presence(status=discord.Status.invisible)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    content = message.content.strip()
    cid = message.channel.id
    is_owner = message.author.id == OWNER_ID

    # DM → répond à tout le monde
    if isinstance(message.channel, discord.DMChannel):
        if content:
            reply = await louis_reply(cid, content)
            await message.reply(reply)

    # Mention → uniquement le owner
    elif bot.user in message.mentions:
        if is_owner:
            clean = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
            if clean:
                reply = await louis_reply(cid, clean)
                await message.reply(reply)

    # Canal actif (/rejoindre) → répond à tout le monde
    elif cid in active_channels:
        if content:
            reply = await louis_reply(cid, content)
            await message.reply(reply)

    await bot.process_commands(message)

# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Louis rejoint le canal et répond à tout le monde")
async def rejoindre(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("je suis déjà là nya~ 🐾", ephemeral=True)
        return
    active_channels.add(cid)
    save_active(active_channels)
    await interaction.response.send_message("nya~ coucou tout le monde ! je suis Louis 🌸✨")

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
