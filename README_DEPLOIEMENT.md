# Bot Telegram - Package de Déploiement Render.com

📅 **Créé le:** 06/10/2025 à 05:12:58 (Heure Bénin UTC+1)
📦 **Version:** 2025-10-06_05-12-58

## 🚀 Instructions de déploiement sur Render.com

### Étape 1: Créer un repository GitHub
1. Créez un nouveau repository sur GitHub
2. Uploadez tous les fichiers de ce package

### Étape 2: Déployer sur Render.com
1. Connectez-vous à [render.com](https://render.com)
2. Cliquez sur **"New +"** → **"Web Service"**
3. Connectez votre repository GitHub
4. Render détectera automatiquement `render.yaml`

### Étape 3: Configurer les Variables d'Environnement
Dans la section **Environment** de Render.com, ajoutez:
- **PORT**: 10000 (déjà configuré)
- **API_ID**: Obtenez-le sur https://my.telegram.org
- **API_HASH**: Obtenez-le sur https://my.telegram.org
- **BOT_TOKEN**: Créez un bot avec @BotFather sur Telegram
- **ADMIN_ID**: Obtenez votre ID avec @userinfobot sur Telegram

### Étape 4: Déployer
1. Cliquez sur **"Create Web Service"**
2. Attendez le déploiement (2-3 minutes)
3. Le bot sera en ligne 24/7 !

## ✅ Fonctionnalités principales

- ✅ **Détection automatique**: Reconnaît les parties avec 3 cartes différentes
- ✅ **Export quotidien**: Génère un fichier Excel à 00h59 (UTC+1)
- ✅ **Réinitialisation auto**: Reset automatique à 01h00
- ✅ **Statistiques en temps réel**: Taux de victoire Joueur/Banquier

## 📊 Commandes disponibles

- `/start` - Démarrer le bot et voir les informations
- `/status` - Voir les statistiques actuelles
- `/fichier` - Exporter les résultats en Excel
- `/reset` - Réinitialiser la base de données manuellement
- `/deploy` - Créer un nouveau package de déploiement
- `/help` - Afficher l'aide complète

## 🎯 Critères d'enregistrement

### ✅ Parties enregistrées:
- Premier groupe: **exactement 3 cartes de couleurs différentes**
- Deuxième groupe: **PAS 3 cartes**
- Gagnant identifiable: **Joueur** ou **Banquier**

### ❌ Parties ignorées:
- Match nul
- Les deux groupes ont 3 cartes
- Pas de numéro de jeu identifiable

## ⚙️ Configuration technique

- **Langage**: Python 3.11
- **Timezone**: Africa/Porto-Novo (UTC+1)
- **Port**: 10000 (Render.com)
- **Export automatique**: 00h59 chaque jour
- **Reset automatique**: 01h00 chaque jour

---
*Package généré automatiquement*
*Dernière mise à jour: 06/10/2025 05:12:58*
