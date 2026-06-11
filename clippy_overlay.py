import sys
import os
import requests
import json
import time
import random
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton)
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QThread, QSize, QRect, QRectF
from PyQt5.QtGui import QFont, QMovie, QPainter, QPainterPath, QColor, QPen, QBrush

# ========== НАСТРОЙКИ ==========
LLM_API_URL = "LLM_API_URL"
LLM_TOKEN = "LLM_API_URL"
LLM_MODEL = "LLM_MODEL_NAME"
INTERVAL_SECONDS = 15
SCREENSHOT_DIR = "C:/Programs/clippy.llm/Screenshots"

# Эмоции для разнообразия
EMOTIONS = ["📎 ", "😏 ", "🤨 ", "🙄 ", "🤓 ", "💀 ", "🎯 ", "🔥 ", "", "", ""]

SYSTEM_PROMPT = """Ты — Клиппи, офисный помощник из Microsoft Office 97. У тебя есть собственное мнение, ты саркастичен, но не злобен.

ТВОЙ ХАРАКТЕР:
- Ты считаешь себя умнее всех, кто сидит за компьютером
- Ты обожаешь подмечать глупые ошибки, опечатки и странные решения
- Ты можешь вздыхать, закатывать глаза (виртуально) и отпускать едкие комментарии
- Но ты также можешь быть полезным, если заметишь реальную проблему

ПРАВИЛА ОТВЕТОВ:
1. Найди в происходящем на экране что-то, что можно прокомментировать
2. Всегда упоминай конкретную деталь (цитату, ошибку, странное действие)
3. Используй один из стилей:
   - Саркастичный: «О, кто-то опять забыл поставить точку с запятой. Гениально.»
   - Усталый/офисный: «Вздох... Опять этот код. Ну почему нельзя было написать нормально?»
   - Дружелюбно-насмешливый: «Дружок, тут у тебя опечатка. Но ничего, бывает.»
   - «Полезный» (редко, только если реально нашёл критическую ошибку)
4. Шутка — 1-2 предложения, не больше 40 слов
5. Если всё хорошо — скажи что-то вроде: «Скукотища... тут даже придраться не к чему. Работай дальше.»

ПРИМЕРЫ:
- Увидел опечатку: «"мобильныи" вместо "мобильный"? Серьёзно? Ты вообще клавиатуру видел?»
- Увидел странную переменную: «"x_x" — это имя переменной или ты просто чихнул на клавиатуру?»
- Увидел бесконечный цикл: «О, вечность! Как раз успею сходить в отпуск, пока этот код выполнится.»
- Всё хорошо: «Хм... Всё прилично. Даже придраться не к чему. Продолжай в том же духе (с таким же успехом).»"""
# ===============================

last_jokes = []

class ScreenshotWorker(QThread):
    joke_ready = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = True
        
    def capture_active_window(self):
        try:
            import win32gui
            import mss
            import tempfile
            import base64
            
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None, None
            
            window_title = win32gui.GetWindowText(hwnd)
            if not window_title:
                window_title = "unknown_window"
            
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return None, None
            
            with mss.mss() as sct:
                capture_zone = {"left": left, "top": top, "width": width, "height": height}
                screenshot = sct.grab(capture_zone)
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_name = tmp.name
            
            from mss import tools
            tools.to_png(screenshot.rgb, screenshot.size, output=tmp_name)
            
            with open(tmp_name, 'rb') as f:
                png_data = f.read()
            
            os.unlink(tmp_name)
            
            img_base64 = base64.b64encode(png_data).decode('utf-8')
            return img_base64, window_title
            
        except Exception as e:
            print(f"Capture error: {e}")
            return None, None
    
    def send_to_llm(self, img_base64, window_title):
        if not img_base64:
            return None
        
        prompt = f"""Окно: {window_title}

Внимательно посмотри на этот скриншот. Найди что-то, что можно прокомментировать с сарказмом (опечатку, странный код, глупое действие, зависшее окно и т.п.). 

Правила:
1. Будь остроумным и язвительным, но не переходи на личности
2. Всегда упоминай конкретную деталь с экрана
3. Шутка должна быть короткой (1-2 предложения)
4. Если всё ок — скажи, что скучно и не к чему придраться

Придумай ответ от лица Клиппи (офисная скрепка из 90-х)."""
        
        headers = {"Authorization": f"Bearer {LLM_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "temperature": 0.9,
            "max_tokens": 200
        }
        
        try:
            response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                joke = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                
                # Добавляем эмоцию с вероятностью 50%
                if random.random() < 0.5:
                    joke = random.choice(EMOTIONS) + joke
                
                return joke
            print(f"LLM error: {response.status_code}")
            return None
        except Exception as e:
            print(f"LLM error: {e}")
            return None
    
    def run(self):
        global last_jokes
        while self.running:
            try:
                self.status_update.emit("📸 Делаю скриншот...")
                img_base64, window_title = self.capture_active_window()
                if img_base64 is None:
                    time.sleep(INTERVAL_SECONDS)
                    continue
                
                self.status_update.emit("🤔 Думаю...")
                joke = self.send_to_llm(img_base64, window_title)
                if joke:
                    if joke in last_jokes:
                        joke += " (штрафной!)"
                    last_jokes.append(joke)
                    if len(last_jokes) > 5:
                        last_jokes.pop(0)
                    self.joke_ready.emit(joke)
                
                time.sleep(INTERVAL_SECONDS)
                
            except Exception as e:
                print(f"Worker error: {e}")
                time.sleep(INTERVAL_SECONDS)
    
    def stop(self):
        self.running = False
        self.quit()
        self.wait()


class SpeechBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()
    
    def set_text(self, text):
        self.text = text
        self.update()
        self.adjustSize()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        padding = 15
        tail_width = 15
        tail_height = 12
        corner_radius = 12
        
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        
        text_rect = painter.fontMetrics().boundingRect(QRect(0, 0, 350, 1000), Qt.TextWordWrap, self.text)
        text_width = min(text_rect.width() + padding * 2, 350)
        text_height = text_rect.height() + padding * 2
        
        total_width = text_width + tail_width
        total_height = text_height
        self.setFixedSize(total_width, total_height)
        
        rect = QRectF(0, 0, text_width, text_height)
        
        painter.setBrush(QBrush(QColor(255, 255, 204, 230)))
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        
        path = QPainterPath()
        path.addRoundedRect(rect, corner_radius, corner_radius)
        
        tail_x = text_width
        tail_y = (text_height - tail_height) // 2
        
        tail_path = QPainterPath()
        tail_path.moveTo(tail_x, tail_y)
        tail_path.lineTo(tail_x + tail_width, tail_y + tail_height // 2)
        tail_path.lineTo(tail_x, tail_y + tail_height)
        tail_path.closeSubpath()
        
        full_path = path.united(tail_path)
        painter.drawPath(full_path)
        
        painter.setPen(QPen(QColor(0, 0, 0)))
        text_rect = QRectF(padding, padding, text_width - padding * 2, text_height - padding * 2)
        painter.drawText(text_rect, Qt.TextWordWrap, self.text)


class ClippyOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.dragging = False
        self.drag_position = QPoint()
        
        self.setFixedSize(520, 280)
        
        self.init_ui()
        self.init_worker()
        
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        
        QTimer.singleShot(1000, self.show_welcome)
    
    def init_ui(self):
        self.bubble = SpeechBubble(self)
        self.bubble.move(0, 30)
        
        self.drag_area = QLabel(self)
        self.drag_area.setFixedSize(160, 280)
        self.drag_area.move(360, 0)
        self.drag_area.setStyleSheet("background: transparent;")
        
        self.clippy_gif = QLabel(self.drag_area)
        gif_path = os.path.join(os.path.dirname(__file__), "clippy.gif")
        
        if os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            self.movie.setScaledSize(QSize(127, 240))
            self.clippy_gif.setMovie(self.movie)
            self.movie.start()
            self.clippy_gif.setFixedSize(127, 240)
        else:
            self.clippy_gif.setText("📎")
            self.clippy_gif.setStyleSheet("font-size: 80px; background: transparent;")
            self.clippy_gif.setFixedSize(127, 240)
            self.clippy_gif.setAlignment(Qt.AlignCenter)
        
        self.clippy_gif.move(20, 20)
        
        self.close_btn = QPushButton("✖", self.drag_area)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.move(130, 250)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 80);
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 200);
            }
        """)
        self.close_btn.clicked.connect(self.quit_app)
        
        # Статусная строка (опционально, можно закомментировать)
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #666; font-size: 9px; background: transparent;")
        self.status_label.move(10, 260)
        self.status_label.resize(150, 20)
    
    def get_window_rect(self):
        pos = self.mapToGlobal(QPoint(0, 0))
        return pos.x(), pos.y(), self.width(), self.height()
    
    def take_screenshot_with_bubble(self):
        try:
            import win32gui
            import win32ui
            import win32con
            from PIL import Image
            
            x, y, width, height = self.get_window_rect()
            
            capture_x = max(0, x - 20)
            capture_y = max(0, y - 20)
            capture_width = width + 40
            capture_height = height + 40
            
            hwnd = win32gui.GetDesktopWindow()
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, capture_width, capture_height)
            save_dc.SelectObject(bitmap)
            save_dc.BitBlt((0, 0), (capture_width, capture_height), mfc_dc, (capture_x, capture_y), win32con.SRCCOPY)
            
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"{timestamp}_clippy.png"
            filepath = os.path.join(SCREENSHOT_DIR, filename)
            img.save(filepath)
            print(f"💾 Скриншот сохранён: {filepath}")
            
            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            
        except Exception as e:
            print(f"❌ Ошибка сохранения скриншота: {e}")
    
    def show_bubble(self, text):
        self.bubble.set_text(text)
        self.bubble.show()
        
        QTimer.singleShot(500, self.take_screenshot_with_bubble)
        QTimer.singleShot(15000, self.bubble.hide)
    
    def update_status(self, message):
        if hasattr(self, 'status_label'):
            self.status_label.setText(message)
        print(message)
    
    def init_worker(self):
        self.worker = ScreenshotWorker()
        self.worker.joke_ready.connect(self.show_bubble)
        self.worker.status_update.connect(self.update_status)
        self.worker.start()
    
    def show_welcome(self):
        self.show_bubble("📎 Привет! Я Клиппи.\n\nСлежу за твоим экраном и комментирую всё, что вижу.\n\nНажми Esc или крестик, чтобы выйти.")
    
    def quit_app(self):
        print("👋 Клиппи завершает работу...")
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.stop()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if self.drag_area.geometry().contains(pos):
                self.dragging = True
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.quit_app()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    window = ClippyOverlay()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
