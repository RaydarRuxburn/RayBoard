#!/usr/bin/env python3
"""Rayboard — Native Linux Soundboard"""

import sys
import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QToolBar, QSlider, QLabel,
    QHeaderView, QAbstractItemView, QSizePolicy, QStatusBar,
    QMenu, QDialog, QDialogButtonBox, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QUrl, Signal, QObject, QThread, QSize
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QKeySequence

try:
    from evdev import InputDevice, ecodes, list_devices
    EVDEV = True
except ImportError:
    EVDEV = False

try:
    from mutagen import File as MutagenFile
    MUTAGEN = True
except ImportError:
    MUTAGEN = False

CONFIG_DIR = Path.home() / ".config" / "rayboard"
SOUNDS_FILE = CONFIG_DIR / "sounds.json"
HOTKEYS_FILE = CONFIG_DIR / "hotkeys.conf"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_SINK = "SoundpadOut"

STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #ffffff;
    font-family: 'Noto Sans', sans-serif;
    font-size: 13px;
}
QTableWidget {
    background-color: #252525;
    alternate-background-color: #2b2b2b;
    border: none;
    gridline-color: #2e2e2e;
    outline: none;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #c0392b;
    color: #ffffff;
}
QTableWidget::item:hover {
    background-color: #3a3a3a;
}
QHeaderView::section {
    background-color: #1a1a1a;
    color: #888888;
    border: none;
    border-right: 1px solid #2e2e2e;
    border-bottom: 1px solid #2e2e2e;
    padding: 5px 8px;
    font-size: 12px;
}
QToolBar {
    background-color: #181818;
    border: none;
    border-bottom: 1px solid #2e2e2e;
    padding: 4px;
    spacing: 6px;
}
QToolBar QToolButton {
    background-color: transparent;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 16px;
}
QToolBar QToolButton:hover {
    background-color: #3a3a3a;
}
QToolBar QToolButton:pressed {
    background-color: #c0392b;
}
QSlider::groove:horizontal {
    height: 3px;
    background: #444444;
    border-radius: 2px;
    margin: 0 4px;
}
QSlider::handle:horizontal {
    background: #c0392b;
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -5px 0;
}
QSlider::sub-page:horizontal {
    background: #c0392b;
    border-radius: 2px;
}
QStatusBar {
    background-color: #181818;
    color: #666666;
    border-top: 1px solid #2e2e2e;
    font-size: 12px;
    padding: 2px 8px;
}
QScrollBar:vertical {
    background: #1e1e1e;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #444444;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QMenu {
    background-color: #252525;
    border: 1px solid #3a3a3a;
    color: #ffffff;
}
QMenu::item:selected {
    background-color: #c0392b;
}
QDialog {
    background-color: #252525;
}
QDialogButtonBox QPushButton {
    background-color: #3a3a3a;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
    min-width: 60px;
}
QDialogButtonBox QPushButton:hover {
    background-color: #c0392b;
}
QComboBox {
    background-color: #2b2b2b;
    color: #ffffff;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 3px 8px;
    min-width: 160px;
    font-size: 12px;
}
QComboBox:hover {
    border-color: #666666;
}
QComboBox:focus {
    border-color: #c0392b;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #888888;
}
QComboBox QAbstractItemView {
    background-color: #252525;
    color: #ffffff;
    border: 1px solid #444444;
    selection-background-color: #c0392b;
    outline: none;
}
"""


def get_pw_devices(kind="sinks"):
    """Return list of (name, description) for PipeWire sinks or sources."""
    try:
        out = subprocess.check_output(
            ['pactl', 'list', kind], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return []
    devices = []
    name = desc = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('Name:'):
            name = line.split(':', 1)[1].strip()
            desc = None
        elif line.startswith('Description:') and name and desc is None:
            desc = line.split(':', 1)[1].strip()
            devices.append((name, desc or name))
            name = desc = None
    return devices


def get_duration(path):
    if not MUTAGEN:
        return ""
    try:
        f = MutagenFile(path)
        if f and hasattr(f.info, 'length'):
            secs = int(f.info.length)
            return f"{secs // 60}:{secs % 60:02d}"
    except Exception:
        pass
    return ""


def load_sounds():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if SOUNDS_FILE.exists():
        try:
            return json.loads(SOUNDS_FILE.read_text())
        except Exception:
            pass
    return []


def save_sounds(sounds):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_FILE.write_text(json.dumps(sounds, indent=2))


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def load_hotkeys():
    hotkeys = {}
    if not HOTKEYS_FILE.exists():
        return hotkeys
    with open(HOTKEYS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                hotkeys[parts[0]] = parts[1].strip()
    return {v: k for k, v in hotkeys.items()}


def save_hotkeys(path_to_key: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Rayboard hotkeys\n# Format: KEY_NAME /path/to/sound\n"]
    for path, key in path_to_key.items():
        lines.append(f"{key} {path}")
    HOTKEYS_FILE.write_text("\n".join(lines) + "\n")


class HotkeyWorker(QObject):
    triggered = Signal(str)

    def __init__(self, hotkeys_by_code):
        super().__init__()
        self.hotkeys_by_code = hotkeys_by_code
        self._running = True

    def run(self):
        if not EVDEV:
            return
        kbd_paths = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                    kbd_paths.append(path)
            except Exception:
                pass
        for path in kbd_paths:
            threading.Thread(target=self._monitor, args=(path,), daemon=True).start()

    def _monitor(self, dev_path):
        try:
            dev = InputDevice(dev_path)
            for event in dev.read_loop():
                if not self._running:
                    break
                if event.type == ecodes.EV_KEY and event.value == 1:
                    if event.code in self.hotkeys_by_code:
                        self.triggered.emit(self.hotkeys_by_code[event.code])
        except Exception:
            pass

    def stop(self):
        self._running = False


class RayboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rayboard")
        self.setMinimumSize(600, 400)
        self.resize(780, 500)
        self.setAcceptDrops(True)

        self.sounds = load_sounds()
        self.path_to_key = load_hotkeys()
        self.cfg = load_config()
        self.current_proc = None
        self.current_row = -1
        self.volume = 100
        self.output_sink = self.cfg.get("output_sink", DEFAULT_SINK)

        self._build_ui()
        self._populate_table()
        self._start_hotkey_worker()

    def _build_ui(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        self.btn_play = QAction("▶", self)
        self.btn_play.setToolTip("Play selected")
        self.btn_play.triggered.connect(self._play_selected)
        toolbar.addAction(self.btn_play)

        self.btn_stop = QAction("■", self)
        self.btn_stop.setToolTip("Stop")
        self.btn_stop.triggered.connect(self._stop)
        toolbar.addAction(self.btn_stop)

        toolbar.addSeparator()

        vol_label = QLabel("🔊")
        vol_label.setStyleSheet("color: #888888; padding: 0 4px;")
        toolbar.addWidget(vol_label)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setToolTip("Volume")
        self.vol_slider.valueChanged.connect(lambda v: setattr(self, 'volume', v))
        toolbar.addWidget(self.vol_slider)

        toolbar.addSeparator()

        out_label = QLabel("Out:")
        out_label.setStyleSheet("color: #888888; padding: 0 4px; font-size: 12px;")
        toolbar.addWidget(out_label)

        self.sink_combo = QComboBox()
        self.sink_combo.setToolTip("Output device — where sounds play")
        toolbar.addWidget(self.sink_combo)

        toolbar.addSeparator()

        in_label = QLabel("In:")
        in_label.setStyleSheet("color: #888888; padding: 0 4px; font-size: 12px;")
        toolbar.addWidget(in_label)

        self.source_combo = QComboBox()
        self.source_combo.setToolTip("Input device (mic / source)")
        toolbar.addWidget(self.source_combo)

        refresh_action = QAction("↻", self)
        refresh_action.setToolTip("Refresh device list")
        refresh_action.triggered.connect(self._refresh_devices)
        toolbar.addAction(refresh_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        drop_hint = QLabel("Drop MP3/WAV files here")
        drop_hint.setStyleSheet("color: #555555; padding: 0 12px; font-size: 12px;")
        toolbar.addWidget(drop_hint)

        self._refresh_devices()
        self.sink_combo.currentIndexChanged.connect(self._on_sink_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Name", "Duration", "Hotkey"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda: self._play_selected())

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 90)
        self.table.verticalHeader().setDefaultSectionSize(28)

        self.setCentralWidget(self.table)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _refresh_devices(self):
        sinks = get_pw_devices("sinks")
        sources = get_pw_devices("sources")

        saved_sink = self.cfg.get("output_sink", DEFAULT_SINK)
        saved_source = self.cfg.get("input_source", "")

        self.sink_combo.blockSignals(True)
        self.sink_combo.clear()
        sink_idx = 0
        for i, (name, desc) in enumerate(sinks):
            self.sink_combo.addItem(desc, name)
            if name == saved_sink:
                sink_idx = i
        if sinks:
            self.sink_combo.setCurrentIndex(sink_idx)
            self.output_sink = self.sink_combo.currentData() or DEFAULT_SINK
        self.sink_combo.blockSignals(False)

        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        src_idx = 0
        for i, (name, desc) in enumerate(sources):
            self.source_combo.addItem(desc, name)
            if name == saved_source:
                src_idx = i
        if sources:
            self.source_combo.setCurrentIndex(src_idx)
        self.source_combo.blockSignals(False)

        count_msg = f"Devices refreshed — {len(sinks)} outputs, {len(sources)} inputs"
        if hasattr(self, 'status'):
            self.status.showMessage(count_msg, 3000)

    def _on_sink_changed(self, idx):
        name = self.sink_combo.itemData(idx)
        if name:
            self.output_sink = name
            self.cfg["output_sink"] = name
            save_config(self.cfg)

    def _on_source_changed(self, idx):
        name = self.source_combo.itemData(idx)
        if name:
            self.cfg["input_source"] = name
            save_config(self.cfg)

    def _populate_table(self):
        self.table.setRowCount(0)
        for i, sound in enumerate(self.sounds):
            self._add_table_row(i, sound)

    def _add_table_row(self, i, sound):
        self.table.insertRow(i)
        path = sound.get("path", "")
        name = sound.get("name", Path(path).stem)
        duration = sound.get("duration", "")
        hotkey = self.path_to_key.get(path, "")

        num = QTableWidgetItem(str(i + 1))
        num.setTextAlignment(Qt.AlignCenter)
        num.setForeground(QColor("#666666"))

        name_item = QTableWidgetItem(name)

        dur_item = QTableWidgetItem(duration)
        dur_item.setTextAlignment(Qt.AlignCenter)
        dur_item.setForeground(QColor("#888888"))

        key_item = QTableWidgetItem(hotkey)
        key_item.setTextAlignment(Qt.AlignCenter)
        key_item.setForeground(QColor("#c0392b"))

        self.table.setItem(i, 0, num)
        self.table.setItem(i, 1, name_item)
        self.table.setItem(i, 2, dur_item)
        self.table.setItem(i, 3, key_item)
        self.table.item(i, 1).setData(Qt.UserRole, path)

    def _play_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        path = self.table.item(row, 1).data(Qt.UserRole)
        self._play(path, row)

    def _play(self, path, row=-1):
        self._stop()
        vol = int(self.volume / 100 * 65536)
        self.current_proc = subprocess.Popen(
            ['paplay', f'--volume={vol}', f'--device={self.output_sink}', path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.current_row = row
        name = Path(path).stem
        self.status.showMessage(f"▶  {name}")

        def watch():
            if self.current_proc:
                self.current_proc.wait()
            if self.current_row == row:
                self.status.showMessage("Ready")
                self.current_row = -1

        threading.Thread(target=watch, daemon=True).start()

    def _stop(self):
        if self.current_proc and self.current_proc.poll() is None:
            self.current_proc.terminate()
        self.current_proc = None
        self.current_row = -1
        self.status.showMessage("Ready")

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        play_action = menu.addAction("▶  Play")
        menu.addSeparator()
        hotkey_action = menu.addAction("⌨  Set Hotkey")
        remove_action = menu.addAction("✕  Remove")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == play_action:
            self.table.setCurrentCell(row, 1)
            self._play_selected()
        elif action == remove_action:
            self._remove_sound(row)
        elif action == hotkey_action:
            self._set_hotkey(row)

    def _remove_sound(self, row):
        self.sounds.pop(row)
        save_sounds(self.sounds)
        self._populate_table()

    def _set_hotkey(self, row):
        path = self.table.item(row, 1).data(Qt.UserRole)
        current = self.path_to_key.get(path, "")

        dialog = QDialog(self)
        dialog.setWindowTitle("Set Hotkey")
        dialog.setFixedSize(320, 120)
        layout = QVBoxLayout(dialog)

        label = QLabel(f"Current: {current or 'None'}\n\nEnter key name (e.g. KEY_F13, KEY_KP1):")
        label.setStyleSheet("color: #aaaaaa; padding: 8px;")
        layout.addWidget(label)

        edit = QLineEdit(current)
        edit.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        layout.addWidget(edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            key = edit.text().strip()
            self.path_to_key.pop(path, None)
            self.path_to_key = {p: k for p, k in self.path_to_key.items() if k != key}
            if key:
                self.path_to_key[path] = key
            save_hotkeys(self.path_to_key)
            self._populate_table()
            self._restart_hotkey_worker()

    def _add_files(self, paths):
        added = False
        for path in paths:
            p = Path(path)
            if p.suffix.lower() not in ('.mp3', '.wav', '.ogg', '.flac', '.m4a'):
                continue
            if any(s.get('path') == str(p) for s in self.sounds):
                continue
            duration = get_duration(str(p))
            self.sounds.append({"path": str(p), "name": p.stem, "duration": duration})
            added = True
        if added:
            save_sounds(self.sounds)
            self._populate_table()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self._add_files(paths)

    def _start_hotkey_worker(self):
        if not EVDEV:
            return
        try:
            hotkeys_by_code = {}
            for path, key_name in self.path_to_key.items():
                code = ecodes.ecodes.get(key_name)
                if code is not None:
                    hotkeys_by_code[code] = path

            self.hk_worker = HotkeyWorker(hotkeys_by_code)
            self.hk_thread = QThread()
            self.hk_worker.moveToThread(self.hk_thread)
            self.hk_worker.triggered.connect(lambda p: self._play(p))
            self.hk_thread.started.connect(self.hk_worker.run)
            self.hk_thread.start()
        except Exception:
            pass

    def _restart_hotkey_worker(self):
        try:
            if hasattr(self, 'hk_worker'):
                self.hk_worker.stop()
            if hasattr(self, 'hk_thread'):
                self.hk_thread.quit()
        except Exception:
            pass
        self._start_hotkey_worker()

    def closeEvent(self, event):
        self._stop()
        try:
            self.hk_worker.stop()
            self.hk_thread.quit()
        except Exception:
            pass
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Rayboard")
    win = RayboardWindow()
    win.show()
    sys.exit(app.exec())
