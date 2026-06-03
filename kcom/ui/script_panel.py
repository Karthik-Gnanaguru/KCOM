"""Script panel — Python script editor with output dock.

Provides a QPlainTextEdit code editor with Python syntax highlighting,
a toolbar (Run / Stop / Open / Save / Clear), and a read-only output pane
that receives text from ScriptRuntime.log_output.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Python syntax highlighter
# ---------------------------------------------------------------------------

class _PythonHighlighter(QSyntaxHighlighter):
    """Minimal Python syntax highlighter — keywords, strings, comments, numbers."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple] = []
        self._build_rules()

    def _fmt(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(700)
        if italic:
            f.setFontItalic(True)
        return f

    def _build_rules(self) -> None:
        import re

        kw_fmt   = self._fmt("#569cd6", bold=True)
        blt_fmt  = self._fmt("#4ec9b0")
        str_fmt  = self._fmt("#ce9178")
        cmt_fmt  = self._fmt("#6a9955", italic=True)
        num_fmt  = self._fmt("#b5cea8")
        deco_fmt = self._fmt("#dcdcaa")

        keywords = (
            "False None True and as assert async await break class continue def "
            "del elif else except finally for from global if import in is lambda "
            "nonlocal not or pass raise return try while with yield"
        ).split()

        builtins = (
            "abs all any bin bool bytes callable chr dict dir divmod enumerate "
            "eval exec filter float format frozenset getattr globals hasattr hash "
            "help hex id input int isinstance issubclass iter len list locals map "
            "max min next object open ord pow print property range repr reversed "
            "round set setattr slice sorted staticmethod str sum super tuple type "
            "vars zip"
        ).split()

        for kw in keywords:
            self._rules.append((re.compile(rf"\b{kw}\b"), kw_fmt))
        for blt in builtins:
            self._rules.append((re.compile(rf"\b{blt}\b"), blt_fmt))

        # Decorators
        self._rules.append((re.compile(r"@\w+"), deco_fmt))
        # Numbers (int, float, hex, binary)
        self._rules.append((re.compile(r"\b(0x[\da-fA-F]+|0b[01]+|\d+\.?\d*([eE][+-]?\d+)?)\b"), num_fmt))
        # Single-quoted strings (non-greedy, no newline)
        self._rules.append((re.compile(r"'[^'\n\\]*(?:\\.[^'\n\\]*)*'"), str_fmt))
        self._rules.append((re.compile(r'"[^"\n\\]*(?:\\.[^"\n\\]*)*"'), str_fmt))
        # Comments
        self._rules.append((re.compile(r"#[^\n]*"), cmt_fmt))

        # Multi-line string state markers stored separately
        self._triple_single = re.compile(r"'''")
        self._triple_double = re.compile(r'"""')
        self._str_fmt = str_fmt

    def highlightBlock(self, text: str) -> None:
        # Apply single-line rules first
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Multi-line triple-quoted strings: state 1 = inside '''  state 2 = inside """
        self.setCurrentBlockState(0)
        prev = self.previousBlockState()

        for state, open_re, close_re in (
            (1, self._triple_single, self._triple_single),
            (2, self._triple_double, self._triple_double),
        ):
            start = 0
            if prev == state:
                # Already inside a triple-quoted block
                m = close_re.search(text, start)
                if m:
                    length = m.end() - start
                    self.setFormat(start, length, self._str_fmt)
                    start = m.end()
                else:
                    self.setCurrentBlockState(state)
                    self.setFormat(start, len(text) - start, self._str_fmt)
                    return

            while start < len(text):
                om = open_re.search(text, start)
                if om is None:
                    break
                cm = close_re.search(text, om.end())
                if cm:
                    length = cm.end() - om.start()
                    self.setFormat(om.start(), length, self._str_fmt)
                    start = cm.end()
                else:
                    self.setCurrentBlockState(state)
                    self.setFormat(om.start(), len(text) - om.start(), self._str_fmt)
                    return


# ---------------------------------------------------------------------------
# ScriptPanel
# ---------------------------------------------------------------------------

_TOOLBAR_BTN = (
    "QPushButton { background: #21262d; color: #e6edf3; border: 1px solid #30363d; "
    "border-radius: 5px; padding: 4px 10px; font-size: 12px; }"
    "QPushButton:hover { background: #30363d; }"
    "QPushButton:disabled { color: #6e7681; border-color: #21262d; background: #161b22; }"
)
_RUN_STYLE = (
    "QPushButton { background: #238636; color: #ffffff; border: 1px solid #2ea043; "
    "border-radius: 5px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
    "QPushButton:hover { background: #2ea043; }"
    "QPushButton:disabled { background: #21262d; color: #6e7681; border-color: #30363d; }"
)
_STOP_STYLE = (
    "QPushButton { background: #da3633; color: #ffffff; border: 1px solid #f85149; "
    "border-radius: 5px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
    "QPushButton:hover { background: #f85149; }"
    "QPushButton:disabled { background: #21262d; color: #6e7681; border-color: #30363d; }"
)


class ScriptPanel(QWidget):
    """Python script editor + output console.

    Signals
    -------
    run_requested(code, filename)
        Emitted when the user clicks Run.  *code* is the editor text;
        *filename* is the current file path (or ``<script>`` if unsaved).
    stop_requested
        Emitted when the user clicks Stop.
    """

    run_requested:  Signal = Signal(str, str)   # (code, filename)
    stop_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_file: str = ""
        self._modified = False
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Toolbar -------------------------------------------------
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(4)

        self._run_btn = QPushButton("▶  Run")
        self._run_btn.setStyleSheet(_RUN_STYLE)
        self._run_btn.setToolTip("Run script (F5)")
        self._run_btn.setShortcut(QKeySequence("F5"))
        toolbar.addWidget(self._run_btn)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setStyleSheet(_STOP_STYLE)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setToolTip("Stop script")
        toolbar.addWidget(self._stop_btn)

        toolbar.addSpacing(8)

        self._open_btn = QPushButton("Open…")
        self._open_btn.setStyleSheet(_TOOLBAR_BTN)
        self._open_btn.setToolTip("Open a Python script file")
        toolbar.addWidget(self._open_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(_TOOLBAR_BTN)
        self._save_btn.setToolTip("Save script (Ctrl+S)")
        self._save_btn.setShortcut(QKeySequence("Ctrl+S"))
        toolbar.addWidget(self._save_btn)

        self._saveas_btn = QPushButton("Save As…")
        self._saveas_btn.setStyleSheet(_TOOLBAR_BTN)
        self._saveas_btn.setToolTip("Save script to a new file")
        toolbar.addWidget(self._saveas_btn)

        toolbar.addStretch()

        self._clear_out_btn = QPushButton("Clear Output")
        self._clear_out_btn.setStyleSheet(_TOOLBAR_BTN)
        self._clear_out_btn.setToolTip("Clear output console")
        toolbar.addWidget(self._clear_out_btn)

        self._file_label = QLabel("<unsaved>")
        self._file_label.setStyleSheet("color: #7d8590; font-size: 11px; padding: 0 6px;")
        toolbar.addWidget(self._file_label)

        root.addLayout(toolbar)

        # ---- Splitter: editor (top) + output (bottom) ----------------
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(4)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setObjectName("scriptEditor")
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor_font = QFont("Monospace", 11)
        editor_font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._editor.setFont(editor_font)
        self._editor.setTabStopDistance(28)  # ~4 spaces at 7px/char
        self._editor.setPlaceholderText(
            "# Write Python here.  Use kcom.send(), kcom.log(), etc.\n"
            "# Press F5 (or the Run button) to execute."
        )
        self._highlighter = _PythonHighlighter(self._editor.document())
        splitter.addWidget(self._editor)

        # Output console
        self._output = QPlainTextEdit()
        self._output.setObjectName("scriptOutput")
        self._output.setReadOnly(True)
        out_font = QFont("Monospace", 10)
        out_font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._output.setFont(out_font)
        self._output.setMaximumBlockCount(2000)
        self._output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        splitter.addWidget(self._output)

        splitter.setSizes([350, 150])
        root.addWidget(splitter, stretch=1)

    def _connect_signals(self) -> None:
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn.clicked.connect(self.stop_requested)
        self._open_btn.clicked.connect(self._on_open)
        self._save_btn.clicked.connect(self._on_save)
        self._saveas_btn.clicked.connect(self._on_save_as)
        self._clear_out_btn.clicked.connect(self._output.clear)
        self._editor.document().contentsChanged.connect(self._on_editor_changed)

    # ------------------------------------------------------------------
    # Public slots — called by ScriptRuntime signals
    # ------------------------------------------------------------------

    def append_output(self, text: str) -> None:
        """Append a line to the output console (called from main thread)."""
        self._output.appendPlainText(text)
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum()
        )

    def on_script_started(self) -> None:
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self.append_output("▶  Script started")

    def on_script_finished(self) -> None:
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self.append_output("■  Script finished")

    def on_script_error(self, traceback_text: str) -> None:
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        for line in traceback_text.rstrip().splitlines():
            self.append_output(line)
        self.append_output("✖  Script error")

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        code = self._editor.toPlainText()
        filename = self._current_file or "<script>"
        self.run_requested.emit(code, filename)

    def _on_editor_changed(self) -> None:
        self._modified = True
        stem = os.path.basename(self._current_file) if self._current_file else "<unsaved>"
        self._file_label.setText(f"* {stem}")

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "", "Python Files (*.py);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                code = fh.read()
        except OSError as e:
            self.append_output(f"Open error: {e}")
            return
        self._editor.setPlainText(code)
        self._current_file = path
        self._modified = False
        self._file_label.setText(os.path.basename(path))

    def _on_save(self) -> None:
        if not self._current_file:
            self._on_save_as()
            return
        self._write_file(self._current_file)

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Script", self._current_file or "", "Python Files (*.py);;All Files (*)"
        )
        if not path:
            return
        self._write_file(path)
        self._current_file = path

    def _write_file(self, path: str) -> None:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._editor.toPlainText())
            self._modified = False
            self._file_label.setText(os.path.basename(path))
        except OSError as e:
            self.append_output(f"Save error: {e}")

    def load_file(self, path: str) -> None:
        """Load a script file from *path* (called by CLI --run)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                code = fh.read()
            self._editor.setPlainText(code)
            self._current_file = path
            self._modified = False
            self._file_label.setText(os.path.basename(path))
        except OSError as e:
            self.append_output(f"Load error: {e}")
