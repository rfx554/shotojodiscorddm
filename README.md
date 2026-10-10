# 📩 DM Ticket Bot

Bot Discord qui transforme les DMs en tickets privés visibles uniquement par les admins.

## Fonctionnement

- Un membre DM le bot → un channel ticket est créé automatiquement (admins only)
- Les messages du membre sont relayés dans le ticket, et vice-versa
- `!fermer` dans le ticket → notifie le membre et supprime le channel

## Setup

### 1. Discord Developer Portal

1. Crée une application sur [discord.com/developers](https://discord.com/developers/applications)
2. Onglet **Bot** → créer le bot → copier le token
3. Activer **Message Content Intent** et **Server Members Intent**
4. Onglet **OAuth2 → URL Generator** → cocher `bot`, puis les permissions :
   - Manage Channels, Send Messages, Read Message History, View Channels
5. Inviter le bot sur ton serveur avec l'URL générée

### 2. Variables d'environnement

Copie `.env.example` en `.env` et remplis :

```
DISCORD_TOKEN=ton_token
GUILD_ID=id_du_serveur       # clic droit sur le serveur → Copier l'identifiant
TICKETS_CATEGORY_ID=id       # optionnel : id de la catégorie où créer les tickets
```

### 3. Lancer en local

```bash
pip install -r requirements.txt
python bot.py
```

## Deploy sur Railway

1. Push le repo sur GitHub
2. Sur [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
3. Sélectionner le repo
4. Onglet **Variables** → ajouter `DISCORD_TOKEN`, `GUILD_ID`, `TICKETS_CATEGORY_ID`
5. Railway détecte le `Procfile` et lance `python bot.py` automatiquement

## Commandes

| Commande | Accès | Description |
|----------|-------|-------------|
| `!fermer` | Admin | Ferme et supprime le ticket |
