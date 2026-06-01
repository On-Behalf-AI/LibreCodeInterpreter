# Migration vers les Skills natives LibreChat

> **Date initiale** : 2026-05-10
> **Mis à jour** : 2026-06-01 après audit croisé avec le code LibreChat (`v0.8.6` HEAD)
> **Auteur** : Claude (Opus 4.7) sur instruction de Damien Juillard
> **Objet** : Analyse de la branche `feat/agent-skills-runtime` à la lumière des Skills natives livrées sur `upstream/dev` (LibreChat v0.8.6 incoming) — et plan de migration.

> **Changelog 2026-06-01** :
> - Confirmé : zip import (`POST /api/skills/import`) supporte arborescences imbriquées en un seul appel — remplace l'approche "POST par fichier" décrite initialement
> - Quantifié : limites binaires (10 MB/fichier, 50 MB zip compressé, 500 MB décompressé)
> - Corrigé : le champ `category` est stocké mais **aucun chemin de code ne le lit** aujourd'hui (sémantique différée)
> - Corrigé : `isExecutable` est **forcé à `false` à l'upload** (`routes/skills.js:233`) — bit exécutable non utilisable
> - Ajouté : SkillFiles uploadés avec `read_only: true` → **chmod 444 dans le sandbox** (`skillFiles.ts:225`)
> - Ajouté : pas d'export skill → zip (le Git skillset reste source de vérité)
> - Ajouté : **1 `SKILL.md` = 1 skill** dans un zip (pas de bundle multi-skills)

## TL;DR

Si les Skills natives LibreChat avaient existé en avril 2026, la branche `feat/agent-skills-runtime` se serait découpée en **deux** projets distincts :

1. Un set de **Skills LibreChat** versionnées en DB qui portent le contenu (instructions + scripts + templates) — environ 70 % de la branche actuelle.
2. Une image **LibreCodeInterpreter** beaucoup plus mince qui ne porte plus que **l'infrastructure runtime** (binaires système, sécurité sandbox, PTC, auth) — environ 30 % de la branche actuelle.

