# Optional Qt6 (PySide6) status window for the server.
#
# Shows current text/image indices with Prev / Next / Toggle buttons.
# Provides file/folder pickers to change sources on the fly,
# minimise-to-tray support, and a tray context menu with "Show Window".
#
# This module is only imported when the server starts *without* --no-gui.

import os
import signal
import sys
from importlib.resources import files

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from .desktop_entry import create_desktop_entry
from .server import Server


def _load_icon() -> QIcon:
    """Load the app icon (SVG rendered via QSvgRenderer, PNG fallback)."""
    from PySide6.QtCore import QByteArray, QRect
    from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen
    from PySide6.QtSvg import QSvgRenderer

    res = files("media_overlay_switchboard.resources")

    # Try SVG rendered at native size, then scaled for each target
    svg = res / "Lavers.svg"
    if svg.is_file():
        svg_bytes = QByteArray(svg.read_bytes())
        renderer = QSvgRenderer(svg_bytes)
        if renderer.isValid():
            icon = QIcon()
            native = renderer.defaultSize()
            # Render at native size for the base pixmap
            pm = QPixmap(native)
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pm)
            # Add smaller sizes by scaling the base pixmap
            for size in (16, 22, 32, 48, 64):
                scaled = pm.scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon.addPixmap(scaled)
            return icon

    # Fall back to PNG
    png = res / "Lavers.png"
    if png.is_file():
        return QIcon(str(png))

    # Last resort: draw a green square
    pm = QPixmap(16, 16)
    pm.fill(QColor("#4CAF50"))
    return QIcon(pm)


