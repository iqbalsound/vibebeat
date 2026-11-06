import json
import random
import sys
from pathlib import Path

import numpy as np
from mutagen import File as MutagenFile
from PySide6.QtCore import QRectF, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                               QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

try:
    from PySide6.QtMultimedia import QAudioBufferOutput  # Qt 6.8+
    HAS_BUF = True
except ImportError:
    HAS_BUF = False

# ---- About box info: edit these to your own details ----
APP_NAME = "VibeBeat"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = ("A simple, fast MP3 player with playlists, album art,\n"
                   "spectrum bars and Light, Dark and Green-on-Black themes.")
AUTHOR_NAME = "Iqbal Uddin Khan"
AUTHOR_TITLE = "Assistant Professor | DIT-HU -- NN Site KHI"
AUTHOR_EMAIL = "iqbalsound@yahoo.com"
GITHUB_URL = "https://github.com/iqbalsound/vibebeat"
COPYRIGHT = "© 2026 Iqbal Uddin Khan. Released under the MIT License."

BANDS = 28
THEMES = ["Light", "Dark", "Green on Black"]
REPEAT_LABELS = ["Repeat: Off", "Repeat: All", "Repeat: One"]
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


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


# ---------------- spectrum ----------------
def spectrum(buf, bands):
    fmt_ = buf.format()
    SF = QAudioFormat.SampleFormat
    sf = fmt_.sampleFormat()
    dtype = {SF.UInt8: np.uint8, SF.Int16: np.int16,
             SF.Int32: np.int32, SF.Float: np.float32}.get(sf)
    if dtype is None:
        raise ValueError("unsupported sample format")
    raw = bytes(buf.constData())[: buf.byteCount()]
    x = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if sf == SF.UInt8:
        x = (x - 128) / 128
    elif sf == SF.Int16:
        x /= 32768
    elif sf == SF.Int32:
        x /= 2 ** 31
    ch = max(1, fmt_.channelCount())
    x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)[-2048:]
    if len(x) < 256:
        return None
    n = len(x)
    mag = np.abs(np.fft.rfft(x * np.hanning(n))) / (n / 4)
    sr = fmt_.sampleRate()
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    edges = np.logspace(np.log10(40), np.log10(min(16000, sr / 2 - 1)), bands + 1)
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
        self.setMinimumHeight(90)

    def push(self, lv):
        self.levels = np.maximum(lv, self.levels * 0.6)
        self.update()

    def decay(self):
        self.levels *= 0.88
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        n, gap = len(self.levels), 3
        bw = (w - gap * (n - 1)) / n
        col = self.palette().color(QPalette.ColorRole.Highlight)
        for i, v in enumerate(self.levels):
            bh = max(2.0, float(v) * h)
            p.fillRect(QRectF(i * (bw + gap), h - bh, bw, bh), col)


# ---------------- themes ----------------
def make_palette(theme):
    if theme == "Light":
        return QApplication.style().standardPalette()
    if theme == "Dark":
        bg, base, text, hl, htext = "#2b2b2b", "#1e1e1e", "#e6e6e6", "#3daee9", "#000000"
    else:
        bg, base, text, hl, htext = "#000000", "#000000", "#00ff41", "#00cc33", "#000000"
    p = QPalette()
    R = QPalette.ColorRole
    for role, c in [(R.Window, bg), (R.WindowText, text), (R.Base, base),
                    (R.AlternateBase, bg), (R.Text, text), (R.Button, bg),
                    (R.ButtonText, text), (R.ToolTipBase, base), (R.ToolTipText, text),
                    (R.Highlight, hl), (R.HighlightedText, htext),
                    (R.PlaceholderText, "#808080"), (R.Link, hl)]:
        p.setColor(role, QColor(c))
    return p


GREEN_QSS = """
QPushButton, QComboBox, QListWidget { border: 1px solid #00ff41; padding: 3px; }
QPushButton:checked { background: #003b10; }
"""


