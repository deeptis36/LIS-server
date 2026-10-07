import os
import sys
import json
import logging
import traceback
from pathlib import Path

import requests
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QTextEdit, QFrame,
    QMessageBox,
)
from PySide6.QtCore import QProcess, Qt


# ============================================================
# ERBA / MultiXL Connector - Desktop UI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
LISTENER_DIR = BASE_DIR.parent / "py-script"
LISTENER_FILE = LISTENER_DIR / "erba_listener.py"
CONFIG_FILE = BASE_DIR / "erba_connector_config.json"
DEVICE_OPTIONS_FILE = BASE_DIR / "source_devices.json"
CONFIG_KEYS = (
    "analyzer_ip",
    "tcp_port",
    "source_device",
    "api_endpoint",
)

logging.basicConfig(
    filename=str(BASE_DIR / "erba_connector.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ERBAConnector")


class ERBAConnector(QWidget):

    def __init__(self):
        super().__init__()

        self.connected = False
        self.listener_process = None
        self.loading_config = False
        self.edit_mode = False
        self.config = self.load_config()

        try:
            self.setWindowTitle("Cocohospitals LIS - Analyzer Connector")
            self.resize(940, 720)
            self.create_ui()
            self.log_message("Application started successfully.")
            self.log_message(f"Listener: {LISTENER_FILE}")

            if not LISTENER_FILE.exists():
                self.log_message(
                    f"WARNING: Listener not found: {LISTENER_FILE}",
                    "WARNING",
                )
        except Exception as exc:
            logger.exception("Application initialization failed")
            self.show_error("Application Error", str(exc))

    # ========================================================
    # UI
    # ========================================================

    def create_ui(self):
        main = QVBoxLayout()
        main.setContentsMargins(28, 22, 28, 22)
        main.setSpacing(12)

        self.setStyleSheet("""
            QWidget {
                background:#eef3f7;
                color:#182434;
                font-family:Inter, Arial, sans-serif;
            }
            QLabel { background:transparent; }
        """)

        header = QFrame()
        header.setObjectName("Header")
        header.setStyleSheet("""
            #Header {
                background:#ffffff;
                border:1px solid #cfd9e5;
                border-radius:6px;
            }
            QLabel { background:transparent; border:0; }
            #BrandBadge {
                background:#eaf4fb;
                border:1px solid #bfd8ea;
                border-radius:4px;
                color:#0f4f7a;
                padding:8px 12px;
                font-size:12px;
                font-weight:800;
            }
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 13, 18, 13)
        hl.setSpacing(14)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)

        title = QLabel("COCOHOSPITALS LIS - Analyzer Connector")
        title.setStyleSheet(
            "color:#0f2f4f;font-size:25px;font-weight:800;"
        )
        subtitle = QLabel(
            "Laboratory Instrument Interface | ASTM TCP/IP"
        )
        subtitle.setStyleSheet(
            "color:#5b6f82;font-size:13px;font-weight:700;"
        )
        brand_badge = QLabel("COCOHOSPITALS LIS")
        brand_badge.setObjectName("BrandBadge")
        brand_badge.setAlignment(Qt.AlignCenter)

        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        hl.addLayout(title_stack)
        hl.addStretch()
        hl.addWidget(brand_badge)
        main.addWidget(header)

        card = QFrame()
        card.setObjectName("ConfigCard")
        card.setStyleSheet("""
            #ConfigCard {
                background:#ffffff;
                border:1px solid #cfd9e5;
                border-radius:6px;
            }
            QLabel {
                color:#25364a;
                font-size:13px;
                font-weight:800;
                border:0;
                background:transparent;
            }
            QLineEdit {
                background:#ffffff;
                border:1px solid #becbd8;
                border-radius:4px;
                padding:9px 11px;
                font-size:14px;
                color:#172033;
            }
            QLineEdit:focus {
                border:1px solid #0f6fa8;
                background:#fbfdff;
            }
            QLineEdit[readOnly="true"] {
                background:#f8fafc;
                color:#243447;
                border:1px solid #d6e0ea;
            }
            QComboBox {
                background:#ffffff;
                border:1px solid #becbd8;
                border-radius:4px;
                padding:9px 11px;
                font-size:14px;
                font-weight:700;
                color:#172033;
            }
            QComboBox QAbstractItemView {
                background:#ffffff;
                color:#172033;
                selection-background-color:#155f8c;
                selection-color:#ffffff;
                font-size:14px;
                font-weight:700;
                outline:0;
                border:1px solid #a9b8c8;
            }
            QComboBox:focus {
                border:1px solid #0f6fa8;
                background:#fbfdff;
            }
            QComboBox:disabled {
                background:#f8fafc;
                color:#243447;
                border:1px solid #d6e0ea;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 14)
        cl.setSpacing(12)

        ct = QLabel("Interface Configuration")
        ct.setStyleSheet(
            "font-size:16px;font-weight:800;color:#182434;border:0;"
        )
        cl.addWidget(ct)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.loading_config = True

        self.ip_input = QLineEdit(self.config["analyzer_ip"])
        self.ip_input.setPlaceholderText("Example: 10.10.10.2")
        form.addRow("Analyzer IP:", self.ip_input)

        self.port_input = QLineEdit(self.config["tcp_port"])
        self.port_input.setPlaceholderText("Example: 5002")
        form.addRow("TCP Port:", self.port_input)

        self.source_device_input = QComboBox()
        self.source_device_input.setEditable(True)
        self.source_device_input.setInsertPolicy(QComboBox.NoInsert)
        self.load_source_device_options()
        form.addRow("Source Device:", self.source_device_input)

        self.api_input = QLineEdit(self.config["api_endpoint"])
        form.addRow("API Endpoint:", self.api_input)

        self.loading_config = False

        cl.addLayout(form)
        main.addWidget(card)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        self.test_button = QPushButton("TEST API")
        self.edit_button = QPushButton("EDIT CONFIGURATION")
        self.connection_button = QPushButton("CONNECT")

        for b in (self.test_button, self.edit_button, self.connection_button):
            b.setMinimumHeight(42)

        self.test_button.setStyleSheet("""
            QPushButton {
                background:#155f8c;color:white;border:none;
                border-radius:4px;font-weight:800;
            }
            QPushButton:hover { background:#104d72; }
            QPushButton:disabled { background:#a6b3c1; }
        """)

        self.edit_button.setStyleSheet("""
            QPushButton {
                background:#ffffff;color:#0f2f4f;
                border:1px solid #a9b8c8;
                border-radius:4px;font-weight:800;
            }
            QPushButton:hover { background:#f1f7fb; }
            QPushButton:disabled {
                color:#8a98a8;background:#eef3f8;border:1px solid #d4dde7;
            }
        """)

        self.connection_button.setStyleSheet("""
            QPushButton {
                background:#157f4f;color:white;border:none;
                border-radius:4px;font-weight:800;
            }
            QPushButton:hover { background:#10643f; }
            QPushButton:disabled { background:#a6b3c1; }
        """)

        buttons.addWidget(self.test_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.connection_button)
        main.addLayout(buttons)

        status_card = QFrame()
        status_card.setObjectName("StatusCard")
        status_card.setStyleSheet("""
            #StatusCard {
                background:#ffffff;
                border:1px solid #cfd9e5;
                border-radius:6px;
            }
            QLabel { background:transparent; border:0; }
        """)
        sl = QHBoxLayout(status_card)
        sl.setContentsMargins(14, 8, 14, 8)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#66788a;font-size:18px;border:0;")
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet(
            "font-size:14px;font-weight:800;color:#536579;border:0;"
        )

        sl.addWidget(self.status_dot)
        sl.addWidget(self.status_label)
        sl.addStretch()
        main.addWidget(status_card)

        log_title = QLabel("Activity Log")
        log_title.setStyleSheet(
            "font-size:16px;font-weight:800;color:#182434;"
        )
        main.addWidget(log_title)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(320)
        self.log_box.setStyleSheet("""
            QTextEdit {
                background:#101827;
                color:#dbe7f3;
                border:1px solid #243044;
                border-radius:6px;
                padding:10px;
                font-family:monospace;
                font-size:13px;
            }
        """)
        main.addWidget(self.log_box)

        self.setLayout(main)

        self.test_button.clicked.connect(self.test_api)
        self.edit_button.clicked.connect(self.edit_configuration)
        self.connection_button.clicked.connect(self.toggle_connection)

        for field in self.config_text_fields():
            field.textChanged.connect(self.configuration_changed)
        self.source_device_input.currentTextChanged.connect(
            self.configuration_changed
        )

        self.set_config_edit_mode(False)

    # ========================================================
    # CONFIGURATION STORAGE
    # ========================================================

    def config_text_fields(self):
        return (
            self.ip_input,
            self.port_input,
            self.api_input,
        )

    def load_source_device_options(self):
        configured_source = self.normalize_source_device(
            self.config["source_device"]
        )
        options = []

        try:
            if DEVICE_OPTIONS_FILE.exists():
                with DEVICE_OPTIONS_FILE.open("r", encoding="utf-8") as file:
                    saved_options = json.load(file)

                if isinstance(saved_options, list):
                    for option in saved_options:
                        option = self.normalize_source_device(option)
                        if option and option not in options:
                            options.append(option)
        except Exception:
            logger.exception("Unable to load source device options")

        if configured_source and configured_source not in options:
            options.append(configured_source)

        self.source_device_input.addItems(options)

        if configured_source:
            self.source_device_input.setEditText(configured_source)
        else:
            self.source_device_input.setEditText("")

    def save_source_device_option(self):
        source = self.normalize_source_device(
            self.source_device_input.currentText()
        )

        if not source:
            return

        self.source_device_input.setEditText(source)

        options = []

        try:
            if DEVICE_OPTIONS_FILE.exists():
                with DEVICE_OPTIONS_FILE.open("r", encoding="utf-8") as file:
                    saved_options = json.load(file)

                if isinstance(saved_options, list):
                    for option in saved_options:
                        option = self.normalize_source_device(option)
                        if option and option not in options:
                            options.append(option)
        except Exception:
            logger.exception("Unable to read source device options")

        if source not in options:
            options.append(source)

            try:
                temp_file = DEVICE_OPTIONS_FILE.with_suffix(".tmp")
                with temp_file.open("w", encoding="utf-8") as file:
                    json.dump(options, file, indent=2)
                    file.write("\n")

                temp_file.replace(DEVICE_OPTIONS_FILE)
                self.source_device_input.addItem(source)
            except Exception:
                logger.exception("Unable to save source device option")
                self.log_message(
                    "Unable to save source device option.",
                    "ERROR",
                )

    def load_config(self):
        config = {key: "" for key in CONFIG_KEYS}

        try:
            if CONFIG_FILE.exists():
                with CONFIG_FILE.open("r", encoding="utf-8") as file:
                    saved_config = json.load(file)

                if isinstance(saved_config, dict):
                    for key in CONFIG_KEYS:
                        value = saved_config.get(key)
                        if isinstance(value, str):
                            config[key] = value

                logger.info("Loaded saved configuration from %s", CONFIG_FILE)
        except Exception:
            logger.exception("Unable to load saved configuration")

        return config

    def current_config(self):
        return {
            "analyzer_ip": self.ip_input.text(),
            "tcp_port": self.port_input.text(),
            "source_device": self.normalize_source_device(
                self.source_device_input.currentText()
            ),
            "api_endpoint": self.api_input.text(),
        }

    def save_config(self):
        try:
            source = self.current_config()["source_device"]
            self.source_device_input.setEditText(source)

            temp_file = CONFIG_FILE.with_suffix(".tmp")
            with temp_file.open("w", encoding="utf-8") as file:
                json.dump(self.current_config(), file, indent=2)
                file.write("\n")

            temp_file.replace(CONFIG_FILE)
        except Exception:
            logger.exception("Unable to save configuration")
            self.log_message(
                "Unable to save configuration changes.",
                "ERROR",
            )

    def normalize_source_device(self, value):
        return str(value or "").strip().upper()

    def configuration_changed(self):
        if self.loading_config:
            return

        self.save_config()

        if self.connected or self.listener_process is not None:
            self.log_message(
                "Configuration changed; disconnecting listener.",
                "WARNING",
            )
            self.disconnect()

    def set_config_edit_mode(self, editing):
        self.edit_mode = editing

        for field in self.config_text_fields():
            field.setReadOnly(not editing)
            field.setProperty("readOnly", not editing)
            field.style().unpolish(field)
            field.style().polish(field)

        self.source_device_input.setEnabled(editing)

        if editing:
            self.edit_button.setText("SAVE CONFIGURATION")
        else:
            self.edit_button.setText("EDIT CONFIGURATION")

    def edit_configuration(self):
        if self.edit_mode:
            self.save_source_device_option()
            self.save_config()
            self.set_config_edit_mode(False)
            self.log_message("Configuration saved.")
            return

        if self.connected or self.listener_process is not None:
            self.log_message(
                "Edit requested; disconnecting previous listener.",
                "WARNING",
            )
            self.disconnect()

        self.set_config_edit_mode(True)
        self.ip_input.setFocus()

    # ========================================================
    # LOGGING
    # ========================================================

    def log_message(self, message, level="INFO"):
        try:
            self.log_box.append(f"[{level}] {message}")
            self.log_box.ensureCursorVisible()

            if level == "ERROR":
                logger.error(message)
            elif level == "WARNING":
                logger.warning(message)
            else:
                logger.info(message)
        except Exception:
            pass

    def detect_level(self, line):
        u = line.upper()
        if "ERROR" in u or "EXCEPTION" in u or "TRACEBACK" in u:
            return "ERROR"
        if "WARNING" in u or "WARN" in u:
            return "WARNING"
        if "SUCCESS" in u:
            return "SUCCESS"
        return "INFO"

    def show_error(self, title, message):
        try:
            QMessageBox.critical(self, title, message)
        except Exception:
            pass

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate_configuration(self):
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        source = self.source_device_input.currentText().strip()
        api = self.api_input.text().strip()

        if not ip:
            raise ValueError("Analyzer IP is required.")
        if not port:
            raise ValueError("TCP port is required.")
        if not source:
            raise ValueError("Source device is required.")
        if not api:
            raise ValueError("API endpoint is required.")
        if not api.startswith(("http://", "https://")):
            raise ValueError(
                "API endpoint must start with http:// or https://"
            )

        try:
            port_number = int(port)
        except ValueError:
            raise ValueError("TCP port must be a number.")

        if not 1 <= port_number <= 65535:
            raise ValueError("TCP port must be between 1 and 65535.")

        return ip, port_number, source, api

    # ========================================================
    # API TEST
    # ========================================================

    def test_api(self):
        self.test_button.setEnabled(False)
        try:
            api = self.api_input.text().strip()
            if not api:
                raise ValueError("API endpoint is empty.")

            self.status_label.setText("Testing API...")
            self.log_message(f"Testing API: {api}")

            response = requests.head(
                api, timeout=10, allow_redirects=True
            )

            self.log_message(
                f"API HTTP status: {response.status_code}"
            )

            if response.status_code < 500:
                self.status_label.setText("API reachable")
                self.log_message("API endpoint is reachable.", "SUCCESS")
                QMessageBox.information(
                    self,
                    "API Test",
                    f"API endpoint is reachable.\n\n"
                    f"HTTP Status: {response.status_code}",
                )
            else:
                raise RuntimeError(
                    f"Server returned HTTP {response.status_code}"
                )

        except requests.Timeout:
            self.log_message("API request timed out.", "ERROR")
            self.status_label.setText("API Timeout")
            self.show_error(
                "API Timeout",
                "The API did not respond within 10 seconds.",
            )
        except requests.ConnectionError as exc:
            self.log_message(f"API connection failed: {exc}", "ERROR")
            self.status_label.setText("API Connection Failed")
            self.show_error("API Connection Failed", str(exc))
        except requests.RequestException as exc:
            self.log_message(f"API request error: {exc}", "ERROR")
            self.status_label.setText("API Error")
            self.show_error("API Request Error", str(exc))
        except Exception as exc:
            logger.exception("API test failed")
            self.log_message(f"API test failed: {exc}", "ERROR")
            self.status_label.setText("API Test Failed")
            self.show_error("API Test Failed", str(exc))
        finally:
            self.test_button.setEnabled(True)

    # ========================================================
    # CONNECTION TOGGLE
    # ========================================================

    def toggle_connection(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def split_api_endpoint(self, endpoint):
        endpoint = endpoint.strip().rstrip("/")
        marker = "/api/"
        pos = endpoint.find(marker)

        if pos == -1:
            return endpoint, "/"

        return endpoint[:pos].rstrip("/"), endpoint[pos:]

    def connect(self):
        try:
            ip, port, source, api = self.validate_configuration()

            if self.listener_process is not None:
                self.log_message(
                    "Listener is already running.",
                    "WARNING",
                )
                return

            if not LISTENER_FILE.exists():
                raise FileNotFoundError(
                    f"Existing ASTM listener not found:\n"
                    f"{LISTENER_FILE}"
                )

            self.log_message("Validating configuration...")
            self.log_message(f"Analyzer IP: {ip}")
            self.log_message(f"TCP Port: {port}")
            self.log_message(f"Source Device: {source}")
            self.log_message(f"API Endpoint: {api}")
            self.log_message("Configuration validation successful.")
            self.log_message("Starting existing ASTM listener...")

            self.connection_button.setText("STARTING...")
            self.connection_button.setEnabled(False)
            self.test_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            self.set_config_edit_mode(False)

            self.listener_process = QProcess(self)
            self.listener_process.setWorkingDirectory(str(LISTENER_DIR))

            env = self.listener_process.processEnvironment()
            env.insert("LISTEN_HOST", "0.0.0.0")
            env.insert("LISTEN_PORT", str(port))
            env.insert("SOURCE_DEVICE", source)
            env.insert("API_ENABLED", "true")
            env.insert("LOG_DIR", str(LISTENER_DIR / "logs"))

            api_base, api_path = self.split_api_endpoint(api)
            env.insert("API_BASE_URL", api_base)
            env.insert("API_PATH_TEMPLATE", api_path)

            self.listener_process.setProcessEnvironment(env)

            self.listener_process.readyReadStandardOutput.connect(
                self.read_listener_output
            )
            self.listener_process.readyReadStandardError.connect(
                self.read_listener_error
            )
            self.listener_process.started.connect(
                self.listener_started
            )
            self.listener_process.errorOccurred.connect(
                self.listener_error
            )
            self.listener_process.finished.connect(
                self.listener_finished
            )

            # -u = unbuffered, so ASTM logs appear immediately in UI.
            self.listener_process.start(
                sys.executable,
                ["-u", str(LISTENER_FILE)],
            )

        except ValueError as exc:
            self.log_message(str(exc), "ERROR")
            self.show_error("Invalid Configuration", str(exc))
            self.set_disconnected_ui()
        except Exception as exc:
            logger.exception("Connect operation failed")
            self.log_message(f"Connection error: {exc}", "ERROR")
            self.set_disconnected_ui()
            self.show_error("Connection Error", str(exc))

    # ========================================================
    # LISTENER OUTPUT -> GUI
    # ========================================================

    def listener_started(self):
        self.connected = True

        port = self.port_input.text().strip()

        self.status_dot.setStyleSheet(
            "color:#16a34a;font-size:18px;border:0;background:transparent;"
        )
        self.status_label.setText(
            f"Connected — Listening on TCP {port}"
        )
        self.status_label.setStyleSheet(
            "font-size:14px;font-weight:800;color:#15803d;border:0;background:transparent;"
        )

        # This is now the only connection control.
        self.connection_button.setText("DISCONNECT")
        self.connection_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        self.set_config_edit_mode(False)

        self.log_message(
            f"Listener started successfully on TCP {port}.",
            "SUCCESS",
        )
        self.log_message(
            "Waiting for ASTM data from analyzer..."
        )

    def read_listener_output(self):
        if not self.listener_process:
            return

        data = self.listener_process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")

        for line in text.splitlines():
            line = line.rstrip()
            if line:
                self.log_message(line, self.detect_level(line))

    def read_listener_error(self):
        if not self.listener_process:
            return

        data = self.listener_process.readAllStandardError()
        text = bytes(data).decode("utf-8", errors="replace")

        for line in text.splitlines():
            line = line.rstrip()
            if line:
                self.log_message(line, "ERROR")

    def listener_error(self, error):
        names = {
            QProcess.FailedToStart: "Listener process failed to start.",
            QProcess.Crashed: "Listener process crashed.",
            QProcess.Timedout: "Listener process timed out.",
            QProcess.WriteError: "Listener process write error.",
            QProcess.ReadError: "Listener process read error.",
            QProcess.UnknownError: "Unknown listener process error.",
        }
        message = names.get(error, f"Listener process error: {error}")
        logger.error(message)
        self.log_message(message, "ERROR")
        self.set_disconnected_ui()

    def listener_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self.log_message(
                f"Listener stopped. Exit code: {exit_code}."
            )
        else:
            self.log_message(
                f"Listener stopped unexpectedly. "
                f"Exit code: {exit_code}, status: {exit_status}.",
                "ERROR",
            )

        self.listener_process = None
        self.set_disconnected_ui()

    # ========================================================
    # DISCONNECT
    # ========================================================

    def disconnect(self):
        try:
            self.log_message("Stopping ASTM listener...")
            self.connection_button.setText("STOPPING...")
            self.connection_button.setEnabled(False)
            self.edit_button.setEnabled(False)

            process = self.listener_process

            if process is not None:
                if process.state() != QProcess.NotRunning:
                    process.terminate()
                    if not process.waitForFinished(2000):
                        self.log_message(
                            "Listener did not stop gracefully; killing it.",
                            "WARNING",
                        )
                        process.kill()
                        process.waitForFinished(1000)

                self.listener_process = None

            self.set_disconnected_ui()
            self.log_message("Disconnected.", "SUCCESS")

        except Exception as exc:
            logger.exception("Disconnect failed")
            self.log_message(f"Disconnect error: {exc}", "ERROR")
            self.listener_process = None
            self.set_disconnected_ui()

    def set_disconnected_ui(self):
        self.connected = False
        self.status_dot.setStyleSheet(
            "color:#64748b;font-size:18px;border:0;background:transparent;"
        )
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet(
            "font-size:14px;font-weight:800;color:#475569;border:0;background:transparent;"
        )
        self.connection_button.setText("CONNECT")
        self.connection_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        self.set_config_edit_mode(False)

    # ========================================================
    # EXCEPTIONS / CLOSE
    # ========================================================

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(
                exc_type, exc_value, exc_traceback
            )
            return

        error_text = "".join(
            traceback.format_exception(
                exc_type, exc_value, exc_traceback
            )
        )
        logger.error("UNHANDLED EXCEPTION:\n%s", error_text)

        try:
            self.log_message(
                f"Unexpected error: {exc_value}",
                "ERROR",
            )
            self.show_error("Unexpected Error", str(exc_value))
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.log_message("Application closing...")
            self.save_config()

            if self.listener_process is not None:
                process = self.listener_process
                if process.state() != QProcess.NotRunning:
                    process.terminate()
                    if not process.waitForFinished(2000):
                        process.kill()
                        process.waitForFinished(1000)

                self.listener_process = None

            logger.info("Application closed.")
        except Exception:
            logger.exception("Application close failed")

        event.accept()


def main():
    app = QApplication(sys.argv)
    window = ERBAConnector()
    sys.excepthook = window.handle_exception
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logger.exception("Fatal application error")
        print("FATAL ERROR:", exc)
        sys.exit(1)
