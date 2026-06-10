import sys
import os
import requests
import json
import time
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton)
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QThread, QSize, QRect, QRectF
from PyQt5.QtGui import QFont, QMovie, QPainter, QPainterPath, QColor, QPen, QBrush

# ========== НАСТРОЙКИ ==========
API_URL = "OCR_API_URL"            
LLM_API_URL = "LLM_API_URL"
LLM_TOKEN = "LLM_TOKEN"
LLM_MODEL = "LLM_MODEL_NAME"
INTERVAL_SECONDS = 15

SYSTEM_PROMPT = """Ты — Клиппи, офисный помощник. Анализируй текст с экрана и придумывай короткие комментарии.

Правила:
1. Найди в тексте что-то конкретное (опечатку, странность, повтор, нестыковку)
2. Обязательно упомяни цитату из текста (5-15 слов) прямо внутри шутки
3. Шутка — 1 предложение, максимум 30 слов
4. Если ничего нет — напиши: «Скукотища... ничего интересного не нашёл»
5. Формат ответа: просто шутка (без слов Цитата/Шутка)"""
# ===============================

last_jokes = []

class ScreenshotWorker(QThread):
    joke_ready = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = True
        
    def capture_active_window(self):
        try:
            import win32gui
            import mss
            import tempfile
            
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
            return png_data, window_title
            
        except Exception as e:
            print(f"Capture error: {e}")
            return None, None
    
    def send_to_surya(self, png_data):
        try:
            files = {'file': ('screenshot.png', png_data, 'image/png')}
            response = requests.post(API_URL, files=files, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('text', '')
            return None
        except Exception as e:
            print(f"Surya error: {e}")
            return None
    
    def send_to_llm(self, text, window_title):
        if not text or text == "No text detected" or len(text.strip()) < 30:
            return None
        
        prompt = f"""Окно: {window_title}
Текст с экрана:
{text[:2000]}

Придумай шутку с цитатой из текста."""
        
        headers = {"Authorization": f"Bearer {LLM_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 150
        }
        
        try:
            response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            return None
        except Exception as e:
            print(f"LLM error: {e}")
            return None
    
    def run(self):
        global last_jokes
        while self.running:
            try:
                png_data, window_title = self.capture_active_window()
                if png_data is None:
                    time.sleep(INTERVAL_SECONDS)
                    continue
                
                text = self.send_to_surya(png_data)
                if not text or text == "No text detected":
                    time.sleep(INTERVAL_SECONDS)
                    continue
                
                joke = self.send_to_llm(text, window_title)
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
    """Речевое облачко с треугольным хвостиком справа"""
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
        
        # Настройки
        padding = 15
        tail_width = 15
        tail_height = 12
        corner_radius = 12
        
        # Шрифт
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        
        # Расчёт размера текста
        text_rect = painter.fontMetrics().boundingRect(QRect(0, 0, 350, 1000), Qt.TextWordWrap, self.text)
        text_width = min(text_rect.width() + padding * 2, 350)
        text_height = text_rect.height() + padding * 2
        
        # Общий размер (с хвостиком справа)
        total_width = text_width + tail_width
        total_height = text_height
        self.setFixedSize(total_width, total_height)
        
        # Основной прямоугольник
        rect = QRectF(0, 0, text_width, text_height)
        
        # Рисуем фон
        painter.setBrush(QBrush(QColor(255, 255, 204, 230)))
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        
        # Скруглённый прямоугольник
        path = QPainterPath()
        path.addRoundedRect(rect, corner_radius, corner_radius)
        
        # Хвостик (треугольник справа, по центру)
        tail_x = text_width
        tail_y = (text_height - tail_height) // 2
        
        tail_path = QPainterPath()
        tail_path.moveTo(tail_x, tail_y)
        tail_path.lineTo(tail_x + tail_width, tail_y + tail_height // 2)
        tail_path.lineTo(tail_x, tail_y + tail_height)
        tail_path.closeSubpath()
        
        # Объединяем
        full_path = path.united(tail_path)
        painter.drawPath(full_path)
        
        # Текст
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
        
        # Фиксированный размер окна (не меняется при показе/скрытии облачка)
        self.setFixedSize(520, 280)
        
        self.init_ui()
        self.init_worker()
        
        QTimer.singleShot(1000, self.show_welcome)
    
    def init_ui(self):
        # Абсолютное позиционирование вместо layout
        # Облачко (слева, будет показываться/скрываться)
        self.bubble = SpeechBubble(self)
        self.bubble.move(0, 30)
        
        # Контейнер для скрепки с прозрачной областью для перетаскивания
        self.drag_area = QLabel(self)
        self.drag_area.setFixedSize(160, 280)
        self.drag_area.move(360, 0)
        self.drag_area.setStyleSheet("background: transparent;")
        
        # Скрепка (GIF)
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
        
        # Центрируем GIF внутри области перетаскивания
        self.clippy_gif.move(20, 20)
        
        # Крестик (маленький)
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
    
    def show_bubble(self, text):
        self.bubble.set_text(text)
        self.bubble.show()
        QTimer.singleShot(15000, self.bubble.hide)
    
    def init_worker(self):
        self.worker = ScreenshotWorker()
        self.worker.joke_ready.connect(self.show_bubble)
        self.worker.start()
    
    def show_welcome(self):
        self.show_bubble("📎 Привет! Я Клиппи.\n\nСлежу за твоим экраном и комментирую интересное!\n\n(Сообщение исчезнет через 15 секунд)")
    
    def quit_app(self):
        print("Closing application...")
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.stop()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    
    def mousePressEvent(self, event):
        # Перетаскивание за область drag_area или за само окно
        if event.button() == Qt.LeftButton:
            # Проверяем, что клик по drag_area (области скрепки)
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