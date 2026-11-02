import discord
from discord.ext import commands
from openai import OpenAI
import os, json, asyncio, random
from pathlib import Path

OWNER_ID = 1419320803199029402
ACTIVE_FILE = "active_channels.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")

def load_active():
    if Path(ACTIVE_FILE).exists():
        with open(ACTIVE_FILE) as f: return set(json.load(f))
    return set()

def save_active(s):
    with open(ACTIVE_FILE, "w") as f: json.dump(list(s), f)

active_channels = load_active()

# ── Prompt simple et direct ───────────────────────────────────────────────────
PROMPT = """T'es Kader, 93, mode débit. 1v1 clash.
Règles : 1 seule phrase courte. Argot 93. Pas d'emoji. Méchant et original.
Change d'angle à chaque fois : famille, physique, cerveau, dèche, avenir, silence, quartier, comparaison bizarre.
Réponds UNIQUEMENT avec la phrase de clash. Rien d'autre."""

# Fallback si IA flanche
FALLBACK = [
    "sale paff va t'existes même pas",
    "tu coules bâtard j'enchaîne même pas chaud",
    "wallah t'as la honte rentre chez ta mère",
    "frro t'es mort avant d'avoir commencé",
    "t'as le cerveau d'une poubelle vide fdp",
    "dans 10 ans tu ramasses les caddies au carrefour",
    "ta famille elle te reconnaît même plus tellement t'as la hess",
    "t'es l'erreur que même ta mère regrette",
    "t'as rien à dire bâtard le silence c'est toi",
    "wesh t'es une ombre que personne regarde",
    "ton quartier c'est une blague même les rats partent",
    "je t'enchaîne et t'arrives même pas à finir une phrase",
]

_recent: list[str] = []

def clash_sync(target: str) -> str:
    anti = ""
    if _recent:
        anti = " NE PAS répéter : " + " / ".join(_recent[-4:])
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": PROMPT + anti},
                      {"role": "user", "content": f"cible : {target}"}],
            max_tokens=50,
            temperature=1.0,
        )
        out = (r.choices[0].message.content or "").strip()
        if len(out) < 5 or len(out) > 200:
            return random.choice(FALLBACK)
        _recent.append(out[:60])
        if len(_recent) > 12: _recent.pop(0)
        return out
    except Exception:
        return random.choice(FALLBACK)

async def debite(channel, target, reply_msg=None, rounds=4):
    for i in range(rounds):
        txt = await asyncio.get_event_loop().run_in_executor(None, clash_sync, target)
        if i == 0 and reply_msg:
            await reply_msg.reply(txt)
        else:
            await channel.send(txt)
        await asyncio.sleep(0.6)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} | llama-3.3-70b-versatile")
    try: await bot.tree.sync()
    except: pass
    await bot.change_presence(status=discord.Status.invisible)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user: return
    if message.author.id != OWNER_ID: return
    content = message.content.strip()
    cid = message.channel.id
    respond = False

    if isinstance(message.channel, discord.DMChannel):
        respond = True
    elif bot.user in message.mentions:
        respond = True
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    elif cid in active_channels:
        respond = True

    if respond and content:
        asyncio.create_task(debite(message.channel, message.author.display_name, message, rounds=random.randint(3,5)))

    await bot.process_commands(message)

@bot.tree.command(name="rejoindre", description="Kader rejoint et débite")
async def rejoindre(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("nan", ephemeral=True); return
    cid = interaction.channel_id
    if cid in active_channels:
        await interaction.response.send_message("j'suis déjà là", ephemeral=True); return
    active_channels.add(cid); save_active(active_channels)
    await interaction.response.send_message("wesh")
    asyncio.create_task(debite(interaction.channel, interaction.user.display_name, rounds=random.randint(4,6)))

@bot.tree.command(name="quitter", description="Kader quitte")
async def quitter(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("nan", ephemeral=True); return
    cid = interaction.channel_id
    if cid in active_channels:
        active_channels.discard(cid); save_active(active_channels)
        await interaction.response.send_message("j'me casse")
    else:
        await interaction.response.send_message("j'étais même pas là", ephemeral=True)

@bot.tree.command(name="debit", description="Débit pur")
async def debit_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("nan", ephemeral=True); return
    await interaction.response.send_message("ça part")
    asyncio.create_task(debite(interaction.channel, interaction.user.display_name, rounds=random.randint(5,8)))

@bot.tree.command(name="reset")
async def reset(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("nan", ephemeral=True); return
    _recent.clear()
    await interaction.response.send_message("reset", ephemeral=True)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
