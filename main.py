import os
import asyncio
import json
import logging
import sys
import zipfile
import shutil
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from telethon.events import ChatAction
from dotenv import load_dotenv
from game_results_manager import GameResultsManager
from yaml_manager import YAMLDataManager
from aiohttp import web
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# --- CONFIGURATION ---
try:
    API_ID = int(os.getenv('API_ID') or '0')
    API_HASH = os.getenv('API_HASH') or ''
    BOT_TOKEN = os.getenv('BOT_TOKEN') or ''
    ADMIN_ID = int(os.getenv('ADMIN_ID') or '0')
    PORT = int(os.getenv('PORT') or '10000')

    # Validation des variables requises
    if not API_ID or API_ID == 0:
        raise ValueError("API_ID manquant ou invalide")
    if not API_HASH:
        raise ValueError("API_HASH manquant")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN manquant")

    logger.info(f"✅ Configuration chargée: API_ID={API_ID}, ADMIN_ID={ADMIN_ID}, PORT={PORT}")
except Exception as e:
    logger.error(f"❌ Erreur configuration: {e}")
    logger.error("Vérifiez vos variables d'environnement dans le fichier .env")
    exit(1)

# Fichier de configuration
CONFIG_FILE = 'bot_config.json'

# Variables globales
detected_stat_channel = None
confirmation_pending = {}
transfer_enabled = True  # Contrôle le transfert des messages

# Gestionnaires
yaml_manager = YAMLDataManager()
results_manager = GameResultsManager()

# Client Telegram
import time
session_name = f'bot_session_{int(time.time())}'
client = TelegramClient(session_name, API_ID, API_HASH)


def load_config():
    """Charge la configuration depuis le fichier JSON"""
    global detected_stat_channel
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                detected_stat_channel = config.get('stat_channel')
                logger.info(f"✅ Configuration chargée: Canal={detected_stat_channel}")
        else:
            logger.info("ℹ️ Aucune configuration trouvée")
    except Exception as e:
        logger.warning(f"⚠️ Erreur chargement configuration: {e}")


