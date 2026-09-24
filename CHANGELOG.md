# Changelog

## V6.1 — Vercel Ready

- Remplacement de `ThreadingHTTPServer` par FastAPI.
- Entrée Vercel : `api/index.py`.
- PostgreSQL via `DATABASE_URL` en production.
- SQLite uniquement pour le développement local.
- Sessions stateless HMAC au lieu de `SESSIONS = {}`.
- Contrat API V6 conservé.
- Détection backend frontend portée de 900 ms à 5 s pour les cold starts.
- Ajout `requirements.txt`, `pyproject.toml`, `.env.example`, `vercel.json` et `db/schema.sql`.
- `/api/status` refuse explicitement une production Vercel sans `DATABASE_URL` ou `SESSION_SECRET`.

## V6

- Comptes élèves/professeur PédagoLab.
- Reprise de progression par élève.
- Overrides professeur indépendants de la progression naturelle.
