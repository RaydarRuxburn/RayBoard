# Rayboard

A native Linux soundboard with PipeWire virtual audio support. Built as a replacement for Soundpad/Resanance on Wayland.

![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- Dark-themed UI with drag & drop support for MP3, WAV, OGG, FLAC, M4A
- Global hotkeys via evdev (works on Wayland, no grab required)
- PipeWire output device selector — play to any sink
- Combine sink (`SoundpadOut`) routes audio to both speakers and a virtual mic simultaneously, so friends in voice chat hear your sounds
- Persists sounds, hotkeys, and device selection across sessions

## Requirements

- Python 3.10+
- PipeWire
- `python-pyside6`
- `python-evdev` (optional — for global hotkeys)
- `python-mutagen` (optional — for duration display)

**Arch / CachyOS:**
```bash
sudo pacman -S python-pyside6 python-evdev python-mutagen
```

**Debian / Ubuntu:**
```bash
sudo apt install python3-pyside6 python3-evdev python3-mutagen
```

## Install

```bash
git clone https://github.com/YOUR_USERNAME/rayboard.git
cd rayboard
bash install.sh
```

The installer will:
1. Copy files to `~/.local/bin/`
2. Ask which PipeWire sink to use as your real speakers
3. Optionally route your mic through the virtual mic
4. Install and start systemd user services
5. Add a desktop entry to your app launcher

## PipeWire virtual audio

The installer creates three PipeWire devices:

| Device | Type | Purpose |
|--------|------|---------|
| `VirtualMic` | Null sink | Internal bus |
| `VirtualMicSource` | Virtual source | Set this as your mic in Discord/TS |
| `SoundpadOut` | Combine sink | Play sounds here — goes to speakers + virtual mic |

In Rayboard, set **Out** to `SoundpadOut`. In Discord/TeamSpeak/OBS, set your mic input to `VirtualMicSource`.

## Usage

- **Drag & drop** audio files onto the window to add them
- **Double-click** or press ▶ to play
- **Right-click** a sound to set a hotkey (e.g. `KEY_F13`, `KEY_KP0`)
- **Out / In** dropdowns in the toolbar to change audio devices
- **↻** to refresh the device list after plugging in audio hardware

### Hotkey names

Use standard Linux key names: `KEY_F13`–`KEY_F24`, `KEY_KP0`–`KEY_KP9`, `KEY_PAUSE`, etc.  
Full list: `python3 -c "from evdev import ecodes; print([k for k in dir(ecodes) if k.startswith('KEY_')])"`

## Config files

| File | Purpose |
|------|---------|
| `~/.config/rayboard/sounds.json` | Sound list |
| `~/.config/rayboard/hotkeys.conf` | Hotkey bindings |
| `~/.config/rayboard/config.json` | Device selection |
| `~/.config/rayboard/virtual-mic.env` | PipeWire sink/mic env vars |

## License

MIT
