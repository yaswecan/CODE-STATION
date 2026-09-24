# Déploiement Vercel — CODE//STATION PédagoLab V6.1

## Architecture

- Frontend HTML/CSS/JS servi par Vercel.
- `api/index.py` expose l'application FastAPI définie dans `server.py`.
- PostgreSQL via `DATABASE_URL` (Neon recommandé pour Vercel).
- Sessions stateless signées par HMAC via `SESSION_SECRET`.
- Plus aucun `SESSIONS = {}` en mémoire.
- Plus aucun `pedagolab.json` en production.

## 1. Créer/connecter PostgreSQL

Dans Vercel : **Storage / Marketplace → Neon → Connect**.
La connexion doit fournir `DATABASE_URL` à l'environnement Production (et Preview si souhaité).

Le schéma est créé automatiquement au premier appel API. Une copie est fournie dans `db/schema.sql`.

## 2. Variables d'environnement

Ajouter dans **Project → Settings → Environment Variables** :

- `DATABASE_URL` — chaîne PostgreSQL Neon/Supabase.
- `SESSION_SECRET` — secret long et aléatoire, par exemple `openssl rand -base64 48`.

Optionnels :

- `SESSION_TTL_SECONDS=43200`
- `PIN_PBKDF2_ITERATIONS=260000`
- `MAX_PROGRESS_BYTES=2000000`

Sans `DATABASE_URL` ou `SESSION_SECRET`, `/api/status` renvoie 503 sur Vercel afin d'éviter une fausse persistance locale.

## 3. Déployer

### GitHub

```bash
git init
git add .
git commit -m "CODE Station V6.1 Vercel"
git branch -M main
git remote add origin <TON_REPO>
git push -u origin main
```

Puis **Vercel → Add New → Project → Import repository → Deploy**.

### CLI

```bash
npm i -g vercel
vercel link
vercel env pull .env.local
vercel dev
vercel deploy --prod
```

## 4. Vérifications

```bash
curl https://TON-PROJET.vercel.app/api/status
```

Réponse attendue :

```json
{
  "codeStationServer": true,
  "version": "6.1-vercel",
  "storage": "postgres",
  "teacherConfigured": false,
  "students": 0
}
```

Ensuite ouvre la racine du site, onglet **Professeur**, initialise le PIN puis crée un compte élève.

## Différences avec le serveur local V6

| V6 locale | V6.1 Vercel |
|---|---|
| `ThreadingHTTPServer` | FastAPI / Vercel Function |
| `pedagolab.json` | PostgreSQL |
| `SESSIONS = {}` | token HMAC signé + expiration |
| processus permanent | requêtes serverless / Fluid compute |
| IP/port local | même domaine Vercel `/api/*` |

## Mode local

Sans `DATABASE_URL`, `server.py` utilise SQLite (`data/pedagolab.sqlite3`) pour le développement uniquement.

Pour reproduire au mieux Vercel localement, utilise :

```bash
vercel dev
```

Le frontend et l'API sont alors servis sur la même origine.
