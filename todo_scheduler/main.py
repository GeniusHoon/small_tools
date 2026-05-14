import sys
import os
import json
import threading
import datetime
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QLabel, QSystemTrayIcon, QMenu, QSlider, QScrollArea,
                             QHBoxLayout, QPushButton, QLineEdit, QDialog, QFormLayout,
                             QDateTimeEdit, QMessageBox, QDialogButtonBox, QFrame, QTextEdit)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QDateTime
from PyQt6.QtGui import QIcon, QAction, QColor, QCursor

import keyboard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

APP_DIR = os.path.join(os.environ.get('APPDATA', ''), 'TodoScheduler')
os.makedirs(APP_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
TOKEN_FILE = os.path.join(APP_DIR, 'token.json')

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"client_id": "", "client_secret": "", "calendar_id": "primary"}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

class WorkerSignals(QObject):
    auth_success = pyqtSignal()
    auth_failed = pyqtSignal(str)
    events_fetched = pyqtSignal(list)
    events_error = pyqtSignal(str)

class HotkeySignals(QObject):
    toggle_visibility = pyqtSignal()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("구글 캘린더 API 설정")
        self.setFixedSize(400, 200)
        self.settings = load_settings()
        
        layout = QFormLayout(self)
        
        self.client_id_input = QLineEdit(self.settings.get("client_id", ""))
        self.client_secret_input = QLineEdit(self.settings.get("client_secret", ""))
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.calendar_id_input = QLineEdit(self.settings.get("calendar_id", "primary"))
        self.calendar_id_input.setPlaceholderText("기본값: primary")
        
        layout.addRow("Client ID:", self.client_id_input)
        layout.addRow("Client Secret:", self.client_secret_input)
        layout.addRow("캘린더 ID:", self.calendar_id_input)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setStyleSheet("""
            * { font-family: 'Pretendard', 'Segoe UI', 'Malgun Gothic', sans-serif; }
            QDialog { background-color: #0B0E14; }
            QLabel { color: #FFFFFF; font-weight: bold; font-size: 13px; }
            QLineEdit { 
                border: 1px solid #2A3441; 
                border-radius: 6px; 
                padding: 6px; 
                background-color: #151B26;
                color: #FFFFFF;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #6C72CB; }
            QPushButton { 
                background-color: #6C72CB; 
                color: white; 
                border-radius: 6px; 
                padding: 6px 15px; 
                font-weight: bold; 
            }
            QPushButton:hover { background-color: #5B61B9; }
        """)

    def get_settings(self):
        return {
            "client_id": self.client_id_input.text().strip(),
            "client_secret": self.client_secret_input.text().strip(),
            "calendar_id": self.calendar_id_input.text().strip() or "primary"
        }