Sur 220 commits, environ 70 % deviendraient inutiles (contenu skills/* qui migre vers la DB) et 30 % resteraient essentiels (image runtime).

---

## 1. Faits vérifiés

### 1.1 Upload de SkillFile EST live sur dev

Aujourd'hui, sur `upstream/dev` HEAD `8fc68ebac` :

- **Zip import** : `POST /api/skills/import` accepte un `.zip` (ou `.skill`, ou `.md`) avec arborescence préservée (`packages/api/src/skills/import.ts:356-436`) — **c'est la voie principale**.
- **Per-file upload** : `POST /api/skills/:id/files` est aussi wired (`api/server/routes/skills.js:317-325`) mais sans UI dédiée à ce jour — utilisable seulement via API client custom.
- Commit clé : `4a5fc701d` "Preserve Nested Skill Paths in Code-Env Uploads" (#12877).
- Le pipeline complet `primeSkillFiles` → `batchUploadCodeEnvFiles` → cache 23 h fonctionne (`packages/api/src/agents/skillFiles.ts:98-308`).

### 1.2 Tailles compatibles avec la limite 100 KB body

| Skill | AGENT_INSTRUCTIONS.md | SKILL.md | Tient dans 100 KB ? |
|---|---|---|---|
| docx | 39 268 | 20 084 | ✅ (avec 40 % de marge) |
| pptx | 15 201 | 9 182 | ✅ |
| xlsx | 3 486 | 11 463 | ✅ |
| pdf | 3 583 | – | ✅ |
| ffmpeg | 1 987 | – | ✅ |
| dataviz | 3 242 | – | ✅ |

### 1.3 Limites de taille pour les fichiers binaires (templates, assets)

| Limite | Valeur | Source |
|---|---|---|
| Par fichier | **10 MB** | `api/server/routes/skills.js:79` + `import.ts:21` |
| Par zip compressé | **50 MB** | `import.ts:18` |
| Total décompressé par zip | **500 MB** | `import.ts:19` |

Pour référence : les templates onbehalfai font max **192 KB** (.docx) et **1.4 MB** (.pptx — `template-oba-corporate.pptx`). On est très large.

### 1.4 La lib `office/` est partagée entre 3 skills

`skills/docx/scripts/office/` (60 fichiers, dont schémas XSD ISO-IEC29500-4_2016, helpers, validators, pack/unpack/soffice) est importée par :
- `skills/xlsx/scripts/recalc.py:14` → `from office.soffice import get_soffice_env`
- `skills/pptx/scripts/thumbnail.py` → idem

C'est donc une **lib système commune**, pas une lib privée à docx.

---

## 2. Comment fonctionne natif LibreChat (synthèse vérifiée)

### Modèle de données

Une **Skill** native est :
- Un enregistrement Mongo (`Skill` + `SkillFile` collections)
- Dont le contenu textuel (Markdown + frontmatter YAML) est dans le champ `body` (100 KB max). Au moment de l'import zip, c'est le fichier littéralement nommé `SKILL.md` (à la racine ou 1 niveau de profondeur) qui devient ce body
- À qui on attache zéro ou plusieurs fichiers (`SkillFile`) avec :
  - une `relativePath` (chemins imbriqués supportés, e.g. `templates/corporate/X.docx`)
  - une `category` (`script` / `reference` / `asset` / `other`) — ⚠️ **stockée mais aucun chemin de code ne la lit aujourd'hui** ; c'est de la métadonnée pure à ce stade
  - un flag `isExecutable` — ⚠️ **forcé à `false` à l'upload** (`routes/skills.js:233`) ; pas d'UI pour le flip ; pas un blocker car les scripts Python s'invoquent par `python3 /mnt/data/...` sans bit exécutable
  - un flag `read_only: true` automatique (chmod 444 dans le sandbox via `X-Amz-Meta-Read-Only` MinIO — `skillFiles.ts:225`)
  - stockés dans le storage configuré (filesystem ou S3)
- Scopée par ACL (`SKILL_OWNER` / `EDITOR` / `VIEWER`) avec `tenantId` optionnel

### Runtime de conversation

1. LibreChat liste les skills accessibles à l'utilisateur (intersection ACL + whitelist Agent + toggle `skills_enabled`)
2. Compose un **catalog** (max 100 skills) qu'il **injecte dans `agent.additional_instructions`** — l'agent voit la liste et leur description
3. Enregistre 3 tools spéciaux : `SkillTool` (invocation), `read_file` (lecture des SkillFiles), `bash_tool` (exécution dans le sandbox `execute_code`)
4. Quand l'agent invoque une skill : substitue `$ARGUMENTS`, **prime les SkillFiles vers le sandbox** via `batchUploadCodeEnvFiles()` (POST batch à l'API code-interpreter), avec **cache 23 h** + check de session active, **fichiers marqués read-only**
5. Le `body` de la skill est injecté comme message "meta" pour donner les instructions de la skill à l'agent

### Ce qui n'est **pas** dans natif

- ❌ Aucune installation automatique de dépendances (pas de `pip install` ni `apt-get` orchestrés)
- ❌ Aucune composition / nesting / import entre skills
- ❌ Aucune préparation d'environnement système (binaires comme LibreOffice doivent déjà exister)
- ❌ Pas de skills "system" pré-livrées avec LibreChat
- ❌ Pas d'historique de versions (juste optimistic concurrency via `Skill.version`)
- ❌ Pas de validation de format des `arguments` côté serveur
- ❌ **Pas d'endpoint d'export** : aucun `GET /api/skills/:id/export` pour round-tripper une skill vers un zip. La source de vérité doit rester ton repo Git.
- ❌ **1 SKILL.md = 1 skill** dans un zip : pour 6 skills, il faut 6 zips séparés (l'import unpack 1 SKILL.md à la racine ou +1 niveau).
- ❌ **Pas d'UI pour ajouter un fichier post-import** : `UploadSkillDialog` n'accepte que `.zip/.skill/.md`. Pour ajouter un fichier après coup, il faut passer par `POST /api/skills/:id/files` en API.
- ❌ **Sémantique `category` non implémentée** : `script` vs `asset` vs `reference` est métadonnée seulement, aucun traitement différentiel (pas de pré-loading des assets, pas de filtrage pour le contexte LLM).

### Ce qui EST dans natif et qu'on n'avait pas mesuré

- ✅ **Zip import one-shot** avec arborescence imbriquée préservée (#12877) — pas besoin d'un `seed-skills.sh` qui POST fichier par fichier.
- ✅ Fichiers uploadés **en lecture seule** dans le sandbox (chmod 444) — contrainte à connaître pour les scripts (cf. piège 9 plus bas).
- ✅ Cache 23h **partagé cross-user au sein d'un tenant** (key = `<tenant>:skill:<id>:v:<version>`), pas seulement per-session.

---

## 3. Mapping pièce-par-pièce de `feat/agent-skills-runtime`

| Pièce de la branche | Sort si on refait à partir de zéro | Justification |
|---|---|---|
| `skills/docx/AGENT_INSTRUCTIONS.md` (39 KB) | → **renommé `SKILL.md` dans le zip** → devient le **body** | Native skills lit le fichier littéralement nommé `SKILL.md` comme body. C'est `AGENT_INSTRUCTIONS.md` (39 KB, tient dans 100 KB) qui doit prendre ce nom. |
| `skills/docx/SKILL.md` actuel (20 KB, "syntaxe détaillée") | → **renommé `reference/SKILL_DETAILED.md`** (SkillFile, `category=reference`) | Doit être renommé pour ne pas entrer en conflit avec le SKILL.md = body. Lu par l'agent via `read_file`. |
| `skills/docx/scripts/fill_template.py`, `fill_cr_template.py`, etc. (23 .py) | → **SkillFiles** (`category=script`, `isExecutable` non utilisable) | Bit exécutable inutile : invocation par `python3 /mnt/data/<skill>/scripts/X.py` via bash_tool. |
| `skills/docx/scripts/office/` (60 fichiers : pack, unpack, soffice, schemas XSD, helpers, validators) | → **bibliothèque système dans l'image** sous `/opt/lib/office/`, exposée via `PYTHONPATH` | ⚠️ Point critique. **Partagée par docx + pptx + xlsx**. Native skills ne supporte pas le partage de code → ne pas dupliquer dans 3 skills, garder comme infra runtime. |
| Templates `.docx` / `.pptx` génériques | → **SkillFiles** dans `templates/` du zip skill (`category` libre, défaut `other`) | Upload binaire OK (≤10 MB/fichier). `relativePath: templates/template-base.docx` → atterrit dans `/mnt/data/<skill>/templates/template-base.docx`. |
| Templates **propriétaires** mountés (commit `cea43d1`) | → **Skills privées par tenant** (skill `docx-tenant-acme`, ACL owner=admin) OU sous-dossier `templates/corporate/` dans la skill publique si le tenant unique | (a) multi-tenant : 1 skill par tenant + ACL ; (b) mono-tenant (onbehalfai) : juste un dossier `templates/corporate/` dans la skill `docx`. Choix par cas. |
| `docker/ptc_bash_server.py` (PTC bash) | → **GARDE dans l'image** | Pure infra sandbox |
| `docker/ptc_server.py` (PTC Python étendu) | → **GARDE dans l'image** | Idem |
| `src/services/sandbox/egress_proxy.py` + `egress_firewall.py` | → **GARDE dans l'image** | Sécurité sandbox. *Plus important encore* avec les skills, parce que le sandbox reçoit du code utilisateur arbitraire (uploadé via skill) |
| Migration MinIO → Garage (`garage.toml`, refactor S3) | → **GARDE dans l'image** | Choix de stockage orthogonal aux skills |
| `AUTH_ENABLED`, basic auth, `src/services/auth.py`, `src/dependencies/auth.py` | → **GARDE dans l'image** | Sécurité service-level |
| File upload restrictions, `tmpfs` durci, sanitization Unicode | → **GARDE dans l'image** | Sécurité fichiers, sanitization alignée LibreChat pour les hash |
| `.gitleaks.toml`, suppression API keys hardcodées | → **GARDE** | Hygiène repo |
| LibreOffice, pandoc, qpdf, ffmpeg, fonts, libreoffice-impress dans le Dockerfile | → **GARDE dans l'image** | **Coeur du sujet** : native skills ne sait pas installer ces binaires de 3 GB |
| `tests/agent_api_tests.py` (79 tests métier) | → **GARDE, regex patterns à adapter** | Le harness reste valable |
| `tests/ralph-wiggum-prompt.md` | → **GARDE** | Orchestrateur orthogonal |
| `tests/smoke/test_agent_skills.sh` | → **GARDE, scope changé** | Vérifie binaires + lib `office/` dans l'image |
| `tests/integration/test_auth_*.py` | → **GARDE** | Auth de l'image inchangée |
| Refactor client-agnostic (`28e2d17`, `92c5952`, `cea43d1`) | → **GARDE** | Permet la publication publique du fork |
| CI simplifiée (`74bb001`, `1032ee9`) | → **GARDE** | Orthogonal |
| `skills/{ffmpeg,pdf,dataviz}/AGENT_INSTRUCTIONS.md` (sans scripts) | → **Skills body-only** (sans SkillFiles) | Cas le plus simple |

### Synthèse

**MIGRE vers les skills natives** : le contenu (instructions Markdown + scripts Python applicatifs + templates binaires + assets). Concrètement, ~150 fichiers répartis sur 6 skills.

**RESTE dans l'image code-interpreter** : tout ce qui ne peut **pas** vivre dans une row Mongo. À savoir : binaires système (LibreOffice, pandoc, ffmpeg, qpdf, fonts), lib Python `office/` (60 fichiers OOXML), infrastructure sandbox (nsjail, PTC, egress proxy, auth, S3 client, sanitization, healthchecks), CI de l'image, harness de tests métier.

---

## 4. Architecture cible

```
┌─────────────────────────────────────────────────────────────┐
│ LibreChat (DB Mongo)                                        │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Skill: "docx"  (uploadée comme docx.zip via UI)      │   │
│ │ ├── body: SKILL.md (39 KB Markdown — renommé        │   │
│ │ │         depuis AGENT_INSTRUCTIONS.md)              │   │
│ │ ├── frontmatter: { allowed-tools: [bash_tool, ...] } │   │
│ │ └── SkillFiles (sandbox path = /mnt/data/docx/...):  │   │
│ │     ├── reference/SKILL_DETAILED.md (cat=reference)  │   │
│ │     ├── scripts/fill_cr_template.py (cat=script)     │   │
│ │     ├── scripts/fill_template.py    (cat=script)     │   │
│ │     ├── scripts/tracked_replace.py  (cat=script)     │   │
│ │     ├── scripts/inject_cover.py     (cat=script)     │   │
│ │     ├── templates/corporate/template-base.docx       │   │
│ │     ├── templates/corporate/template-cr.docx         │   │
│ │     ├── templates/corporate/template-courrier.docx   │   │
│ │     ├── templates/corporate/logo-onbehalfai.svg      │   │
│ │     └── templates/corporate/heading-unnumbered.lua   │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                             │
│ Skill: "pptx" — body + scripts/* + templates/*             │
│ Skill: "xlsx" — body + scripts/* (recalc, etc.)            │
│ Skill: "pdf"   — body uniquement                           │
│ Skill: "ffmpeg" — body uniquement                          │
│ Skill: "dataviz" — body uniquement                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ batchUploadCodeEnvFiles()
                          │ (cache 23h)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ LibreCodeInterpreter (Docker image)                         │
│                                                             │
│ ┌─ Binaires système ────────────────────────────────────┐  │
│ │ LibreOffice + Impress, pandoc, qpdf, ffmpeg, fonts   │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─ Lib partagée OOXML (PYTHONPATH=/opt/lib) ────────────┐  │
│ │ /opt/lib/office/                                      │  │
│ │   ├── pack.py, unpack.py, soffice.py, validate.py    │  │
│ │   ├── helpers/                                        │  │
│ │   ├── validators/                                     │  │
│ │   └── schemas/ISO-IEC29500-4_2016/*.xsd (~50 XSDs)   │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌─ Sandbox runtime ─────────────────────────────────────┐  │
│ │ - nsjail (isolation)                                  │  │
│ │ - PTC Python + bash (orchestration multi-tools)       │  │
│ │ - Egress proxy + firewall (allowlist)                 │  │
│ │ - Auth (AUTH_ENABLED, basic auth)                     │  │
│ │ - S3 client (Garage)                                  │  │
│ │ - File sanitization (aligned LibreChat)               │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ Endpoint POST /upload/batch ◄── reçoit les SkillFiles     │
│ Endpoint POST /exec ◄── exécute les scripts skill          │
└─────────────────────────────────────────────────────────────┘
```

### Avantages

- Mise à jour d'une instruction agent = un PATCH dans LibreChat (pas de rebuild d'image)
- Multi-tenancy native (un client privé peut avoir sa skill `docx-onbehalf` + son template confidentiel sans rebuild d'image)
- ACL standard, partage, versioning optimistic
- L'image code-interpreter perd ~150 fichiers (les skills/), gagne 60 fichiers (la lib office/ remontée en `/opt/lib/`), peut potentiellement réduire la taille de quelques centaines de Mo

---

## 5. Plan "from scratch" (10-15 jours de dev)

### Phase 0 — Préparation (1-2 jours)

- Lire `docs/AGENT_SKILLS.md` upstream + le code de `packages/api/src/skills/` et `packages/api/src/agents/skillFiles.ts`
- Tester manuellement la création d'une skill simple via UI LibreChat (`/skills/new`) avec un body Markdown + 1 SkillFile script
- Tester le primage via une conversation avec un agent attaché à la skill, vérifier dans les logs Code API que `batchUploadCodeEnvFiles` est appelé
- Vérifier que `read_file` et `bash_tool` voient bien le SkillFile dans le sandbox

### Phase 1 — Image code-interpreter mince (3-5 jours)

- Repartir de `main` (upstream `usnavy13`)
- Ajouter au Dockerfile : LibreOffice, pandoc, qpdf, ffmpeg, fonts, libreoffice-impress
- Créer `/opt/lib/office/` avec la lib OOXML (les 60 fichiers de `skills/docx/scripts/office/`)
- Configurer `PYTHONPATH=/opt/lib:$PYTHONPATH` dans le sandbox
- Apporter PTC bash (`docker/ptc_bash_server.py`)
- Apporter egress proxy + firewall + auth + sanitization (les ~12 fichiers `src/services/sandbox/egress*.py`, `src/services/auth.py`, `src/dependencies/auth.py`)
- Apporter migration Garage (`garage.toml` + boto3 client)
- Apporter `.gitleaks.toml`, restrictions upload, tmpfs durci
- Nouveau fichier doc `docs/RUNTIME_LIBRARIES.md` qui documente la lib `office/` et son contrat avec les skills
- Tests unit/integration : garder ceux qui touchent à l'infra (auth, egress, programmatic, ptc, sandbox), abandonner ceux liés à `/opt/skills/`

### Phase 2 — Création des skills natives dans LibreChat (2-3 jours)

Approche **zip import one-shot** (depuis l'audit 2026-06-01) :

1. Préparer un repo `skillset/` avec une structure prête à zipper :
   ```
   skillset/
   ├── bundle.sh          # zippe chaque sous-dossier en <skill>.zip
   ├── docx/
   │   ├── SKILL.md       # renommé depuis AGENT_INSTRUCTIONS.md → body
   │   ├── scripts/       # WITHOUT office/ (lib système LCI)
   │   ├── templates/
   │   │   └── corporate/ # .docx, .png, .svg, .lua
   │   └── reference/
   │       └── SKILL_DETAILED.md  # renommé depuis SKILL.md
   ├── pptx/  (idem)
   ├── xlsx/  (idem)
   ├── pdf/, ffmpeg/, dataviz/  (body-only, juste SKILL.md)
   ```
2. Lancer `./bundle.sh` → produit `dist/docx.zip`, `dist/pptx.zip`, etc.
3. Pour chaque zip : drag-drop dans LibreChat UI (Skills > Import) — l'arborescence est préservée (#12877).
4. Configurer 6 agents LibreChat avec `Agent.skills` qui pointent vers les skills correspondantes.

Pour reproductibilité (CI / nouveau déploiement), garder `bundle.sh` versionné dans Git et automatiser l'upload via `POST /api/skills/import` en multipart (curl ou client Node).

> **Note historique** : la version initiale du doc suggérait `POST /api/skills` + `POST /api/skills/:id/files` par fichier. L'audit 2026-06-01 a confirmé que le zip import (`/api/skills/import`) accepte une arborescence imbriquée en un seul appel — c'est plus simple et c'est la voie principale supportée par l'UI.

### Phase 3 — Templates propriétaires par tenant (1-2 jours)

Pour chaque client/tenant qui a ses propres templates corporés :

1. Créer une skill privée `docx-tenant-acme` (ACL : owner=admin tenant)
2. Y uploader les templates propriétaires
3. Configurer leur agent pour utiliser cette skill au lieu de la skill générique

Si un client a > 50 templates volumineux : envisager un `tenants/<tenant>/templates/` mount runtime de fallback (mais c'est l'exception, pas la règle).

### Phase 4 — Tests (2-3 jours)

- Refactor `tests/agent_api_tests.py` : adapter les patterns regex aux nouveaux artefacts du reasoning (le tool call est `skill:docx` avec args plutôt que `python fill_cr_template.py`)
- Garder Ralph Wiggum
- Ajouter des tests qui valident le **chargement** des skills (POST `/api/skills`, vérification ACL, intersection per-agent)
- Smoke test : binaires + lib office/ + skills présentes dans LibreChat

### Phase 5 — Documentation et publication (1-2 jours)

- Doc `docs/SKILLS_VS_RUNTIME.md` qui clarifie la séparation
- Mettre à jour `docs/INSTALLATION_GUIDE.md` avec les deux étapes (image + seed skills)
- Publier le fork code-interpreter "client-agnostic" sur GitHub

---

## 6. Plan de migration progressive (à partir de l'existant)

Si on veut migrer **maintenant** plutôt que recommencer :

### Étape 1 — Garder le double-mode pendant la migration

- L'image actuelle continue de monter `/opt/skills/` (rétrocompatible avec les agents existants)
- En parallèle, créer les skills natives dans LibreChat
- Les agents migrés un par un : on bascule l'agent à la skill native, on retire le `AGENT_INSTRUCTIONS.md` du prompt agent dans `librechat.yaml`
- Coexistence pendant 2-4 semaines

### Étape 2 — Promotion de `office/` en lib système

- Déplacer `skills/docx/scripts/office/` vers `/opt/lib/office/` dans l'image
- Configurer `PYTHONPATH` dans nsjail
- Vérifier que les scripts pptx/xlsx qui font `from office.soffice import ...` continuent de fonctionner

### Étape 3 — Migration agent par agent

Ordre suggéré (du plus simple au plus complexe) : **ffmpeg → pdf → dataviz → xlsx → pptx → docx**.

Pour chaque : préparer `skillset/<skill>/`, bundler en zip (`bundle.sh`), importer dans LibreChat via UI ou `POST /api/skills/import`, configurer agent LibreChat, tester avec sous-set des 79 tests, basculer.

DOCX en dernier parce que c'est 81 fichiers et la skill la plus chargée (et templates corporate à embarquer).

### Étape 4 — Nettoyage de l'image

- Une fois tous les agents migrés : retirer `/opt/skills/{docx,pptx,xlsx,pdf,ffmpeg,dataviz}` du Dockerfile
- Retirer la doc `docs/AGENT_SKILLS.md` (devenue obsolete)
- Garder `docs/PROGRAMMATIC_TOOL_CALLING.md`, `docs/SECURITY.md`, `docs/STATE_PERSISTENCE.md` qui restent pertinents

### Étape 5 — Réajuster le harness de test

- `tests/agent_api_tests.py` : refactor des regex patterns
- `tests/ralph-wiggum-prompt.md` : update si le format des prompts d'invocation change

---

## 7. Pièges et zones grises

### Piège 1 — Limite 100 KB sur le body

On est safe aujourd'hui, mais si la skill docx s'enrichit (39 KB → 100 KB), on hit un mur. Stratégie : ne mettre dans le `body` que la **méthodologie** (quand utiliser quoi), et déporter les détails de syntaxe dans des SkillFiles `category=reference` que l'agent lit via `read_file`.

### Piège 2 — Lib `office/` partagée

Native skills ne supporte ni les imports entre skills, ni les "system skills". Il y a **deux mauvaises solutions** :

- ❌ Bundler `office/` dans chaque skill → 180 SkillFile records, mises à jour 3× plus lourdes
- ❌ Faire de `office/` une 7ème skill que les autres référencent → ne fonctionne pas (pas de composition)

**Bonne solution** : `office/` devient une lib **système de l'image** sous `/opt/lib/office/` exposée via `PYTHONPATH`. C'est exactement le statut qu'a déjà `python-docx`, `openpyxl`, etc. — c'est juste une lib Python.

### Piège 3 — Dépendances Python applicatives

Aujourd'hui dans l'image : `python-pptx`, `pptxgenjs`, `python-docx`, `openpyxl`, `lxml`, `cloudpickle`, `boto3`, `matplotlib`, `seaborn`. Native skills ne fait **pas** de `pip install` automatique. Donc ces deps doivent rester pré-installées dans l'image. C'est le comportement actuel et c'est correct — il faut juste documenter explicitement le contrat skill ↔ image.

### Piège 4 — `$ARGUMENTS` substitution

Les skills natives substituent `$ARGUMENTS` dans le `body`. Les scripts actuels parsent un `<config.json>` en argument CLI. Pas de friction directe, mais si on veut exploiter `$ARGUMENTS` (par exemple "skill `docx` invoquée avec `format: cr, theme: blue`"), il faut remanier la couche de prompt pour utiliser ce pattern. Ce n'est pas obligatoire — on peut continuer à passer un fichier de config.

### Piège 5 — Templates propriétaires + ACL skills

Si chaque tenant veut sa skill `docx-templates-{tenant}` avec ses templates, il faut un **process de provisioning** : un admin doit créer la skill, uploader les templates, partager avec le tenant, configurer leur agent. Pas de magie. Pour 1-2 tenants c'est ok ; à 50 tenants on veut scripter.

### Piège 6 — Monitoring & rollback

Mettre à jour une skill = un PATCH atomique. Pas de rollback natif (juste optimistic concurrency). Si on casse une skill en prod, il faut remettre l'ancien `body`/`SkillFile` à la main.

**Mitigation** : versionner les définitions de skills dans un repo Git (par exemple `LibreCodeInterpreter/skills-source/`) et faire le déploiement vers LibreChat via un script idempotent — ça donne l'historique côté Git.

### Piège 7 — Cache 23 h des SkillFiles dans le sandbox

LibreChat cache les uploads de SkillFile pendant 23 h dans le sandbox (vérification de session active). Quand on met à jour un script, le sandbox peut servir l'ancienne version pendant un cycle. À surveiller : invalider explicitement (rotation de session) ou attendre l'expiration.

### Piège 8 — Tests et reasoning patterns

Les 79 tests vérifient que l'agent appelle le bon script via regex sur le reasoning. Avec native skills, le reasoning expose probablement `tool_use: skill, name: docx-cr, input: {...}` plutôt que `python fill_cr_template.py ...`. Patterns à adapter — c'est mécanique mais à ne pas oublier.

### Piège 9 — Read-only des SkillFiles dans le sandbox (audit 2026-06-01)

Les SkillFiles uploadés sont marqués `read_only: true` côté MinIO → **chmod 444** dans le sandbox (`skillFiles.ts:225`). **Les scripts ne peuvent pas modifier les templates en place.**

Contrat à respecter dans `scripts/fill_template.py` et consorts : toujours **copier** le template vers `/mnt/data/work/` (ou répertoire de travail), modifier la copie, écrire la sortie ailleurs. À auditer sur les 23 scripts docx + scripts pptx avant la migration.

### Piège 10 — Pas d'export skill → zip (audit 2026-06-01)

Il n'existe **pas** de `GET /api/skills/:id/export` pour récupérer une skill sous forme de zip. Conséquence : la source de vérité doit rester le **repo Git `skillset/`** ; LibreChat n'est qu'un cache de déploiement.

Workflow opérationnel : modifier dans Git → re-bundle → re-upload (LibreChat bump la version, cache 23h invalidé naturellement).

### Piège 11 — 1 SKILL.md = 1 skill par zip (audit 2026-06-01)

L'import zip cherche **un seul** `SKILL.md` (racine ou +1 niveau de profondeur). Pour 6 skills, il faut **6 zips séparés** (pas un seul `skillset.zip` global).

Conséquence pratique : le script `bundle.sh` produit `dist/<skill>.zip` × 6, pas un mega-zip.

### Piège 12 — Renommage AGENT_INSTRUCTIONS.md → SKILL.md (audit 2026-06-01)

Le repo actuel a deux fichiers distincts : `AGENT_INSTRUCTIONS.md` (39 KB, méthodologie) et `SKILL.md` (20 KB, syntaxe détaillée). Native skills ne lit **que** le fichier nommé `SKILL.md` comme body.

À la migration :
- `AGENT_INSTRUCTIONS.md` → renommé en `SKILL.md` à la racine de la skill (devient le body, 39 KB tient dans la limite 100 KB)
- L'ancien `SKILL.md` → déplacé en `reference/SKILL_DETAILED.md` (SkillFile, accédé par `read_file`)

---

## 8. Composantes finales par couche

### LibreCodeInterpreter (image Docker) — RESTE

1. **Image OS** :
   - LibreOffice (+ Impress, Calc, Writer)
   - pandoc, qpdf, ffmpeg
   - Fonts pack
   - Lib Python `office/` (60 fichiers OOXML, sous `/opt/lib/office/`)
   - Deps Python : python-docx, openpyxl, python-pptx, pptxgenjs, lxml, matplotlib, etc.

2. **Couche sandbox** :
   - nsjail
   - PTC Python + PTC bash
   - Egress proxy + allowlist
   - Auth (basic + API key)
   - File sanitization Unicode
   - tmpfs hardening

3. **Endpoints API** (inchangés) :
   - POST `/exec` (exécution code)
   - POST `/exec/programmatic` + continuation
   - POST `/upload/batch` (cible des `batchUploadCodeEnvFiles` LibreChat)
   - GET `/sessions/:id` (état)
   - Auth/admin endpoints

4. **Stockage** : Garage S3.

5. **CI** : build + test + publish image.

6. **Tests d'image** :
   - Smoke (binaires, lib office)
   - Auth, egress, PTC, sanitization
   - **Pas** les tests métier des 79 cas

### LibreChat (DB) — NOUVEAU

1. **Catalogue Skills** : 6 skills (docx, pptx, xlsx, pdf, ffmpeg, dataviz), uploadées via **zip import** depuis le repo `skillset/`. Chaque skill = 1 zip (`docx.zip`, `pptx.zip`, …).
2. **Templates métier** : portés dans `templates/` à l'intérieur de chaque skill zip. Pour multi-tenant : 1 skill privée par tenant + ACL. Pour mono-tenant (cas onbehalfai) : sous-dossier `templates/corporate/` dans la skill publique.
3. **Per-agent assignment** : `Agent.skills` whitelist + `skills_enabled`.
4. **Permissions et ACL** : qui peut créer/voir/partager une skill.
5. **Tests métier** (les 79 cas) : exécutés contre LibreChat, pas contre le sandbox.
6. **Source de vérité Git** : repo `skillset/` versionné (pas d'export depuis LibreChat), avec `bundle.sh` qui produit les zips et un script de re-upload idempotent.

---

## 9. Recommandation

**À court terme** (cette semaine) : ne toucher à rien sur la branche `feat/agent-skills-runtime`. Elle fonctionne, l'image est buildée, les agents tournent. Profiter des Skills natives pour des **nouveaux** besoins (skills légères, single-purpose, sans gros templates) et garder l'existant.

**À moyen terme** (3-6 mois) : migrer skill par skill, en commençant par **ffmpeg, pdf, dataviz** (skills body-only sans script — migration triviale, gain pédagogique). Cela permet de valider le pattern, écrire le script de seed, ajuster le harness de test, sans risquer la prod sur DOCX.

**À long terme** (6-12 mois) : finaliser la migration de docx, pptx, xlsx (les complexes). À ce moment, l'image LibreCodeInterpreter peut être maigrie, publiée publiquement comme un *Office sandbox runtime générique*, et le contenu (skills + templates) vit côté LibreChat — ce qui est cohérent avec la posture stratégique de fork client-agnostic.

**À ne pas faire** : essayer de tout migrer d'un coup. Ce sont 220 commits, 6 skills, 79 tests métier — un big-bang serait du suicide opérationnel.
