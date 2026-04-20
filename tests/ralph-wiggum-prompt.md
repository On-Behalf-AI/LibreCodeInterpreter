# Ralph Wiggum Prompt — Agent Skills Test Suite

## Objectif

Exécuter la suite de 76 tests des agents LibreChat et corriger itérativement les échecs jusqu'à ce que tous les tests passent. Chaque itération : lancer les tests, analyser les échecs, corriger la cause racine (instructions agent, scripts, prompts de test), vérifier.

## Contexte

Ce projet est un fork enrichi de LibreCodeInterpreter (`On-Behalf-AI/LibreCodeInterpreter`, branche `feat/agent-skills-runtime`). Il sert de runtime pour 6 agents LibreChat spécialisés (DOCX, PPTX, XLSX, PDF, FFmpeg, DataViz) qui transforment des documents avec des templates corporate On Behalf AI.

### Architecture

```
skills/
├── docx/   → AGENT_INSTRUCTIONS.md (27 KB) + scripts/ + templates/onbehalfai/
│   ├── scripts/
│   │   ├── fill_template.py          ← Guide/rapport from JSON
│   │   ├── fill_cr_template.py       ← Compte-rendu from JSON
│   │   ├── fill_courrier_template.py ← Courrier/lettre from JSON
│   │   ├── inject_cover.py           ← Post-process pandoc output (10 steps)
│   │   ├── tracked_replace.py, accept_changes.py, comment.py
│   │   └── office/ (unpack.py, pack.py, validate.py, soffice.py)
│   └── templates/onbehalfai/
│       ├── template-base.docx         ← Guides, rapports
│       ├── template-compte-rendu.docx ← CRs
│       ├── template-courrier.docx     ← Lettres
│       └── reference-pandoc.docx      ← Pandoc styles+footer
├── pptx/   → AGENT_INSTRUCTIONS.md (14 KB) + scripts/ + templates/onbehalfai/
├── xlsx/   → AGENT_INSTRUCTIONS.md (3 KB)
├── pdf/    → AGENT_INSTRUCTIONS.md (3 KB)
├── ffmpeg/ → AGENT_INSTRUCTIONS.md (2 KB)
└── dataviz/ → AGENT_INSTRUCTIONS.md (3 KB)

tests/
├── agent_api_tests.py   ← 79 tests (33 self-contained + 46 need-file)
└── results/             ← JSON reports
```

### Agents MongoDB IDs

| Agent | MongoDB ID | Model |
|-------|-----------|-------|
| DOCX | agent_docx_complete | Claude Sonnet 4.5 |
| PPTX | agent_pptx_complete | Claude Sonnet 4.5 |
| XLSX | agent_xlsx_complete | Claude Sonnet 4.5 |
| PDF | agent_pdf_complete | Claude Sonnet 4.5 |
| FFmpeg | agent_quick_edits | Claude Sonnet 4.5 |
| DataViz | agent_data_viz | Gemini 2.5 Pro |

## Instructions par itération

### 1. Lancer les tests

```bash
cd /home/damien/LibreCodeInterpreter

# Self-contained tests only (faster, no file upload needed)
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py --no-file

# Specific agent
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py --agent docx --no-file

# Specific failing tests
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py D01b D01c P01b X01 A01

# All tests (long: ~10 min per test × 76 tests)
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py
```

### 2. Lire le rapport

```bash
# Latest report
ls -t tests/results/report_*.json | head -1 | xargs cat
```

Le rapport JSON contient pour chaque test :
- `status`: PASS / FAIL / ERROR
- `error`: message d'erreur
- `methodology_checks`: patterns trouvés (FOUND) ou manquants (MISSING)
- `response_preview`: extrait de la réponse de l'agent

### 3. Diagnostiquer les échecs

Pour chaque test FAIL ou ERROR :

**Si FAIL (methodology pattern MISSING)** :
- L'agent n'utilise pas la bonne approche. Cause probable : AGENT_INSTRUCTIONS.md insuffisant.
- Lire `skills/<agent>/AGENT_INSTRUCTIONS.md` et vérifier que la méthodologie attendue y est documentée.
- Si le pattern de test est trop strict, adapter le pattern regex dans `tests/agent_api_tests.py`.

**Si ERROR (timeout ou erreur API)** :
- Vérifier que l'agent est déployé : `docker exec -i chat-mongodb mongosh --quiet LibreChat --eval "db.agents.findOne({id:'<agent_id>'},{id:1,name:1})"`
- Vérifier que l'API est up : `curl -s http://127.0.0.1:3080/api/agents/v1/responses -H "Authorization: Bearer $(cat .agent-api-key)" -d '{"model":"agent_docx_complete","input":"test","stream":false}' | head -c 200`
- Vérifier que le code-interpreter tourne : `curl -s http://127.0.0.1:8010/health`

