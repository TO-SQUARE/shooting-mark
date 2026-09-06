from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


ASSET_DIR = Path(__file__).resolve().parent
SVG_DIR = ASSET_DIR / "data"


def list_windows() -> list[tuple[int, str]]:
    if sys.platform != "win32":
        return []
    windows: list[tuple[int, str]] = []
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        state = " (minimized)" if user32.IsIconic(hwnd) else ""
        windows.append((int(hwnd), f"{title.value}{state}"))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def window_geometry(hwnd: int) -> QRect | None:
    if sys.platform != "win32":
        return None
    rect = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


class NativeMessage(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("w_param", ctypes.c_size_t),
        ("l_param", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("point_x", ctypes.c_long),
        ("point_y", ctypes.c_long),
    ]


class CrosshairCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.renderer: QSvgRenderer | None = None
        self.tint = QColor("#ff3030")
        self.opacity = 1.0
        self.crosshair_size = 72
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_svg(self, path: Path) -> None:
        self.renderer = QSvgRenderer(str(path), self)
        self.update()

    def set_tint(self, color: QColor) -> None:
        self.tint = color
        self.update()

    def paintEvent(self, event) -> None:
        if self.renderer is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)
        bounds = QRect(
            (self.width() - self.crosshair_size) // 2,
            (self.height() - self.crosshair_size) // 2,
            self.crosshair_size,
            self.crosshair_size,
        )
        self.renderer.render(painter, bounds)


class OverlayWindow(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.canvas = CrosshairCanvas(self)
        self.asset_path: Path | None = None
        self.target_hwnd: int | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self._make_click_through()

    def set_screen(self, screen) -> None:
        self.target_hwnd = None
        self.setGeometry(screen.geometry())

    def set_target_window(self, hwnd: int | None) -> None:
        self.target_hwnd = hwnd
        self.update_target_geometry()

    def update_target_geometry(self) -> None:
        if self.target_hwnd is None:
            return
        if sys.platform == "win32" and not ctypes.windll.user32.IsWindow(self.target_hwnd):
            self.target_hwnd = None
            return
        if sys.platform == "win32" and ctypes.windll.user32.IsIconic(self.target_hwnd):
            return
        geometry = window_geometry(self.target_hwnd)
        if geometry is not None and geometry.width() > 0 and geometry.height() > 0:
            self.setGeometry(geometry)
            self._raise_above_target()

    def _raise_above_target(self) -> None:
        if sys.platform != "win32" or not self.winId():
            return
        user32 = ctypes.windll.user32
        hwnd = int(self.winId())
        hwnd_insert_after = ctypes.c_void_p(-1)  # HWND_TOPMOST
        flags = 0x0001 | 0x0002 | 0x0010 | 0x0040  # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
        user32.SetWindowPos(hwnd, hwnd_insert_after, 0, 0, 0, 0, flags)

    def set_asset(self, path: Path) -> None:
        self.asset_path = path
        self.canvas.set_svg(path)

    def set_size(self, value: int) -> None:
        self.canvas.crosshair_size = value
        self.canvas.update()

    def resizeEvent(self, event) -> None:
        self.canvas.setGeometry(self.rect())
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._make_click_through()
        self._raise_above_target()

    def _make_click_through(self) -> None:
        if sys.platform != "win32" or not self.winId():
            return
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, -20)
        no_activate = 0x08000000
        user32.SetWindowLongW(hwnd, -20, ex_style | 0x20 | 0x80000 | no_activate)


