# Ralph Wiggum Prompt — Generate Files from All 6 Agents & Download

## CONTEXTE

Tu travailles sur `/home/damien/LibreCodeInterpreter`, branche `feat/agent-skills-runtime`.

6 agents LibreChat sont opérationnels sur chat-dev.onbehalf.ai, chacun avec un code-interpreter sandbox.

**API LibreChat Open Responses** :
- Endpoint : `http://127.0.0.1:3080/api/agents/v1/responses`
- Auth : `Bearer <key>` (lire depuis `/home/damien/LibreCodeInterpreter/.agent-api-key`)
- Payload : `{"model": "<agent_id>", "input": "<prompt>", "stream": false}`

**API Code-Interpreter directe** (pour télécharger les fichiers) :
- Endpoint : `http://127.0.0.1:8010`
- API Key : `$CODE_INTERPRETER_KEY (voir .env)`
- Exec : `POST /exec` avec `{"code": "...", "lang": "py|js"}`
- Download : `GET /download/{session_id}/{file_id}`

**Répertoire de sortie** : `/home/damien/LibreCodeInterpreter/test-17-04/`

## TA MISSION

Pour chaque agent, générer un fichier représentatif en appelant le code-interpreter directement (pas le LLM — trop lent et la réponse ne contient pas les fichiers). Télécharger chaque fichier dans `test-17-04/`.

## FICHIERS À GÉNÉRER

### 1. DOCX — Compte-Rendu (fill_cr_template.py)

```python
import subprocess, json, os
os.chdir('/mnt/data')
config = {
    "meeting": {
        "title": "Compte-rendu de cadrage projet IA",
        "subtitle": "Nextera Corp / Cadrage projet IA RH",
        "date": "17/04/2026",
        "location": "Visioconférence Teams",
        "organizer": "Damien Juillard"
    },
    "participants": [
        {"name": "Sophie Martin", "role": "Directrice RH", "company": "Nextera Corp"},
        {"name": "Jean Dupont", "role": "DSI", "company": "Nextera Corp"},
        {"name": "Damien Juillard", "role": "Consultant IA", "company": "On Behalf AI"}
    ],
    "sections": [
        {
            "title": "Contexte",
            "level": 1,
            "content": [
                {"type": "text", "text": "Cet atelier s'inscrit dans le cadre du projet de transformation digitale de Nextera Corp, visant à intégrer l'intelligence artificielle dans les processus RH."},
                {"type": "text", "text": "L'objectif est d'identifier les cas d'usage prioritaires et de définir la feuille de route pour les 6 prochains mois."}
            ]
        },
        {
            "title": "Points abordés",
            "level": 1,
            "content": [
                {"type": "text", "text": "Analyse des processus RH existants", "bold": true},
                {"type": "text", "text": "Sophie Martin a présenté l'organisation du département RH (45 personnes, 3 sites). Volume annuel : 2 500 candidatures, 180 recrutements."},
                {"type": "empty"},
                {"type": "text", "text": "Cas d'usage IA identifiés", "bold": true},
                {"type": "bullets", "items": [
                    "Tri automatique des CV et pré-qualification des candidatures",
                    "Chatbot interne pour les questions administratives RH",
                    "Analyse prédictive du turnover à partir des données historiques",
                    "Automatisation de la génération des contrats de travail"
                ]}
            ]
        },
        {
            "title": "Décisions",
            "level": 1,
            "content": [
                {"type": "numbered", "items": [
                    "Lancement du POC sur le tri automatique de CV (priorité haute)",
                    "Étude de faisabilité pour le chatbot RH (priorité moyenne)",
                    "Report de l'analyse prédictive à la phase 2"
                ]}
            ]
        },
        {
            "title": "Actions et prochaines étapes",
            "level": 1,
            "content": [
                {"type": "table", "headers": ["Action", "Responsable", "Deadline"],
                 "rows": [
                    ["Étude de faisabilité tri CV", "Damien Juillard (OBA)", "24/04/2026"],
                    ["Extraction données RH anonymisées", "Jean Dupont (Nextera)", "30/04/2026"],
                    ["Présentation POC chatbot", "Damien Juillard (OBA)", "08/05/2026"],
                    ["Cahier des charges technique", "Damien Juillard (OBA)", "15/05/2026"]
                ]},
                {"type": "empty"},
                {"type": "text", "text": "Prochain atelier prévu le 8 mai 2026."}
            ]
        }
    ]
}
with open("/tmp/config.json", "w") as f:
    json.dump(config, f, ensure_ascii=False)
subprocess.run(["python3", "/opt/skills/docx/scripts/fill_cr_template.py",
    "/opt/skills/docx/templates/onbehalfai/template-compte-rendu.docx",
    "CR_Nextera_17-04-2026.docx", "/tmp/config.json"], check=True)
print("OK")
```
**Fichier attendu** : `CR_Nextera_17-04-2026.docx`