class AddEditEventDialog(QDialog):
    def __init__(self, parent=None, event_data=None):
        super().__init__(parent)
        self.event_data = event_data
        self.is_edit = event_data is not None
        
        title = "일정 수정" if self.is_edit else "새 일정 추가"
        self.setWindowTitle(title)
        self.setFixedSize(350, 250)
        
        layout = QFormLayout(self)
        
        self.summary_input = QLineEdit()
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        self.start_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.start_edit.setCalendarPopup(True)
        self.end_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.end_edit.setCalendarPopup(True)
        
        if self.is_edit:
            self.summary_input.setText(event_data.get('summary', ''))
            self.description_input.setPlainText(event_data.get('description', ''))
            start_dt = event_data.get('start', {}).get('dateTime')
            end_dt = event_data.get('end', {}).get('dateTime')
            if start_dt:
                self.start_edit.setDateTime(QDateTime.fromString(start_dt, Qt.DateFormat.ISODate))
            if end_dt:
                self.end_edit.setDateTime(QDateTime.fromString(end_dt, Qt.DateFormat.ISODate))
                
        layout.addRow("제목:", self.summary_input)
        layout.addRow("메모:", self.description_input)
        layout.addRow("시작 시간:", self.start_edit)
        layout.addRow("종료 시간:", self.end_edit)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.button_box)
        layout.addRow(buttons_layout)
        
        self.setStyleSheet("""
            * { font-family: 'Pretendard', 'Segoe UI', 'Malgun Gothic', sans-serif; }
            QDialog { background-color: #0B0E14; }
            QLabel { color: #FFFFFF; font-weight: bold; font-size: 13px; }
            QLineEdit, QTextEdit, QDateTimeEdit { 
                border: 1px solid #2A3441; 
                border-radius: 6px; 
                padding: 6px; 
                background-color: #151B26;
                color: #FFFFFF;
            }
            QLineEdit:focus, QTextEdit:focus, QDateTimeEdit:focus { border: 1px solid #6C72CB; }
            QDateTimeEdit::drop-down { border: 0px; }
            QPushButton { 
                background-color: #6C72CB; 
                color: white; 
                border-radius: 6px; 
                padding: 6px 15px; 
                font-weight: bold; 
            }
            QPushButton:hover { background-color: #5B61B9; }
            QCalendarWidget QWidget { alternate-background-color: #151B26; }
            QCalendarWidget QAbstractItemView:enabled { color: white; background-color: #151B26; selection-background-color: #6C72CB; }
            QCalendarWidget QToolButton { color: white; }
        """)

    def get_event_body(self):
        start_dt = self.start_edit.dateTime().toPyDateTime()
        end_dt = self.end_edit.dateTime().toPyDateTime()
        
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()
        
        import time
        offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
        offset = -offset
        hours, minutes = divmod(offset // 60, 60)
        tz_str = f"{hours:+03d}:{minutes:02d}"
        
        return {
            'summary': self.summary_input.text().strip() or "(제목 없음)",
            'description': self.description_input.toPlainText().strip(),
            'start': {
                'dateTime': start_iso + tz_str,
            },
            'end': {
                'dateTime': end_iso + tz_str,
            },
        }

class TodoSchedulerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.really_quit = False
        self.creds = None
        self.service = None
        self.settings = load_settings()
        
        self.worker_signals = WorkerSignals()
        self.worker_signals.auth_success.connect(self._auth_success)
        self.worker_signals.auth_failed.connect(self._auth_failed)
        self.worker_signals.events_fetched.connect(self._update_todo_ui)
        self.worker_signals.events_error.connect(self._show_error)
        
        self.hotkey_signals = HotkeySignals()
        self.hotkey_signals.toggle_visibility.connect(self.toggle_window)
        
        try:
            keyboard.add_hotkey('ctrl+f11', self.emit_toggle_signal)
        except Exception as e:
            logging.warning(f"Could not register global hotkey. {e}")
        
        self.init_ui()
        self.setup_tray()
        self.apply_styles()
        
        self.authenticate(silent=True)
            
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_events)
        self.refresh_timer.start(3600 * 1000)
        
    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        screen = QApplication.primaryScreen().availableGeometry()
        width = int(screen.width() * 0.2)
        height = screen.height()
        x = screen.width() - width
        y = screen.top()
        
        self.setGeometry(x, y, width, height)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setObjectName("centralWidget")
        
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(15, 15, 15, 15)
        
        title_layout = QHBoxLayout()
        title_label = QLabel("Todo Scheduler")
        title_label.setObjectName("titleLabel")
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(30, 30)
        self.add_btn.clicked.connect(self.show_add_dialog)
        self.add_btn.setToolTip("새 일정 추가")
        
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.clicked.connect(self.load_events)
        self.refresh_btn.setToolTip("새로고침")
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.refresh_btn)
        title_layout.addWidget(self.add_btn)
        self.layout.addLayout(title_layout)
        
        slider_layout = QHBoxLayout()
        slider_label = QLabel("투명도:")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(90)
        self.opacity_slider.valueChanged.connect(self.change_opacity)
        slider_layout.addWidget(slider_label)
        slider_layout.addWidget(self.opacity_slider)
        self.layout.addLayout(slider_layout)
        
        self.status_label = QLabel("API 연동 대기 중...")
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("scrollArea")
        
        self.todo_container = QWidget()
        self.todo_container.setObjectName("todoContainer")
        self.todo_layout = QVBoxLayout(self.todo_container)
        self.todo_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.todo_layout.setSpacing(10)
        self.scroll_area.setWidget(self.todo_container)
        
        self.layout.addWidget(self.scroll_area)
        
        self.setWindowOpacity(0.9)
        
    def apply_styles(self):
        self.setStyleSheet("""
            * { font-family: 'Pretendard', 'Segoe UI', 'Malgun Gothic', sans-serif; }
            #centralWidget {
                background-color: #0B0E14;
                border-left: 1px solid #1E2536;
                border-top: 1px solid #1E2536;
                border-bottom: 1px solid #1E2536;
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
            }
            #titleLabel {
                font-size: 22px;
                font-weight: 800;
                color: #FFFFFF;
            }
            QLabel {
                color: #A0AABF;
            }
            QPushButton {
                background-color: #6C72CB;
                color: white;
                border: none;
                border-radius: 15px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #5B61B9;
            }
            QPushButton:pressed {
                background-color: #4A50A3;
            }
            #scrollArea, #todoContainer {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #0B0E14;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #2A3441;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4D5E7A;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #2A3441;
                height: 6px;
                background: #151B26;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #6C72CB;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #6C72CB;
                width: 12px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 6px;
            }
        """)

    def emit_toggle_signal(self):
        self.hotkey_signals.toggle_visibility.emit()

    def toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def change_opacity(self, value):
        self.setWindowOpacity(value / 100.0)
        
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        icon = QIcon.fromTheme("appointment-new") 
        if icon.isNull():
            from PyQt6.QtGui import QPixmap, QPainter
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setBrush(QColor("#6C72CB"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
            painter.setBrush(QColor("white"))
            painter.drawRect(12, 20, 40, 6)
            painter.drawRect(12, 34, 40, 6)
            painter.drawRect(12, 48, 20, 6)
            painter.end()
            icon = QIcon(pixmap)
            
        self.tray_icon.setIcon(icon)
        
        tray_menu = QMenu()
        
        tray_menu.setStyleSheet("""
            * { font-family: 'Pretendard', 'Segoe UI', 'Malgun Gothic', sans-serif; }
            QMenu { background-color: #151B26; border: 1px solid #2A3441; border-radius: 5px; }
            QMenu::item { padding: 8px 25px; color: #FFFFFF; }
            QMenu::item:selected { background-color: #2A3441; }
        """)
        
        show_action = QAction("보이기/숨기기 (Ctrl+F11)", self)
        show_action.triggered.connect(self.toggle_window)
        tray_menu.addAction(show_action)
        
        settings_action = QAction("설정 (Settings)", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
    def closeEvent(self, event):
        if not self.really_quit:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Todo Scheduler",
                "프로그램이 트레이로 최소화되었습니다.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            event.accept()
            
    def quit_app(self):
        self.really_quit = True
        QApplication.quit()
        
    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_settings()
            save_settings(new_settings)
            self.settings = new_settings
            
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            self.creds = None
            self.service = None
            
            self.authenticate(silent=False)

    def authenticate(self, silent=True):
        client_id = self.settings.get("client_id")
        client_secret = self.settings.get("client_secret")
        
        if not client_id or not client_secret:
            self.status_label.setText("설정에서 Client ID와 Secret을 입력해주세요.")
            return
            
        self.status_label.setText("인증 진행 중...")
        threading.Thread(target=self._auth_thread, args=(client_id, client_secret, silent), daemon=True).start()

    def _auth_thread(self, client_id, client_secret, silent):
        try:
            if os.path.exists(TOKEN_FILE):
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    if silent:
                        self.worker_signals.auth_failed.emit("API 연동을 위해 트레이 우클릭 -> 설정에서 로그인 해주세요.")
                        return
                    
                    client_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost"]
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                    
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
                    
            self.service = build('calendar', 'v3', credentials=self.creds)
            self.worker_signals.auth_success.emit()
            
        except Exception as e:
            self.worker_signals.auth_failed.emit(str(e))

    def _auth_success(self):
        self.status_label.setText("✅ 구글 캘린더 연동 완료")
        self.status_label.setStyleSheet("color: #98C379; font-size: 12px; font-weight: bold;")
        self.load_events()

    def _auth_failed(self, message):
        self.status_label.setText(f"인증 실패: {message}")
        self.status_label.setStyleSheet("color: #E06C75; font-size: 12px;")

    def load_events(self):
        if not self.service:
            logging.warning("Service is not initialized. Cannot load events.")
            return
            
        self.status_label.setText("일정 불러오는 중...")
        logging.info("Starting load_events thread...")
        threading.Thread(target=self._fetch_events_thread, daemon=True).start()
        
    def _fetch_events_thread(self):
        try:
            logging.info("Executing Google API events().list() request...")
            calendar_id = self.settings.get("calendar_id", "primary")
            
            # Start of today in local timezone
            now = datetime.datetime.now()
            start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_min = start_of_today.astimezone().isoformat()
            
            events_result = self.service.events().list(
                calendarId=calendar_id, timeMin=time_min,
                maxResults=50, singleEvents=True,
                orderBy='startTime').execute()
            
            events = events_result.get('items', [])
            logging.info(f"Successfully fetched {len(events)} events from Google API.")
            
            self.worker_signals.events_fetched.emit(events)
        except Exception as e:
            logging.error(f"Error fetching events: {e}")
            self.worker_signals.events_error.emit(str(e))
            
    def _update_todo_ui(self, events):
        logging.info("Updating UI with fetched events...")
        self.status_label.setText("✅ 구글 캘린더 갱신 완료")
        
        while self.todo_layout.count():
            item = self.todo_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        if not events:
            no_events_label = QLabel("다가오는 일정이 없습니다.")
            no_events_label.setStyleSheet("color: #6C72CB; font-style: italic; padding: 10px; font-size: 14px;")
            no_events_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.todo_layout.addWidget(no_events_label)
            return

        for event in events:
            item_widget = QFrame()
            item_widget.setObjectName("TodoItem")
            
            item_widget.setStyleSheet("""
                QFrame#TodoItem {
                    background-color: #151B26;
                    border-radius: 12px;
                    border: 1px solid #2A3441;
                }
                QFrame#TodoItem:hover {
                    background-color: #1A2230;
                    border: 1px solid #4D5E7A;
                }
            """)
            
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(15, 12, 15, 12)
            
            text_layout = QVBoxLayout()
            
            summary = event.get('summary', '(제목 없음)')
            title_label = QLabel(summary)
            title_label.setStyleSheet("font-weight: bold; color: #FFFFFF; font-size: 15px; border: none; background: transparent;")
            title_label.setWordWrap(True)
            
            start = event.get('start', {})
            start_dt = start.get('dateTime') or start.get('date')
            
            if start_dt:
                try:
                    dt = datetime.datetime.fromisoformat(start_dt)
                    time_str = dt.strftime("%Y년 %m월 %d일 %H:%M")
                except:
                    time_str = start_dt
            else:
                time_str = "시간 미정"
                
            time_label = QLabel(time_str)
            time_label.setStyleSheet("color: #4DB8FF; font-size: 12px; margin-top: 4px; border: none; background: transparent; font-weight: bold;")
            
            text_layout.addWidget(title_label)
            text_layout.addWidget(time_label)
            
            description = event.get('description', '')
            if description:
                desc_label = QLabel(description)
                desc_label.setStyleSheet("color: #8B9BB4; font-size: 12px; margin-top: 6px; border: none; background: transparent;")
                desc_label.setWordWrap(True)
                text_layout.addWidget(desc_label)
            
            # Buttons layout
            btn_layout = QVBoxLayout()
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
            
            event_type = event.get('eventType', 'default')
            is_editable = (event_type == 'default')
            
            if is_editable:
                edit_btn = QPushButton("수정")
                edit_btn.setFixedSize(45, 25)
                edit_btn.setStyleSheet("""
                    QPushButton { background-color: transparent; color: #4DB8FF; border: 1px solid #4DB8FF; border-radius: 6px; font-size: 11px; font-weight: bold; }
                    QPushButton:hover { background-color: rgba(77, 184, 255, 0.1); }
                """)
                edit_btn.clicked.connect(lambda checked, e=event: self.edit_event(e))
                
                delete_btn = QPushButton("삭제")
                delete_btn.setFixedSize(45, 25)
                delete_btn.setStyleSheet("""
                    QPushButton { background-color: transparent; color: #E06C75; border: 1px solid #E06C75; border-radius: 6px; font-size: 11px; font-weight: bold; }
                    QPushButton:hover { background-color: rgba(224, 108, 117, 0.1); }
                """)
                delete_btn.clicked.connect(lambda checked, e=event: self.delete_event(e))
                
                btn_layout.addWidget(edit_btn)
                btn_layout.addWidget(delete_btn)
            else:
                type_label = QLabel("특수 일정\n(읽기 전용)")
                type_label.setStyleSheet("color: #6B7B94; font-size: 11px; font-weight: bold;")
                type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_layout.addWidget(type_label)
            
            item_layout.addLayout(text_layout)
            item_layout.addLayout(btn_layout)
            
            self.todo_layout.addWidget(item_widget)
            
        self.todo_layout.addStretch()
        logging.info("UI update complete.")
        
    def _show_error(self, error_message):
        self.status_label.setText("오류 발생")
        error_label = QLabel(f"일정을 불러오지 못했습니다:\n{error_message}")
        error_label.setStyleSheet("color: #E06C75; background-color: #1E1A24; border: 1px solid #E06C75; border-radius: 8px; padding: 12px;")
        error_label.setWordWrap(True)
        self.todo_layout.addWidget(error_label)

    def show_add_dialog(self):
        if not self.service:
            QMessageBox.warning(self, "오류", "먼저 설정에서 API 연동을 진행해주세요.")
            return
            
        dialog = AddEditEventDialog(self)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            body = dialog.get_event_body()
            calendar_id = self.settings.get("calendar_id", "primary")
            try:
                self.service.events().insert(calendarId=calendar_id, body=body).execute()
                self.load_events()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"일정 추가 실패: {e}")

    def edit_event(self, event_data):
        if not self.service:
            return
            
        dialog = AddEditEventDialog(self, event_data)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            calendar_id = self.settings.get("calendar_id", "primary")
            event_id = event_data['id']
            
            try:
                body = dialog.get_event_body()
                self.service.events().update(calendarId=calendar_id, eventId=event_id, body=body).execute()
                self.load_events()
            except Exception as e:
                err_msg = str(e)
                if 'eventTypeRestriction' in err_msg or 'birthday' in err_msg.lower():
                    QMessageBox.critical(self, "오류", "일정 수정 실패:\n생일이나 기념일 등 특수 일정은 앱에서 수정할 수 없습니다.")
                else:
                    QMessageBox.critical(self, "오류", f"일정 수정 실패: {e}")

    def delete_event(self, event_data):
        if not self.service:
            return
            
        reply = QMessageBox.question(self, '삭제 확인', f"'{event_data.get('summary', '')}' 일정을 삭제하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            calendar_id = self.settings.get("calendar_id", "primary")
            event_id = event_data['id']
            try:
                self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                self.load_events()
            except Exception as e:
                err_msg = str(e)
                if 'eventTypeRestriction' in err_msg or 'birthday' in err_msg.lower():
                    QMessageBox.critical(self, "오류", "일정 삭제 실패:\n생일이나 기념일 등 특수 일정은 앱에서 삭제할 수 없습니다.")
                else:
                    QMessageBox.critical(self, "오류", f"일정 삭제 실패: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = TodoSchedulerApp()
    window.show()
    sys.exit(app.exec())
