#!/usr/bin/env bash
# Desinstal·lació completa. Elimina servei, carpeta del projecte (codi, venv,
# .env, sessions de Telegram), temporals i NOMÉS els paquets apt que va instal·lar
# install.sh. Els paquets que ja hi eren abans no es toquen.
# NO esborra res de JELLYFIN_PATH (els episodis ja descarregats es conserven).
# Ús: uninstall.sh [--yes]
set -uo pipefail

[[ $EUID -eq 0 ]] || { echo "Executa'l com a root." >&2; exit 1; }

# S'executa des d'una còpia a /tmp perquè el script pugui esborrar la seva pròpia carpeta.
if [[ -z "${TGJF_COPY:-}" ]]; then
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TMP="$(mktemp /tmp/tgjf-uninstall.XXXXXX)"
    cp "${BASH_SOURCE[0]}" "$TMP"
    TGJF_COPY=1 TGJF_DIR="$DIR" TGJF_SELF="$TMP" exec bash "$TMP" "$@"
fi
DIR="$TGJF_DIR"
META="$DIR/.install"
SERVICE=/etc/systemd/system/telegram-jellyfin.service

ASSUME_YES=0
[[ "${1:-}" == "--yes" ]] && ASSUME_YES=1

env_get() { [[ -f "$DIR/.env" ]] && grep -E "^$1=" "$DIR/.env" | tail -n1 | cut -d= -f2- | tr -d "\"'" || true; }
BOT_TOKEN="$(env_get BOT_TOKEN)"
ADMIN_ID="$(env_get ADMIN_USER_ID)"
DOWNLOAD_DIR="$(env_get DOWNLOAD_DIR)"; DOWNLOAD_DIR="${DOWNLOAD_DIR:-/tmp/downloads}"

APT_PKGS=()
if [[ -s "$META/apt-installed.txt" ]]; then
    mapfile -t APT_PKGS < "$META/apt-installed.txt"
fi

echo "Es faran aquestes accions:"
echo "  - aturar i eliminar el servei telegram-jellyfin"
echo "  - esborrar $DIR (codi, venv, .env i sessions de Telegram)"
echo "  - netejar els temporals de $DOWNLOAD_DIR"
if ((${#APT_PKGS[@]})); then
    echo "  - eliminar paquets apt instal·lats per aquest projecte: ${APT_PKGS[*]}"
else
    echo "  - cap paquet apt (no n'hi ha de registrats o ja hi eren)"
fi
echo "  - NO es toca JELLYFIN_PATH"

if ((!ASSUME_YES)); then
    read -r -p "Segur? Escriu 'si' per continuar: " ans
    [[ "$ans" == "si" ]] || { echo "Cancel·lat."; rm -f "$TGJF_SELF"; exit 1; }
fi

systemctl disable --now telegram-jellyfin 2>/dev/null || true
rm -f "$SERVICE"
systemctl daemon-reload 2>/dev/null || true

# Temporals: només els directoris de lot (<n>_<n>) i el directori si queda buit.
if [[ -d "$DOWNLOAD_DIR" && "$DOWNLOAD_DIR" != "/" ]]; then
    find "$DOWNLOAD_DIR" -mindepth 1 -maxdepth 1 -type d -regex '.*/[0-9]+_[0-9]+' -exec rm -rf {} + 2>/dev/null
    rmdir "$DOWNLOAD_DIR" 2>/dev/null || true
fi

# Paquets: es simula abans; si la purga arrossegués paquets aliens a la llista, s'omet.
APT_NOTE=""
if ((${#APT_PKGS[@]})); then
    mapfile -t WOULD_REMOVE < <(apt-get -s purge "${APT_PKGS[@]}" 2>/dev/null | awk '/^Remv/{print $2}')
    EXTRA=()
    for p in "${WOULD_REMOVE[@]}"; do
        printf '%s\n' "${APT_PKGS[@]}" | grep -qx "$p" || EXTRA+=("$p")
    done
    if ((${#EXTRA[@]})); then
        APT_NOTE="Paquets apt NO eliminats perquè altres programes en depenen: ${EXTRA[*]}"
        echo "$APT_NOTE"
    else
        DEBIAN_FRONTEND=noninteractive apt-get purge -y "${APT_PKGS[@]}"
    fi
fi

cd /
rm -rf "$DIR"

if [[ -n "$BOT_TOKEN" && -n "$ADMIN_ID" ]] && command -v curl >/dev/null 2>&1; then
    curl -s -m 15 "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${ADMIN_ID}" \
        --data-urlencode "text=🗑 Desinstal·lació completada. ${APT_NOTE}" >/dev/null || true
fi

echo "Desinstal·lació completada."
rm -f "$TGJF_SELF"
