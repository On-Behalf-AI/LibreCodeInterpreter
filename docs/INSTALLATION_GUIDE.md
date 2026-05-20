# Guide de déploiement — LibreCodeInterpreter (branche `feat/agent-skills-runtime`)

Ce guide décrit comment redéployer **à l'identique du VPS `vmi2994848` (chat-dev.onbehalf.ai)** la stack LibreCodeInterpreter (image runtime + Redis + MinIO + skills mount) sur un nouveau serveur, intégrée à une instance LibreChat déjà en place.

État reflété par ce guide : commit `61d860c` ("refactor: decouple skills from Docker image — Phase 1"). Les skills (scripts, instructions, templates) ne sont plus *bakées* dans l'image Docker ; elles sont montées au runtime depuis le filesystem hôte.

---

## 0. Architecture cible

```
┌──────────────────────────────────────────────────────────────┐
│ Réseau Docker `librechat_default`                            │
│                                                              │
│  ┌────────────┐   HTTP    ┌──────────────────────────┐       │
│  │ LibreChat  │──────────▶│ code-interpreter-api      │       │
│  │ API        │  :8000    │ (image runtime pur)       │       │
│  └────────────┘           │  nsjail / PTC / sandbox   │       │
│                           └─────────┬────────────────┘       │
│                                     │                        │
│           ┌─────────────────────────┼─────────────────┐      │
│           ▼                         ▼                 ▼      │
│  ┌──────────────────┐    ┌──────────────────┐  ┌──────────┐  │
│  │ code-interpreter │    │ code-interpreter │  │  Volume  │  │
│  │   -redis         │    │   -minio         │  │  bind    │  │
│  │  (sessions)      │    │  (S3 files)      │  │ skills/  │  │
│  └──────────────────┘    └──────────────────┘  └──────────┘  │
│                                                       ▲      │
└───────────────────────────────────────────────────────┼──────┘
                                                       │
                          /home/damien/data/skills/  ──┘
                          (sur l'hôte, monté :ro)
```

Le container `code-interpreter-api` :

- N'expose **aucun port** en dehors de `127.0.0.1:8010` (R1.a PSSI).
- Tourne en `privileged: true` (nsjail crée des namespaces utilisateur).
- Reçoit les skills via **volume mount** `~/data/skills:/opt/skills:ro` — un rebuild n'est plus nécessaire pour modifier un script ou un template.
- Utilise **MinIO** comme stockage S3 (la stack upstream pointe sur Garage ; sur ce VPS le `.env` map les vars `S3_*` sur MinIO existant).

---

## 1. Prérequis sur le nouveau serveur

| Élément | Version / Détail |
|---------|------------------|
| OS | Ubuntu 22.04 ou 24.04 (testé sur les deux) |
| Docker Engine | ≥ 24.0 |
| Docker Compose | ≥ v2.24.4 (pour `!override`) |
| Espace disque | ≥ 12 Go libres (image = 8.86 Go + volumes) |
| RAM libre | ≥ 1.5 Go pour la stack code-interpreter seule |
| Kernel | Support des user namespaces + cgroups v2 (par défaut sur Ubuntu 22.04+) |
| Git | ≥ 2.30 |
| **LibreChat** | Déjà déployé et fonctionnel, avec MongoDB + API + reverse proxy |

Ports requis (locaux uniquement, bind `127.0.0.1`) :

- `8010` — code-interpreter API (mappe sur `8000` du container)
- `9000`, `9001` — MinIO (API + console)
- `6379` — Redis (interne à la stack, non publié)

---

## 2. Préparation de l'arborescence hôte

```bash
# Répertoires standards (adapter le user/group à votre infra)
sudo mkdir -p /home/damien/data/skills
sudo chown -R damien:damien /home/damien/data
```

> Sur le VPS actuel : le propriétaire des fichiers `.env` est `damien:projet` (GID 1003) avec permissions `0660`. Adapter si vous utilisez un autre groupe partagé.

---

## 3. Cloner le repo et basculer sur la branche