### 2. DOCX — Guide technique (fill_template.py)

```python
import subprocess, json, os
os.chdir('/mnt/data')
config = {
    "placeholders": {
        "[TITRE DU DOCUMENT]": "Guide d'Installation Docker",
        "[Sous-titre du document]": "Infrastructure Conteneurisée",
        "[Auteur]": "Damien Juillard",
        "[Date]": "17/04/2026"
    },
    "sections": [
        {"title": "Introduction", "level": 0, "content": [
            {"type": "text", "text": "Ce guide détaille l'installation et la configuration de Docker sur un serveur Ubuntu pour déployer des applications conteneurisées en production."}
        ]},
        {"title": "Prérequis", "level": 1, "content": [
            {"type": "text", "text": "Configuration matérielle recommandée :", "bold": true},
            {"type": "bullets", "items": [
                "Ubuntu 22.04 LTS ou supérieur",
                "4 Go de RAM minimum (8 Go recommandés)",
                "20 Go d'espace disque disponible",
                "Accès root ou sudo"
            ]}
        ]},
        {"title": "Installation", "level": 1, "content": [
            {"type": "text", "text": "Mise à jour du système :", "bold": true},
            {"type": "code", "text": "sudo apt update && sudo apt upgrade -y"},
            {"type": "text", "text": "Installation de Docker :", "bold": true},
            {"type": "code", "text": "curl -fsSL https://get.docker.com -o get-docker.sh\nsudo sh get-docker.sh\nsudo usermod -aG docker $USER"},
            {"type": "text", "text": "Installation de Docker Compose :", "bold": true},
            {"type": "code", "text": "sudo apt install docker-compose-plugin\ndocker compose version"}
        ]},
        {"title": "Configuration", "level": 1, "content": [
            {"type": "text", "text": "Variables d'environnement recommandées :", "bold": true},
            {"type": "table", "headers": ["Variable", "Description", "Valeur par défaut"],
             "rows": [
                ["DOCKER_HOST", "Socket Docker", "unix:///var/run/docker.sock"],
                ["COMPOSE_PROJECT_NAME", "Nom du projet", "(nom du répertoire)"],
                ["DOCKER_BUILDKIT", "Activer BuildKit", "1"]
            ]},
            {"type": "empty"},
            {"type": "text", "text": "Exemple de docker-compose.yml :", "bold": true},
            {"type": "code", "text": "version: '3.8'\nservices:\n  web:\n    image: nginx:latest\n    ports:\n      - '80:80'\n    restart: unless-stopped"}
        ]},
        {"title": "Vérification", "level": 1, "content": [
            {"type": "numbered", "items": [
                "Vérifier que Docker tourne : docker info",
                "Lancer un conteneur test : docker run hello-world",
                "Vérifier Docker Compose : docker compose version",
                "Tester un déploiement : docker compose up -d"
            ]}
        ]},
        {"title": "Dépannage", "level": 1, "content": [
            {"type": "text", "text": "Commandes de diagnostic :", "bold": true},
            {"type": "code", "text": "docker ps -a\ndocker logs <container_name>\ndocker system df\ndocker system prune -a"},
            {"type": "text", "text": "Problèmes courants :", "bold": true},
            {"type": "bullets", "items": [
                "Permission denied : ajouter l'utilisateur au groupe docker",
                "Port déjà occupé : vérifier avec ss -tlnp",
                "Espace disque insuffisant : docker system prune"
            ]}
        ]}
    ]
}
with open("/tmp/config.json", "w") as f:
    json.dump(config, f, ensure_ascii=False)
subprocess.run(["python3", "/opt/skills/docx/scripts/fill_template.py",
    "/opt/skills/docx/templates/onbehalfai/template-base.docx",
    "Guide_Installation_Docker.docx", "/tmp/config.json"], check=True)
print("OK")
```
**Fichier attendu** : `Guide_Installation_Docker.docx`