def save_config():
    """Sauvegarde la configuration dans le fichier JSON"""
    try:
        config = {
            'stat_channel': detected_stat_channel
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        # Aussi sauvegarder dans YAML
        if yaml_manager:
            yaml_manager.set_config('stat_channel', detected_stat_channel)

        logger.info(f"💾 Configuration sauvegardée: Canal={detected_stat_channel}")
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde configuration: {e}")


async def start_bot():
    """Démarre le bot"""
    try:
        logger.info("🚀 DÉMARRAGE DU BOT...")

        # Charger la configuration
        load_config()

        # Démarrer le client Telegram
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot Telegram connecté")

        # Obtenir les infos du bot
        me = await client.get_me()
        username = getattr(me, 'username', 'Unknown') or f"ID:{getattr(me, 'id', 'Unknown')}"
        logger.info(f"✅ Bot opérationnel: @{username}")

        if detected_stat_channel:
            logger.info(f"📊 Surveillance du canal: {detected_stat_channel}")
        else:
            logger.info("⚠️ Aucun canal configuré. Ajoutez le bot à un canal pour commencer.")

    except Exception as e:
        logger.error(f"❌ Erreur démarrage: {e}")
        return False

    return True


# --- GESTION DES INVITATIONS ---
@client.on(events.ChatAction())
async def handler_join(event):
    """Gère l'ajout du bot à un canal"""
    global confirmation_pending

    try:
        if event.user_joined or event.user_added:
            me = await client.get_me()
            me_id = getattr(me, 'id', None)

            if event.user_id == me_id:
                channel_id = event.chat_id

                # Normaliser l'ID si nécessaire
                if str(channel_id).startswith('-207') and len(str(channel_id)) == 14:
                    channel_id = int('-100' + str(channel_id)[4:])

                # Éviter les doublons
                if channel_id in confirmation_pending:
                    return

                confirmation_pending[channel_id] = 'waiting_confirmation'

                # Obtenir les infos du canal
                try:
                    chat = await client.get_entity(channel_id)
                    chat_title = getattr(chat, 'title', f'Canal {channel_id}')
                except:
                    chat_title = f'Canal {channel_id}'

                # Envoyer l'invitation à l'admin
                invitation_msg = f"""🔔 **Nouveau canal détecté**

📋 **Canal** : {chat_title}
🆔 **ID** : {channel_id}

Pour surveiller ce canal et stocker les résultats:
• `/set_channel {channel_id}`

Le bot stockera automatiquement les parties où le premier groupe de parenthèses contient exactement 3 cartes différentes."""

                try:
                    await client.send_message(ADMIN_ID, invitation_msg)
                    logger.info(f"✉️ Invitation envoyée pour: {chat_title} ({channel_id})")
                except Exception as e:
                    logger.error(f"❌ Erreur envoi invitation: {e}")

    except Exception as e:
        logger.error(f"❌ Erreur dans handler_join: {e}")


@client.on(events.NewMessage(pattern=r'/set_channel (-?\d+)'))
async def set_channel(event):
    """Configure le canal à surveiller"""
    global detected_stat_channel, confirmation_pending

    try:
        # Seulement en privé avec l'admin
        if event.is_group or event.is_channel:
            return

        if event.sender_id != ADMIN_ID:
            await event.respond("❌ Seul l'administrateur peut configurer les canaux")
            return

        # Extraire l'ID du canal
        match = event.pattern_match
        channel_id = int(match.group(1))

        # Vérifier si le canal est en attente
        if channel_id not in confirmation_pending:
            await event.respond("❌ Ce canal n'est pas en attente de configuration")
            return

        detected_stat_channel = channel_id
        confirmation_pending[channel_id] = 'configured'

        # Sauvegarder
        save_config()

        try:
            chat = await client.get_entity(channel_id)
            chat_title = getattr(chat, 'title', f'Canal {channel_id}')
        except:
            chat_title = f'Canal {channel_id}'

        await event.respond(f"""✅ **Canal configuré avec succès**
📋 {chat_title}

Le bot va maintenant:
• Surveiller les messages de ce canal
• Stocker les parties avec 3 cartes dans le premier groupe
• Identifier le gagnant (Joueur ou Banquier)
• Ignorer les matchs nuls et les cas où les deux groupes ont 3 cartes

Utilisez /fichier pour exporter les résultats.""")

        logger.info(f"✅ Canal configuré: {channel_id}")

    except Exception as e:
        logger.error(f"❌ Erreur set_channel: {e}")


# Dictionnaire pour stocker les messages transférés {canal_message_id: admin_message_id}
transferred_messages = {}

# --- TRAITEMENT DES MESSAGES ---
@client.on(events.NewMessage())
async def handle_message(event):
    """Traite les messages entrants"""
    try:
        # Ignorer les messages du bot lui-même
        me = await client.get_me()
        if event.sender_id == me.id:
            return

        # Gérer les confirmations en privé
        if not event.is_group and not event.is_channel:
            if event.sender_id in confirmation_pending:
                pending_action = confirmation_pending.get(event.sender_id)
                if isinstance(pending_action, dict) and pending_action.get('action') == 'reset_database':
                    message_text = event.message.message.strip().upper()
                    if message_text == 'OUI':
                        await event.respond("🔄 **Remise à zéro en cours...**")

                        # Réinitialiser la base de données
                        results_manager._save_yaml([])
                        logger.info("✅ Base de données remise à zéro manuellement")

                        # Créer un nouveau fichier Excel vide
                        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        new_file_path = f"resultats_{timestamp}.xlsx"
                        empty_file = results_manager.export_to_txt(file_path=new_file_path)

                        if empty_file and os.path.exists(empty_file):
                            await client.send_file(
                                event.sender_id,
                                empty_file,
                                caption="📄 **Nouveau fichier Excel créé**\n\nLe fichier est vide et prêt pour de nouvelles données."
                            )

                        await event.respond("✅ **Remise à zéro effectuée**\n\nLa base de données a été réinitialisée avec succès!")

                        # Retirer la confirmation en attente
                        del confirmation_pending[event.sender_id]
                        return
                    else:
                        await event.respond("❌ **Remise à zéro annulée**\n\nVeuillez répondre 'OUI' pour confirmer la remise à zéro.")
                        del confirmation_pending[event.sender_id]
                        return

        # Vérifier si c'est un message du canal surveillé
        if detected_stat_channel and event.chat_id == detected_stat_channel:
            message_text = event.message.message

            # Log de tous les messages reçus
            logger.info(f"📨 Message du canal: {message_text[:100]}...")

            # TRANSFERT AUTOMATIQUE: Envoyer une copie du message à l'admin (si activé)
            if transfer_enabled:
                try:
                    transfer_msg = f"📨 **Message du canal:**\n\n{message_text}"
                    sent_msg = await client.send_message(ADMIN_ID, transfer_msg)
                    # Stocker l'association entre le message du canal et celui envoyé
                    transferred_messages[event.message.id] = sent_msg.id
                except Exception as e:
                    logger.error(f"❌ Erreur transfert message: {e}")

            # Traiter le message avec le gestionnaire de résultats
            success, info = results_manager.process_message(message_text)

            if success:
                logger.info(f"✅ {info}")
                # Notifier l'admin
                try:
                    await client.send_message(ADMIN_ID, f"✅ Partie enregistrée!\n{info}")
                except:
                    pass
            else:
                # Log pour comprendre pourquoi les messages sont ignorés
                logger.info(f"⚠️ Message ignoré: {info}")

    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}")
        import traceback
        logger.error(traceback.format_exc())


