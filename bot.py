import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import io
import json
import httpx
import wave
import struct
import tempfile
from pathlib import Path
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
LLM_MODEL     = "llama-3.3-70b-versatile"
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
bot = commands.Bot(command_prefix="!", intents=intents)
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
        data = resp.json()
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
    source = discord.FFmpegPCMAudio(path)
    done = asyncio.Event()
    def after(err):
        if err:
            print(f"[TTS] Erreur lecture : {err}")
        try:
            os.unlink(path)
        except:
            pass
        done.set()
    vc.play(source, after=after)
    await done.wait()

# ── Recorder custom (sans discord.sinks) ─────────────────────────────────────
class AudioRecorder(discord.AudioSink):
    """Enregistre l'audio PCM de tous les utilisateurs dans un buffer."""

    def __init__(self):
        self.buffers: dict[int, bytearray] = defaultdict(bytearray)

    def write(self, data: discord.AudioData):
        self.buffers[data.user.id] += data.data

    def cleanup(self):
        pass

    def save_wav(self, user_id: int, path: str):
        """Sauvegarde le buffer PCM en fichier WAV."""
        pcm = bytes(self.buffers.get(user_id, b""))
        if not pcm:
            return False
        with wave.open(path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)   # 16-bit
            wf.setframerate(48000)
            wf.writeframes(pcm)
        return True

    def get_active_users(self) -> list[int]:
        """Retourne les user_id qui ont parlé (buffer non vide)."""
        return [uid for uid, buf in self.buffers.items() if len(buf) > 8000]

# ── Sessions vocales actives ──────────────────────────────────────────────────
voice_sessions: dict[int, dict] = {}  # guild_id → {vc, text_channel, recorder, recording}

# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Le bot rejoint ton salon vocal")
async def cmd_rejoindre(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("T'es pas dans un salon vocal !", ephemeral=True)
        return
    vocal_channel = interaction.user.voice.channel
    guild_id = interaction.guild_id
    if guild_id in voice_sessions:
        await interaction.response.send_message("Je suis déjà dans un salon vocal.", ephemeral=True)
        return
    try:
        vc = await vocal_channel.connect()
    except Exception as e:
        await interaction.response.send_message(f"Erreur de connexion : {e}", ephemeral=True)
        return
    voice_sessions[guild_id] = {
        "vc": vc,
        "text_channel": interaction.channel,
        "recorder": None,
        "recording": False,
    }
    await interaction.response.send_message(
        f"✅ Connecté à **{vocal_channel.name}** — utilise `/parler` pour me parler !"
    )

@bot.tree.command(name="quitter", description="Le bot quitte le salon vocal")
async def cmd_quitter(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    session = voice_sessions.get(guild_id)
    if not session:
        await interaction.response.send_message("Je suis pas dans un salon vocal.", ephemeral=True)
        return
    vc: discord.VoiceClient = session["vc"]
    if vc.is_playing():
        vc.stop()
    await vc.disconnect()
    del voice_sessions[guild_id]
    await interaction.response.send_message("👋 Déconnecté.")

@bot.tree.command(name="parler", description="Enregistre ta voix 5s et le bot répond vocalement")
async def cmd_parler(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    session = voice_sessions.get(guild_id)
    if not session:
        await interaction.response.send_message(
            "Le bot n'est pas dans un salon vocal. Utilise `/rejoindre` d'abord.", ephemeral=True
        )
        return
    if not interaction.user.voice or interaction.user.voice.channel != session["vc"].channel:
        await interaction.response.send_message(
            "T'es pas dans le même salon vocal que moi.", ephemeral=True
        )
        return
    if session["recording"]:
        await interaction.response.send_message("Enregistrement déjà en cours !", ephemeral=True)
        return

    vc: discord.VoiceClient = session["vc"]
    await interaction.response.send_message("🔴 **Enregistrement... Parle maintenant ! (5 secondes)**")

    recorder = AudioRecorder()
    session["recorder"] = recorder
    session["recording"] = True

    vc.listen(recorder)
    await asyncio.sleep(5)
    vc.stop_listening()

    session["recording"] = False
    active_users = recorder.get_active_users()

    if not active_users:
        await interaction.channel.send("Je n'ai rien entendu 🤔")
        return

    for user_id in active_users:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        saved = recorder.save_wav(user_id, wav_path)
        if not saved:
            continue

        member = interaction.guild.get_member(user_id)
        name = member.display_name if member else "Quelqu'un"

        await interaction.channel.send(f"🎤 *Transcription de {name}...*")
        text = await transcribe_audio(wav_path)
        try:
            os.unlink(wav_path)
        except:
            pass

        if not text:
            await interaction.channel.send(f"({name} a parlé mais je n'ai pas compris)")
            continue

        await interaction.channel.send(f"**{name} :** {text}")
        response = await ask_llm(interaction.channel_id, text)
        await interaction.channel.send(f"🤖 **Bot :** {response}")
        await play_tts(vc, response)

@bot.tree.command(name="chat", description="Parle au bot par écrit (répond aussi en vocal si connecté)")
@app_commands.describe(message="Ton message")
async def cmd_chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    response = await ask_llm(interaction.channel_id, message)
    session = voice_sessions.get(interaction.guild_id)
    vocal_note = ""
    if session:
        await play_tts(session["vc"], response)
        vocal_note = " *(lu à voix haute)*"
    await interaction.followup.send(f"🤖 {response}{vocal_note}")

@bot.tree.command(name="reset", description="Remet l'historique de conversation à zéro")
async def cmd_reset(interaction: discord.Interaction):
    histories[interaction.channel_id].clear()
    await interaction.response.send_message("🔄 Historique réinitialisé.", ephemeral=True)

@bot.tree.command(name="aide", description="Affiche les commandes disponibles")
async def cmd_aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Commandes du bot", color=0x5865F2)
    embed.add_field(name="/rejoindre", value="Le bot rejoint ton salon vocal", inline=False)
    embed.add_field(name="/quitter",   value="Le bot quitte le salon vocal", inline=False)
    embed.add_field(name="/parler",    value="Enregistre ta voix 5s et le bot répond vocalement", inline=False)
    embed.add_field(name="/chat <message>", value="Texte → LLM → réponse texte + vocal si connecté", inline=False)
    embed.add_field(name="/reset",     value="Remet l'historique à zéro", inline=False)
    embed.set_footer(text="LLM : Groq llama-3.3-70b • TTS : gTTS • STT : Whisper via Groq")
    await interaction.response.send_message(embed=embed)

# ── Réponse en DM ou mention ──────────────────────────────────────────────────
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
    await bot.process_commands(message)

# ── On ready ──────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"[sync] Erreur : {e}")
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
