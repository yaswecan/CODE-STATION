# Déploiement Vercel + Neon — V6.2

## Variables obligatoires
- `DATABASE_URL` : chaîne PostgreSQL Neon (idéalement pooled)
- `SESSION_SECRET` : secret aléatoire long

## Dépendances
`requirements.txt` est obligatoire et inclus dans cette version.

## Vercel
Le projet expose FastAPI via `server.py`, un entrypoint reconnu nativement par Vercel.
- `/` sert `JOUER.html`
- `/api/status` vérifie la connexion Neon

## Premier test
1. Déployer.
2. Ouvrir `/api/status`.
3. Résultat attendu : `storage: postgres`, `teacherConfigured: false` au premier lancement.
4. Ouvrir `/` puis initialiser le PIN professeur.