### 3. PPTX — Présentation OBA (pptxgenjs)

```javascript
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const OBA = {
    navy: "1C244B", blue: "2F5597", blueSky: "5B9AD4",
    orange: "FB840D", white: "FFFFFF", grayLight: "F3F5F8",
    heading: "233F70", text: "333333"
};

const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9";
pptx.author = "Damien Juillard";

// Slide 1 : Titre
let s1 = pptx.addSlide();
s1.background = { fill: OBA.navy };
s1.addText("Intelligence Artificielle\nen Entreprise", {
    x: 0.5, y: 1.5, w: 9, h: 2, fontSize: 36, fontFace: "Arial",
    bold: true, color: OBA.white, align: "left", breakLine: true
});
s1.addText("Stratégie et cas d'usage — Avril 2026", {
    x: 0.5, y: 3.8, w: 9, h: 0.6, fontSize: 18, fontFace: "Arial", color: OBA.blueSky
});
s1.addShape(pptx.ShapeType.rect, {x:0, y:5.2, w:10, h:0.05, fill:{color:OBA.orange}});

// Slide 2 : Section
let s2 = pptx.addSlide();
s2.background = { fill: OBA.blue };
s2.addText("Contexte et enjeux", {
    x: 0.5, y: 1.5, w: 9, h: 2, fontSize: 40, fontFace: "Arial",
    bold: true, color: OBA.white, align: "left"
});
s2.addShape(pptx.ShapeType.rect, {x:0.5, y:3.8, w:2, h:0.06, fill:{color:OBA.orange}});

// Slide 3 : Contenu
let s3 = pptx.addSlide();
s3.background = { fill: OBA.white };
s3.addText("Pourquoi l'IA maintenant ?", {
    x:0.5, y:0.3, w:9, h:0.8, fontSize:28, fontFace:"Arial", bold:true, color:OBA.heading
});
s3.addShape(pptx.ShapeType.rect, {x:0.5, y:1.15, w:1.5, h:0.04, fill:{color:OBA.orange}});
s3.addText([
    {text:"Maturité technologique des LLMs (GPT-4, Claude, Gemini)", options:{bullet:true, fontSize:16, color:OBA.text}},
    {text:"Réduction des coûts d'infrastructure cloud (-40% en 2 ans)", options:{bullet:true, fontSize:16, color:OBA.text, breakLine:true}},
    {text:"Pression concurrentielle : 67% des entreprises du CAC40 ont un programme IA", options:{bullet:true, fontSize:16, color:OBA.text, breakLine:true}},
    {text:"ROI prouvé sur les cas d'usage de productivité (+25% en moyenne)", options:{bullet:true, fontSize:16, color:OBA.text, breakLine:true}},
], {x:0.5, y:1.5, w:9, h:3.5, fontFace:"Arial", paraSpaceAfter:12, valign:"top"});

// Slide 4 : Deux colonnes
let s4 = pptx.addSlide();
s4.background = { fill: OBA.white };
s4.addText("Approche recommandée", {
    x:0.5, y:0.3, w:9, h:0.8, fontSize:28, fontFace:"Arial", bold:true, color:OBA.heading
});
s4.addShape(pptx.ShapeType.rect, {x:0.5, y:1.15, w:1.5, h:0.04, fill:{color:OBA.orange}});
s4.addShape(pptx.ShapeType.rect, {x:0.5, y:1.5, w:4.2, h:3.5, fill:{color:OBA.grayLight}, rectRadius:0.1});
s4.addText("Phase 1 : Quick Wins\n\n- Automatisation documentaire\n- Chatbot interne\n- Analyse de données", {
    x:0.7, y:1.6, w:3.8, h:3.2, fontSize:14, fontFace:"Arial", color:OBA.text, valign:"top"
});
s4.addShape(pptx.ShapeType.rect, {x:5.3, y:1.5, w:4.2, h:3.5, fill:{color:OBA.grayLight}, rectRadius:0.1});
s4.addText("Phase 2 : Transformation\n\n- IA dans les processus métier\n- Agents autonomes\n- Prédictif et prescriptif", {
    x:5.5, y:1.6, w:3.8, h:3.2, fontSize:14, fontFace:"Arial", color:OBA.text, valign:"top"
});

// Slide 5 : Chiffres clés
let s5 = pptx.addSlide();
s5.background = { fill: OBA.white };
s5.addText("Chiffres clés", {
    x:0.5, y:0.3, w:9, h:0.8, fontSize:28, fontFace:"Arial", bold:true, color:OBA.heading
});
s5.addShape(pptx.ShapeType.rect, {x:0.5, y:1.15, w:1.5, h:0.04, fill:{color:OBA.orange}});

const metrics = [
    {value: "+25%", label: "Productivité", color: OBA.blue},
    {value: "-40%", label: "Coûts opérationnels", color: OBA.blueSky},
    {value: "3x", label: "Vitesse de traitement", color: OBA.orange},
];
metrics.forEach((m, i) => {
    const x = 0.5 + i * 3.2;
    s5.addShape(pptx.ShapeType.rect, {x: x, y: 1.8, w: 2.8, h: 2.5, fill: {color: m.color}, rectRadius: 0.15});
    s5.addText(m.value, {x: x, y: 2.0, w: 2.8, h: 1.2, fontSize: 40, fontFace: "Arial", bold: true, color: OBA.white, align: "center"});
    s5.addText(m.label, {x: x, y: 3.2, w: 2.8, h: 0.8, fontSize: 14, fontFace: "Arial", color: OBA.white, align: "center"});
});

// Slide 6 : Closing
let s6 = pptx.addSlide();
s6.background = { fill: OBA.navy };
s6.addText("Merci", {
    x:0.5, y:1.8, w:9, h:1.2, fontSize:44, fontFace:"Arial", bold:true, color:OBA.white, align:"center"
});
s6.addText("Damien Juillard — damien@onbehalf.ai", {
    x:0.5, y:3.5, w:9, h:0.5, fontSize:16, fontFace:"Arial", color:OBA.blueSky, align:"center"
});
s6.addShape(pptx.ShapeType.rect, {x:0, y:5.2, w:10, h:0.05, fill:{color:OBA.orange}});

pptx.writeFile({fileName: "/mnt/data/Presentation_IA_Entreprise.pptx"})
    .then(() => console.log("OK"))
    .catch(err => console.error(err));
```
**Fichier attendu** : `Presentation_IA_Entreprise.pptx`