```bash
cd /home/damien
git clone https://github.com/On-Behalf-AI/LibreCodeInterpreter.git
cd LibreCodeInterpreter
git checkout feat/agent-skills-runtime
git pull origin feat/agent-skills-runtime
```

> Le **nom exact de la branche** est `feat/agent-skills-runtime`. Sur le VPS actuel, le déploiement tourne depuis `merge/main-into-feat-skills-2026-05-14` (la branche d'intégration qui rebase régulièrement `feat/agent-skills-runtime` sur `main`). Pour un nouveau déploiement, partir directement de `feat/agent-skills-runtime` est plus simple.

---

## 4. Copier les skills dans `~/data/skills`

Les skills sont **séparées de l'image** depuis le commit `61d860c`. Le repo fournit la version "corporate" par défaut dans `skills/` — à copier sur l'hôte une fois pour toutes :

```bash
cd /home/damien/LibreCodeInterpreter

# IMPORTANT : -L pour résoudre le symlink pptx/scripts/office -> docx/scripts/office.
# Sans -L, le mount Docker verrait un symlink cassé.
cp -rL skills/. /home/damien/data/skills/

# Vérification
ls /home/damien/data/skills/
# Attendu : dataviz docx ffmpeg pdf pptx xlsx

# Le dossier office doit être un VRAI directory (pas un symlink) côté pptx :
test -d /home/damien/data/skills/pptx/scripts/office && \
  ! -L /home/damien/data/skills/pptx/scripts/office && \
  echo "OK"
```

Pour des templates client, voir §11 « Personnalisation des templates ».

---

## 5. Configurer le `.env` de code-interpreter

Créer `/home/damien/LibreCodeInterpreter/.env` :

```bash
cat > /home/damien/LibreCodeInterpreter/.env << EOF
# Code Interpreter API Configuration

# ── Authentication ──────────────────────────────────────────────
# Génération : openssl rand -hex 32
# IMPORTANT : cette clé doit être recopiée à l'identique dans LE .env de
# LibreChat (variable LIBRECHAT_CODE_API_KEY) — voir §8.
API_KEY=$(openssl rand -hex 32)

# ── Redis ───────────────────────────────────────────────────────
REDIS_HOST=localhost     # override à 'code-interpreter-redis' via compose env
REDIS_PORT=6379

# ── MinIO (legacy var, conservée pour les scripts internes) ────
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# ── S3 (cible effective : MinIO via ces vars depuis le refactor upstream) ──
S3_ENDPOINT=code-interpreter-minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=code-interpreter-files
S3_SECURE=false
S3_REGION=us-east-1

# ── Sandbox Pool ────────────────────────────────────────────────
# Désactivé sur le VPS actuel pour économiser la RAM (charge variable).
# Mettre à true sur un serveur dédié pour pré-chauffer 5 REPL Python.
SANDBOX_POOL_ENABLED=false
REPL_ENABLED=false

# ── Sandbox Network ─────────────────────────────────────────────
# true = sandbox peut faire pip/npm install et appeler des APIs externes
# (passe par un proxy d'allowlist anti-SSRF).
ENABLE_SANDBOX_NETWORK=true

# ── Sandbox Timeout ─────────────────────────────────────────────
# 300s (vs 30s par défaut) pour laisser le temps aux jobs Azure Translator,
# pandoc lourd, ffmpeg, etc.
MAX_EXECUTION_TIME=300

# ── Logging ─────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

chmod 660 /home/damien/LibreCodeInterpreter/.env
chown damien:projet /home/damien/LibreCodeInterpreter/.env  # ajuster le groupe
```

**Notes** :

- `API_KEY` est la clé que LibreChat utilisera pour s'authentifier auprès du code-interpreter. **Conservez-la**, elle resservira au §8.
- `MINIO_*` et `S3_*` pointent **deux fois** les mêmes credentials. C'est volontaire : le refactor upstream `64b4494` a renommé les vars `MINIO_*` → `S3_*` pour passer à Garage. Sur ce VPS on garde MinIO, donc on map les nouvelles vars `S3_*` vers MinIO.
- `SANDBOX_EGRESS_ALLOWLIST` n'est PAS dans le `.env` : elle est définie dans le compose (§7) car spécifique au bridge fichiers optionnel (§10).

---

## 6. Builder l'image Docker

```bash
cd /home/damien/LibreCodeInterpreter
docker build --target app -t code-interpreter:agent-skills .
```

- **Durée** : ~30–45 min au premier build (téléchargement LibreOffice + pandoc + ffmpeg + Python packages).
- **Builds suivants** : ~2–5 s grâce au cache Docker — depuis le commit `61d860c`, l'image **ne contient plus** les skills donc une modif de `skills/` ne déclenche aucun rebuild.
- Si le build échoue sur `apt-get update` (mirrors Ubuntu en sync), relancer après quelques minutes.

L'image finale fait **~8.9 Go** (LibreOffice + R + Python + Node + Go).

---

## 7. Ajouter les services dans `deploy-compose.override.yml` de LibreChat

Éditer `/home/damien/LibreChat/deploy-compose.override.yml` et ajouter dans `services:` les 4 services suivants. **Adapter** les labels `security.*` si vous n'utilisez pas la PSSI onbehalf.ai (sinon supprimer les blocs `labels:`).

```yaml
services:

  code-interpreter-api:
    labels:
      security.managed: "true"
      security.stack: "librechat"
      security.update.method: "build"
      security.update.policy: "code-interpreter.yaml"
    build: /home/damien/LibreCodeInterpreter
    image: code-interpreter:agent-skills
    container_name: code-interpreter-api
    init: true
    privileged: true
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
    env_file:
      - /home/damien/LibreCodeInterpreter/.env
    environment:
      - REDIS_HOST=code-interpreter-redis
      - MINIO_ENDPOINT=code-interpreter-minio:9000
      # Décommenter UNIQUEMENT si vous configurez le bridge §10
      # - SANDBOX_EGRESS_ALLOWLIST=code-files.example.com
    ports:
      - 127.0.0.1:8010:8000
    tmpfs:
      - /app/data:size=100m
    volumes:
      - code-interpreter-sandbox-data:/var/lib/code-interpreter/sandboxes
      - /home/damien/LibreCodeInterpreter/ssl:/app/ssl:ro
      - /home/damien/data/skills:/opt/skills:ro
    depends_on:
      code-interpreter-minio-init:
        condition: service_completed_successfully
      code-interpreter-redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:8000/health"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 30s
    networks:
      - default

  code-interpreter-redis:
    labels:
      security.managed: "true"
      security.stack: "librechat"
      security.update.method: "pull"
      security.update.policy: "code-interpreter.yaml"
    image: redis:7-alpine
    container_name: code-interpreter-redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
    command: >
      redis-server --appendonly yes --appendfsync everysec
      --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    volumes:
      - code-interpreter-redis-data:/data

  code-interpreter-minio:
    labels:
      security.managed: "true"
      security.stack: "librechat"
      security.update.method: "pull"
      security.update.policy: "code-interpreter.yaml"
    image: minio/minio:latest
    container_name: code-interpreter-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    deploy:
      resources:
        limits:
          memory: 256M
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
      # Décommenter UNIQUEMENT si vous configurez le bridge §10
      # MINIO_SERVER_URL: https://code-files.example.com
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
    ports:
      # R1.a PSSI : bind localhost seulement. Accès externe via Caddy
      # (cf §10 bridge optionnel).
      - 127.0.0.1:9000:9000
    volumes:
      - code-interpreter-minio-data:/data

  code-interpreter-minio-init:
    labels:
      security.managed: "true"
      security.stack: "librechat"
      security.update.method: "pull"
      security.update.policy: "code-interpreter.yaml"
    image: minio/mc:latest
    depends_on:
      code-interpreter-minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set myminio http://code-interpreter-minio:9000 minioadmin minioadmin;
      mc mb --ignore-existing myminio/code-interpreter-files;
      exit 0;
      "

volumes:
  code-interpreter-sandbox-data:
  code-interpreter-redis-data:
  code-interpreter-minio-data:
```

---

## 8. Modifier le `.env` de LibreChat

Ajouter ces variables dans `/home/damien/LibreChat/.env` :

```bash
# ─── Code Interpreter integration ─────────────────────────────
# Clé identique à API_KEY du .env de code-interpreter (§5)
LIBRECHAT_CODE_API_KEY=<COLLER_ICI_LA_VALEUR_DE_API_KEY_DU_§5>

# Format "user-in-URL" (RFC 3986) : l'API key sert d'identifiant Basic auth.
# Le hostname DOIT correspondre au container_name (§7) et au port interne 8000.
LIBRECHAT_CODE_BASEURL=http://<API_KEY_IDENTIQUE>@code-interpreter-api:8000

# ─── MinIO credentials (utilisées par le compose §7) ──────────
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

> **Sécurité prod** : changer `minioadmin` / `minioadmin` pour des valeurs aléatoires. Sur le VPS actuel on les a gardés car MinIO n'est pas exposé hors du host (R1.a). Si vous activez le bridge §10, **changez impérativement** ces credentials.

> **Format `user@host`** : LibreChat n'a pas de champ « API key » distinct pour le code-interpreter, il extrait la credential du userinfo de l'URL. Le serveur valide via header `Authorization: Basic base64("<KEY>:")`.

---

## 9. Démarrer les services et vérifier

```bash
cd /home/damien/LibreChat

# Démarrer la stack code-interpreter (les autres services LibreChat
# ne sont pas touchés)
docker compose \
  -f deploy-compose.yml -f deploy-compose.override.yml \
  up -d code-interpreter-minio code-interpreter-minio-init \
        code-interpreter-redis code-interpreter-api
```

> **R9 PSSI** : ne JAMAIS utiliser `docker run` pour redémarrer ces containers — toujours passer par `docker compose -f ... up -d`. Sinon ils perdent leurs labels, healthchecks et limites mémoire.

### Vérifications

```bash
# 1. Tous les containers sont healthy
docker ps --filter "name=code-interpreter" \
  --format "table {{.Names}}\t{{.Status}}"
# Attendu :
#   code-interpreter-api      Up X minutes (healthy)
#   code-interpreter-redis    Up X minutes (healthy)
#   code-interpreter-minio    Up X minutes (healthy)

# 2. Health endpoint répond
curl -s http://127.0.0.1:8010/health | python3 -m json.tool
# Attendu : {"status":"healthy","version":"1.x.x","service":"code-interpreter-api"}

# 3. Authentification OK depuis l'intérieur du réseau Docker
docker exec LibreChat \
  curl -sf -H "x-api-key: $(grep ^API_KEY /home/damien/LibreCodeInterpreter/.env | cut -d= -f2)" \
  http://code-interpreter-api:8000/api/v1/sessions/list

# 4. Les skills sont vues
docker exec code-interpreter-api ls /opt/skills/
# Attendu : dataviz docx ffmpeg pdf pptx xlsx

# 5. Test d'exécution depuis le sandbox
curl -s -X POST http://127.0.0.1:8010/v1/execute \
  -H "x-api-key: $(grep ^API_KEY /home/damien/LibreCodeInterpreter/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"language":"python","code":"print(1+1)"}'
# Attendu : {"output":"2\n", "success":true, ...}
```

Redémarrer LibreChat-API pour qu'il prenne en compte les nouvelles vars :

```bash
docker compose -f deploy-compose.yml -f deploy-compose.override.yml \
  up -d --force-recreate api
```

Tester côté UI : ouvrir une conversation avec un modèle supportant `execute_code` et lui demander d'exécuter `print("hello")` — l'icône code-interpreter doit apparaître et le résultat s'afficher.

---

## 10. (Optionnel) Bridge fichiers `code-files.<domain>`

Cette section n'est nécessaire **que** si vous voulez que d'autres services (par exemple un adapter n8n) puissent envoyer des fichiers au sandbox via presigned URL — c'est le pattern utilisé sur ce VPS pour le Hermes adapter.

Sans ce bridge, le sandbox accède à MinIO uniquement en interne via le DNS Docker (`code-interpreter-minio:9000`) — suffisant pour le mode LibreChat standard.

### 10.1 DNS

Faire pointer `code-files.<votre-domaine>` vers l'IP publique du VPS (A/AAAA).

### 10.2 Caddy (reverse proxy vers MinIO)

Ajouter dans `/etc/caddy/Caddyfile` :

```caddyfile
code-files.<votre-domaine> {
    reverse_proxy 127.0.0.1:9000
    # Pas d'Authelia ici : MinIO valide lui-même les signatures S3.
}
```

`systemctl reload caddy`.

### 10.3 MinIO : URL publique

Dans la section `code-interpreter-minio` du compose (§7), décommenter :

```yaml
    environment:
      MINIO_SERVER_URL: https://code-files.<votre-domaine>
```

### 10.4 Sandbox : autoriser le hostname dans l'allowlist

Dans la section `code-interpreter-api` du compose (§7), décommenter :

```yaml
    environment:
      - SANDBOX_EGRESS_ALLOWLIST=code-files.<votre-domaine>
```

### 10.5 (Si vous avez un service uploader)

Créer un user MinIO scopé write-only sur un bucket dédié (`bridge-transfer`) avec lifecycle 1 jour. Voir le `code-interpreter-minio-init` du VPS pour le snippet (`mc admin user add` + `mc ilm rule add --expire-days 1`).

Restart : `docker compose -f deploy-compose.yml -f deploy-compose.override.yml up -d code-interpreter-api code-interpreter-minio`.

---

## 11. Personnalisation des templates

Depuis Phase 1, les templates vivent dans `~/data/skills/{docx,pptx}/templates/` côté hôte. Pour ajouter un template client :

```bash
cd /home/damien/data/skills

# DOCX
mkdir -p docx/templates/<client>
cp /chemin/vers/client.docx docx/templates/<client>/template-base.docx
cp /chemin/vers/client_cr.docx docx/templates/<client>/template-compte-rendu.docx
cp /chemin/vers/client_logo.png docx/templates/<client>/logo.png

# PPTX
mkdir -p pptx/templates/<client>
cp /chemin/vers/client.pptx pptx/templates/<client>/template-corporate.pptx
```

**Aucun rebuild n'est nécessaire** : le mount `:ro` voit les nouveaux fichiers immédiatement. Si vous mettez à jour les `AGENT_INSTRUCTIONS.md` côté skills, restart le container suffit (ou pas même — les instructions sont relues à chaque session) :

```bash
cd /home/damien/LibreChat
docker compose -f deploy-compose.yml -f deploy-compose.override.yml \
  up -d code-interpreter-api
```

Voir `docs/CREATE_NEW_BRAND_TEMPLATES.md` pour le détail du template DOCX (couleurs, styles, polices, logos) et PPTX (les 12 layouts essentiels).

---

## 12. Mise à jour ultérieure

Quand de nouveaux commits arrivent sur la branche :

```bash
cd /home/damien/LibreCodeInterpreter
git pull origin feat/agent-skills-runtime

# Si le diff touche le Dockerfile ou docker/requirements/* → rebuild
docker build --target app -t code-interpreter:agent-skills .

# Si le diff touche skills/* → re-syncer le mount hôte
cp -rL skills/. /home/damien/data/skills/

# Restart (compose, JAMAIS docker run — R9 PSSI)
cd /home/damien/LibreChat
docker compose -f deploy-compose.yml -f deploy-compose.override.yml \
  up -d code-interpreter-api
```

---

## 13. (Optionnel) Création des 6 agents LibreChat

Si vous déployez en même temps une nouvelle instance LibreChat (sans agents préexistants), créer les 6 agents qui exploitent le runtime — script complet conservé hors de ce fichier dans le commit historique, ou s'inspirer de ce squelette :

```bash
docker exec -i chat-mongodb mongosh --quiet LibreChat << 'EOF'
db.agents.insertOne({
  id: "agent_docx_complete",
  name: "Word DOCX Complete",
  description: "Création/édition de documents Word.",
  provider: "anthropic",
  model: "claude-sonnet-4.5",
  tools: ["execute_code"],
  recursion_limit: 25,
  artifacts: "enabled",
  author: "<USER_ID>",
  authorName: "<VOTRE_NOM>",
  instructions: "",   // sera injecté depuis skills/docx/AGENT_INSTRUCTIONS.md
  versions: [],
  createdAt: new Date(),
  updatedAt: new Date(),
});
// + agent_pptx_complete, agent_xlsx_complete, agent_pdf_complete,
//   agent_quick_edits (ffmpeg), agent_data_viz (gemini-2.5-pro)
EOF
```

Puis injecter les `AGENT_INSTRUCTIONS.md` dans le champ `instructions` de chaque agent via un script Node ou directement via mongosh. Sur le VPS actuel : 6 agents définis dans MongoDB avec instructions de 2000–40000 caractères chacun, peuvent être dumpés avec :

```bash
docker exec chat-mongodb mongodump --db LibreChat --collection agents \
  --query='{id:/^agent_/}' --out /tmp/dump
```

et restaurés ailleurs avec `mongorestore`.

---

## 14. Résolution de problèmes

### Le container n'est pas healthy

```bash
docker logs code-interpreter-api --tail 80
```

Vérifier :
- Redis et MinIO accessibles depuis le container (`docker exec code-interpreter-api ping -c1 code-interpreter-redis`)
- L'image a bien été buildée (`docker images | grep agent-skills`)
- `/opt/skills/` est non vide (sinon le mount `~/data/skills` est vide ou inexistant)

### `AttributeError` sur `office.soffice` côté pptx

→ Le symlink `pptx/scripts/office` n'a pas été résolu. Re-syncer avec `cp -rL skills/. /home/damien/data/skills/`.

### Les fichiers générés sont inaccessibles depuis LibreChat

→ Vérifier `MINIO_ENDPOINT=code-interpreter-minio:9000` dans l'env du container code-interpreter-api ET que `code-interpreter-minio-init` a bien créé le bucket `code-interpreter-files` (logs : `docker logs code-interpreter-minio-init`).

### `nsjail` échoue avec `clone(): Operation not permitted`

→ Le container doit être `privileged: true` ET avoir `cap_add: [SYS_ADMIN, NET_ADMIN]` si vous utilisez la base `docker-compose.yml` upstream (la stack VPS utilise `privileged: true` qui inclut tout — choix moins fin mais plus simple).

### LibreChat n'invoque pas le code-interpreter

→ Vérifier dans `/home/damien/LibreChat/.env` : `LIBRECHAT_CODE_API_KEY` et `LIBRECHAT_CODE_BASEURL` présents, et la clé est identique au `API_KEY` du `.env` code-interpreter. Recréer LibreChat-API : `docker compose ... up -d --force-recreate api`.

### Build Docker échoue sur `apt-get update`

```
E: Failed to fetch http://archive.ubuntu.com/... Mirror sync in progress?
```
→ Relancer après quelques minutes (fenêtre de sync Ubuntu mirrors).

---

## 15. Annexe — différence avec l'image upstream `usnavy13/LibreCodeInterpreter`

Le fork `On-Behalf-AI/LibreCodeInterpreter`, branche `feat/agent-skills-runtime`, ajoute par rapport à upstream `main` :

- **6 skills "métier"** (docx, pptx, xlsx, pdf, ffmpeg, dataviz) avec `AGENT_INSTRUCTIONS.md`, scripts Python, templates corporate.
- **Lib partagée `office/`** (60 fichiers — pack/unpack DOCX/XLSX/PPTX, soffice helper, schémas XSD ISO29500).
- **PTC bash server** (`docker/ptc_bash_server.py`) en plus du PTC Python.
- **Décorrélation skills/image** (Phase 1, commit `61d860c`) : mount runtime au lieu de baking.
- **Auth basic + x-api-key** + endpoint admin protégé par `MASTER_API_KEY`.
- **Sandbox network avec allowlist proxy** (anti-SSRF) — variable `ENABLE_SANDBOX_NETWORK`.
- **MinIO** maintenu (vs Garage upstream) via mapping des vars `S3_*`.

Cf. `docs/MIGRATION_TO_NATIVE_SKILLS.md` pour le plan de migration vers les Skills natives LibreChat (v0.8.6+), qui rendra obsolète la partie "contenu" de la branche.