@client.on(events.MessageEdited())
async def handle_edited_message(event):
    """Traite les messages édités"""
    try:
        # Vérifier si c'est un message du canal surveillé
        if detected_stat_channel and event.chat_id == detected_stat_channel:
            message_text = event.message.message

            logger.info(f"✏️ Message édité dans le canal: {message_text[:100]}...")

            # Si on a transféré ce message, éditer la copie (si le transfert est activé)
            if transfer_enabled:
                if event.message.id in transferred_messages:
                    admin_msg_id = transferred_messages[event.message.id]
                    try:
                        transfer_msg = f"📨 **Message du canal (✏️ ÉDITÉ):**\n\n{message_text}"
                        await client.edit_message(ADMIN_ID, admin_msg_id, transfer_msg)
                        logger.info(f"✅ Message transféré édité")
                    except Exception as e:
                        logger.error(f"❌ Erreur édition message transféré: {e}")
                else:
                    # Si le message n'était pas dans notre cache, l'envoyer comme nouveau
                    try:
                        transfer_msg = f"📨 **Message du canal (✏️ ÉDITÉ - nouveau):**\n\n{message_text}"
                        sent_msg = await client.send_message(ADMIN_ID, transfer_msg)
                        transferred_messages[event.message.id] = sent_msg.id
                    except Exception as e:
                        logger.error(f"❌ Erreur transfert message édité: {e}")

            # Retraiter le message avec le gestionnaire de résultats
            success, info = results_manager.process_message(message_text)

            if success:
                logger.info(f"✅ {info}")
                # Notifier l'admin de la partie enregistrée (message édité finalisé)
                try:
                    stats = results_manager.get_stats()
                    notification = f"""✅ **Partie enregistrée (message finalisé)!**

{info}

📊 **Statistiques actuelles:**
• Total: {stats['total']} parties
• Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)"""
                    await client.send_message(ADMIN_ID, notification)
                except Exception as e:
                    logger.error(f"Erreur notification: {e}")
            else:
                # Ne pas notifier pour les messages en cours (⏰)
                if "en cours d'édition" not in info:
                    logger.info(f"⚠️ Message édité ignoré: {info}")

    except Exception as e:
        logger.error(f"❌ Erreur traitement message édité: {e}")
        import traceback
        logger.error(traceback.format_exc())


# --- COMMANDES ---
@client.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    """Commande /start"""
    if event.is_group or event.is_channel:
        return

    await event.respond("""👋 **Bot de Stockage de Résultats de Jeux**

Ce bot stocke automatiquement les résultats des parties où le premier groupe de parenthèses contient exactement 3 cartes différentes.

**Commandes disponibles:**
• `/status` - Voir l'état du bot et les statistiques
• `/fichier` - Exporter les résultats en fichier TXT
• `/help` - Aide détaillée

**Configuration:**
1. Ajoutez le bot à votre canal
2. Utilisez `/set_channel` pour configurer
3. Le bot enregistrera automatiquement les résultats

Développé pour stocker les victoires Joueur/Banquier.""")


@client.on(events.NewMessage(pattern='/status'))
async def cmd_status(event):
    """Affiche le statut du bot"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        # Obtenir les statistiques
        stats = results_manager.get_stats()

        status_msg = f"""📊 **STATUT DU BOT**

