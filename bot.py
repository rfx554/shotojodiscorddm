import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import io
import json
import httpx
import random
import wave
import struct
from pathlib import Path
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Dépendances optionnelles ──────────────────────────────────────────────────
try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("[WARN] gTTS non installé — pas de TTS vocal")

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    print("[WARN] SpeechRecognition non installé — pas de STT vocal")

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN", "")
LLM_MODEL      = "llama-3.3-70b-versatile"
WHISPER_MODEL  = "whisper-large-v3"
MAX_HISTORY    = 40   # messages dans l'historique
TTS_LANG       = "fr"
LISTEN_SILENCE = 2.0  # secondes de silence avant d'envoyer l'audio

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
    """Envoie un message au LLM et retourne la réponse texte."""
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
async def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcrit de l'audio (bytes WAV) via l'API Whisper de Groq."""
    try:
        async with httpx.AsyncClient(timeout=30) as hx:
            resp = await hx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={
                    "file": ("audio.wav", audio_bytes, "audio/wav"),
                    "model": (None, WHISPER_MODEL),
                    "language": (None, "fr"),
                },
            )
        data = resp.json()
        text = data.get("text", "").strip()
        return text
    except Exception as e:
        print(f"[STT] Erreur : {e}")
        return ""


# ── TTS ───────────────────────────────────────────────────────────────────────
def text_to_speech_file(text: str, path: str = "/tmp/tts_output.mp3"):
    """Convertit du texte en MP3 avec gTTS."""
    if not TTS_AVAILABLE:
        return None
    try:
        tts = gTTS(text=text, lang=TTS_LANG, slow=False)
        tts.save(path)
        return path
    except Exception as e:
        print(f"[TTS] Erreur : {e}")
        return None


async def play_tts(vc: discord.VoiceClient, text: str):
    """Génère et joue du TTS dans le salon vocal."""
    if not TTS_AVAILABLE:
        return
    path = await asyncio.get_event_loop().run_in_executor(
        None, text_to_speech_file, text
    )
    if not path or not os.path.exists(path):
        return
    if vc.is_playing():
        vc.stop()
    source = discord.FFmpegPCMAudio(path)
    vc.play(source)
    # Attend que la lecture soit finie
    while vc.is_playing():
        await asyncio.sleep(0.1)


# ── Sink pour enregistrement audio ───────────────────────────────────────────
class VoiceSink(discord.sinks.WaveSink):
    """Sink qui collecte l'audio de tous les utilisateurs."""
    pass


# ── Gestion des salons vocaux actifs ─────────────────────────────────────────
voice_sessions: dict[int, dict] = {}  # guild_id → {vc, channel_id, ...}


async def handle_recording(guild: discord.Guild, sink: VoiceSink, channel: discord.TextChannel):
    """Callback appelé quand l'enregistrement s'arrête."""
    guild_id = guild.id
    session = voice_sessions.get(guild_id)
    if not session:
        return

    vc: discord.VoiceClient = session["vc"]

    # Récupère l'audio de tous les utilisateurs qui ont parlé
    for user_id, audio in sink.audio_data.items():
        audio_bytes = audio.file.read()
        if len(audio_bytes) < 4000:  # trop court, probablement du silence
            continue

        user = guild.get_member(user_id)
        username = user.display_name if user else "Quelqu'un"

        # Transcription
        await channel.send(f"🎤 *Transcription en cours...*", delete_after=5)
        text = await transcribe_audio(audio_bytes)

        if not text:
            continue

        await channel.send(f"**{username} :** {text}")

        # Génération réponse LLM
        response = await ask_llm(channel.id, text)
        await channel.send(f"🤖 **Bot :** {response}")

        # Lecture vocale
        await play_tts(vc, response)


# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="rejoindre", description="Le bot rejoint ton salon vocal et écoute")
async def cmd_rejoindre(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "T'es pas dans un salon vocal !", ephemeral=True
        )
        return

    vocal_channel = interaction.user.voice.channel
    guild_id = interaction.guild_id

    if guild_id in voice_sessions:
        await interaction.response.send_message(
            "Je suis déjà dans un salon vocal.", ephemeral=True
        )
        return

    try:
        vc = await vocal_channel.connect()
    except Exception as e:
        await interaction.response.send_message(f"Erreur de connexion : {e}", ephemeral=True)
        return

    voice_sessions[guild_id] = {
        "vc": vc,
        "channel_id": interaction.channel_id,
        "text_channel": interaction.channel,
    }

    await interaction.response.send_message(
        f"✅ Connecté à **{vocal_channel.name}** — utilisez `/parler` pour me parler !"
    )


@bot.tree.command(name="quitter", description="Le bot quitte le salon vocal")
async def cmd_quitter(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    session = voice_sessions.get(guild_id)

    if not session:
        await interaction.response.send_message("Je suis pas dans un salon vocal.", ephemeral=True)
        return

    vc: discord.VoiceClient = session["vc"]
    await vc.disconnect()
    del voice_sessions[guild_id]
    await interaction.response.send_message("👋 Déconnecté.")


@bot.tree.command(name="parler", description="Enregistre ta voix et le bot répond")
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

    vc: discord.VoiceClient = session["vc"]

    await interaction.response.send_message("🔴 **Enregistrement... Parle maintenant ! (5 secondes)**")

    # Lance l'enregistrement pendant 5 secondes
    sink = VoiceSink()
    text_channel = interaction.channel

    def stop_callback(sink, channel, *args):
        asyncio.create_task(handle_recording(interaction.guild, sink, channel))

    vc.start_recording(sink, stop_callback, text_channel)
    await asyncio.sleep(5)
    vc.stop_recording()


@bot.tree.command(name="chat", description="Parle au bot par écrit")
@app_commands.describe(message="Ton message")
async def cmd_chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    response = await ask_llm(interaction.channel_id, message)

    # Si le bot est dans un salon vocal, lire la réponse aussi
    guild_id = interaction.guild_id
    session = voice_sessions.get(guild_id)
    vocal_note = ""
    if session:
        vc = session["vc"]
        await play_tts(vc, response)
        vocal_note = " *(lu à voix haute)*"

    await interaction.followup.send(f"🤖 {response}{vocal_note}")


@bot.tree.command(name="reset", description="Réinitialise l'historique de conversation")
async def cmd_reset(interaction: discord.Interaction):
    histories[interaction.channel_id].clear()
    await interaction.response.send_message("🔄 Historique réinitialisé.", ephemeral=True)


@bot.tree.command(name="aide", description="Affiche les commandes disponibles")
async def cmd_aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Commandes du bot", color=0x5865F2)
    embed.add_field(name="/rejoindre", value="Le bot rejoint ton salon vocal", inline=False)
    embed.add_field(name="/quitter", value="Le bot quitte le salon vocal", inline=False)
    embed.add_field(name="/parler", value="Enregistre ta voix 5s et le bot répond", inline=False)
    embed.add_field(name="/chat <message>", value="Parle au bot par écrit (il répond aussi en vocal si connecté)", inline=False)
    embed.add_field(name="/reset", value="Réinitialise l'historique de la conversation", inline=False)
    embed.set_footer(text="Modèle LLM : Groq • TTS : gTTS • STT : Whisper via Groq")
    await interaction.response.send_message(embed=embed)


# ── Message handler (réponse en DM ou mention) ────────────────────────────────
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
        raise ValueError("DISCORD_TOKEN manquant dans les variables d'environnement")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY manquant dans les variables d'environnement")
    bot.run(DISCORD_TOKEN)
