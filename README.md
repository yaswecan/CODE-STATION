# CODE//STATION V6.1 — PédagoLab Accounts · Vercel Ready

Cette version conserve le jeu et le système de comptes V6, mais remplace le serveur local permanent par une architecture compatible **Vercel Functions**.

## Ce qui a changé

- `server.py` expose maintenant une application **FastAPI** (`app`) au lieu d'un `ThreadingHTTPServer` permanent ;
- `api/index.py` est l'entrée Vercel ;
- comptes et progression utilisent **PostgreSQL** via `DATABASE_URL` en production ;
- les sessions ne sont plus stockées dans `SESSIONS = {}` : elles utilisent des **tokens HMAC signés et expirables** ;
- en développement local, SQLite reste disponible si `DATABASE_URL` n'est pas défini ;
- le contrat `/api/...` reste compatible avec `src/accounts.js` ;
- la détection du backend attend jusqu'à 5 s afin de tolérer un cold start de Function.

## Déploiement Vercel

1. Connecte le dépôt à Vercel.
2. Ajoute **Neon** (ou un autre PostgreSQL) au projet.
3. Vérifie que `DATABASE_URL` existe dans les variables d'environnement.
4. Ajoute :

```text
SESSION_SECRET=<secret long aléatoire>
```

Génération possible :

```bash
openssl rand -base64 48
```

5. Déploie.
6. Vérifie :

```text
https://TON-PROJET.vercel.app/api/status
```

La réponse doit indiquer `"codeStationServer": true` et `"storage": "postgres"`.

Ensuite ouvre la racine du site, onglet **Professeur**, initialise le PIN puis crée les comptes élèves.

Guide complet : [`docs/DEPLOIEMENT_VERCEL.md`](docs/DEPLOIEMENT_VERCEL.md).

## Développement local

Le plus fidèle à la production :

```bash
npm i -g vercel
vercel dev
```

Vercel sert alors le frontend et `/api/*` sur la même origine.

Pour tester uniquement l'API avec SQLite :

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

L'API écoute alors par défaut sur `http://127.0.0.1:8765/api/status`.

## Déblocage professeur

Un override de deck donne **accès**, mais ne valide aucune compétence :

- progression naturelle inchangée ;
- ateliers non validés ;
- évaluation non validée ;
- badge « accès professeur » côté élève.

## Sécurité

- PIN élève/prof : PBKDF2-HMAC-SHA256 + sel ;
- tokens de session signés avec `SESSION_SECRET` ;
- expiration des tokens (12 h par défaut) ;
- progression liée à l'identité authentifiée côté serveur ;
- aucune base JSON publique dans le déploiement.

Pour une intégration complète au produit PédagoLab, voir `docs/INTEGRATION_PEDAGOLAB.md`.