**Si FAIL (Gemini/DataViz)** :
- Le DataViz agent utilise Gemini 2.5 Pro qui ne retourne pas les `function_call` outputs dans l'API response.
- Les patterns ne matchent que sur reasoning + message text. Adapter les patterns si nécessaire.

### 4. Corriger

**Modifier les instructions agent** :
```bash
# 1. Éditer le fichier
nano skills/<agent>/AGENT_INSTRUCTIONS.md

# 2. Mettre à jour MongoDB
cat > /tmp/update.js << 'JSEOF'
const fs = require('fs');
const i = fs.readFileSync('skills/<agent>/AGENT_INSTRUCTIONS.md', 'utf8');
const e = JSON.stringify(i);
fs.writeFileSync('/tmp/m.js', `db.agents.updateOne({id:"<agent_id>"},{$set:{instructions:${e},"versions.0.instructions":${e}}})`);
JSEOF
node /tmp/update.js && docker exec -i chat-mongodb mongosh --quiet LibreChat < /tmp/m.js
```

**Modifier un script** :
```bash
# 1. Éditer le script
nano skills/docx/scripts/fill_template.py

# 2. Rebuild l'image Docker
docker buildx build --target app --tag code-interpreter:agent-skills .

# 3. Redémarrer le container
docker stop code-interpreter-api && docker rm code-interpreter-api
docker run -d --name code-interpreter-api --restart unless-stopped --init \
  --cap-add SYS_ADMIN --security-opt apparmor:unconfined \
  --network librechat_clean_default \
  -p 127.0.0.1:8010:8000 \
  --env-file /home/damien/LibreCodeInterpreter/.env \
  -e REDIS_HOST=code-interpreter-redis \
  -e MINIO_ENDPOINT=code-interpreter-minio:9000 \
  -v code-interpreter-sandbox-data:/var/lib/code-interpreter/sandboxes \
  -v /home/damien/LibreCodeInterpreter/ssl:/app/ssl:ro \
  --tmpfs /app/data:size=100m \
  code-interpreter:agent-skills
```

**Modifier un pattern de test** :
- Si le pattern regex est trop strict ou ne capture pas le bon texte.
- Éditer `tests/agent_api_tests.py`, trouver le test par son ID, adapter `patterns`.
- Attention : le test checke le texte de reasoning + message, PAS le code exécuté.

### 5. Vérifier le fix

Relancer uniquement les tests qui ont échoué :
```bash
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py <test_id_1> <test_id_2>
```

### 6. Committer les progrès

```bash
cd /home/damien/LibreCodeInterpreter
git add -A
git commit -m "fix: <description du fix>

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

## Critères de succès

### CS1 : Tous les tests self-contained passent (33 tests)
```bash
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py --no-file
```
Résultat attendu : `33 passed, 0 failed, 0 errors / 33 total`

### CS2 : Les tests NEEDS_FILE fonctionnent en mode methodology (46 tests)
Les tests avec fichiers tournent et vérifient la méthodologie de l'agent (sans upload de fichier). Le prompt est assez précis pour que l'agent raisonne correctement.
```bash
AGENT_API_KEY=$(cat .agent-api-key) python3 tests/agent_api_tests.py --only-file
```
Résultat attendu : majorité PASS (l'agent décrit la bonne méthodologie même sans fichier réel).

### CS3 : Zéro ERROR
Aucun test ne doit retourner ERROR (timeout ou exception). Si un agent ne répond pas, investiguer et corriger.

## Stratégie de progression

1. **Phase 1** : Commencer par `--no-file` (30 tests self-contained, rapide)
2. **Phase 2** : Passer à `--agent docx`, puis `--agent pptx`, etc. (un agent à la fois)
3. **Phase 3** : Lancer la suite complète `--only-file` pour les tests avec fichiers
4. **Phase 4** : Tout en une fois, confirmer 76/76 PASS

## Limitations connues

- **Open Responses API** : ne retourne PAS le code exécuté (`function_call.arguments` toujours vide). On ne peut vérifier que la méthodologie via reasoning + message text.
- **Gemini (DataViz)** : ne retourne pas les `function_call` outputs du tout. Les tests DataViz sont limités au texte visible.
- **File upload** : l'API Responses ne supporte pas encore les fichiers (`requestFiles: []` hardcodé dans LibreChat). Les tests NEEDS_FILE vérifient la méthodologie uniquement.
- **Timeout** : chaque test a un timeout de 10 minutes. Les agents avec code execution complexe peuvent être lents.

## Itérations maximales

50 itérations pour atteindre CS1 + CS2 + CS3.

## Completion promise

Quand les critères CS1, CS2 et CS3 sont atteints (30/30 self-contained PASS + majorité des 46 file-tests PASS + 0 ERROR), tu peux conclure :

```
<promise>ALL_AGENT_TESTS_PASS</promise>
```

**RAPPEL CRITIQUE** : ne sors cette promise que si les tests ont RÉELLEMENT été exécutés et passent. Ne mens pas pour sortir de la boucle.