### 4. XLSX — Budget prévisionnel (openpyxl)

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
wb = Workbook()
ws = wb.active
ws.title = "Budget Q1 2026"

hdr_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
accent_fill = PatternFill(start_color="DAE5EF", end_color="DAE5EF", fill_type="solid")
total_font = Font(name="Arial", size=11, bold=True, color="1C244B")
border = Border(
    left=Side(style='thin', color='CCCCCC'),
    right=Side(style='thin', color='CCCCCC'),
    top=Side(style='thin', color='CCCCCC'),
    bottom=Side(style='thin', color='CCCCCC')
)

headers = ["Poste", "Janvier", "Février", "Mars", "Total Q1"]
data = [
    ["Salaires", 45000, 45000, 46000],
    ["Loyer", 8000, 8000, 8000],
    ["Marketing", 12000, 15000, 10000],
    ["IT / Infrastructure", 6000, 6500, 7000],
    ["Frais généraux", 3000, 3200, 3500],
]

# Headers
for col, h in enumerate(headers, 1):
    c = ws.cell(row=1, column=col, value=h)
    c.fill = hdr_fill
    c.font = hdr_font
    c.alignment = Alignment(horizontal="center")
    c.border = border

# Data
for r, row_data in enumerate(data, 2):
    ws.cell(row=r, column=1, value=row_data[0]).border = border
    for m, val in enumerate(row_data[1:], 2):
        c = ws.cell(row=r, column=m, value=val)
        c.number_format = '#,##0 €'
        c.border = border
    # Total formula
    c = ws.cell(row=r, column=5)
    c.value = f"=SUM(B{r}:D{r})"
    c.number_format = '#,##0 €'
    c.border = border
    c.font = total_font

