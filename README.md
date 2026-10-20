# Telegram → Jellyfin

Eina en Python per cercar fitxers d'episodis a l'historial d'un xat o canal de
Telegram, descarregar-los amb un compte d'usuari de Telegram (Telethon),
descomprimir arxius i organitzar vídeos i subtítols perquè Jellyfin els pugui
identificar.

El bot de Telegram s'utilitza per rebre les ordres i mostrar el menú interactiu.
La cerca i les descàrregues les fa el compte d'usuari, no el bot, de manera que
es poden gestionar fitxers grans sempre que Telegram i el compte tinguin accés
al contingut.

> Utilitza l'eina només amb contingut al qual tens dret d'accés i de descàrrega.
> Protegeix especialment les credencials i els fitxers de sessió de Telethon.

## Contingut

- [Requisits](#requisits)
- [Preparar Telegram](#preparar-telegram)
- [Instal·lació automàtica (recomanada)](#instal·lació-automàtica-recomanada)
- [Desinstal·lació completa](#desinstal·lació-completa)
- [Instal·lació manual en Debian o Ubuntu LXC](#instal·lació-manual-en-debian-o-ubuntu-lxc)
- [Configuració de `.env`](#configuració-de-env)
- [Primera autenticació i arrencada](#primera-autenticació-i-arrencada)
- [Manual d'ús](#manual-dús)
- [Organització dels fitxers](#organització-dels-fitxers)
- [Servei systemd](#servei-systemd)
- [Permisos i muntatges de Proxmox](#permisos-i-muntatges-de-proxmox)
- [Registre i resolució de problemes](#registre-i-resolució-de-problemes)
- [Limitacions conegudes](#limitacions-conegudes)

## Requisits

- Debian o Ubuntu en un contenidor LXC amb accés a Internet.
- Python 3.10 o posterior, `venv` i `pip`.
- Un compte de Telegram que pugui llegir el xat/canal d'origen i descarregar-ne
  els fitxers.
- Un bot de Telegram per a les ordres i els botons.
- Espai temporal suficient per descarregar i descomprimir els fitxers.
- Un directori de sèries de Jellyfin accessible des del contenidor. La
  integració amb l'API de Jellyfin és opcional.
- `7z` per als arxius `.zip`, `.7z` i `.rar`; `unrar` es fa servir primer per
  als `.rar` si està instal·lat.

### Dependències del sistema

En Debian/Ubuntu:

```bash
apt update
apt install -y python3 python3-venv python3-pip p7zip-full
```

Si el repositori de la distribució ofereix `unrar`, també es pot instal·lar:

```bash
apt install -y unrar
```

El paquet `unrar` pot requerir activar el repositori `non-free` de Debian.
Sense `unrar`, el programa prova d'extreure els `.rar` amb `7z`.

Les dependències Python són a [`requirements.txt`](./requirements.txt):

```text
telethon
cryptg
aiohttp
python-dotenv
```

## Preparar Telegram

### 1. Obtenir les credencials de l'API

1. Inicia sessió a [my.telegram.org](https://my.telegram.org/).
2. Ves a **API development tools** i crea una aplicació.
3. Desa l'`api_id` i l'`api_hash`. Són les variables `API_ID` i `API_HASH`.

### 2. Crear el bot

1. A Telegram, obre [@BotFather](https://t.me/BotFather).
2. Crea un bot amb `/newbot` i desa el token com a `BOT_TOKEN`.
3. Inicia una conversa privada amb el bot i envia-li `/start` almenys una
   vegada. Telegram no permet que el bot t'escrigui abans que l'usuari l'hagi
   iniciat.
4. Obté el teu identificador numèric de Telegram i posa'l a `ADMIN_USER_ID`.
   Pots consultar-lo amb un bot d'informació d'usuari de confiança.

El programa només admet les ordres i els callbacks de l'identificador definit a
`ADMIN_USER_ID`. No comparteixis el token ni l'identificador de sessió.

### 3. Donar accés al compte d'usuari

El compte de Telegram que autenticarà Telethon ha de pertànyer al canal o xat
privat obert o tenir-hi accés. Un canal privat al qual aquest compte no s'hagi
unit no es podrà cercar, encara que el bot hi sigui membre. Per als canals
públics, es pot fer servir l'username públic o l'identificador numèric.

## Instal·lació automàtica (recomanada)

Copia el projecte al CT (per exemple a `/opt/telegram-jellyfin`) i, com a root:

```bash
cd /opt/telegram-jellyfin
chmod +x install.sh uninstall.sh
./install.sh
```

[`install.sh`](./install.sh):

- fa una foto dels paquets apt instal·lats **abans** de tocar res;
- instal·la només els que falten (`python3`, `python3-venv`, `python3-pip`,
  `p7zip-full` i, si és possible, `unrar`). Els que ja hi eren no es toquen;
- guarda a `.install/apt-installed.txt` els paquets nous, dependències
  incloses;
- crea l'entorn virtual, instal·la `requirements.txt`, prepara `.env` i genera
  el servei systemd amb les rutes correctes.

Després segueix els passos que mostra (editar `.env`, login interactiu amb
`venv/bin/python main.py` i `systemctl enable --now telegram-jellyfin`).

## Desinstal·lació completa

Per esborrar-ho tot hi ha dues vies:

- des del terminal del CT: `/opt/telegram-jellyfin/uninstall.sh` (demana
  confirmació; amb `--yes` no pregunta);
- des de Telegram: `/desinstalar` al bot i **Sí, esborra-ho tot**.

Què fa:

1. Atura, desactiva i elimina el servei systemd.
2. Tanca la sessió d'usuari de Telegram (només des del bot) i esborra la
   carpeta del projecte: codi, `venv`, `.env` i sessions.
3. Neteja els temporals de `DOWNLOAD_DIR` (només els directoris de lot).
4. Elimina **només** els paquets apt de `.install/apt-installed.txt`. Si
   alguna altra cosa del sistema en depèn, aquests paquets s'ometen i
   s'avisa. Si no hi ha registre (instal·lació manual), no es toca cap
   paquet.
5. El script s'executa des d'una còpia a `/tmp` per poder esborrar-se a si
   mateix i, si pot, t'envia un missatge final per Telegram.

**No** s'esborra res de `JELLYFIN_PATH`: els episodis ja descarregats es
conserven. Per treure l'accés del compte també pots revocar la sessió a
Telegram → Configuració → Dispositius.

## Instal·lació manual en Debian o Ubuntu LXC

Exemple d'instal·lació a `/opt/telegram-jellyfin`:

```bash
mkdir -p /opt/telegram-jellyfin
```

Copia-hi els fitxers del projecte:

```text
config.py
fileops.py
main.py
parsing.py
requirements.txt
telegram-jellyfin.service
.env.example
```

Després crea l'entorn virtual i instal·la les dependències:

```bash
cd /opt/telegram-jellyfin
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

Crea la configuració local i edita-la:

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Omple les variables de `.env` segons la secció següent. No afegeixis aquest
fitxer ni els fitxers de sessió a cap repositori públic o còpia no protegida.

## Configuració de `.env`

Exemple:

```dotenv
API_ID=123456
API_HASH=posa_aqui_el_teu_api_hash
BOT_TOKEN=123456789:posa_aqui_el_token_del_bot
ADMIN_USER_ID=123456789

# Directori arrel de sèries que Jellyfin té muntat com a biblioteca.
JELLYFIN_PATH=/media/jellyfin/series

# Opcional: URL base del servidor Jellyfin, sense barra final.
JELLYFIN_URL=http://192.168.1.50:8096

# Opcional: clau d'API Jellyfin amb permisos per refrescar la biblioteca.
JELLYFIN_API_KEY=posa_aqui_la_clau_api

# Directoris opcionals; valors per defecte mostrats.
DOWNLOAD_DIR=/tmp/downloads
SESSION_DIR=/opt/telegram-jellyfin/sessions
```

| Variable | Obligatòria | Descripció |
| --- | --- | --- |
| `API_ID` | Sí | Identificador numèric de l'aplicació Telegram. |
| `API_HASH` | Sí | Hash de l'aplicació Telegram. |
| `BOT_TOKEN` | Sí | Token creat amb BotFather. |
| `ADMIN_USER_ID` | Sí | ID numèric de l'administrador autoritzat. |
| `JELLYFIN_PATH` | No | Directori arrel de les sèries. Per defecte, `/media/jellyfin/series`. |
| `JELLYFIN_URL` | No | URL base de Jellyfin. Si està buida, no es fa la crida de refresc. |
| `JELLYFIN_API_KEY` | No | Clau d'API de Jellyfin. Si està buida, no es fa la crida de refresc. |
| `DOWNLOAD_DIR` | No | Directori temporal de descàrrega. Per defecte, `/tmp/downloads`. |
| `SESSION_DIR` | No | Directori de sessions Telethon. Per defecte, `./sessions`. |

Per crear una clau d'API a Jellyfin, obre el Dashboard d'administració i ves a
**Advanced → API Keys** (el nom exacte pot variar segons la versió). La crida
que fa l'eina és `POST /Library/Refresh` amb la capçalera `X-Emby-Token`.

El directori `JELLYFIN_PATH` ha de ser el directori que conté les carpetes de
sèries, no la carpeta d'una sèrie concreta. Per exemple:

```text
/media/jellyfin/series/
├── Dr Slump/
└── Una altra sèrie/
```

## Primera autenticació i arrencada

Abans d'engegar el servei systemd, cal crear la sessió del compte d'usuari amb
una execució interactiva. Inicia el bot amb `/start` prèviament, tal com s'ha
indicat a [Preparar Telegram](#preparar-telegram), i executa:

```bash
cd /opt/telegram-jellyfin
venv/bin/python main.py
```

La primera vegada, Telethon demanarà al terminal:

1. El número de telèfon del compte d'usuari, amb prefix internacional.
2. El codi d'inici de sessió que Telegram envia.
3. La contrasenya, si el compte té verificació en dos passos.

Quan el programa indiqui que està llest i el bot t'hagi escrit, atura'l amb
`Ctrl+C`. Es crearà un fitxer de sessió dins de `SESSION_DIR`. Aquest fitxer
dona accés al compte: limita'n els permisos i no l'esborris mentre el servei
estigui en ús. Després ja es pot iniciar amb systemd.

Si s'executa com un usuari Linux diferent, aquest usuari també ha de ser el
propietari o tenir permisos d'escriptura al directori de sessió, al directori
temporal i al directori de Jellyfin.

## Manual d'ús

### Comanda de cerca

Al xat privat del bot, envia:

```text
/buscar <ID_o_username_del_xat> <rang> [paraula clau]
```

Exemples:

```text
/buscar -100123456789 01x01-03x15 Dr Slump
/buscar @canal_public 01x01-01x12
```

El rang és inclusiu i té el format `TTxEE-TTxEE`: temporada i episodi
d'inici, guionet i temporada i episodi de final. Per exemple,
`01x01-03x15`. La cerca recorre l'historial accessible del xat i busca els
números d'episodi al nom del fitxer o al text del missatge.

Formats de número que es poden detectar, entre d'altres:

```text
1x05
01x05
S01E05
S1 E05
T1 E05
T01E05
```

La paraula clau opcional és una coincidència de text sense distingir
majúscules/minúscules al nom del fitxer o al peu de foto. Si s'escriu, també
s'utilitza com a nom inicial de la sèrie al menú; es pot canviar des del menú.
Per cercar sense paraula clau, no afegeixis aquest argument.

### Selecció i confirmació

Quan s'han trobat episodis, el bot mostra el nombre d'elements, la mida total
aproximada, el rang trobat i un menú:

1. **Selecciona una carpeta existent** amb els botons de nom. Es mostren fins
   a 30 carpetes de `JELLYFIN_PATH`.
2. Prem **Nova sèrie** per escriure un nom nou al xat del bot. Després
   d'enviar el nom, el missatge amb la vista prèvia tornarà a aparèixer.
3. Ajusta **Temp − / Temp +** o **Ep − / Ep +** per afegir o restar offsets a
   la temporada o a l'episodi.
4. Comprova la vista prèvia de la ruta del primer episodi. El format final és:

   ```text
   <JELLYFIN_PATH>/<Sèrie>/Season XX/<Sèrie> - SXXEXX.ext
   ```

5. Prem **Confirmar i Processar** per iniciar el lot o **Cancel·lar** per
   descartar-lo.

El lot es posa en cua i només se'n descarrega un alhora. Durant la descàrrega
el bot mostra l'episodi actual i, periòdicament, el progrés en MB. Telegram pot
imposar una espera temporal (`FloodWait`); el programa espera el temps indicat
i continua. Al final envia un resum dels fitxers processats i indica si s'ha
sol·licitat el refresc de Jellyfin.

## Organització dels fitxers

Per a una sèrie anomenada `Dr Slump`, un episodi `01x05` en format `.mkv` es
desa així:

```text
/media/jellyfin/series/Dr Slump/Season 01/Dr Slump - S01E05.mkv
```

Extensions de vídeo admeses: `.mkv`, `.mp4` i `.avi`. Arxius comprimits
admesos: `.rar`, `.zip` i `.7z`. Es cerquen també subtítols `.srt`, `.ass`,
`.ssa`, `.sub` i `.vtt`.

Els arxius es descarreguen a un subdirectori de `DOWNLOAD_DIR`, s'extreuen
allà i després se'n mouen els vídeos i subtítols detectats. Després d'una
extracció correcta, l'arxiu comprimit s'esborra. En cas d'error, es registra
l'episodi com a fallit i s'esborra el directori temporal del lot. Els subtítols
amb numeració coincident es mouen amb el vídeo; si el destí del subtítol ja
existeix, se'n conserva una còpia amb un sufix numèric. Si ja existeix un
fitxer de vídeo amb el mateix nom final, se substitueix.

## Servei systemd

El fitxer [`telegram-jellyfin.service`](./telegram-jellyfin.service) assumeix
que el projecte està a `/opt/telegram-jellyfin`, que l'entorn virtual és
`/opt/telegram-jellyfin/venv` i que `.env` és a `/opt/telegram-jellyfin/.env`.
Instal·la i activa el servei després d'haver creat la sessió:

```bash
cp /opt/telegram-jellyfin/telegram-jellyfin.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now telegram-jellyfin
```

Ordres d'administració:

```bash
systemctl status telegram-jellyfin
systemctl restart telegram-jellyfin
systemctl stop telegram-jellyfin
journalctl -u telegram-jellyfin -f
```

Per executar el servei com a usuari Linux no privilegiat, afegeix al bloc
`[Service]` de la unitat, per exemple:

```ini
User=telegram-jellyfin
Group=media
```

Assegura't que aquest usuari pot llegir i escriure a `JELLYFIN_PATH`, a
`DOWNLOAD_DIR` i a `SESSION_DIR`. Després de modificar la unitat, executa
`systemctl daemon-reload` i reinicia el servei.

## Permisos i muntatges de Proxmox

Si els fitxers de Jellyfin són en un directori del host muntat dins del LXC,
configura el mount point de Proxmox perquè apunti a la carpeta correcta i
comprova els permisos des de dins del contenidor. El procés del servei ha de
poder:

- crear carpetes de sèrie i temporada;
- moure o substituir fitxers de vídeo;
- escriure i esborrar els fitxers temporals;
- llegir la sessió de Telethon.

Un muntatge de només lectura no permetrà organitzar els fitxers. En LXC no
privilegiats, els UID/GID del host poden estar mapejats; ajusta els permisos o
grups al host i al contenidor segons el teu muntatge, sense fer el directori
accessible a tothom.

Preveu espai lliure suficient a `DOWNLOAD_DIR`: durant l'extracció pot haver-hi
alhora l'arxiu comprimit i el contingut extret. Per defecte, `/tmp` pot ser
petit o estar en memòria; si cal, configura `DOWNLOAD_DIR` en un volum amb més
espai.

## Registre i resolució de problemes

Consulta el registre del servei:

```bash
journalctl -u telegram-jellyfin -n 100 --no-pager
journalctl -u telegram-jellyfin -f
```

Problemes habituals:

- **El bot no respon:** comprova `BOT_TOKEN`, `ADMIN_USER_ID` i que estiguis
  parlant amb el bot correcte. El bot només accepta el compte administrador
  configurat.
- **El bot no pot iniciar la conversa:** envia `/start` al bot manualment
  abans d'engegar el servei.
- **No es pot accedir al xat:** assegura't que el compte d'usuari de Telethon
  n'és membre o hi té accés, i comprova l'ID o username. Els IDs de canals
  solen tenir el prefix `-100`.
- **Es demana un codi cada vegada o es rebutja la sessió:** atura el servei,
  comprova que `SESSION_DIR` sigui persistent i accessible pel mateix usuari,
  i torna a autenticar el compte executant `main.py` en un terminal.
- **No es troben episodis:** comprova el rang i que el número d'episodi aparegui
  al nom del fitxer o al text del missatge en un format reconegut. Revisa també
  les extensions admeses i la paraula clau.
- **Error en extreure un arxiu:** comprova que `7z` o `unrar` estigui
  instal·lat, que l'arxiu no estigui malmès o protegit amb contrasenya i que
  hi hagi espai disponible.
- **Error en moure els fitxers:** comprova permisos, muntatges i espai al
  directori `JELLYFIN_PATH`.
- **Jellyfin no refresca:** comprova `JELLYFIN_URL`, la clau d'API, la
  connectivitat des del contenidor i el registre del servei.

## Limitacions conegudes

- La cerca recorre l'historial accessible complet; en canals amb molt
  contingut pot trigar. No s'ha configurat un límit d'historial.
- Per entrar al resultat, el missatge ha de tenir un fitxer amb una de les
  extensions admeses i un número d'episodi detectable que caigui dins del rang.
- Si hi ha més d'un fitxer detectat per al mateix episodi, es conserva el
  primer que retorna Telegram (normalment el més recent).
- Si una descàrrega té un sol vídeo, se li assigna l'episodi del missatge. Si
  un arxiu conté diversos vídeos, cada vídeo necessita un número detectable
  al seu propi nom.
- El menú mostra com a màxim 30 carpetes de sèrie existents.
- Els menús i lots pendents es guarden en memòria. Si es reinicia el procés,
  els menús antics deixen de funcionar; torna a executar la cerca.
- La resposta de refresc de Jellyfin és opcional. Si no s'ha configurat la
  URL o la clau, el lot es processa igualment però no s'envia cap petició.
