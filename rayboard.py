#!/usr/bin/env python3
"""Rayboard 2.0 — Native Linux Soundboard"""

import sys, json, subprocess, threading, uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTreeWidget, QTreeWidgetItem,
    QToolBar, QSlider, QLabel, QHeaderView, QAbstractItemView,
    QSizePolicy, QStatusBar, QMenu, QDialog, QDialogButtonBox,
    QComboBox, QLineEdit, QSystemTrayIcon, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QSize
from PySide6.QtGui import QAction, QColor, QFont, QIcon

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

CONFIG_DIR   = Path.home() / ".config" / "rayboard"
SOUNDS_FILE  = CONFIG_DIR / "sounds.json"
CONFIG_FILE  = CONFIG_DIR / "config.json"
DEFAULT_SINK = "SoundpadOut"

CAT_ROLE  = Qt.UserRole        # category id stored on cat item col 0
SND_ROLE  = Qt.UserRole + 1    # sound dict stored on sound item col 0

STYLE = """
QMainWindow, QWidget { background:#1e1e1e; color:#fff; font-family:'Noto Sans',sans-serif; font-size:13px; }

QTreeWidget {
    background:#252525; alternate-background-color:#272727;
    border:none; outline:none;
}
QTreeWidget::item { padding:3px 6px; border:none; }
QTreeWidget::item:selected { background:#c0392b; color:#fff; }
QTreeWidget::item:hover:!selected { background:#333; }
QTreeWidget::branch { background:#252525; }
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {
    image: url(none); border-image: none;
}

QHeaderView::section {
    background:#1a1a1a; color:#666; border:none;
    border-right:1px solid #2e2e2e; border-bottom:1px solid #2e2e2e;
    padding:5px 8px; font-size:12px;
}

QToolBar {
    background:#181818; border:none; border-bottom:1px solid #2e2e2e;
    padding:4px; spacing:5px;
}
QToolBar QToolButton {
    background:transparent; color:#fff; border:none;
    border-radius:4px; padding:3px 7px; font-size:15px;
}
QToolBar QToolButton:hover    { background:#3a3a3a; }
QToolBar QToolButton:pressed  { background:#c0392b; }
QToolBar QToolButton:checked  { background:#7d1f1a; color:#fff; }

QSlider::groove:horizontal { height:3px; background:#444; border-radius:2px; margin:0 4px; }
QSlider::handle:horizontal { background:#c0392b; width:12px; height:12px; border-radius:6px; margin:-5px 0; }
QSlider::sub-page:horizontal { background:#c0392b; border-radius:2px; }

QStatusBar { background:#181818; color:#555; border-top:1px solid #2e2e2e; font-size:12px; padding:2px 8px; }

QScrollBar:vertical { background:#1e1e1e; width:8px; border:none; }
QScrollBar::handle:vertical { background:#444; border-radius:4px; min-height:20px; }
QScrollBar::handle:vertical:hover { background:#555; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

QMenu { background:#252525; border:1px solid #3a3a3a; color:#fff; }
QMenu::item:selected { background:#c0392b; }
QMenu::separator { height:1px; background:#3a3a3a; margin:3px 0; }

QDialog { background:#252525; }
QDialogButtonBox QPushButton {
    background:#3a3a3a; color:#fff; border:none; border-radius:4px;
    padding:6px 16px; min-width:60px;
}
QDialogButtonBox QPushButton:hover { background:#c0392b; }

QLineEdit {
    background:#1e1e1e; color:#fff; border:1px solid #444;
    border-radius:4px; padding:4px 8px; font-size:13px;
}
QLineEdit:focus { border-color:#c0392b; }

QComboBox {
    background:#2b2b2b; color:#fff; border:1px solid #444;
    border-radius:4px; padding:3px 8px; min-width:150px; font-size:12px;
}
QComboBox:focus { border-color:#c0392b; }
QComboBox::drop-down { border:none; width:18px; }
QComboBox::down-arrow { border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid #888; width:0; height:0; }
QComboBox QAbstractItemView { background:#252525; color:#fff; border:1px solid #444; selection-background-color:#c0392b; outline:none; }
"""