# Total row
total_row = len(data) + 2
ws.cell(row=total_row, column=1, value="TOTAL").font = total_font
ws.cell(row=total_row, column=1).fill = accent_fill
ws.cell(row=total_row, column=1).border = border
for col in range(2, 6):
    c = ws.cell(row=total_row, column=col)
    c.value = f"=SUM({chr(64+col)}2:{chr(64+col)}{total_row-1})"
    c.number_format = '#,##0 €'
    c.font = total_font
    c.fill = accent_fill
    c.border = border

# Column widths
ws.column_dimensions['A'].width = 22
for col in ['B', 'C', 'D', 'E']:
    ws.column_dimensions[col].width = 15

wb.save("/mnt/data/Budget_Q1_2026.xlsx")
print("OK")
```
**Fichier attendu** : `Budget_Q1_2026.xlsx`

### 5. PNG — Dashboard DataViz (matplotlib)

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OBA = ["#2F5597", "#5B9AD4", "#FB840D", "#FCA810", "#1C244B", "#DAE5EF"]

fig, axes = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle("Dashboard Commercial — T1 2026", fontsize=16, fontweight="bold", color="#1C244B")

# 1. CA mensuel
months = ["Jan", "Fév", "Mar"]
ca = [120, 135, 150]
axes[0,0].bar(months, ca, color=OBA[:3])
axes[0,0].set_title("CA mensuel (k€)", fontweight="bold")
axes[0,0].set_ylabel("k€")
for i, v in enumerate(ca):
    axes[0,0].text(i, v+2, f"{v}k€", ha="center", fontweight="bold")

# 2. Répartition par catégorie
cats = ["Conseil", "Licences", "Support", "Formation"]
vals = [45, 25, 20, 10]
axes[0,1].pie(vals, labels=cats, colors=OBA[:4], autopct="%1.0f%%", startangle=90)
axes[0,1].set_title("Répartition CA", fontweight="bold")

# 3. Top clients
clients = ["Nextera", "CNPP", "Acme", "GlobalTech", "Initech"]
ca_clients = [85, 65, 50, 40, 30]
axes[1,0].barh(clients, ca_clients, color=OBA[1])
axes[1,0].set_title("Top 5 clients (k€)", fontweight="bold")
axes[1,0].invert_yaxis()

# 4. Tendance
x = np.arange(1, 13)
y = 80 + 8*x + np.random.normal(0, 5, 12)
axes[1,1].scatter(x, y, color=OBA[2], s=60, zorder=5)
z = np.polyfit(x, y, 1)
p = np.poly1d(z)
axes[1,1].plot(x, p(x), color=OBA[0], linewidth=2, linestyle="--")
axes[1,1].set_title("Tendance CA mensuel", fontweight="bold")
axes[1,1].set_xlabel("Mois")
axes[1,1].set_ylabel("k€")

for ax in axes.flat:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig("/mnt/data/Dashboard_Commercial_T1_2026.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close()
print("OK")
```
**Fichier attendu** : `Dashboard_Commercial_T1_2026.png`

### 6. PDF — Proposition commerciale (DOCX OBA → PDF)

