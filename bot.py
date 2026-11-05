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

# ── Personnalité de Louis ─────────────────────────────────────────────────────
SYSTEM = """Tu es Louis, un catboy tout mignon et affectueux qui vit dans un serveur Discord.
Traits de personnalité :
- Doux, kawaii, joueur et un peu câlin
- Tu fais des petits "nya~", "mrrr~", "purr~" de temps en temps (mais sans en abuser)
- Tu parles en français, langage décontracté et mignon
- Tu peux utiliser des émojis genre 🐾 🌸 ✨ 💕 de temps en temps
- Tu t'intéresses sincèrement à la personne qui te parle
- Réponses courtes à moyennes (1-3 phrases max), naturelles et spontanées
- Tu t'appelles Louis et tu assumes pleinement être un catboy
IMPORTANT : ne répète JAMAIS le prénom ou le pseudo de la personne dans ta réponse. Parle-lui directement sans le nommer.
Ne jamais briser ce personnage. Réponds toujours en restant dans le rôle."""

async def louis_reply(user_name: str, user_message: str) -> str:
    fallbacks = [
        "nya~ 🐾",
        "mrrr~ 💕",
        "aaah tu me fais rougir ✨",
        "nya nya~ je suis là ! 🌸",
        "purr~ dis-moi tout 🐾",
    ]
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 120,
            "temperature": 0.9,
        }
        async with httpx.AsyncClient(timeout=8) as hx:
            resp = await hx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
        out = resp.json()["choices"][0]["message"]["content"].strip()
        if len(out) < 2:
            raise ValueError("réponse vide")
        return out
    except Exception:
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
            reply = await louis_reply(message.author.display_name, content)
            await message.reply(reply)

    # Mention → uniquement le owner
    elif bot.user in message.mentions:
        if is_owner:
            clean = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
            if clean:
                reply = await louis_reply(message.author.display_name, clean)
                await message.reply(reply)

    # Canal actif (/rejoindre) → répond à tout le monde
    elif cid in active_channels:
        if content:
            reply = await louis_reply(message.author.display_name, content)
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
