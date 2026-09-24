# Tests V6.1 Vercel

## Résultats

- API Vercel/local : **31 contrôles PASS**
  - status ;
  - setup professeur ;
  - authentification professeur ;
  - création Alice/Bob ;
  - unicité username ;
  - authentification élève ;
  - sauvegarde et reprise de progression ;
  - séparation des progressions ;
  - override deck 4 ;
  - override sans modification de `unlocked` ;
  - reset PIN ;
  - reset progression ;
  - protections d'authentification ;
  - garde-fou Vercel sans `DATABASE_URL`.
- Moteur principal existant : **334 PASS / 0 FAIL**.
- Quêtes annexes / side-core : **88 PASS / 0 FAIL**.
- Compilation Python : `server.py`, `api/index.py` et le test API compilent sans erreur.
- Démarrage HTTP Uvicorn réel : `/api/status` répond avec `codeStationServer=true` et `storage=sqlite` en mode local.

## Ce qui n'a pas été testé depuis cet environnement

- Connexion à une vraie instance Neon/PostgreSQL distante : `psycopg` n'est pas installé dans l'image d'exécution locale. La dépendance est déclarée dans `requirements.txt` et `pyproject.toml` pour Vercel.
- Déploiement réel sur un compte Vercel : nécessite les identifiants et variables d'environnement du propriétaire du projet.

## Contrat conservé

Les URLs utilisées par `src/accounts.js` restent identiques :

- `GET /api/status`
- `POST /api/teacher/setup`
- `POST /api/login/teacher`
- `POST /api/login/student`
- `GET /api/teacher/students`
- `GET /api/me/access`
- `POST /api/progress`
- `POST /api/teacher/students`
- `POST /api/teacher/students/{id}/overrides`
- `POST /api/teacher/students/{id}/pin`
- `POST /api/teacher/students/{id}/reset-progress`
