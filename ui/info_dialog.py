from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)


class TransactionInfoDialog(QDialog):
    """Окно с исходным объектом операции из файла банка (JSON-текст)."""

    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Информация об операции")
        self.resize(720, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setPlainText(text)
        layout.addWidget(self.text, 1)

        buttons = QDialogButtonBox()
        copy_btn = buttons.addButton("Копировать", QDialogButtonBox.ButtonRole.ActionRole)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text))
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
