# Templates DOCX

Les templates propriétaires (fichiers `.docx`, logos, filtres Lua) ne sont **pas** stockés dans ce dépôt Git.

Ils sont injectés au runtime via un **volume mount Docker** depuis le serveur hôte :

```
~/data/templates/docx/onbehalfai/ → /opt/skills/docx/templates/onbehalfai/ (read-only)
```

## Pourquoi

Ce dépôt est un fork public. Les templates contiennent l'identité visuelle (logo, mise en page) et le formalisme de l'entreprise, qui ne doivent pas être accessibles publiquement.

## Comment ajouter/modifier un template

1. Modifier le fichier sur le serveur : `~/data/templates/docx/onbehalfai/`
2. Redémarrer le container pour prise en compte (si nécessaire) :
   ```bash
   cd ~/LibreChat && docker compose -f deploy-compose.yml -f deploy-compose.override.yml up -d code-interpreter-api
   ```
3. Aucun commit Git nécessaire.

## Ref

EXI-DLP (PSSI §5.17, SOS §16)