class Player(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource("icon.png")))
        self.resize(560, 720)
        self.setAcceptDrops(True)
        self.tracks, self.index, self.history = [], -1, []
        self.shuffle, self.repeat = False, 0
        self.fake = not HAS_BUF

        self.audio = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)
        if HAS_BUF:
            self.buf_out = QAudioBufferOutput(self)
            self.buf_out.audioBufferReceived.connect(self.on_buffer)
            self.player.setAudioBufferOutput(self.buf_out)

        # --- widgets ---
        self.art = QLabel("♪")
        self.art.setFixedSize(150, 150)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setFrameShape(QLabel.Shape.Box)
        self.art.setStyleSheet("font-size: 56px;")
        self.lbl_title = QLabel("No track loaded")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.lbl_title.setWordWrap(True)
        self.lbl_artist, self.lbl_album = QLabel(""), QLabel("")
        self.bars = BarGraph(BANDS)
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
        btn_about = QPushButton("About")
        self.theme_box = QComboBox()
        self.theme_box.addItems(THEMES)

        # --- layout ---
        info = QVBoxLayout()
        for w in (self.lbl_title, self.lbl_artist, self.lbl_album):
            info.addWidget(w)
        info.addStretch()
        top = QHBoxLayout()
        top.addWidget(self.art)
        top.addLayout(info, 1)

        controls = QHBoxLayout()
        for b in (self.btn_prev, self.btn_play, self.btn_stop, self.btn_next,
                  self.btn_shuffle, self.btn_repeat):
            controls.addWidget(b)
        vol = QHBoxLayout()
        vol.addWidget(QLabel("Volume"))
        vol.addWidget(self.volume)
        vol.addWidget(QLabel("Theme"))
        vol.addWidget(self.theme_box)
        manage = QHBoxLayout()
        for b in (btn_add, btn_folder, btn_remove, btn_clear, btn_about):
            manage.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.bars)
        lay.addWidget(self.seek)
        lay.addWidget(self.time)
        lay.addLayout(controls)
        lay.addLayout(vol)
        lay.addWidget(self.playlist, 1)
        lay.addLayout(manage)

        # --- signals ---
        btn_add.clicked.connect(self.add_files)
        btn_folder.clicked.connect(self.add_folder)
        btn_remove.clicked.connect(self.remove_selected)
        btn_clear.clicked.connect(self.clear_all)
        btn_about.clicked.connect(self.show_about)
        self.btn_prev.clicked.connect(self.prev)
        self.btn_next.clicked.connect(lambda: self.next(auto=False))
        self.btn_stop.clicked.connect(self.player.stop)
        self.btn_play.clicked.connect(self.toggle)
        self.btn_shuffle.toggled.connect(lambda v: setattr(self, "shuffle", v))
        self.btn_repeat.clicked.connect(self.cycle_repeat)
        self.theme_box.currentTextChanged.connect(self.apply_theme)
        self.playlist.itemDoubleClicked.connect(lambda _: self.play_index(self.playlist.currentRow()))
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.mediaStatusChanged.connect(self.on_status)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

        self.volume.setValue(70)
        self.load_state()

    # ----- visualizer -----
    def on_buffer(self, buf):
        try:
            lv = spectrum(buf, BANDS)
            if lv is not None:
                self.bars.push(lv)
        except Exception:
            self.fake = True  # fall back to animated bars

    def tick(self):
        if self.fake and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.bars.push(np.random.rand(BANDS) * np.linspace(0.9, 0.3, BANDS))
        self.bars.decay()

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
            self, "Add audio files", str(Path.home()), "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)")
        self.add_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder", str(Path.home()))
        if d:
            self.add_paths(sorted(str(p) for p in Path(d).rglob("*") if p.is_file()))

    def remove_selected(self):
        row = self.playlist.currentRow()
        if row < 0:
            return
        self.playlist.takeItem(row)
        del self.tracks[row]
        self.history.clear()
        if row == self.index:
            self.player.stop()
            self.index = -1
        elif row < self.index:
            self.index -= 1

    def clear_all(self):
        self.player.stop()
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
            paths += [str(x) for x in p.rglob("*")] if p.is_dir() else [str(p)]
        self.add_paths(sorted(paths))

    # ----- playback -----
    def show_meta(self, path):
        if not path:
            self.lbl_title.setText("No track loaded")
            self.lbl_artist.setText("")
            self.lbl_album.setText("")
            self.art.clear()
            self.art.setText("♪")
            return
        m = read_meta(path)
        self.lbl_title.setText(m["title"])
        self.lbl_artist.setText(m["artist"])
        self.lbl_album.setText(m["album"])
        if m["art"]:
            self.art.setPixmap(m["art"].scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        else:
            self.art.clear()
            self.art.setText("♪")

    def play_index(self, i, from_history=False, play=True):
        if not 0 <= i < len(self.tracks):
            return
        if self.index >= 0 and not from_history and i != self.index:
            self.history.append(self.index)
        self.index = i
        self.playlist.setCurrentRow(i)
        self.player.setSource(QUrl.fromLocalFile(self.tracks[i]))
        self.show_meta(self.tracks[i])
        if play:
            self.player.play()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.index == -1:
            self.play_index(max(0, self.playlist.currentRow()))
        else:
            self.player.play()

    def next(self, auto=False):
        n = len(self.tracks)
        if not n:
            return
        if auto and self.repeat == 2:
            self.player.setPosition(0)
            self.player.play()
            return
        if self.shuffle and n > 1:
            self.play_index(random.choice([i for i in range(n) if i != self.index]))
            return
        nxt = self.index + 1
        if nxt >= n:
            if auto and self.repeat == 0:
                self.player.stop()
                return
            nxt = 0
        self.play_index(nxt)

    def prev(self):
        if self.player.position() > 3000:
            self.player.setPosition(0)
        elif self.history:
            self.play_index(self.history.pop(), from_history=True)
        elif self.index > 0:
            self.play_index(self.index - 1, from_history=True)

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        self.btn_repeat.setText(REPEAT_LABELS[self.repeat])

    def on_status(self, s):
        if s == QMediaPlayer.MediaStatus.EndOfMedia:
            self.next(auto=True)

    def on_position(self, pos):
        if not self.seek.isSliderDown():
            self.seek.setValue(pos)
        self.time.setText(f"{fmt(pos)} / {fmt(self.player.duration())}")

    def on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setText("⏸" if playing else "▶")

    # ----- theme -----
    def apply_theme(self, name):
        QApplication.instance().setPalette(make_palette(name))
        self.setStyleSheet(GREEN_QSS if name == "Green on Black" else "")

    # ----- about -----
    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        lay = QVBoxLayout(dlg)
        logo = QLabel()
        pm = QPixmap(resource("icon.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
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
                "repeat": self.repeat, "theme": self.theme_box.currentText()}
        try:
            state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def load_state(self):
        try:
            d = json.loads(state_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.apply_theme("Dark")
            self.theme_box.setCurrentText("Dark")
            return
        self.volume.setValue(d.get("volume", 70))
        self.btn_shuffle.setChecked(d.get("shuffle", False))
        self.repeat = d.get("repeat", 0)
        self.btn_repeat.setText(REPEAT_LABELS[self.repeat])
        theme = d.get("theme", "Dark")
        self.theme_box.setCurrentText(theme)
        self.apply_theme(theme)
        self.add_paths(d.get("tracks", []), autoplay=False)
        idx = d.get("index", -1)
        if 0 <= idx < len(self.tracks):
            self.play_index(idx, play=False)

    def closeEvent(self, e):
        self.save_state()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    w = Player()
    w.show()
    sys.exit(app.exec())