class GlobalHotkeyFilter(QObject, QAbstractNativeEventFilter):
    hotkey_pressed = Signal()

    def __init__(self) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self.registered = False
        if sys.platform == "win32":
            self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, 1, 0x0002 | 0x0004, 0x43))

    def nativeEventFilter(self, event_type, message):
        if self.registered and sys.platform == "win32":
            native_message = ctypes.cast(int(message), ctypes.POINTER(NativeMessage)).contents
            if native_message.message == 0x0312:
                self.hotkey_pressed.emit()
                return True, 0
        return False, 0

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, 1)
            self.registered = False


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = CrosshairCanvas(self)
        self.canvas.setMinimumSize(QSize(160, 160))

    def set_asset(self, path: Path) -> None:
        self.canvas.set_svg(path)

    def set_size(self, value: int) -> None:
        self.canvas.crosshair_size = value
        self.canvas.update()

    def resizeEvent(self, event) -> None:
        self.canvas.setGeometry(self.rect())
        super().resizeEvent(event)


class ControlPanel(QMainWindow):
    settings_changed = Signal(Path, int, int, int)

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.assets = sorted(SVG_DIR.glob("*.svg"))
        self.overlay = OverlayWindow()
        self.hotkey_filter = GlobalHotkeyFilter()
        self.app.installNativeEventFilter(self.hotkey_filter)
        self.target_timer = QTimer(self)
        self.target_timer.setInterval(100)
        self.target_timer.timeout.connect(self.overlay.update_target_geometry)
        self.current_asset = self.assets[0] if self.assets else None
        self._build_ui()
        self._connect_signals()
        self._load_initial_state()

    def _build_ui(self) -> None:
        self.setWindowTitle("Shooting Mark")
        self.setMinimumSize(520, 680)
        self.setWindowIcon(QIcon(str(ASSET_DIR / "shooting-mark.png")))

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Shooting Mark")
        title.setObjectName("title")
        self.about_button = QPushButton("About")
        self.about_button.setObjectName("about")
        self.about_button.setToolTip("About Shooting Mark")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.about_button)
        layout.addLayout(header)

        subtitle = QLabel("Choose a design, tune its appearance, and keep it centered.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        self.preview = PreviewWidget()
        self.preview.setObjectName("preview")
        layout.addWidget(self.preview)

        design_group = QGroupBox("Design library")
        design_layout = QVBoxLayout(design_group)
        self.asset_list = QListWidget()
        self.asset_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.asset_list.setIconSize(QSize(72, 72))
        self.asset_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.asset_list.setMovement(QListWidget.Movement.Static)
        self.asset_list.setSpacing(8)
        for asset in self.assets:
            item = QListWidgetItem(self._asset_icon(asset), asset.stem.replace("-", " ").title())
            item.setData(Qt.ItemDataRole.UserRole, str(asset))
            self.asset_list.addItem(item)
        design_layout.addWidget(self.asset_list)
        layout.addWidget(design_group)

        controls = QGroupBox("Appearance")
        form = QFormLayout(controls)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(16, 240)
        self.size_slider.setValue(72)
        self.size_value = QSpinBox()
        self.size_value.setRange(16, 240)
        self.size_value.setValue(72)
        size_row = QHBoxLayout()
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_value)
        form.addRow("Size", size_row)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_value = QSpinBox()
        self.opacity_value.setRange(20, 100)
        self.opacity_value.setSuffix(" %")
        self.opacity_value.setValue(100)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value)
        form.addRow("Opacity", opacity_row)

        self.screen_combo = QComboBox()
        self._refresh_screens()
        form.addRow("Display", self.screen_combo)
        layout.addWidget(controls)

        target_group = QGroupBox("Overlay location")
        target_layout = QFormLayout(target_group)
        self.location_combo = QComboBox()
        self.location_combo.addItem("Center on selected display", "screen")
        self.location_combo.addItem("Attach to a window", "window")
        target_layout.addRow("Mode", self.location_combo)
        window_row = QHBoxLayout()
        self.window_combo = QComboBox()
        self.refresh_windows_button = QPushButton("Refresh")
        window_row.addWidget(self.window_combo, 1)
        window_row.addWidget(self.refresh_windows_button)
        target_layout.addRow("Window", window_row)
        layout.addWidget(target_group)

        actions = QHBoxLayout()
        self.toggle_button = QPushButton("Show crosshair")
        self.toggle_button.setObjectName("primary")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.close_button = QPushButton("Exit")
        actions.addWidget(self.toggle_button, 1)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        hint = QLabel("Global shortcut: Ctrl+Shift+C toggles visibility")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.setStyleSheet(
            """
            QWidget#root { background: #11161d; color: #f4f8fc; }
            QWidget#root QLabel, QWidget#root QGroupBox { color: #f4f8fc; }
            QLabel#title { color: #f3f7fb; font-size: 25px; font-weight: 700; }
            QLabel#subtitle, QLabel#hint { color: #a9d8ee; }
            QGroupBox { color: #dcefff; border: 1px solid #293441; border-radius: 8px; margin-top: 10px; padding: 15px 12px 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #b4c1cf; }
            QWidget#preview { background: #202a35; border: 1px solid #364454; border-radius: 8px; }
            QListWidget { background: #171e27; border: 1px solid #293441; border-radius: 6px; outline: 0; }
            QListWidget::item { color: #f4f8fc; padding: 6px; border-radius: 6px; }
            QListWidget::item:selected { background: #2c5360; color: #ffffff; }
            QSlider::groove:horizontal { height: 4px; background: #344150; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #5bd0bb; }
            QSpinBox, QComboBox { min-height: 28px; background: #1a222c; color: #f4f8fc; border: 1px solid #354252; border-radius: 5px; padding: 0 7px; }
            QComboBox QAbstractItemView { background: #1a222c; color: #f4f8fc; selection-background-color: #2c5360; selection-color: #ffffff; }
            QPushButton { min-height: 36px; padding: 0 18px; border: 1px solid #3c4b5c; border-radius: 5px; background: #202b37; color: #e9eef5; }
            QPushButton:hover { background: #2b3948; }
            QPushButton#primary { background: #237e72; border-color: #4bb9a7; font-weight: 700; }
            QPushButton#primary:checked { background: #2d3945; border-color: #56687b; }
            """
        )

    def _connect_signals(self) -> None:
        self.asset_list.currentItemChanged.connect(self._asset_changed)
        self.size_slider.valueChanged.connect(self.size_value.setValue)
        self.size_value.valueChanged.connect(self.size_slider.setValue)
        self.size_value.valueChanged.connect(self._size_changed)
        self.opacity_slider.valueChanged.connect(self.opacity_value.setValue)
        self.opacity_value.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity_value.valueChanged.connect(self._opacity_changed)
        self.screen_combo.currentIndexChanged.connect(self._screen_changed)
        self.location_combo.currentIndexChanged.connect(self._location_changed)
        self.window_combo.currentIndexChanged.connect(self._window_changed)
        self.refresh_windows_button.clicked.connect(self._refresh_windows)
        self.toggle_button.toggled.connect(self._visibility_changed)
        self.close_button.clicked.connect(self.close)
        self.about_button.clicked.connect(self._show_about)
        self.hotkey_filter.hotkey_pressed.connect(self._toggle_visibility)
        self.app.screenAdded.connect(self._refresh_screens)
        self.app.screenRemoved.connect(self._refresh_screens)
        self._refresh_windows()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Shooting Mark",
            "<h2>Shooting Mark</h2>"
            "<p>It is a simple tool that displays a customizable crosshair "
            "over the screen or a selected window.</p>"
            "<p>It offers multiple designs, adjustable size and opacity, "
            "multi-monitor support, and the ability to show or hide the "
            "crosshair using the <b>Ctrl+Shift+C</b> shortcut.</p>"
            "<p>Created by <b>TOSQUARE0</b>.</p>",
        )

    def _load_initial_state(self) -> None:
        if not self.assets:
            self.toggle_button.setEnabled(False)
            return
        self.asset_list.setCurrentRow(0)
        self._screen_changed(0)
        self.overlay.show()

    def _refresh_windows(self) -> None:
        selected = self.window_combo.currentData()
        own_hwnd = int(self.winId()) if self.winId() else 0
        overlay_hwnd = int(self.overlay.winId()) if self.overlay.winId() else 0
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        for hwnd, title in list_windows():
            if hwnd in (own_hwnd, overlay_hwnd):
                continue
            self.window_combo.addItem(title, hwnd)
        self.window_combo.blockSignals(False)
        if selected is not None:
            for index in range(self.window_combo.count()):
                if self.window_combo.itemData(index) == selected:
                    self.window_combo.setCurrentIndex(index)
                    break

    def _location_changed(self, index: int) -> None:
        is_window_mode = self.location_combo.itemData(index) == "window"
        self.window_combo.setEnabled(is_window_mode)
        self.refresh_windows_button.setEnabled(is_window_mode)
        if is_window_mode:
            self._window_changed(self.window_combo.currentIndex())
            self.target_timer.start()
        else:
            self.target_timer.stop()
            self._screen_changed(self.screen_combo.currentIndex())

    def _window_changed(self, index: int) -> None:
        if self.location_combo.currentData() != "window" or index < 0:
            return
        hwnd = self.window_combo.itemData(index)
        self.overlay.set_target_window(int(hwnd) if hwnd is not None else None)

    def _asset_icon(self, path: Path) -> QIcon:
        image = QImage(72, 72, QImage.Format.Format_ARGB32)
        image.fill(QColor("#202a35"))
        renderer = QSvgRenderer(str(path))
        painter = QPainter(image)
        renderer.render(painter, QRect(9, 9, 54, 54))
        painter.end()
        return QIcon(QPixmap.fromImage(image))

    def _asset_changed(self, item: QListWidgetItem | None, previous) -> None:
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self.current_asset = path
        self.preview.set_asset(path)
        self.overlay.set_asset(path)

    def _size_changed(self, value: int) -> None:
        self.preview.set_size(value)
        self.overlay.set_size(value)

    def _opacity_changed(self, value: int) -> None:
        opacity = value / 100
        self.preview.canvas.opacity = opacity
        self.overlay.canvas.opacity = opacity
        self.preview.canvas.update()
        self.overlay.canvas.update()

    def _refresh_screens(self, *args) -> None:
        selected = self.screen_combo.currentData()
        self.screen_combo.blockSignals(True)
        self.screen_combo.clear()
        primary_screen = self.app.primaryScreen()
        for index, screen in enumerate(self.app.screens()):
            geometry = screen.geometry()
            primary_label = " - Main display" if screen is primary_screen else ""
            label = (
                f"Display {index + 1}: {screen.name()} | "
                f"{geometry.width()} x {geometry.height()} px | "
                f"position {geometry.x()}, {geometry.y()}{primary_label}"
            )
            self.screen_combo.addItem(label, screen)
        self.screen_combo.blockSignals(False)
        if selected is not None:
            for index in range(self.screen_combo.count()):
                if self.screen_combo.itemData(index) is selected:
                    self.screen_combo.setCurrentIndex(index)
                    break
        self._screen_changed(self.screen_combo.currentIndex())

    def _screen_changed(self, index: int) -> None:
        if hasattr(self, "location_combo") and self.location_combo.currentData() == "window":
            return
        if index < 0:
            return
        screen = self.screen_combo.itemData(index)
        if screen is not None:
            self.overlay.set_screen(screen)

    def _visibility_changed(self, visible: bool) -> None:
        self.toggle_button.setText("Hide crosshair" if visible else "Show crosshair")
        self.overlay.setVisible(visible)

    def _toggle_visibility(self) -> None:
        self.toggle_button.setChecked(not self.toggle_button.isChecked())

    def closeEvent(self, event) -> None:
        self.hotkey_filter.unregister()
        self.overlay.close()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Shooting Mark")
    app.setWindowIcon(QIcon(str(ASSET_DIR / "shooting-mark.png")))
    window = ControlPanel(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())