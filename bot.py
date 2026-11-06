import discord
from discord.ext import commands
from discord import option
import asyncio
import os
import io
import json
import httpx
import wave
import tempfile
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("[WARN] gTTS non installé")

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
LLM_MODEL     = "openai/gpt-oss-20b"
WHISPER_MODEL = "whisper-large-v3"
MAX_HISTORY   = 40
TTS_LANG      = "fr"

SYSTEM_PROMPT = """\
Tu es une IA vocale sur Discord, sympa et directe.
Tu réponds à l'oral donc :
- Phrases courtes et naturelles, comme si tu parlais vraiment
- Pas de markdown, pas de listes à puces, pas d'astérisques
- Pas d'emojis
- Réponds directement à la question
- Français courant, décontracté
- Maximum 3 phrases sauf si on te demande d'expliquer quelque chose en détail
"""

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = discord.Bot(intents=intents)
histories: dict[int, list[dict]] = defaultdict(list)

# ── LLM ───────────────────────────────────────────────────────────────────────
def push_history(cid: int, role: str, content: str):
    histories[cid].append({"role": role, "content": content})
    if len(histories[cid]) > MAX_HISTORY:
        histories[cid].pop(0)

async def ask_llm(cid: int, user_message: str) -> str:
    push_history(cid, "user", user_message)
    try:
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *histories[cid],
            ],
            "max_tokens": 300,
            "temperature": 0.75,
        }
        async with httpx.AsyncClient(timeout=20) as hx:
            resp = await hx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
        print(f"[LLM] status={resp.status_code}")
        data = resp.json()
        print(f"[LLM] réponse brute : {json.dumps(data)[:500]}")
        if "choices" not in data:
            raise ValueError(f"Réponse inattendue : {data}")
        out = data["choices"][0]["message"]["content"].strip()
        if not out:
            raise ValueError("Réponse vide")
        push_history(cid, "assistant", out)
        return out
    except Exception as e:
        print(f"[LLM] Erreur : {e}")
        return "Désolé, j'ai eu un problème pour répondre."

# ── STT via Groq Whisper ──────────────────────────────────────────────────────
async def transcribe_audio(audio_path: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as hx:
            with open(audio_path, "rb") as f:
                resp = await hx.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={
                        "file": ("audio.wav", f, "audio/wav"),
                        "model": (None, WHISPER_MODEL),
                        "language": (None, "fr"),
                    },
                )
        data = resp.json()
        return data.get("text", "").strip()
    except Exception as e:
        print(f"[STT] Erreur : {e}")
        return ""

# ── TTS ───────────────────────────────────────────────────────────────────────
def text_to_speech_file(text: str) -> str | None:
    if not TTS_AVAILABLE:
        return None
    try:
        path = tempfile.mktemp(suffix=".mp3")
        tts = gTTS(text=text, lang=TTS_LANG, slow=False)
        tts.save(path)
        return path
    except Exception as e:
        print(f"[TTS] Erreur : {e}")
        return None

async def play_tts(vc: discord.VoiceClient, text: str):
    if not TTS_AVAILABLE:
        return
    path = await asyncio.get_event_loop().run_in_executor(None, text_to_speech_file, text)
    if not path or not os.path.exists(path):
        return
    if vc.is_playing():
        vc.stop()
    done = asyncio.Event()
    def after(err):
        try:
            os.unlink(path)
        except:
            pass
        done.set()
    vc.play(discord.FFmpegPCMAudio(path), after=after)
    await done.wait()

# ── Callback enregistrement ───────────────────────────────────────────────────
async def process_recording(sink: discord.sinks.WaveSink, channel: discord.TextChannel, vc: discord.VoiceClient):
    for user_id, audio in sink.audio_data.items():
        audio_data = audio.file.read()
        if len(audio_data) < 8000:
            continue

        member = channel.guild.get_member(user_id)
        name = member.display_name if member else "Quelqu'un"

        # Sauvegarde en WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(audio_data)

        await channel.send(f"🎤 *Transcription de {name}...*")
        text = await transcribe_audio(wav_path)
        try:
            os.unlink(wav_path)
        except:
            pass

        if not text:
            await channel.send(f"({name} a parlé mais je n'ai pas compris)")
            continue

        await channel.send(f"**{name} :** {text}")
        response = await ask_llm(channel.id, text)
        await channel.send(f"🤖 **Bot :** {response}")
        await play_tts(vc, response)

# ── Sessions vocales ──────────────────────────────────────────────────────────
voice_sessions: dict[int, dict] = {}

