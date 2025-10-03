# Bot Telegram - Résultats de Jeux Bcarte

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
