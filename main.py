import json
import random
import re
import sys
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import miniaudio
import numpy as np
from mutagen import File as MutagenFile
from PySide6.QtCore import QEvent, QRectF, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QMenu, QMessageBox, QPushButton, QSizeGrip,
                               QSlider, QVBoxLayout, QWidget)
from scipy.signal import sosfilt

# ---- About box info: edit these to your own details ----
APP_NAME = "VibeBeat"
APP_VERSION = "3.0.0"
APP_DESCRIPTION = ("A simple, fast MP3 player with a graphic equalizer, playlists,\n"
                   "album art, detachable spectrum bars and 3 themes.")
AUTHOR_NAME = "Iqbal Uddin Khan"
AUTHOR_TITLE = "Assistant Professor | DIT-HU -- NN Site KHI"
AUTHOR_EMAIL = "iqbalsound@yahoo.com"
GITHUB_URL = "https://github.com/iqbalsound/vibebeat"
COPYRIGHT = "© 2026 Iqbal Uddin Khan. Released under the MIT License."

SR = 44100
BANDS = 28
BAR_POS = 1
REPEAT_LABELS = ["Repeat: Off", "Repeat: All", "Repeat: One"]
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac"}
PLAYLIST_EXT = {".xspf", ".m3u", ".m3u8", ".pls"}
BAR_COLORS = {"Fluorescent Green": "#39FF14", "White": "#FFFFFF",
              "Fluorescent Blue": "#04D9FF", "Fluorescent Purple": "#BC13FE"}
BAR_STYLES = ["Solid bars", "Segmented bars"]
XSPF_NS = "http://xspf.org/ns/0/"

EQ_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_PRESETS = {
    "Flat":         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Rock":         [5, 4, 3, 1, -1, -1, 1, 3, 4, 5],
    "Pop":          [-1, 2, 4, 5, 3, 0, -1, -1, -1, -1],
    "Vocal":        [-3, -3, -2, 1, 4, 5, 4, 2, 0, -1],
    "Bass Boosted": [8, 7, 6, 4, 2, 0, 0, 0, 0, 0],
}

THEMES = {
    "Light": dict(bg="#f2f2f2", base="#ffffff", text="#202020", hl="#2d8cff",
                  htext="#ffffff", btn="#e6e6e6", border="#bdbdbd"),
    "Dark": dict(bg="#2b2b2b", base="#1e1e1e", text="#e6e6e6", hl="#3daee9",
                 htext="#000000", btn="#3a3a3a", border="#555555"),
    "Green on Black": dict(bg="#000000", base="#000000", text="#00ff41", hl="#00cc33",
                           htext="#000000", btn="#001a06", border="#00ff41"),
}


def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / name)


def state_file():
    d = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def fmt(ms):
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


# ---------------- tags & album art ----------------
def read_meta(path, want_art=True):
    meta = {"title": Path(path).stem, "artist": "", "album": "", "art": None}
    try:
        easy = MutagenFile(path, easy=True)
        if easy and easy.tags:
            meta["title"] = easy.tags.get("title", [meta["title"]])[0]
            meta["artist"] = easy.tags.get("artist", [""])[0]
            meta["album"] = easy.tags.get("album", [""])[0]
    except Exception:
        pass
    if want_art:
        try:
            f = MutagenFile(path)
            data = None
            if f is not None:
                if getattr(f, "pictures", None):
                    data = f.pictures[0].data
                elif f.tags is not None:
                    if hasattr(f.tags, "getall") and f.tags.getall("APIC"):
                        data = f.tags.getall("APIC")[0].data
                    elif "covr" in f.tags:
                        data = bytes(f.tags["covr"][0])
            if data:
                pm = QPixmap()
                if pm.loadFromData(data):
                    meta["art"] = pm
        except Exception:
            pass
    return meta


