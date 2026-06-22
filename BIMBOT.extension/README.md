# BIMBOT pyRevit Extension

Acest folder este o extensie pyRevit validă. Pentru a fi vizibilă în managerul `EXTENSIONS` din pyRevit, trebuie:

1. Să fie publicată pe GitHub într-un repository accesibil colegilor.
2. Să adaugi în repo un `extensions.json` central dacă folosești un index de extensii pyRevit.
3. Să fie instalată de colegi prin pyRevit Extensions Manager sau copiată în folderul lor `pyRevit\extensions\`.

---

## Conținutul extensiei

- `BIMBOT.tab` — tab-ul pyRevit care conține unelte IFC și DWG.
- `extension.json` — manifestul extensiei pyRevit.

## Pas rapid

Dacă nu folosești un index central, colegii pot instala local copiaând `BIMBOT.extension` în:

- `%APPDATA%\pyRevit-Master\extensions\`

