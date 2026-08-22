#!/bin/bash
set -e

BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[rayboard]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo -e "${BOLD}Rayboard Installer${NC}"
echo "─────────────────────────────────────────"

# ── dependency check ─────────────────────────────────────────────────────────
info "Checking dependencies..."

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        die "Missing: $1 — install it and re-run"
    fi
}
check_cmd python3
check_cmd pactl
check_cmd paplay

python3 -c "import PySide6" 2>/dev/null || die "Missing Python package: PySide6 (pip install pyside6)"
python3 -c "import evdev"   2>/dev/null || warn "Optional: python-evdev not found — global hotkeys won't work (pip install evdev)"
python3 -c "import mutagen" 2>/dev/null || warn "Optional: python-mutagen not found — duration display disabled (pip install mutagen)"

success "Dependencies OK"

# ── install files ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/systemd/user"
mkdir -p "$HOME/.config/rayboard"

info "Installing rayboard.py..."
cp "$SCRIPT_DIR/rayboard.py" "$HOME/.local/bin/rayboard.py"
chmod +x "$HOME/.local/bin/rayboard.py"

info "Installing virtual-mic-setup.sh..."
cp "$SCRIPT_DIR/assets/virtual-mic-setup.sh" "$HOME/.local/bin/virtual-mic-setup.sh"
chmod +x "$HOME/.local/bin/virtual-mic-setup.sh"

info "Installing systemd services..."
cp "$SCRIPT_DIR/assets/rayboard.service"    "$HOME/.config/systemd/user/rayboard.service"
cp "$SCRIPT_DIR/assets/virtual-mic.service" "$HOME/.config/systemd/user/virtual-mic.service"

info "Installing desktop entry..."
DESKTOP_DEST="$HOME/.local/share/applications/rayboard.desktop"
cp "$SCRIPT_DIR/assets/rayboard.desktop" "$DESKTOP_DEST"
# Fix %u placeholder to actual username
sed -i "s|/home/%u/|$HOME/|g" "$DESKTOP_DEST"

success "Files installed"

# ── PipeWire setup ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}PipeWire Virtual Audio Setup${NC}"
echo "─────────────────────────────────────────"
echo "Available output sinks:"
pactl list sinks short | awk '{print NR". "$2}' || true
echo ""

DEFAULT_SINK=$(pactl get-default-sink 2>/dev/null || echo "")
read -rp "Output sink to combine with VirtualMic [${DEFAULT_SINK}]: " USER_SINK
REAL_SINK="${USER_SINK:-$DEFAULT_SINK}"

echo ""
echo "Available input sources (mic):"
pactl list sources short | grep -v monitor | awk '{print NR". "$2}' || true
echo ""
read -rp "Mic source to route through VirtualMic (leave blank to skip): " MIC_SOURCE

ENV_FILE="$HOME/.config/rayboard/virtual-mic.env"
{
    echo "RAYBOARD_SINK=${REAL_SINK}"
    [ -n "$MIC_SOURCE" ] && echo "RAYBOARD_MIC=${MIC_SOURCE}"
} > "$ENV_FILE"
success "Written: $ENV_FILE"

# ── input group ───────────────────────────────────────────────────────────────
if ! groups | grep -q '\binput\b'; then
    echo ""
    warn "You're not in the 'input' group — global hotkeys need it."
    read -rp "Add yourself to the input group now? (requires sudo) [Y/n]: " ADD_INPUT
    if [[ "${ADD_INPUT,,}" != "n" ]]; then
        sudo usermod -aG input "$USER"
        warn "Log out and back in for the group change to take effect."
    fi
fi

# ── enable services ───────────────────────────────────────────────────────────
echo ""
info "Enabling systemd services..."
systemctl --user daemon-reload
systemctl --user enable --now virtual-mic.service
systemctl --user enable --now rayboard.service
success "Services started"

# ── icon ──────────────────────────────────────────────────────────────────────
mkdir -p "$HOME/.local/share/icons"
if [ -f "$SCRIPT_DIR/assets/rayboard.png" ]; then
    cp "$SCRIPT_DIR/assets/rayboard.png" "$HOME/.local/share/icons/rayboard.png"
    success "Icon installed"
fi
sed -i "s|%h|$HOME|g" "$DESKTOP_DEST"

echo ""
echo -e "${GREEN}${BOLD}Rayboard installed!${NC}"
echo "Launch it from your app menu or run:  python3 ~/.local/bin/rayboard.py"