def rounded_pixmap(pm, size, radius):
    pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap((size - pm.width()) // 2, (size - pm.height()) // 2, pm)
    p.end()
    return out


# ---------------- playlist files (XSPF / M3U / M3U8 / PLS) ----------------
def write_playlist(path, tracks):
    ext = Path(path).suffix.lower()
    metas = [read_meta(t, want_art=False) for t in tracks]
    if ext == ".xspf":
        ET.register_namespace("", XSPF_NS)
        q = lambda t: f"{{{XSPF_NS}}}{t}"
        root = ET.Element(q("playlist"), version="1")
        ET.SubElement(root, q("title")).text = f"{APP_NAME} playlist"
        tl = ET.SubElement(root, q("trackList"))
        for t, m in zip(tracks, metas):
            tr = ET.SubElement(tl, q("track"))
            ET.SubElement(tr, q("location")).text = QUrl.fromLocalFile(t).toString()
            ET.SubElement(tr, q("title")).text = m["title"]
            if m["artist"]:
                ET.SubElement(tr, q("creator")).text = m["artist"]
            if m["album"]:
                ET.SubElement(tr, q("album")).text = m["album"]
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    elif ext in (".m3u", ".m3u8"):
        lines = ["#EXTM3U"]
        for t, m in zip(tracks, metas):
            name = f"{m['artist']} - {m['title']}" if m["artist"] else m["title"]
            lines += [f"#EXTINF:-1,{name}", t]
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif ext == ".pls":
        lines = ["[playlist]"]
        for i, (t, m) in enumerate(zip(tracks, metas), 1):
            lines += [f"File{i}={t}", f"Title{i}={m['title']}", f"Length{i}=-1"]
        lines += [f"NumberOfEntries={len(tracks)}", "Version=2"]
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        raise ValueError(f"Unsupported playlist type: {ext}")


def read_playlist(path):
    p = Path(path)
    ext, base = p.suffix.lower(), p.parent

    def fix(s):
        s = s.strip()
        u = QUrl(s)
        if u.isLocalFile():
            return u.toLocalFile()
        q = Path(s)
        return str(q if q.is_absolute() else base / q)

    out = []
    if ext == ".xspf":
        for el in ET.parse(path).getroot().iter():
            if el.tag.endswith("location") and el.text:
                out.append(fix(el.text))
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if ext == ".pls":
                m = re.match(r"File\d+=(.*)", line, re.I)
                if m:
                    out.append(fix(m.group(1)))
            elif line and not line.startswith("#"):
                out.append(fix(line))
    return out


# ---------------- audio engine (decode + equalizer + output) ----------------
def peaking_sos(gains, sr=SR, q=1.41):
    rows = []
    for f, g in zip(EQ_FREQS, gains):
        A = 10 ** (g / 40)
        w0 = 2 * np.pi * f / sr
        al = np.sin(w0) / (2 * q)
        c = np.cos(w0)
        b0, b1, b2 = 1 + al * A, -2 * c, 1 - al * A
        a0, a1, a2 = 1 + al / A, -2 * c, 1 - al / A
        rows.append([b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0])
    return np.array(rows)


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = None
        self.pos = 0
        self.playing = False
        self.ended = False
        self.vol = 0.7 ** 2
        self.sos = peaking_sos([0] * 10)
        self.zi = np.zeros((10, 2, 2))
        self.pre = 1.0
        self.bypass = True
        self.viz = np.zeros(2048, dtype=np.float32)
        self.device = None
        self.error = ""

    def start_device(self):
        try:
            self.device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2, sample_rate=SR, buffersize_msec=80)
            gen = self._stream()
            next(gen)
            self.device.start(gen)
            return True
        except Exception as ex:
            self.error = str(ex)
            return False

    def close(self):
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass

    def _stream(self):
        frames = yield b""
        while True:
            try:
                chunk = self._render(frames)
            except Exception:
                chunk = bytes(frames * 4)
            frames = yield chunk

    def _render(self, n):
        with self.lock:
            if not self.playing or self.data is None:
                return bytes(n * 4)
            chunk = self.data[self.pos:self.pos + n]
            k = len(chunk)
            self.pos += k
            if k < n:
                self.playing = False
                self.ended = True
            out = np.zeros((n, 2), dtype=np.float32)
            if k:
                x = chunk.astype(np.float32) / 32768.0
                if not self.bypass:
                    x, self.zi = sosfilt(self.sos, x * self.pre, axis=0, zi=self.zi)
                self.viz = np.concatenate(
                    (self.viz, x.mean(axis=1).astype(np.float32)))[-2048:]
                out[:k] = x * self.vol
            return (np.clip(out, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

    # --- control (called from the GUI thread) ---
    def load(self, path):
        dec = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.SIGNED16,
                                    nchannels=2, sample_rate=SR)
        arr = np.frombuffer(dec.samples, dtype=np.int16).reshape(-1, 2)
        with self.lock:
            self.playing = False
            self.ended = False
            self.data = arr
            self.pos = 0
            self.zi[:] = 0

    def play(self):
        with self.lock:
            if self.data is None:
                return
            if self.pos >= len(self.data):
                self.pos = 0
            self.ended = False
            self.playing = True

    def pause(self):
        with self.lock:
            self.playing = False

    def stop(self):
        with self.lock:
            self.playing = False
            self.ended = False
            self.pos = 0
            self.zi[:] = 0

    def seek(self, ms):
        with self.lock:
            if self.data is not None:
                self.pos = int(min(max(ms, 0) * SR / 1000, len(self.data)))
                self.zi[:] = 0

    def position_ms(self):
        return int(self.pos * 1000 / SR)

    def duration_ms(self):
        d = self.data
        return 0 if d is None else int(len(d) * 1000 / SR)

    def set_volume(self, v):
        self.vol = float(v) ** 2

    def set_gains(self, gains):
        gains = [float(g) for g in gains]
        sos = peaking_sos(gains)
        pre = 10 ** (-max(0.0, max(gains)) / 20)   # headroom against clipping
        bypass = not any(gains)
        with self.lock:
            self.sos, self.pre, self.bypass = sos, pre, bypass
            if bypass:
                self.zi[:] = 0

    def get_viz(self):
        return self.viz.copy()


# ---------------- spectrum bars ----------------
def spectrum(x, bands):
    n = len(x)
    if n < 1024:
        return None
    mag = np.abs(np.fft.rfft(x * np.hanning(n))) / (n / 4)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    edges = np.logspace(np.log10(40), np.log10(16000), bands + 1)
    out = np.zeros(bands)
    for i in range(bands):
        sel = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if sel.any():
            out[i] = mag[sel].max()
        else:
            out[i] = mag[min(np.searchsorted(freqs, edges[i]), len(mag) - 1)]
    db = 20 * np.log10(out + 1e-6)
    return np.clip((db + 75) / 65, 0, 1)


class BarGraph(QWidget):
    def __init__(self, bands):
        super().__init__()
        self.levels = np.zeros(bands)
        self.color = QColor(BAR_COLORS["Fluorescent Green"])
        self.segmented = False
        self.setMinimumHeight(90)
        self.setMinimumWidth(160)

    def push(self, lv):
        self.levels = np.maximum(lv, self.levels * 0.6)
        self.update()

    def decay(self):
        self.levels *= 0.88
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 10, 10, 235))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)

        m = 8
        w, h = self.width() - 2 * m, self.height() - 2 * m
        n, gap = len(self.levels), 3
        bw = (w - gap * (n - 1)) / n
        dim = QColor(self.color)
        dim.setAlpha(35)
        seg, sgap = 7, 2
        rows = max(1, int((h + sgap) // (seg + sgap)))
        for i, v in enumerate(self.levels):
            x = m + i * (bw + gap)
            if not self.segmented:
                bh = max(2.0, float(v) * h)
                r = min(3.0, bw / 2)
                p.setBrush(self.color)
                p.drawRoundedRect(QRectF(x, m + h - bh, bw, bh), r, r)
            else:
                lit = int(round(float(v) * rows))
                for r_ in range(rows):
                    y = m + h - (r_ + 1) * seg - r_ * sgap
                    p.setBrush(self.color if r_ < lit else dim)
                    p.drawRoundedRect(QRectF(x, y, bw, seg), 1.5, 1.5)


class FloatBars(QWidget):
    """Frameless, rounded window holding the bar graph. Keep-on-top is optional."""
    closed = Signal()

    def __init__(self, owner, on_top=True):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(f"{APP_NAME} bars")
        self.setWindowIcon(QIcon(resource("icon.png")))
        self.setMinimumSize(200, 90)
        self.resize(440, 170)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.grip = QSizeGrip(self)

    def set_on_top(self, on):
        was_visible = self.isVisible()
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        if was_visible:
            self.show()
            self.setGeometry(geo)

    def hold(self, graph):
        graph.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lay.addWidget(graph)
        self.grip.raise_()

    def resizeEvent(self, e):
        self.grip.move(self.width() - self.grip.width() - 2,
                       self.height() - self.grip.height() - 2)
        super().resizeEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        self.owner.attach()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction("Attach to main window", self.owner.attach)
        top = menu.addAction("Keep on top")
        top.setCheckable(True)
        top.setChecked(self.owner.on_top.isChecked())
        top.toggled.connect(self.owner.on_top.setChecked)
        cm = menu.addMenu("Colour")
        for n in BAR_COLORS:
            cm.addAction(n, lambda checked=False, n=n: self.owner.color_box.setCurrentText(n))
        sm = menu.addMenu("Style")
        for i, n in enumerate(BAR_STYLES):
            sm.addAction(n, lambda checked=False, i=i: self.owner.style_box.setCurrentIndex(i))
        menu.exec(e.globalPos())

    def closeEvent(self, e):
        self.closed.emit()
        e.accept()


# ---------------- equalizer window ----------------
class EqDialog(QDialog):
    changed = Signal(list)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Equalizer")
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.sliders, self.labels = [], []
        for f in EQ_FREQS:
            col = QVBoxLayout()
            val = QLabel("0 dB")
            val.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            s = QSlider(Qt.Orientation.Vertical)
            s.setRange(-12, 12)
            s.setValue(0)
            s.setMinimumHeight(170)
            s.valueChanged.connect(self._moved)
            name = QLabel(f"{f // 1000}k" if f >= 1000 else str(f))
            name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(val)
            col.addWidget(s, 1, Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(name)
            row.addLayout(col)
            self.sliders.append(s)
            self.labels.append(val)
        lay.addLayout(row)
        btn = QPushButton("Reset to Flat")
        btn.clicked.connect(lambda: self.set_gains([0] * 10, emit=True))
        lay.addWidget(btn)

    def gains(self):
        return [float(s.value()) for s in self.sliders]

    def _refresh(self):
        for s, l in zip(self.sliders, self.labels):
            l.setText(f"{s.value():+d} dB")

    def _moved(self, _=None):
        self._refresh()
        self.changed.emit(self.gains())

    def set_gains(self, g, emit=False):
        for s, v in zip(self.sliders, g):
            s.blockSignals(True)
            s.setValue(int(round(v)))
            s.blockSignals(False)
        self._refresh()
        if emit:
            self.changed.emit(self.gains())


# ---------------- themes ----------------
def make_palette(c):
    p = QPalette()
    R = QPalette.ColorRole
    for role, col in [(R.Window, c["bg"]), (R.WindowText, c["text"]), (R.Base, c["base"]),
                      (R.AlternateBase, c["bg"]), (R.Text, c["text"]), (R.Button, c["btn"]),
                      (R.ButtonText, c["text"]), (R.ToolTipBase, c["base"]),
                      (R.ToolTipText, c["text"]), (R.Highlight, c["hl"]),
                      (R.HighlightedText, c["htext"]), (R.PlaceholderText, "#808080"),
                      (R.Link, c["hl"])]:
        p.setColor(role, QColor(col))
    return p


def make_qss(c):
    return f"""
QPushButton, QComboBox {{
    background: {c['btn']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 8px; padding: 5px 10px;
}}
QPushButton:hover, QComboBox:hover {{ border-color: {c['hl']}; }}
QPushButton:pressed, QPushButton:checked {{ background: {c['hl']}; color: {c['htext']}; }}
QComboBox QAbstractItemView {{
    background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 6px; selection-background-color: {c['hl']}; selection-color: {c['htext']};
}}
QListWidget {{
    background: {c['base']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 12px; padding: 4px;
}}
QListWidget::item {{ padding: 4px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {c['hl']}; color: {c['htext']}; }}
QLabel#art {{ border: 1px solid {c['border']}; border-radius: 14px; background: {c['base']}; }}
QSlider::groove:horizontal {{ height: 6px; background: {c['border']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c['hl']}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {c['text']}; width: 14px; margin: -5px 0; border-radius: 7px;
}}
QSlider::groove:vertical {{ width: 6px; background: {c['border']}; border-radius: 3px; }}
QSlider::add-page:vertical {{ background: {c['hl']}; border-radius: 3px; }}
QSlider::handle:vertical {{
    background: {c['text']}; height: 14px; margin: 0 -5px; border-radius: 7px;
}}
"""


class Player(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource("icon.png")))
        self.resize(600, 900)
        self.setAcceptDrops(True)
        self.tracks, self.index, self.history = [], -1, []
        self.shuffle, self.repeat = False, 0
        self.floating = self.auto_detached = self.placed = False

        self.engine = Engine()
        self.audio_ok = self.engine.start_device()

        # --- widgets ---
        self.art = QLabel("♪")
        self.art.setObjectName("art")
        self.art.setFixedSize(150, 150)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet("font-size: 56px;")
        self.lbl_title = QLabel("No track loaded")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.lbl_title.setWordWrap(True)
        self.lbl_artist, self.lbl_album = QLabel(""), QLabel("")
        self.bars = BarGraph(BANDS)
        self.float_win = FloatBars(self, True)
        self.float_win.closed.connect(self.attach)
        self.color_box = QComboBox()
        self.color_box.addItems(list(BAR_COLORS))
        self.style_box = QComboBox()
        self.style_box.addItems(BAR_STYLES)
        self.btn_detach = QPushButton("Detach bars")
        self.on_top = QCheckBox("Keep bars on top")
        self.on_top.setChecked(True)
        self.auto_pop = QCheckBox("Pop out bars when minimised")
        self.auto_pop.setChecked(True)
        self.eq_box = QComboBox()
        self.eq_box.addItems(list(EQ_PRESETS) + ["Custom"])
        self.btn_eq = QPushButton("Equalizer sliders")
        self.eq_dialog = EqDialog(self)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.time = QLabel("0:00 / 0:00")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.playlist = QListWidget()

        self.btn_prev, self.btn_play, self.btn_stop, self.btn_next = (
            QPushButton(t) for t in ("⏮", "▶", "⏹", "⏭"))
        self.btn_shuffle = QPushButton("Shuffle")
        self.btn_shuffle.setCheckable(True)
        self.btn_repeat = QPushButton(REPEAT_LABELS[0])
        btn_add, btn_folder = QPushButton("Add files"), QPushButton("Add folder")
        btn_remove, btn_clear = QPushButton("Remove"), QPushButton("Clear")
        btn_open_pl, btn_save_pl = QPushButton("Open playlist"), QPushButton("Save playlist")
        btn_about = QPushButton("About")
        self.theme_box = QComboBox()
        self.theme_box.addItems(list(THEMES))

        # --- layout ---
        info = QVBoxLayout()
        for w in (self.lbl_title, self.lbl_artist, self.lbl_album):
            info.addWidget(w)
        info.addStretch()
        top = QHBoxLayout()
        top.addWidget(self.art)
        top.addLayout(info, 1)

        bar_row1 = QHBoxLayout()
        bar_row1.addWidget(QLabel("Bar colour"))
        bar_row1.addWidget(self.color_box, 1)
        bar_row1.addWidget(QLabel("Style"))
        bar_row1.addWidget(self.style_box, 1)
        bar_row2 = QHBoxLayout()
        bar_row2.addWidget(self.btn_detach)
        bar_row2.addWidget(self.on_top, 1)
        bar_row3 = QHBoxLayout()
        bar_row3.addWidget(self.auto_pop)
        eq_row = QHBoxLayout()
        eq_row.addWidget(QLabel("Equalizer"))
        eq_row.addWidget(self.eq_box, 1)
        eq_row.addWidget(self.btn_eq)

        controls = QHBoxLayout()
        for b in (self.btn_prev, self.btn_play, self.btn_stop, self.btn_next,
                  self.btn_shuffle, self.btn_repeat):
            controls.addWidget(b)
        vol = QHBoxLayout()
        vol.addWidget(QLabel("Volume"))
        vol.addWidget(self.volume)
        vol.addWidget(QLabel("Theme"))
        vol.addWidget(self.theme_box)
        manage1, manage2 = QHBoxLayout(), QHBoxLayout()
        for b in (btn_add, btn_folder, btn_remove, btn_clear):
            manage1.addWidget(b)
        for b in (btn_open_pl, btn_save_pl, btn_about):
            manage2.addWidget(b)

        self.lay = QVBoxLayout(self)
        self.lay.addLayout(top)           # index 0
        self.lay.addWidget(self.bars)     # index 1 (BAR_POS)
        self.lay.addLayout(bar_row1)
        self.lay.addLayout(bar_row2)
        self.lay.addLayout(bar_row3)
        self.lay.addLayout(eq_row)
        self.lay.addWidget(self.seek)
        self.lay.addWidget(self.time)
        self.lay.addLayout(controls)
        self.lay.addLayout(vol)
        self.lay.addWidget(self.playlist, 1)
        self.lay.addLayout(manage1)
        self.lay.addLayout(manage2)

        # --- signals ---
        btn_add.clicked.connect(self.add_files)
        btn_folder.clicked.connect(self.add_folder)
        btn_remove.clicked.connect(self.remove_selected)
        btn_clear.clicked.connect(self.clear_all)
        btn_open_pl.clicked.connect(self.open_playlist)
        btn_save_pl.clicked.connect(self.save_playlist)
        btn_about.clicked.connect(self.show_about)
        self.btn_detach.clicked.connect(self.toggle_detach)
        self.on_top.toggled.connect(self.float_win.set_on_top)
        self.color_box.currentTextChanged.connect(self.set_bar_color)
        self.style_box.currentIndexChanged.connect(self.set_bar_style)
        self.eq_box.currentTextChanged.connect(self.on_eq_preset)
        self.btn_eq.clicked.connect(self.show_eq)
        self.eq_dialog.changed.connect(self.on_eq_slider)
        self.btn_prev.clicked.connect(self.prev)
        self.btn_next.clicked.connect(lambda: self.next(auto=False))
        self.btn_stop.clicked.connect(self.engine.stop)
        self.btn_play.clicked.connect(self.toggle)
        self.btn_shuffle.toggled.connect(lambda v: setattr(self, "shuffle", v))
        self.btn_repeat.clicked.connect(self.cycle_repeat)
        self.theme_box.currentTextChanged.connect(self.apply_theme)
        self.playlist.itemDoubleClicked.connect(lambda _: self.play_index(self.playlist.currentRow()))
        self.seek.sliderMoved.connect(self.engine.seek)
        self.volume.valueChanged.connect(lambda v: self.engine.set_volume(v / 100))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

        self.volume.setValue(70)
        self.load_state()
        if not self.audio_ok:
            QTimer.singleShot(400, lambda: QMessageBox.warning(
                self, APP_NAME, f"Could not open the audio output:\n{self.engine.error}"))

    # ----- equalizer -----
    def show_eq(self):
        self.eq_dialog.show()
        self.eq_dialog.raise_()

    def on_eq_preset(self, name):
        if name in EQ_PRESETS:
            g = EQ_PRESETS[name]
            self.eq_dialog.set_gains(g)
            self.engine.set_gains(g)

    def on_eq_slider(self, gains):
        self.eq_box.blockSignals(True)
        self.eq_box.setCurrentText("Custom")
        self.eq_box.blockSignals(False)
        self.engine.set_gains(gains)

    # ----- bar graph: colour, style, detach -----
    def set_bar_color(self, name):
        if name in BAR_COLORS:
            self.bars.color = QColor(BAR_COLORS[name])
            self.bars.update()

    def set_bar_style(self, i):
        self.bars.segmented = (i == 1)
        self.bars.update()

    def detach(self):
        if self.floating:
            return
        self.floating = True
        if not self.placed:
            g = self.frameGeometry()
            self.float_win.move(g.right() + 12, g.top())
            self.placed = True
        self.float_win.hold(self.bars)
        self.float_win.show()
        self.bars.show()
        self.btn_detach.setText("Attach bars")

    def attach(self):
        if not self.floating:
            return
        self.floating = False
        self.auto_detached = False
        self.bars.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.lay.insertWidget(BAR_POS, self.bars)
        self.bars.show()
        self.float_win.hide()
        self.btn_detach.setText("Detach bars")

    def toggle_detach(self):
        self.attach() if self.floating else self.detach()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                if self.auto_pop.isChecked() and not self.floating:
                    self.detach()
                    self.auto_detached = True
            elif self.auto_detached:
                self.attach()

    # ----- main timer: bars, position, track end -----
    def tick(self):
        eng = self.engine
        if eng.ended:
            eng.ended = False
            self.next(auto=True)
        playing = eng.playing
        if playing:
            lv = spectrum(eng.get_viz(), BANDS)
            if lv is not None:
                self.bars.push(lv)
        self.bars.decay()
        txt = "⏸" if playing else "▶"
        if self.btn_play.text() != txt:
            self.btn_play.setText(txt)
        pos, dur = eng.position_ms(), eng.duration_ms()
        if not self.seek.isSliderDown():
            self.seek.setValue(pos)
        self.time.setText(f"{fmt(pos)} / {fmt(dur)}")

    # ----- playlist -----
    def add_paths(self, paths, autoplay=True):
        added = 0
        for f in paths:
            if Path(f).suffix.lower() in AUDIO_EXT and Path(f).exists():
                m = read_meta(f, want_art=False)
                label = f"{m['artist']} - {m['title']}" if m["artist"] else m["title"]
                self.tracks.append(f)
                self.playlist.addItem(label)
                added += 1
        if added and autoplay and self.index == -1:
            self.play_index(0)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add audio files", str(Path.home()), "Audio (*.mp3 *.wav *.ogg *.flac)")
        self.add_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder", str(Path.home()))
        if d:
            self.add_paths(sorted(str(p) for p in Path(d).rglob("*") if p.is_file()))

    def open_playlist(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Open playlist", str(Path.home()),
            "Playlists (*.xspf *.m3u *.m3u8 *.pls);;All files (*)")
        if f:
            self.load_playlist_file(f)

    def load_playlist_file(self, f):
        try:
            self.add_paths(read_playlist(f))
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"Could not read playlist:\n{ex}")

    def save_playlist(self):
        if not self.tracks:
            QMessageBox.information(self, APP_NAME, "The playlist is empty.")
            return
        f, sel = QFileDialog.getSaveFileName(
            self, "Save playlist", str(Path.home() / "vibebeat-playlist.xspf"),
            "XSPF (*.xspf);;M3U8 (*.m3u8);;M3U (*.m3u);;PLS (*.pls)")
        if not f:
            return
        if Path(f).suffix.lower() not in PLAYLIST_EXT:
            ext = next((x for x in ("xspf", "m3u8", "m3u", "pls") if f"*.{x}" in sel), "xspf")
            f += f".{ext}"
        try:
            write_playlist(f, self.tracks)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"Could not save playlist:\n{ex}")

    def remove_selected(self):
        row = self.playlist.currentRow()
        if row < 0:
            return
        self.playlist.takeItem(row)
        del self.tracks[row]
        self.history.clear()
        if row == self.index:
            self.engine.stop()
            self.index = -1
        elif row < self.index:
            self.index -= 1

    def clear_all(self):
        self.engine.stop()
        self.playlist.clear()
        self.tracks.clear()
        self.history.clear()
        self.index = -1
        self.show_meta(None)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for u in e.mimeData().urls():
            p = Path(u.toLocalFile())
            if p.suffix.lower() in PLAYLIST_EXT:
                self.load_playlist_file(str(p))
            elif p.is_dir():
                paths += [str(x) for x in p.rglob("*")]
            else:
                paths.append(str(p))
        self.add_paths(sorted(paths))

    # ----- playback -----
    def show_meta(self, path):
        self.art.clear()
        self.art.setText("♪")
        if not path:
            self.lbl_title.setText("No track loaded")
            self.lbl_artist.setText("")
            self.lbl_album.setText("")
            return
        m = read_meta(path)
        self.lbl_title.setText(m["title"])
        self.lbl_artist.setText(m["artist"])
        self.lbl_album.setText(m["album"])
        if m["art"]:
            self.art.setPixmap(rounded_pixmap(m["art"], 150, 14))

    def play_index(self, i, from_history=False, play=True):
        if not 0 <= i < len(self.tracks):
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        err = None
        try:
            self.engine.load(self.tracks[i])
        except Exception as ex:
            err = str(ex)
        finally:
            QApplication.restoreOverrideCursor()
        if err:
            QMessageBox.warning(self, APP_NAME, f"Could not play this file:\n{err}")
            return
        if self.index >= 0 and not from_history and i != self.index:
            self.history.append(self.index)
        self.index = i
        self.playlist.setCurrentRow(i)
        self.seek.setRange(0, self.engine.duration_ms())
        self.show_meta(self.tracks[i])
        if play:
            self.engine.play()

    def toggle(self):
        if self.engine.playing:
            self.engine.pause()
        elif self.index == -1:
            self.play_index(max(0, self.playlist.currentRow()))
        else:
            self.engine.play()

    def next(self, auto=False):
        n = len(self.tracks)
        if not n:
            return
        if auto and self.repeat == 2:
            self.engine.seek(0)
            self.engine.play()
            return
        if self.shuffle and n > 1:
            self.play_index(random.choice([i for i in range(n) if i != self.index]))
            return
        nxt = self.index + 1
        if nxt >= n:
            if auto and self.repeat == 0:
                self.engine.stop()
                return
            nxt = 0
        self.play_index(nxt)

    def prev(self):
        if self.engine.position_ms() > 3000:
            self.engine.seek(0)
        elif self.history:
            self.play_index(self.history.pop(), from_history=True)
        elif self.index > 0:
            self.play_index(self.index - 1, from_history=True)

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        self.btn_repeat.setText(REPEAT_LABELS[self.repeat])

    # ----- theme -----
    def apply_theme(self, name):
        c = THEMES.get(name, THEMES["Dark"])
        app = QApplication.instance()
        app.setPalette(make_palette(c))
        app.setStyleSheet(make_qss(c))

    # ----- about -----
    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        lay = QVBoxLayout(dlg)
        logo = QLabel()
        pm = QPixmap(resource("icon.png"))
        if not pm.isNull():
            logo.setPixmap(rounded_pixmap(pm, 96, 18))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(
            f"<h2>{APP_NAME}</h2><p>Version {APP_VERSION}</p>"
            f"<p>{APP_DESCRIPTION.replace(chr(10), '<br>')}</p><hr>"
            f"<p><b>{AUTHOR_NAME}</b><br>{AUTHOR_TITLE}<br>"
            f"<a href='mailto:{AUTHOR_EMAIL}'>{AUTHOR_EMAIL}</a><br>"
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>"
            f"<p><small>{COPYRIGHT}</small></p>")
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setOpenExternalLinks(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(logo)
        lay.addWidget(text)
        lay.addWidget(close)
        dlg.exec()

    # ----- saved state -----
    def save_state(self):
        data = {"tracks": self.tracks, "index": self.index,
                "volume": self.volume.value(), "shuffle": self.shuffle,
                "repeat": self.repeat, "theme": self.theme_box.currentText(),
                "bar_color": self.color_box.currentText(),
                "bar_style": self.style_box.currentIndex(),
                "bar_on_top": self.on_top.isChecked(),
                "auto_pop": self.auto_pop.isChecked(),
                "eq_preset": self.eq_box.currentText(),
                "eq_gains": self.eq_dialog.gains()}
        try:
            state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def load_state(self):
        try:
            d = json.loads(state_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.theme_box.setCurrentText("Dark")
            self.apply_theme("Dark")
            return
        self.volume.setValue(d.get("volume", 70))
        self.btn_shuffle.setChecked(d.get("shuffle", False))
        self.repeat = d.get("repeat", 0)
        self.btn_repeat.setText(REPEAT_LABELS[self.repeat])
        theme = d.get("theme", "Dark")
        self.theme_box.setCurrentText(theme)
        self.apply_theme(theme)
        self.color_box.setCurrentText(d.get("bar_color", "Fluorescent Green"))
        self.style_box.setCurrentIndex(d.get("bar_style", 0))
        self.on_top.setChecked(d.get("bar_on_top", True))
        self.auto_pop.setChecked(d.get("auto_pop", True))
        preset = d.get("eq_preset", "Flat")
        if preset == "Custom":
            g = d.get("eq_gains", [0] * 10)
            self.eq_box.blockSignals(True)
            self.eq_box.setCurrentText("Custom")
            self.eq_box.blockSignals(False)
            self.eq_dialog.set_gains(g)
            self.engine.set_gains(g)
        else:
            self.eq_box.setCurrentText(preset)
            self.on_eq_preset(preset)
        self.add_paths(d.get("tracks", []), autoplay=False)
        idx = d.get("index", -1)
        if 0 <= idx < len(self.tracks):
            self.play_index(idx, play=False)

    def closeEvent(self, e):
        self.float_win.blockSignals(True)
        self.float_win.close()
        self.eq_dialog.close()
        self.save_state()
        self.engine.close()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    w = Player()
    w.show()
    files = [a for a in sys.argv[1:] if Path(a).is_file()]
    if files:  # files passed from the file manager ("Open with VibeBeat")
        n = len(w.tracks)
        w.add_paths(files, autoplay=False)
        if len(w.tracks) > n:
            w.play_index(n)
    sys.exit(app.exec())