**Configuration:**
• Canal surveillé: {f'✅ Configuré (ID: {detected_stat_channel})' if detected_stat_channel else '❌ Non configuré'}
• Transfert des messages: {'🔔 Activé' if transfer_enabled else '🔕 Désactivé'}

**Statistiques:**
• Total de parties: {stats['total']}
• Victoires Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Victoires Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)

**Critères de stockage:**
✅ Exactement 3 cartes dans le premier groupe
✅ Gagnant identifiable (Joueur ou Banquier)
❌ Ignore les matchs nuls
❌ Ignore si les deux groupes ont 3 cartes

Utilisez /fichier pour exporter les résultats."""

        await event.respond(status_msg)

    except Exception as e:
        logger.error(f"❌ Erreur status: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/fichier'))
async def cmd_fichier(event):
    """Exporte les résultats en fichier Excel"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📊 Génération du fichier Excel en cours...")

        # Générer le fichier avec nom automatique (date + heure)
        file_path = results_manager.export_to_txt()

        if file_path and os.path.exists(file_path):
            # Envoyer le fichier
            await client.send_file(
                event.chat_id,
                file_path,
                caption="📊 **Export des résultats**\n\nFichier Excel généré avec succès!"
            )
            logger.info("✅ Fichier Excel exporté et envoyé")
        else:
            await event.respond("❌ Erreur lors de la génération du fichier Excel")

    except Exception as e:
        logger.error(f"❌ Erreur export fichier: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/deploy'))
async def cmd_deploy(event):
    """Crée un package de déploiement pour Render.com"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📦 Préparation du package de déploiement pour Replit...")

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        deploy_zip = f"deploy_replit_{timestamp}.zip"

        # Créer le fichier .replit temporaire pour Replit
        replit_content = """language = "python3"
    run = "python main.py"

    [nix]
    channel = "stable-23_11"

    [env]
    API_ID = ""
    API_HASH = ""
    BOT_TOKEN = ""
    ADMIN_ID = ""
    PORT = "10000"
    TZ = "Africa/Porto-Novo"
    """

        with open('.replit', 'w', encoding='utf-8') as f:
            f.write(replit_content)
        logger.info("✅ Fichier .replit créé")

        # Créer le fichier requirements.txt
        requirements_content = """telethon==1.34.0
python-dotenv==1.0.0
aiohttp==3.9.1
PyYAML==6.0.1
openpyxl==3.1.2
"""

        with open('requirements.txt', 'w', encoding='utf-8') as f:
            f.write(requirements_content)
        logger.info("✅ Fichier requirements.txt créé")

        # Créer le fichier README.md pour le déploiement
        readme_content = """# Bot Telegram - Résultats de Jeux Bcarte

Bot Telegram qui enregistre automatiquement les résultats des parties de jeu.

## Déploiement sur Replit

### Prérequis
- Compte Replit
- Identifiants Telegram (API_ID, API_HASH, BOT_TOKEN, ADMIN_ID)

### Instructions de déploiement

1. **Créer un nouveau Repl**
   - Allez sur replit.com
   - Cliquez sur "Create Repl" → "Import from GitHub" (optionnel)
   - Ou créez un nouveau Repl Python

2. **Uploader les fichiers**
   - Uploadez tous les fichiers de ce package
   - Vérifiez que .replit est présent

3. **Configurer les Secrets**
   - Cliquez sur l'icône cadenas 🔒 (Secrets)
   - Ajoutez ces variables :
     - `API_ID` : Votre Telegram API ID (depuis https://my.telegram.org)
     - `API_HASH` : Votre Telegram API Hash
     - `BOT_TOKEN` : Token de votre bot (depuis @BotFather)
     - `ADMIN_ID` : Votre ID utilisateur Telegram (depuis @userinfobot)

4. **Déployer**
   - Ouvrez l'onglet "Deployments"
   - Cliquez sur "Deploy"
   - Choisissez le type de déploiement :
     - **Reserved VM** : Pour un bot 24/7 avec coût fixe
     - **Autoscale** : Pour économiser quand le bot est inactif
   - Attendez la fin du déploiement

## Fonctionnalités automatiques

### Remise à zéro quotidienne
- **Heure** : 1h00 du matin (heure béninoise UTC+1)
- **Action** : La base de données est vidée automatiquement
- **Export** : Un nouveau fichier Excel vide est créé
- **Notification** : L'admin reçoit le nouveau fichier Excel

### Export automatique
- L'intervalle peut être configuré avec `/settime`
- Exemples : 
"""

        with open('README.md', 'w', encoding='utf-8') as f:
            f.write(readme_content)
        logger.info("✅ Fichier README.md créé")

        files_to_include = [
            'main.py',
            'game_results_manager.py',
            'yaml_manager.py',
            'requirements.txt',
            '.replit',
            'README.md',
            '.env.example'
        ]

        if os.path.exists('runtime.txt'):
            files_to_include.append('runtime.txt')

        with zipfile.ZipFile(deploy_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files_to_include:
                if os.path.exists(file):
                    zipf.write(file, file)
                    logger.info(f"✅ Ajouté: {file}")

            if os.path.exists('data'):
                for root, dirs, files in os.walk('data'):
                    for file in files:
                        if file.endswith('.yaml'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, '.')
                            zipf.write(file_path, arcname)
                            logger.info(f"✅ Ajouté: {arcname}")

        # Caption court pour le fichier
        short_caption = f"""📦 **Package Replit créé!**

✅ Fichiers inclus
✅ Configuration complète
✅ Port 10000 configuré

Voir le message suivant pour les instructions."""

        # Instructions détaillées dans un message séparé
        detailed_instructions = """**📋 Instructions de déploiement:**

**1️⃣ Contenu du package:**
• Fichiers Python (main.py, game_results_manager.py, yaml_manager.py)
• Configuration Replit (.replit avec fuseau horaire UTC+1)
• Dépendances (requirements.txt)
• Documentation (README.md)

**2️⃣ Fonctionnalités:**
🕐 Reset auto à 1h00 (Bénin UTC+1)
📊 Export auto Excel
📍 Port 10000
🏥 Health check /health

**3️⃣ Étapes:**
1. Uploadez les fichiers dans Replit
2. Secrets (🔒) :
   - API_ID (my.telegram.org)
   - API_HASH
   - BOT_TOKEN (@BotFather)
   - ADMIN_ID (@userinfobot)
3. Onglet Deployments → Deploy
4. Choisir Reserved VM ou Autoscale

Le bot démarre automatiquement!"""

        # Envoyer le fichier avec caption court
        await client.send_file(
            ADMIN_ID,
            deploy_zip,
            caption=short_caption
        )
        
        # Envoyer les instructions détaillées
        await client.send_message(ADMIN_ID, detailed_instructions)

        logger.info(f"✅ Package de déploiement Replit créé: {deploy_zip}")

        # Nettoyer le fichier .replit temporaire
        if os.path.exists('.replit'):
            os.remove('.replit')
            logger.info("✅ Fichier .replit temporaire supprimé")

    except Exception as e:
        logger.error(f"❌ Erreur création package: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern=r'/settime (\d+)(m|h)'))
async def cmd_settime(event):
    """Configure l'intervalle d'envoi automatique du fichier"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        match = event.pattern_match
        value = int(match.group(1))
        unit = match.group(2)

        # Convertir en minutes
        if unit == 'h':
            interval_minutes = value * 60
        else:
            interval_minutes = value

        # Vérifier les limites (5 min à 24h)
        if interval_minutes < 5 or interval_minutes > 1440:
            await event.respond("❌ L'intervalle doit être entre 5 minutes et 24 heures")
            return

        # Sauvegarder la configuration
        yaml_manager.set_config('auto_export_interval', interval_minutes)

        # Redémarrer la tâche d'export automatique
        await restart_auto_export_task()

        await event.respond(f"✅ Envoi automatique configuré: toutes les {value}{unit}\n\n⚠️ Remise à zéro quotidienne à 1h00 du matin (heure Bénin UTC+1)")
        logger.info(f"✅ Intervalle d'export configuré: {interval_minutes} minutes")

    except Exception as e:
        logger.error(f"❌ Erreur settime: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/stop_transfer'))
async def cmd_stop_transfer(event):
    """Désactive le transfert des messages du canal"""
    global transfer_enabled

    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Seul l'administrateur peut contrôler le transfert")
        return

    transfer_enabled = False
    await event.respond("🔕 **Transfert des messages désactivé**\n\nLes messages du canal ne seront plus transférés en privé.\n\nUtilisez /start_transfer pour réactiver.")
    logger.info("🔕 Transfert des messages désactivé")


@client.on(events.NewMessage(pattern='/start_transfer'))
async def cmd_start_transfer(event):
    """Active le transfert des messages du canal"""
    global transfer_enabled

    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Seul l'administrateur peut contrôler le transfert")
        return

    transfer_enabled = True
    await event.respond("🔔 **Transfert des messages activé**\n\nLes messages du canal seront à nouveau transférés en privé.")
    logger.info("🔔 Transfert des messages activé")


@client.on(events.NewMessage(pattern='/reset'))
async def cmd_reset(event):
    """Remet à zéro la base de données manuellement"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("⚠️ **Confirmation requise**\n\nÊtes-vous sûr de vouloir remettre à zéro la base de données?\n\nRépondez 'OUI' pour confirmer.")

        confirmation_pending[event.sender_id] = {
            'action': 'reset_database',
            'timestamp': datetime.now()
        }

        logger.info("⚠️ Confirmation de remise à zéro en attente")

    except Exception as e:
        logger.error(f"❌ Erreur commande reset: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    """Affiche l'aide"""
    if event.is_group or event.is_channel:
        return

    help_msg = """📖 **AIDE - Bot de Stockage de Résultats**

**Fonctionnement:**
Le bot surveille un canal et stocke automatiquement les parties qui remplissent ces critères:

✅ **Critères d'enregistrement:**
• Le premier groupe de parenthèses contient exactement 3 cartes différentes
• Le deuxième groupe ne contient PAS 3 cartes
• Un gagnant est clairement identifiable (Joueur ou Banquier)

❌ **Cas ignorés:**
• Matchs nuls
• Les deux groupes ont 3 cartes
• Pas de numéro de jeu identifiable

**Commandes:**
• `/start` - Message de bienvenue
• `/status` - Voir les statistiques
• `/fichier` - Exporter en fichier Excel manuellement
• `/deploy` - Créer un package pour déployer sur Replit
• `/settime 30m` ou `/settime 2h` - Configurer l'envoi automatique (5min-24h)
• `/reset` - Remettre à zéro la base de données manuellement
• `/stop_transfer` - Désactiver le transfert des messages du canal
• `/start_transfer` - Réactiver le transfert des messages du canal
• `/help` - Afficher cette aide

**Export automatique:**
• Le fichier Excel est envoyé automatiquement à l'intervalle défini
• Remise à zéro automatique à 1h00 du matin (heure Bénin UTC+1) chaque jour
• Exemples: `/settime 15m`, `/settime 1h`, `/settime 6h`

**Configuration:**
1. Ajoutez le bot à votre canal Telegram
2. Utilisez la commande `/set_channel ID` en message privé
3. Le bot commencera à surveiller automatiquement

**Format attendu des messages:**
Les messages doivent contenir:
• Un numéro de jeu (#N123 ou similaire)
• Deux groupes entre parenthèses: (cartes) - (cartes)
• Une indication du gagnant (Joueur/Banquier)

**Support:**
Pour toute question, contactez l'administrateur."""

    await event.respond(help_msg)


# --- SERVEUR WEB (HEALTH CHECK) ---
async def index(request):
    """Page d'accueil du bot"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Telegram - Résultats de Jeux</title>
        <meta charset="utf-8">
    </head>
    <body>
        <h1>🤖 Bot Telegram - Stockage de Résultats</h1>
        <p>Le bot est en ligne et fonctionne correctement.</p>
        <ul>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/status">Statut et Statistiques (JSON)</a></li>
        </ul>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html', status=200)


async def health_check(request):
    """Endpoint de vérification de santé"""
    return web.Response(text="OK", status=200)


async def status_api(request):
    """Endpoint de statut"""
    stats = results_manager.get_stats()
    status_data = {
        "status": "running",
        "channel_configured": detected_stat_channel is not None,
        "channel_id": detected_stat_channel,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }
    return web.json_response(status_data)


async def start_web_server():
    """Démarre le serveur web en arrière-plan"""
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', status_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Serveur web démarré sur le port {PORT}")


# Variables pour les tâches automatiques
auto_export_task = None


async def auto_export_file():
    """Envoie automatiquement le fichier Excel à l'intervalle configuré"""
    while True:
        try:
            # Récupérer l'intervalle configuré (en minutes)
            interval_minutes = yaml_manager.get_config('auto_export_interval', 60)

            # Attendre l'intervalle
            await asyncio.sleep(interval_minutes * 60)

            # Générer et envoyer le fichier Excel avec nom automatique (date + heure)
            logger.info("📤 Export automatique du fichier Excel...")
            file_path = results_manager.export_to_txt()

            if file_path and os.path.exists(file_path):
                stats = results_manager.get_stats()
                caption = f"""📄 **Export Automatique**

📊 Statistiques:
• Total: {stats['total']} parties
• Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)

⏱️ Prochain envoi dans {interval_minutes} minutes"""

                await client.send_file(
                    ADMIN_ID,
                    file_path,
                    caption=caption
                )
                logger.info("✅ Fichier Excel exporté automatiquement")

        except asyncio.CancelledError:
            logger.info("🛑 Tâche d'export automatique arrêtée")
            break
        except Exception as e:
            logger.error(f"❌ Erreur export automatique: {e}")
            await asyncio.sleep(60)  # Attendre 1 minute avant de réessayer


async def daily_reset():
    """Remise à zéro quotidienne à 1h00 du matin (heure du Bénin UTC+1)"""
    while True:
        try:
            # Créer le fuseau horaire du Bénin (UTC+1)
            benin_tz = timezone(timedelta(hours=1))

            # Obtenir l'heure actuelle au Bénin
            now_benin = datetime.now(benin_tz)

            # Calculer 1h00 du matin (Bénin)
            tomorrow_1am_benin = now_benin.replace(hour=1, minute=0, second=0, microsecond=0)

            # Si on a dépassé 1h00 aujourd'hui, viser demain
            if now_benin.hour >= 1:
                tomorrow_1am_benin += timedelta(days=1)

            wait_seconds = (tomorrow_1am_benin - now_benin).total_seconds()
            logger.info(f"⏰ Prochaine remise à zéro dans {wait_seconds/3600:.1f} heures (à 1h00 heure Bénin)")

            # Attendre jusqu'à 1h00
            await asyncio.sleep(wait_seconds)

            # Effectuer la remise à zéro
            logger.info("🔄 REMISE À ZÉRO QUOTIDIENNE À 1H00...")

            # Réinitialiser les données
            results_manager._save_yaml([])
            logger.info("✅ Base de données remise à zéro")

            # Créer un nouveau fichier Excel vide pour la nouvelle journée
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            new_file_path = f"resultats_{timestamp}.xlsx"
            empty_file = results_manager.export_to_txt(file_path=new_file_path)

            if empty_file and os.path.exists(empty_file):
                await client.send_file(
                    ADMIN_ID,
                    empty_file,
                    caption="📄 **Nouveau fichier Excel créé à 1h00**\n\nLe fichier est vide et prêt pour une nouvelle journée."
                )

            await client.send_message(ADMIN_ID, "🔄 **Remise à zéro automatique effectuée à 1h00**\n\nLa base de données a été réinitialisée pour une nouvelle journée.")

        except asyncio.CancelledError:
            logger.info("🛑 Tâche de remise à zéro arrêtée")
            break
        except Exception as e:
            logger.error(f"❌ Erreur remise à zéro: {e}")
            await asyncio.sleep(3600)  # Attendre 1 heure avant de réessayer


async def restart_auto_export_task():
    """Redémarre la tâche d'export automatique"""
    global auto_export_task

    # Annuler la tâche existante
    if auto_export_task and not auto_export_task.done():
        auto_export_task.cancel()
        try:
            await auto_export_task
        except asyncio.CancelledError:
            pass

    # Créer une nouvelle tâche
    auto_export_task = asyncio.create_task(auto_export_file())


# --- MAIN ---
async def main():
    """Fonction principale"""
    try:
        # Démarrer le serveur web
        await start_web_server()

        # Démarrer le bot
        success = await start_bot()
        if not success:
            logger.error("❌ Échec du démarrage du bot")
            return

        logger.info("✅ Bot complètement opérationnel")
        logger.info("📊 En attente de messages...")

        # Démarrer les tâches automatiques
        asyncio.create_task(auto_export_file())
        asyncio.create_task(daily_reset())
        logger.info("✅ Tâches automatiques démarrées (export + remise à zéro)")

        # Garder le bot actif
        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"❌ Erreur dans main: {e}")
    finally:
        await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot arrêté par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")