class MainWindow(QMainWindow):
    """Main GUI window that displays current overlay state and lets the
    user control it via buttons."""

    def __init__(self, server: Server, suffix: str) -> None:
        super().__init__()
        self.server = server
        self.suffix = suffix

        self.setWindowTitle(f"Media Overlay Switchboard [{suffix}]")
        self.setWindowIcon(_load_icon())
        self.setMinimumSize(480, 450)

        # ---------- central widget ----------
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # --- title label -------------------------------------------------
        title = QLabel(f"Media Overlay Switchboard  \u2014  {suffix}")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title.setFont(title_font)
        layout.addWidget(title)

        # --- text group --------------------------------------------------
        text_grp = QGroupBox("Text Overlay")
        tx = QVBoxLayout(text_grp)

        scroll_text = QScrollArea()
        scroll_text.setWidgetResizable(True)
        scroll_text.setMinimumHeight(60)
        self.lbl_text = QLabel("No text loaded")
        self.lbl_text.setAlignment(Qt.AlignTop)
        self.lbl_text.setWordWrap(True)
        scroll_text.setWidget(self.lbl_text)
        tx.addWidget(scroll_text, 1)

        nav_row = QHBoxLayout()
        self.btn_text_prev = QPushButton("\u25c0 Prev")
        self.btn_text_next = QPushButton("Next \u25b6")
        self.btn_text_toggle = QPushButton("Toggle Hide")
        nav_row.addWidget(self.btn_text_prev)
        nav_row.addWidget(self.btn_text_next)
        nav_row.addWidget(self.btn_text_toggle)
        tx.addLayout(nav_row)

        source_row = QHBoxLayout()
        self.btn_text_file = QPushButton("Select Text File\u2026")
        self.lbl_text_path = QLabel("")
        self.lbl_text_path.setStyleSheet("color: #888;")
        source_row.addWidget(self.btn_text_file)
        source_row.addWidget(self.lbl_text_path, 1)
        tx.addLayout(source_row)

        layout.addWidget(text_grp, 1)

        # --- image group -------------------------------------------------
        img_grp = QGroupBox("Image Overlay")
        im = QVBoxLayout(img_grp)

        scroll_image = QScrollArea()
        scroll_image.setWidgetResizable(True)
        scroll_image.setFixedHeight(40)
        self.lbl_image = QLabel("No image loaded")
        self.lbl_image.setWordWrap(True)
        self.lbl_image.setAlignment(Qt.AlignTop)
        scroll_image.setWidget(self.lbl_image)
        im.addWidget(scroll_image, 1)

        nav_row2 = QHBoxLayout()
        self.btn_image_prev = QPushButton("\u25c0 Prev")
        self.btn_image_next = QPushButton("Next \u25b6")
        self.btn_image_toggle = QPushButton("Toggle Hide")
        nav_row2.addWidget(self.btn_image_prev)
        nav_row2.addWidget(self.btn_image_next)
        nav_row2.addWidget(self.btn_image_toggle)
        im.addLayout(nav_row2)

        source_row2 = QHBoxLayout()
        self.btn_image_folder = QPushButton("Select Images Folder\u2026")
        self.lbl_image_path = QLabel("")
        self.lbl_image_path.setStyleSheet("color: #888;")
        source_row2.addWidget(self.btn_image_folder)
        source_row2.addWidget(self.lbl_image_path, 1)
        im.addLayout(source_row2)

        # placeholder size row (inside Image Overlay box)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Placeholder size:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 99999)
        self.spin_width.setValue(server.config.transparent_width)
        self.spin_width.valueChanged.connect(self._on_size_changed)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(1, 99999)
        self.spin_height.setValue(server.config.transparent_height)
        self.spin_height.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.spin_width)
        size_row.addWidget(QLabel("x"))
        size_row.addWidget(self.spin_height)
        size_row.addStretch()
        im.addLayout(size_row)

        layout.addWidget(img_grp, 0)

        # --- target folder row -------------------------------------------
        target_row = QHBoxLayout()
        self.btn_target_folder = QPushButton("Select Target Folder\u2026")
        self.lbl_target_path = QLabel("")
        self.lbl_target_path.setStyleSheet("color: #888;")
        target_row.addWidget(self.btn_target_folder)
        target_row.addWidget(self.lbl_target_path, 1)
        layout.addLayout(target_row)

        # --- bottom row --------------------------------------------------
        bottom = QHBoxLayout()
        self.btn_desktop_entry = QPushButton("Create Desktop Entry")
        self.btn_quit = QPushButton("Quit")
        self.btn_hide_tray = QPushButton("Hide to Tray")
        bottom.addWidget(self.btn_desktop_entry, 1)
        bottom.addWidget(self.btn_hide_tray, 1)
        bottom.addWidget(self.btn_quit, 1)
        layout.addLayout(bottom)

        # ---------- signals -----------------------------------------------
        self.btn_text_prev.clicked.connect(self._on_text_prev)
        self.btn_text_next.clicked.connect(self._on_text_next)
        self.btn_text_toggle.clicked.connect(self._on_text_toggle)
        self.btn_text_file.clicked.connect(self._on_select_text_file)
        self.btn_image_prev.clicked.connect(self._on_image_prev)
        self.btn_image_next.clicked.connect(self._on_image_next)
        self.btn_image_toggle.clicked.connect(self._on_image_toggle)
        self.btn_image_folder.clicked.connect(self._on_select_image_folder)
        self.btn_target_folder.clicked.connect(self._on_select_target_folder)
        self.btn_desktop_entry.clicked.connect(self._on_create_desktop_entry)
        self.btn_hide_tray.clicked.connect(self.hide)
        self.btn_quit.clicked.connect(self._quit_app)

        # ---------- tray --------------------------------------------------
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(_load_icon())
        self.tray_icon.setToolTip(f"MOS [{suffix}]")

        tray_menu = QMenu()
        show_act = QAction("Show Window", self)
        show_act.triggered.connect(self.show)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self._quit_app)
        tray_menu.addAction(show_act)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_act)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # ---------- refresh timer -----------------------------------------
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

        self._refresh()

    # ---- navigation handlers ---------------------------------------------

    def _on_text_prev(self) -> None:
        self.server.cmd_text_prev()
        self._refresh()

    def _on_text_next(self) -> None:
        self.server.cmd_text_next()
        self._refresh()

    def _on_text_toggle(self) -> None:
        self.server.cmd_text_toggle()
        self._refresh()

    def _on_image_prev(self) -> None:
        self.server.cmd_image_prev()
        self._refresh()

    def _on_image_next(self) -> None:
        self.server.cmd_image_next()
        self._refresh()

    def _on_image_toggle(self) -> None:
        self.server.cmd_image_toggle()
        self._refresh()

    # ---- source-selection handlers ---------------------------------------

    def _on_select_text_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Text File", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        self.server.config.text_file = path
        self.server.config.save(self.server.suffix)
        self.server.reload()
        self._refresh()

    def _on_select_image_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Images Folder", "", QFileDialog.Option.ShowDirsOnly
        )
        if not path:
            return
        self.server.config.images_folder = path
        self.server.config.save(self.server.suffix)
        self.server.reload()
        self._refresh()

    def _on_select_target_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Target Folder", "", QFileDialog.Option.ShowDirsOnly
        )
        if not path:
            return
        self.server.config.target_folder = path
        self.server.config.save(self.server.suffix)
        self.server.reload()
        self._refresh()

    # ---- placeholder size -------------------------------------------------

    def _on_size_changed(self) -> None:
        self.server.config.transparent_width = self.spin_width.value()
        self.server.config.transparent_height = self.spin_height.value()
        self.server.config.save(self.server.suffix)
        self.server.reload()

    # ---- display update --------------------------------------------------

    def _refresh(self) -> None:
        st = self.server.get_status()

        # text label
        if st["text_total"] > 0:
            label = (
                f"Entry {st['text_index'] + 1} / {st['text_total']}"
                f"{'  (HIDDEN)' if st['text_hidden'] else ''}"
            )
            entry = st.get("text_entry", "")
            if entry:
                label += f"\n{entry}"
            self.lbl_text.setText(label)
        else:
            self.lbl_text.setText("No text loaded  (select a text file)")

        # text path
        p = self.server.config.text_file
        self.lbl_text_path.setText(p if p else "")

        # image label
        if st["image_total"] > 0:
            label = (
                f"Image {st['image_index'] + 1} / {st['image_total']}"
                f"{'  (HIDDEN)' if st['image_hidden'] else ''}"
            )
            fname = st.get("image_file", "")
            if fname:
                label += f"\n{fname}"
            self.lbl_image.setText(label)
        else:
            self.lbl_image.setText("No images loaded  (select an images folder)")

        # image path
        p = self.server.config.images_folder
        self.lbl_image_path.setText(p if p else "")

        # target path
        p = self.server.config.target_folder
        self.lbl_target_path.setText(p if p else "")

    # ---- tray (minimise-to-tray) -----------------------------------------

    def _on_tray_activated(self, reason: int) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.server.config.hide_to_tray_no_warn:
            self.hide()
            event.ignore()
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Media Overlay Switchboard")
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)

        msg = QLabel(
            "Closing this window will hide the application to the system tray."
        )
        msg.setWordWrap(True)
        lay.addWidget(msg)

        cb = QCheckBox("Don't show this message again")
        lay.addWidget(cb)

        btn_row = QHBoxLayout()
        hide_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        quit_btn = QPushButton("Quit Instead")
        btn_row.addWidget(hide_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(quit_btn)
        lay.addLayout(btn_row)

        action = [None]

        hide_btn.clicked.connect(lambda: action.__setitem__(0, "hide") or dlg.accept())
        cancel_btn.clicked.connect(lambda: action.__setitem__(0, "cancel") or dlg.reject())
        quit_btn.clicked.connect(lambda: action.__setitem__(0, "quit") or dlg.accept())

        dlg.exec()

        if action[0] == "quit":
            self._quit_app()
            event.accept()
        elif action[0] == "hide":
            if cb.isChecked():
                self.server.config.hide_to_tray_no_warn = True
                self.server.config.save(self.server.suffix)
            self.hide()
            event.ignore()
        else:
            event.ignore()

    def _on_create_desktop_entry(self) -> None:
        appimage = os.environ.get("APPIMAGE")
        result = create_desktop_entry(appimage, terminal=False)
        if result:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Desktop Entry Created",
                f"Desktop entry created at:\n{result}",
            )
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Error",
                "Failed to create desktop entry. See terminal for details.",
            )

    def _quit_app(self) -> None:
        self.tray_icon.hide()
        self.server.stop()
        QApplication.quit()

    # ---- lifecycle helpers for external callers ---------------------------

    def stop_server(self) -> None:
        self.server.stop()


def run_gui(server: Server, suffix: str) -> None:
    """Create the QApplication and MainWindow, then enter the event loop.

    Handles Ctrl+C cleanly by installing a SIGINT handler that quits
    the Qt event loop.  A background timer ensures Python signal
    handlers are polled regularly (Qt does not do this by itself).
    """
    app = QApplication.instance() or QApplication(sys.argv)

    icon = _load_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Allow Python signal handlers (e.g. SIGINT / Ctrl+C) to be
    # processed by waking the Qt event loop every 200 ms.
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(200)

    # On SIGINT quit the event loop cleanly instead of printing a
    # traceback from inside Qt's poll.
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())

    win = MainWindow(server, suffix)
    win.show()
    try:
        app.exec()
    finally:
        wake.stop()
        win.stop_server()