# ── helpers ────────────────────────────────────────────────────────────────────

def new_id():
    return uuid.uuid4().hex[:8]

def get_duration(path):
    if not MUTAGEN: return ""
    try:
        f = MutagenFile(path)
        if f and hasattr(f.info, 'length'):
            s = int(f.info.length)
            return f"{s//60}:{s%60:02d}"
    except Exception: pass
    return ""

def get_pw_devices(kind="sinks"):
    try:
        out = subprocess.check_output(['pactl','list',kind], text=True, stderr=subprocess.DEVNULL)
    except Exception: return []
    devices, name, desc = [], None, None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('Name:'): name = line.split(':',1)[1].strip(); desc = None
        elif line.startswith('Description:') and name and desc is None:
            desc = line.split(':',1)[1].strip()
            devices.append((name, desc or name)); name = desc = None
    return devices

def _empty_data():
    return {'version': 2, 'categories': [{'id': new_id(), 'name': 'General', 'sounds': []}]}

def load_sounds():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SOUNDS_FILE.exists(): return _empty_data()
    try:
        d = json.loads(SOUNDS_FILE.read_text())
        if isinstance(d, list):  # migrate v1
            return {'version': 2, 'categories': [{'id': new_id(), 'name': 'General', 'sounds': [
                {**s, 'id': new_id(), 'volume': 100, 'loop': False, 'hotkey': ''} for s in d
            ]}]}
        # ensure all sounds have ids and required fields
        for cat in d.get('categories', []):
            for s in cat.get('sounds', []):
                s.setdefault('id', new_id())
                s.setdefault('volume', 100)
                s.setdefault('loop', False)
                s.setdefault('hotkey', '')
        return d
    except Exception: return _empty_data()

def save_sounds(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_FILE.write_text(json.dumps(data, indent=2))

def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text())
        except Exception: pass
    return {}

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ── signal bridge (for thread → main thread communication) ─────────────────────

class _Bridge(QObject):
    status   = Signal(str)
    stop_all = Signal()

# ── hotkey worker ──────────────────────────────────────────────────────────────

class HotkeyWorker(QObject):
    triggered = Signal(str)  # emits sound id
    stop_all  = Signal()

    def __init__(self, hotkeys_by_code, stop_all_code):
        super().__init__()
        self.hotkeys_by_code = hotkeys_by_code
        self.stop_all_code   = stop_all_code
        self._running = True

    def run(self):
        if not EVDEV: return
        kbd_paths = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                    kbd_paths.append(path)
            except Exception: pass
        for p in kbd_paths:
            threading.Thread(target=self._monitor, args=(p,), daemon=True).start()

    def _monitor(self, dev_path):
        try:
            dev = InputDevice(dev_path)
            for ev in dev.read_loop():
                if not self._running: break
                if ev.type == ecodes.EV_KEY and ev.value == 1:
                    if self.stop_all_code and ev.code == self.stop_all_code:
                        self.stop_all.emit()
                    elif ev.code in self.hotkeys_by_code:
                        self.triggered.emit(self.hotkeys_by_code[ev.code])
        except Exception: pass

    def stop(self): self._running = False

# ── custom tree (handles drag-drop sync) ───────────────────────────────────────

class SoundTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = None  # set by window after creation

    def dropEvent(self, event):
        super().dropEvent(event)
        if self.main_win:
            self.main_win._sync_from_tree()

# ── main window ────────────────────────────────────────────────────────────────

class RayboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rayboard 2.0")
        self.setMinimumSize(640, 420)
        self.resize(820, 560)
        self.setAcceptDrops(True)

        self.data        = load_sounds()
        self.cfg         = load_config()
        self.output_sink = self.cfg.get('output_sink', DEFAULT_SINK)
        self.overlap     = self.cfg.get('overlap', False)
        self.active      = []   # [{proc, sound_id, loop_ref, path}]
        self._updating   = False

        self._bridge = _Bridge()
        self._bridge.status.connect(lambda m: self.status.showMessage(m))
        self._bridge.stop_all.connect(self._stop_all)

        self._build_ui()
        self._populate_tree()
        self._start_hotkey_worker()
        self._setup_tray()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # toolbar
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        act_play = QAction("▶", self); act_play.setToolTip("Play selected"); act_play.triggered.connect(self._play_selected)
        act_stop = QAction("■", self); act_stop.setToolTip("Stop all");      act_stop.triggered.connect(self._stop_all)
        tb.addAction(act_play)
        tb.addAction(act_stop)
        tb.addSeparator()

        tb.addWidget(_lbl("🔊", "#666"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(100); self.vol_slider.setFixedWidth(90)
        self.vol_slider.setToolTip("Global volume")
        tb.addWidget(self.vol_slider)
        tb.addSeparator()

        self.overlap_btn = QAction("⊕ Overlap", self)
        self.overlap_btn.setToolTip("Play multiple sounds at once")
        self.overlap_btn.setCheckable(True)
        self.overlap_btn.setChecked(self.overlap)
        self.overlap_btn.toggled.connect(self._toggle_overlap)
        tb.addAction(self.overlap_btn)
        tb.addSeparator()

        tb.addWidget(_lbl("Out:", "#666"))
        self.sink_combo = QComboBox(); self.sink_combo.setToolTip("Output device")
        tb.addWidget(self.sink_combo)
        tb.addSeparator()

        tb.addWidget(_lbl("In:", "#666"))
        self.src_combo = QComboBox(); self.src_combo.setToolTip("Input device")
        tb.addWidget(self.src_combo)

        act_refresh = QAction("↻", self); act_refresh.setToolTip("Refresh devices"); act_refresh.triggered.connect(self._refresh_devices)
        tb.addAction(act_refresh)
        tb.addSeparator()

        self.search = QLineEdit(); self.search.setPlaceholderText("Search…"); self.search.setFixedWidth(160)
        self.search.setStyleSheet("QLineEdit { background:#2b2b2b; color:#fff; border:1px solid #444; border-radius:4px; padding:3px 8px; font-size:12px; }")
        self.search.textChanged.connect(self._filter)
        tb.addWidget(self.search)

        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(_lbl("Drop audio files here", "#444"))

        # second toolbar row: add category button
        tb2 = QToolBar()
        tb2.setMovable(False)
        tb2.setIconSize(QSize(16, 16))
        tb2.setStyleSheet("QToolBar { background:#202020; border:none; border-bottom:1px solid #2e2e2e; padding:2px 6px; spacing:4px; }")
        self.addToolBar(tb2)

        act_add_cat = QAction("+ Add Category", self)
        act_add_cat.setToolTip("Add a new category")
        act_add_cat.triggered.connect(self._add_category)
        act_add_cat.setStyleSheet if False else None
        tb2.addAction(act_add_cat)

        # tree
        self.tree = SoundTree(self)
        self.tree.main_win = self
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Duration", "Vol", "Hotkey"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDropIndicatorShown(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed); self.tree.setColumnWidth(1, 70)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed); self.tree.setColumnWidth(2, 90)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed); self.tree.setColumnWidth(3, 100)
        self.tree.setIndentation(16)

        self.setCentralWidget(self.tree)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        self._refresh_devices()
        self.sink_combo.currentIndexChanged.connect(self._on_sink_changed)
        self.src_combo.currentIndexChanged.connect(self._on_src_changed)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(QIcon.fromTheme('audio-headset'), self)
        m = QMenu()
        m.addAction("Show Rayboard").triggered.connect(self.show)
        m.addAction("Stop All").triggered.connect(self._stop_all)
        m.addSeparator()
        m.addAction("Quit").triggered.connect(QApplication.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    # ── device handling ────────────────────────────────────────────────────────

    def _refresh_devices(self):
        sinks   = get_pw_devices("sinks")
        sources = get_pw_devices("sources")
        saved_sink = self.cfg.get('output_sink', DEFAULT_SINK)
        saved_src  = self.cfg.get('input_source', '')

        self.sink_combo.blockSignals(True); self.sink_combo.clear()
        for i, (n, d) in enumerate(sinks):
            self.sink_combo.addItem(d, n)
            if n == saved_sink: self.sink_combo.setCurrentIndex(i)
        if sinks: self.output_sink = self.sink_combo.currentData() or DEFAULT_SINK
        self.sink_combo.blockSignals(False)

        self.src_combo.blockSignals(True); self.src_combo.clear()
        for i, (n, d) in enumerate(sources):
            self.src_combo.addItem(d, n)
            if n == saved_src: self.src_combo.setCurrentIndex(i)
        self.src_combo.blockSignals(False)

    def _on_sink_changed(self, idx):
        n = self.sink_combo.itemData(idx)
        if n: self.output_sink = n; self.cfg['output_sink'] = n; save_config(self.cfg)

    def _on_src_changed(self, idx):
        n = self.src_combo.itemData(idx)
        if n: self.cfg['input_source'] = n; save_config(self.cfg)

    # ── tree population ────────────────────────────────────────────────────────

    def _populate_tree(self):
        self._updating = True
        self.tree.clear()
        for cat in self.data.get('categories', []):
            cat_item = self._make_cat_item(cat)
            self.tree.addTopLevelItem(cat_item)
            for sound in cat.get('sounds', []):
                snd_item = self._make_snd_item(sound)
                cat_item.addChild(snd_item)
                self._attach_vol_slider(sound, snd_item)
            cat_item.setExpanded(True)
        self._updating = False

    def _make_cat_item(self, cat):
        item = QTreeWidgetItem([cat['name'], '', '', ''])
        item.setData(0, CAT_ROLE, cat['id'])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDropEnabled)
        item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
        f = QFont(); f.setBold(True)
        item.setFont(0, f)
        item.setForeground(0, QColor('#c0392b'))
        item.setBackground(0, QColor('#1a1a1a'))
        item.setBackground(1, QColor('#1a1a1a'))
        item.setBackground(2, QColor('#1a1a1a'))
        item.setBackground(3, QColor('#1a1a1a'))
        return item

    def _make_snd_item(self, sound):
        hotkey_txt = sound.get('hotkey', '')
        if sound.get('loop'): hotkey_txt = ('🔁 ' + hotkey_txt).strip()
        item = QTreeWidgetItem([
            sound.get('name', Path(sound.get('path','')).stem),
            sound.get('duration', ''),
            '',
            hotkey_txt,
        ])
        item.setData(0, SND_ROLE, sound)
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled)
        item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
        item.setForeground(1, QColor('#666'))
        item.setForeground(3, QColor('#c0392b'))
        return item

    def _attach_vol_slider(self, sound, item):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 200)
        slider.setValue(sound.get('volume', 100))
        slider.setToolTip(f"{sound.get('volume', 100)}%")
        slider.setStyleSheet("""
            QSlider::groove:horizontal { height:3px; background:#444; border-radius:2px; margin:0 2px; }
            QSlider::handle:horizontal { background:#c0392b; width:10px; height:10px; border-radius:5px; margin:-4px 0; }
            QSlider::sub-page:horizontal { background:#c0392b; border-radius:2px; }
        """)
        def on_change(v, s=sound, i=item, sl=slider):
            s['volume'] = v
            sl.setToolTip(f"{v}%")
            i.setData(0, SND_ROLE, s)
            found = self._find_sound(s['id'])
            if found: found['volume'] = v
            save_sounds(self.data)
        slider.valueChanged.connect(on_change)
        wrap = QWidget(); wrap.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(wrap); lay.setContentsMargins(4, 2, 4, 2); lay.addWidget(slider)
        self.tree.setItemWidget(item, 2, wrap)

    def _sync_from_tree(self):
        """Read tree back into data after drag-drop."""
        new_cats = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            ci = root.child(i)
            cat_id = ci.data(0, CAT_ROLE)
            sounds = []
            for j in range(ci.childCount()):
                si = ci.child(j)
                s = si.data(0, SND_ROLE)
                if s: sounds.append(s)
            new_cats.append({'id': cat_id or new_id(), 'name': ci.text(0), 'sounds': sounds})
        self.data['categories'] = new_cats
        save_sounds(self.data)

    # ── item change / rename ───────────────────────────────────────────────────

    def _on_item_changed(self, item, col):
        if self._updating or col != 0: return
        sound = item.data(0, SND_ROLE)
        if sound:
            sound['name'] = item.text(0)
            item.setData(0, SND_ROLE, sound)
            save_sounds(self.data)
        else:
            # category rename
            self._sync_from_tree()

    def _on_double_click(self, item, col):
        # double-click on a sound plays it; on category does nothing (edit handled by tree)
        if item.data(0, SND_ROLE) and col != 0:
            self._play_item(item)

    # ── search / filter ────────────────────────────────────────────────────────

    def _filter(self, text):
        text = text.lower().strip()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            ci = root.child(i)
            visible = 0
            for j in range(ci.childCount()):
                si = ci.child(j)
                match = not text or text in si.text(0).lower()
                si.setHidden(not match)
                if match: visible += 1
            ci.setHidden(bool(text) and visible == 0)

    # ── playback ───────────────────────────────────────────────────────────────

    def _play_selected(self):
        item = self.tree.currentItem()
        if item and item.data(0, SND_ROLE):
            self._play_item(item)

    def _play_item(self, item):
        sound = item.data(0, SND_ROLE)
        if sound: self._play(sound)

    def _play(self, sound):
        path = sound.get('path', '')
        if not Path(path).exists():
            self.status.showMessage(f"File not found: {path}", 4000); return

        if not self.overlap: self._stop_all()

        s_vol  = sound.get('volume', 100)
        g_vol  = self.vol_slider.value()
        vol    = int((s_vol / 100) * (g_vol / 100) * 65536)
        loop_ref = [sound.get('loop', False)]  # mutable so watcher can read updates

        try:
            proc = subprocess.Popen(
                ['paplay', f'--volume={vol}', f'--device={self.output_sink}', path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.status.showMessage(f"Error: {e}", 4000); return

        entry = {'proc': proc, 'sound_id': sound['id'], 'loop_ref': loop_ref, 'path': path}
        self.active.append(entry)
        self._bridge.status.emit(f"▶  {sound.get('name','')}")

        def watch():
            proc.wait()
            if entry in self.active: self.active.remove(entry)
            # loop?
            current = self._find_sound(sound['id'])
            if current and current.get('loop') and loop_ref[0]:
                self._play(current)
            elif not self.active:
                self._bridge.status.emit("Ready")

        threading.Thread(target=watch, daemon=True).start()

    def _find_sound(self, sound_id):
        for cat in self.data.get('categories', []):
            for s in cat.get('sounds', []):
                if s.get('id') == sound_id: return s
        return None

    def _stop_all(self):
        for e in self.active:
            if e['proc'].poll() is None:
                e['proc'].terminate()
            e['loop_ref'][0] = False
        self.active.clear()
        self.status.showMessage("Ready")

    def _toggle_overlap(self, checked):
        self.overlap = checked
        self.cfg['overlap'] = checked
        save_config(self.cfg)

    # ── context menus ──────────────────────────────────────────────────────────

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            menu.addAction("+ Add Category").triggered.connect(self._add_category)
        elif item.data(0, CAT_ROLE) and not item.data(0, SND_ROLE):
            # category
            menu.addAction("Rename").triggered.connect(lambda: self.tree.editItem(item, 0))
            menu.addAction("Add Sound Here").triggered.connect(lambda: self._prompt_add_sound(item))
            menu.addSeparator()
            menu.addAction("Delete Category").triggered.connect(lambda: self._delete_category(item))
        else:
            # sound
            sound = item.data(0, SND_ROLE)
            menu.addAction("▶  Play").triggered.connect(lambda: self._play_item(item))
            menu.addAction("■  Stop All").triggered.connect(self._stop_all)
            menu.addSeparator()
            loop_lbl = "✓ Loop (on)" if sound.get('loop') else "Loop"
            menu.addAction(loop_lbl).triggered.connect(lambda: self._toggle_loop(item))
            menu.addAction("Set Volume…").triggered.connect(lambda: self._set_volume(item))
            menu.addAction("Set Hotkey…").triggered.connect(lambda: self._set_hotkey(item))
            menu.addSeparator()
            menu.addAction("Remove").triggered.connect(lambda: self._remove_sound(item))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ── category operations ────────────────────────────────────────────────────

    def _add_category(self):
        cat = {'id': new_id(), 'name': 'New Category', 'sounds': []}
        self.data['categories'].append(cat)
        save_sounds(self.data)
        self._updating = True
        ci = self._make_cat_item(cat)
        self.tree.addTopLevelItem(ci)
        ci.setExpanded(True)
        self._updating = False
        self.tree.editItem(ci, 0)

    def _delete_category(self, cat_item):
        cat_id = cat_item.data(0, CAT_ROLE)
        self.data['categories'] = [c for c in self.data['categories'] if c['id'] != cat_id]
        save_sounds(self.data)
        idx = self.tree.indexOfTopLevelItem(cat_item)
        self.tree.takeTopLevelItem(idx)

    # ── sound operations ───────────────────────────────────────────────────────

    def _prompt_add_sound(self, cat_item):
        # Users can also drag & drop — this is a fallback text entry
        dialog = QDialog(self); dialog.setWindowTitle("Add Sound"); dialog.setFixedSize(360, 90)
        layout = QVBoxLayout(dialog)
        edit = QLineEdit(); edit.setPlaceholderText("/path/to/sound.mp3")
        layout.addWidget(QLabel("File path:")); layout.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        if dialog.exec() == QDialog.Accepted:
            self._add_files([edit.text().strip()], cat_item)

    def _remove_sound(self, snd_item):
        sound = snd_item.data(0, SND_ROLE)
        for cat in self.data['categories']:
            cat['sounds'] = [s for s in cat['sounds'] if s.get('id') != sound.get('id')]
        save_sounds(self.data)
        parent = snd_item.parent()
        if parent:
            parent.removeChild(snd_item)

    def _toggle_loop(self, item):
        sound = item.data(0, SND_ROLE)
        sound['loop'] = not sound.get('loop', False)
        item.setData(0, SND_ROLE, sound)
        hk = sound.get('hotkey', '')
        item.setText(3, ('🔁 ' + hk).strip() if sound['loop'] else hk)
        # update in data
        s = self._find_sound(sound['id'])
        if s: s['loop'] = sound['loop']
        save_sounds(self.data)

    def _set_volume(self, item):
        sound = item.data(0, SND_ROLE)
        dialog = QDialog(self); dialog.setWindowTitle(f"Volume — {sound.get('name','')}"); dialog.setFixedSize(300, 110)
        layout = QVBoxLayout(dialog)
        slider = QSlider(Qt.Horizontal); slider.setRange(0, 200); slider.setValue(sound.get('volume', 100))
        lbl = QLabel(f"{sound.get('volume',100)}%")
        lbl.setAlignment(Qt.AlignCenter)
        slider.valueChanged.connect(lambda v: lbl.setText(f"{v}%"))
        layout.addWidget(QLabel("Volume (0–200%):"))
        layout.addWidget(slider); layout.addWidget(lbl)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        if dialog.exec() == QDialog.Accepted:
            v = slider.value(); sound['volume'] = v
            item.setData(0, SND_ROLE, sound)
            s = self._find_sound(sound['id'])
            if s: s['volume'] = v
            save_sounds(self.data)
            # update the inline slider widget
            wrap = self.tree.itemWidget(item, 2)
            if wrap:
                sl = wrap.findChild(QSlider)
                if sl: sl.blockSignals(True); sl.setValue(v); sl.blockSignals(False)

    def _set_hotkey(self, item):
        sound = item.data(0, SND_ROLE)
        current = sound.get('hotkey', '')
        dialog = QDialog(self); dialog.setWindowTitle("Set Hotkey"); dialog.setFixedSize(320, 110)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Current: {current or 'None'}\n\nKey name (e.g. KEY_F13, KEY_KP1):"))
        edit = QLineEdit(current); layout.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        if dialog.exec() == QDialog.Accepted:
            key = edit.text().strip()
            # remove key from any other sound first
            for cat in self.data['categories']:
                for s in cat['sounds']:
                    if s.get('hotkey') == key and s['id'] != sound['id']:
                        s['hotkey'] = ''
            sound['hotkey'] = key
            item.setData(0, SND_ROLE, sound)
            hk_txt = ('🔁 ' + key).strip() if sound.get('loop') else key
            item.setText(3, hk_txt)
            s = self._find_sound(sound['id'])
            if s: s['hotkey'] = key
            save_sounds(self.data)
            self._restart_hotkey_worker()

    # ── drag & drop files onto window ──────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        # Drop into selected category or first category
        target_cat = None
        sel = self.tree.currentItem()
        if sel:
            if sel.data(0, CAT_ROLE) and not sel.data(0, SND_ROLE):
                target_cat = sel
            elif sel.parent():
                target_cat = sel.parent()
        if target_cat is None and self.tree.topLevelItemCount():
            target_cat = self.tree.topLevelItem(0)
        self._add_files(paths, target_cat)

    def _add_files(self, paths, cat_item=None):
        if cat_item is None:
            if self.tree.topLevelItemCount():
                cat_item = self.tree.topLevelItem(0)
            else:
                self._add_category()
                cat_item = self.tree.topLevelItem(0)

        cat_id = cat_item.data(0, CAT_ROLE)
        cat    = next((c for c in self.data['categories'] if c['id'] == cat_id), None)
        if not cat: return

        added = False
        for path in paths:
            p = Path(path)
            if p.suffix.lower() not in ('.mp3','.wav','.ogg','.flac','.m4a'): continue
            if any(s.get('path') == str(p) for c in self.data['categories'] for s in c['sounds']): continue
            sound = {'id': new_id(), 'path': str(p), 'name': p.stem, 'duration': get_duration(str(p)), 'volume': 100, 'loop': False, 'hotkey': ''}
            cat['sounds'].append(sound)
            self._updating = True
            snd_item = self._make_snd_item(sound)
            cat_item.addChild(snd_item)
            self._attach_vol_slider(sound, snd_item)
            self._updating = False
            added = True
        if added:
            cat_item.setExpanded(True)
            save_sounds(self.data)

    # ── hotkey worker ──────────────────────────────────────────────────────────

    def _build_hotkey_map(self):
        if not EVDEV: return {}, None
        hkmap = {}
        for cat in self.data.get('categories', []):
            for s in cat.get('sounds', []):
                key = s.get('hotkey', '')
                if key:
                    code = ecodes.ecodes.get(key)
                    if code is not None: hkmap[code] = s['id']
        stop_key = self.cfg.get('stop_all_key', 'KEY_PAUSE')
        stop_code = ecodes.ecodes.get(stop_key) if stop_key else None
        return hkmap, stop_code

    def _start_hotkey_worker(self):
        if not EVDEV: return
        try:
            hkmap, stop_code = self._build_hotkey_map()
            self.hk_worker = HotkeyWorker(hkmap, stop_code)
            self.hk_thread = QThread()
            self.hk_worker.moveToThread(self.hk_thread)
            self.hk_worker.triggered.connect(self._hotkey_play)
            self.hk_worker.stop_all.connect(self._stop_all)
            self.hk_thread.started.connect(self.hk_worker.run)
            self.hk_thread.start()
        except Exception: pass

    def _restart_hotkey_worker(self):
        try:
            if hasattr(self, 'hk_worker'): self.hk_worker.stop()
            if hasattr(self, 'hk_thread'): self.hk_thread.quit()
        except Exception: pass
        self._start_hotkey_worker()

    def _hotkey_play(self, sound_id):
        s = self._find_sound(sound_id)
        if s: self._play(s)

    # ── window events ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._stop_all()
        try: self.hk_worker.stop(); self.hk_thread.quit()
        except Exception: pass
        self.tray.hide()
        event.accept()


# ── small helpers ──────────────────────────────────────────────────────────────

def _lbl(text, color="#888"):
    l = QLabel(text)
    l.setStyleSheet(f"color:{color}; padding:0 4px; font-size:12px;")
    return l


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Rayboard")
    app.setQuitOnLastWindowClosed(False)  # keep alive in tray
    win = RayboardWindow()
    win.show()
    sys.exit(app.exec())