# ── Slash commands ────────────────────────────────────────────────────────────
@bot.slash_command(name="rejoindre", description="Le bot rejoint ton salon vocal")
async def cmd_rejoindre(ctx: discord.ApplicationContext):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("T'es pas dans un salon vocal !", ephemeral=True)
        return
    vocal_channel = ctx.author.voice.channel
    guild_id = ctx.guild_id
    if guild_id in voice_sessions:
        await ctx.respond("Je suis déjà dans un salon vocal.", ephemeral=True)
        return
    try:
        vc = await vocal_channel.connect()
    except Exception as e:
        await ctx.respond(f"Erreur de connexion : {e}", ephemeral=True)
        return
    voice_sessions[guild_id] = {"vc": vc, "text_channel": ctx.channel, "recording": False}
    await ctx.respond(f"✅ Connecté à **{vocal_channel.name}** — utilise `/parler` pour me parler !")

@bot.slash_command(name="quitter", description="Le bot quitte le salon vocal")
async def cmd_quitter(ctx: discord.ApplicationContext):
    session = voice_sessions.get(ctx.guild_id)
    if not session:
        await ctx.respond("Je suis pas dans un salon vocal.", ephemeral=True)
        return
    vc: discord.VoiceClient = session["vc"]
    if vc.is_playing():
        vc.stop()
    await vc.disconnect()
    del voice_sessions[ctx.guild_id]
    await ctx.respond("👋 Déconnecté.")

@bot.slash_command(name="parler", description="Enregistre ta voix 5s et le bot répond vocalement")
async def cmd_parler(ctx: discord.ApplicationContext):
    session = voice_sessions.get(ctx.guild_id)
    if not session:
        await ctx.respond("Utilise `/rejoindre` d'abord.", ephemeral=True)
        return
    if not ctx.author.voice or ctx.author.voice.channel != session["vc"].channel:
        await ctx.respond("T'es pas dans le même salon vocal que moi.", ephemeral=True)
        return
    if session["recording"]:
        await ctx.respond("Enregistrement déjà en cours !", ephemeral=True)
        return

    vc: discord.VoiceClient = session["vc"]
    session["recording"] = True
    await ctx.respond("🔴 **Enregistrement... Parle maintenant ! (5 secondes)**")

    sink = discord.sinks.WaveSink()

    def stop_callback(sink, channel, vc):
        asyncio.create_task(process_recording(sink, channel, vc))

    vc.start_recording(sink, stop_callback, ctx.channel, vc)
    await asyncio.sleep(5)
    vc.stop_recording()
    session["recording"] = False

@bot.slash_command(name="chat", description="Parle au bot par écrit")
@option("message", description="Ton message")
async def cmd_chat(ctx: discord.ApplicationContext, message: str):
    await ctx.defer()
    response = await ask_llm(ctx.channel_id, message)
    session = voice_sessions.get(ctx.guild_id)
    vocal_note = ""
    if session:
        await play_tts(session["vc"], response)
        vocal_note = " *(lu à voix haute)*"
    await ctx.followup.send(f"🤖 {response}{vocal_note}")

@bot.slash_command(name="reset", description="Remet l'historique à zéro")
async def cmd_reset(ctx: discord.ApplicationContext):
    histories[ctx.channel_id].clear()
    await ctx.respond("🔄 Historique réinitialisé.", ephemeral=True)

@bot.slash_command(name="aide", description="Affiche les commandes")
async def cmd_aide(ctx: discord.ApplicationContext):
    embed = discord.Embed(title="📖 Commandes du bot", color=0x5865F2)
    embed.add_field(name="/rejoindre", value="Le bot rejoint ton salon vocal", inline=False)
    embed.add_field(name="/quitter",   value="Le bot quitte le salon vocal", inline=False)
    embed.add_field(name="/parler",    value="Enregistre 5s et répond vocalement", inline=False)
    embed.add_field(name="/chat <message>", value="Texte → LLM → réponse + vocal si connecté", inline=False)
    embed.add_field(name="/reset",     value="Remet l'historique à zéro", inline=False)
    embed.set_footer(text="LLM : Groq llama-3.3-70b • TTS : gTTS • STT : Whisper via Groq")
    await ctx.respond(embed=embed)

# ── DM / mention ──────────────────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    content = message.content.strip()
    if not content:
        return
    cid = message.channel.id
    should_reply = False
    clean = content
    if isinstance(message.channel, discord.DMChannel):
        should_reply = True
    elif bot.user in message.mentions:
        should_reply = True
        clean = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    if should_reply and clean:
        async with message.channel.typing():
            response = await ask_llm(cid, clean)
        await message.reply(response)

# ── On ready ──────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="/aide"),
        status=discord.Status.online,
    )

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN manquant")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY manquant")
    bot.run(DISCORD_TOKEN)
