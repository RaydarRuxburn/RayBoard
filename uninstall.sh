#!/bin/bash
set -e

BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "\033[0;36m[rayboard]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }

echo -e "${BOLD}Rayboard Uninstaller${NC}"
echo "─────────────────────────────────────────"

# ── stop & disable services ───────────────────────────────────────────────────
info "Stopping services..."
systemctl --user stop  rayboard.service    2>/dev/null || true
systemctl --user stop  virtual-mic.service 2>/dev/null || true
systemctl --user disable rayboard.service    2>/dev/null || true
systemctl --user disable virtual-mic.service 2>/dev/null || true
success "Services stopped"

# ── remove files ──────────────────────────────────────────────────────────────
info "Removing files..."
rm -f "$HOME/.local/bin/rayboard.py"
rm -f "$HOME/.local/bin/rayboard2.py"
rm -f "$HOME/.local/bin/virtual-mic-setup.sh"
rm -f "$HOME/.local/share/applications/rayboard.desktop"
rm -f "$HOME/.local/share/icons/rayboard.png"
rm -f "$HOME/.config/systemd/user/rayboard.service"
rm -f "$HOME/.config/systemd/user/virtual-mic.service"
rm -f "$HOME/.config/pipewire/pipewire.conf.d/99-input-denoising.conf"
systemctl --user daemon-reload
systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
success "Files removed"

# ── optionally remove config & sounds ─────────────────────────────────────────
echo ""
if [ -d "$HOME/.config/rayboard" ]; then
    read -rp "Delete saved sounds and config? (~/.config/rayboard) [y/N]: " DEL_CFG
    if [[ "${DEL_CFG,,}" == "y" ]]; then
        rm -rf "$HOME/.config/rayboard"
        success "Config deleted"
    else
        info "Config kept at ~/.config/rayboard"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}Rayboard uninstalled.${NC}"
