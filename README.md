# 🤖 Discord AI Bot — Claude

Bot Discord alimenté par l'IA Claude (Anthropic). Il répond intelligemment aux messages, garde une mémoire de conversation par salon, et peut rejoindre des groupes privés via une commande slash.

---

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 💬 Réponses IA | Répond via Claude (claude-sonnet-4-6) |
| 📩 Messages privés | Toujours actif en DM |
| 🔔 Mention | Répondre quand on le mentionne avec `@` |
| `/rejoindre` | Rejoint un salon et répond à tous les messages |
| `/quitter` | Quitte un salon actif |
| `/effacer` | Efface la mémoire de conversation |
| `/statut` | Affiche l'état du bot dans le salon |
| 🧠 Mémoire | Garde les 10 derniers échanges par salon |

---

## 🚀 Déploiement

### Étape 1 — Créer le bot Discord

1. Va sur [discord.com/developers/applications](https://discord.com/developers/applications)
2. Clique **New Application** → donne un nom
3. Va dans **Bot** → clique **Add Bot**
4. Sous **Token** → clique **Reset Token** → copie le token
5. Sous **Privileged Gateway Intents**, active :
   - ✅ **Message Content Intent**
   - ✅ **Server Members Intent**
6. Va dans **OAuth2 → URL Generator** :
   - Scopes : `bot` + `applications.commands`
   - Permissions : `Send Messages`, `Read Message History`, `View Channels`
7. Copie l'URL générée et colle-la dans ton navigateur pour inviter le bot

### Étape 2 — Clé API Anthropic

1. Va sur [console.anthropic.com](https://console.anthropic.com)
2. **API Keys** → **Create Key** → copie la clé

### Étape 3 — GitHub

```bash
git init
git add .
git commit -m "Initial commit — Discord AI Bot"
git remote add origin https://github.com/TON_USER/discord-ai-bot.git
git push -u origin main
```

### Étape 4 — Railway

1. Va sur [railway.app](https://railway.app) → connecte-toi avec GitHub
2. **New Project** → **Deploy from GitHub repo** → sélectionne ton dépôt
3. Dans **Variables**, ajoute :
   ```
   DISCORD_TOKEN     = ton_token_discord
   ANTHROPIC_API_KEY = ta_clé_anthropic
   ```
4. Railway détecte le `Dockerfile` et lance le build automatiquement ✅

---

## 🧪 Test en local

```bash
# Copier le fichier d'environnement
cp .env.example .env
# Remplir .env avec tes vraies clés

# Installer les dépendances
pip install -r requirements.txt

# Lancer le bot
python bot.py
```

---

## 📋 Commandes disponibles

| Commande | Description |
|---|---|
| `/rejoindre` | Le bot rejoint et répond à tous les messages du salon |
| `/quitter` | Le bot cesse de répondre automatiquement |
| `/effacer` | Efface la mémoire de la conversation |
| `/statut` | Affiche l'état du bot dans le salon actuel |
| `@BotName message` | Parle au bot depuis n'importe quel salon |

---

## 🏗️ Structure du projet

```
discord-ai-bot/
├── bot.py               # Code principal du bot
├── requirements.txt     # Dépendances Python
├── Dockerfile           # Image Docker pour Railway
├── railway.toml         # Config Railway
├── .env.example         # Variables d'environnement (exemple)
├── .gitignore
└── README.md
```

---

## 📄 Licence

MIT — Libre d'utilisation et de modification.
