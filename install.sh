#!/usr/bin/env bash
# Instal·la el projecte a la carpeta on és aquest script (Debian/Ubuntu, com a root).
# Només instal·la els paquets apt que NO hi eren i en guarda la llista a
# .install/apt-installed.txt, perquè uninstall.sh sàpiga què pot eliminar.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Executa'l com a root." >&2; exit 1; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
META="$DIR/.install"
SERVICE=/etc/systemd/system/telegram-jellyfin.service
mkdir -p "$META"

installed_pkgs() {
    dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' | awk '$1 ~ /^ii/ {print $2}' | sort -u
}

# Només es fa la foto "abans" la primera vegada, per no perdre el rastre en reinstal·lar.
if [[ ! -f "$META/apt-before.txt" ]]; then
    installed_pkgs > "$META/apt-before.txt"
fi

WANTED=(python3 python3-venv python3-pip p7zip-full)
MISSING=()
for p in "${WANTED[@]}"; do
    dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done

if ((${#MISSING[@]})); then
    echo "Instal·lant paquets que falten: ${MISSING[*]}"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${MISSING[@]}"
else
    echo "Els paquets de sistema ja hi eren; no es toca res."
fi

# unrar és opcional (pot requerir 'non-free'); si no hi és, s'usarà 7z.
if ! command -v unrar >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y unrar 2>/dev/null \
        || echo "unrar no disponible; s'usarà 7z per als .rar."
fi

# Diferència = paquets nous (inclosos els que han entrat com a dependències).
installed_pkgs | comm -13 "$META/apt-before.txt" - > "$META/apt-installed.txt" || true

if [[ ! -d "$DIR/venv" ]]; then
    python3 -m venv "$DIR/venv"
fi
"$DIR/venv/bin/pip" install --upgrade pip
"$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"

if [[ ! -f "$DIR/.env" ]]; then
    cp "$DIR/.env.example" "$DIR/.env"
    echo "Creat $DIR/.env a partir de l'exemple: edita'l abans d'engegar."
fi
chmod 600 "$DIR/.env"

cat > "$SERVICE" <<EOF
[Unit]
Description=Telegram -> Jellyfin downloader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload

cat <<EOF

Instal·lació feta a $DIR.
Següents passos:
  1) nano $DIR/.env
  2) cd $DIR && venv/bin/python main.py     (login interactiu; després Ctrl+C)
  3) systemctl enable --now telegram-jellyfin
Per desinstal·lar-ho tot: $DIR/uninstall.sh   (o /desinstalar al bot)
EOF