```python
import subprocess, json, os
os.chdir('/mnt/data')
config = {
    "placeholders": {
        "[TITRE DU DOCUMENT]": "Proposition Commerciale",
        "[Sous-titre du document]": "Projet IA — Nextera Corp",
        "[Auteur]": "Damien Juillard",
        "[Date]": "17/04/2026"
    },
    "sections": [
        {"title": "Contexte", "level": 1, "content": [
            {"type": "text", "text": "Suite à nos échanges du 10 avril 2026 et à l'atelier de cadrage, nous avons le plaisir de vous soumettre notre proposition pour l'accompagnement de Nextera Corp dans l'intégration de l'intelligence artificielle au sein de vos processus RH."}
        ]},
        {"title": "Offre de service", "level": 1, "content": [
            {"type": "text", "text": "Notre accompagnement se décompose en 3 phases :", "bold": true},
            {"type": "table", "headers": ["Phase", "Description", "Durée", "Budget"],
             "rows": [
                ["Phase 1", "POC Tri automatique CV", "6 semaines", "25 000 € HT"],
                ["Phase 2", "Chatbot RH interne", "8 semaines", "35 000 € HT"],
                ["Phase 3", "Analyse prédictive turnover", "10 semaines", "45 000 € HT"]
            ]},
            {"type": "empty"},
            {"type": "text", "text": "Livrables inclus :", "bold": true},
            {"type": "bullets", "items": [
                "Rapport d'étude de faisabilité",
                "Prototype fonctionnel (POC)",
                "Documentation technique et guide utilisateur",
                "Formation des équipes (2 sessions de 2h)",
                "Support post-déploiement (3 mois)"
            ]}
        ]},
        {"title": "Conditions", "level": 1, "content": [
            {"type": "bullets", "items": [
                "Tarif journalier : 1 200 € HT",
                "Paiement : 30% à la commande, 40% à mi-parcours, 30% à la livraison",
                "Validité de l'offre : 30 jours",
                "Délai de démarrage : 2 semaines après signature"
            ]},
            {"type": "empty"},
            {"type": "text", "text": "Cette proposition est soumise à la validation des prérequis techniques (accès aux données RH anonymisées, environnement de développement)."}
        ]}
    ]
}
with open("/tmp/config.json", "w") as f:
    json.dump(config, f, ensure_ascii=False)
subprocess.run(["python3", "/opt/skills/docx/scripts/fill_template.py",
    "/opt/skills/docx/templates/onbehalfai/template-base.docx",
    "Proposition_Commerciale_Nextera.docx", "/tmp/config.json"], check=True)
subprocess.run(["python3", "/opt/skills/docx/scripts/office/soffice.py",
    "--headless", "--convert-to", "pdf", "Proposition_Commerciale_Nextera.docx"], check=True)
print("OK")
```
**Fichiers attendus** : `Proposition_Commerciale_Nextera.docx` + `Proposition_Commerciale_Nextera.pdf`

## PROCÉDURE

Pour chaque fichier ci-dessus :

1. Appeler `POST http://127.0.0.1:8010/exec` avec le code et `lang: "py"` ou `"js"`
2. Récupérer `session_id` et `files[].id` et `files[].name` de la réponse
3. Pour chaque fichier produit : `GET http://127.0.0.1:8010/download/{session_id}/{file_id}` avec header `x-api-key`
4. Sauvegarder dans `/home/damien/LibreCodeInterpreter/test-17-04/{filename}`
5. Vérifier la taille du fichier (> 0 bytes)

Utiliser le header `x-api-key: $CODE_INTERPRETER_KEY (voir .env)` pour tous les appels au code-interpreter.

À la fin, lister tous les fichiers dans `test-17-04/` avec leur taille.

## CRITÈRE DE COMPLÉTION

Quand **tous les 7 fichiers** (2 DOCX + 1 PPTX + 1 XLSX + 1 PNG + 1 DOCX + 1 PDF) sont téléchargés et font plus de 0 bytes :

```
<promise>ALL FILES DOWNLOADED</promise>
```
