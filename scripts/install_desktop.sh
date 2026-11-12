#!/usr/bin/env bash
# Instala un lanzador de Sonora en el menú de aplicaciones de Linux.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$APPS_DIR/sonora.desktop"

mkdir -p "$APPS_DIR"
chmod +x "$DIR/run.sh"

cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Sonora
GenericName=Conversor de música y vídeo
Comment=Convierte enlaces de YouTube y otros sitios a MP3 o MP4
Exec=$DIR/run.sh
Path=$DIR
Icon=$DIR/assets/icon.svg
Terminal=false
Categories=AudioVideo;Audio;Video;
Keywords=mp3;mp4;youtube;audio;video;conversor;descargar;
StartupWMClass=Sonora
EOF

chmod +x "$ENTRY"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "· Lanzador instalado en: $ENTRY"
echo "· Ya puedes abrir Sonora desde el menú de aplicaciones."
