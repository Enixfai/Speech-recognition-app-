import sys
import json
import asyncio
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
import websockets
from scipy.signal import resample_poly  # Библиотека для качественного ресемплинга
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QWidget, QTextEdit, QLabel, QFileDialog)
from PyQt6.QtCore import pyqtSignal, QObject

class SocketSignals(QObject):
    message_received = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

class MeetingClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meeting Assistant - Resampling Enabled")
        self.resize(600, 800)

        self.is_recording = False
        self.target_sr = 16000 # Целевая частота для сервера
        
        # Настройки VAD
        self.silence_threshold = 200   
        self.max_silence_sec = 1.5     
        self.current_silence_sec = 0.0 
        self.is_speaking = False       
        self.pre_roll_buffer = [] 

        self.signals = SocketSignals()
        self.signals.message_received.connect(self.on_text_received)
        self.signals.connected.connect(lambda: self.status_label.setText("Статус: ПОДКЛЮЧЕНО"))
        self.signals.disconnected.connect(lambda: self.status_label.setText("Статус: ОТКЛЮЧЕНО"))

        self.init_ui()

        self.loop = None
        self.ws = None
        self.thread = threading.Thread(target=self.start_async_loop, daemon=True)
        self.thread.start()

    def init_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel("Статус: Отключено")
        layout.addWidget(self.status_label)

        self.btn_record = QPushButton("Микрофон (Авто-16кГц)")
        self.btn_record.clicked.connect(self.toggle_recording)
        layout.addWidget(self.btn_record)

        self.btn_file = QPushButton("Файл (С автоматическим ресемплингом)")
        self.btn_file.setStyleSheet("background-color: #e8f5e9;")
        self.btn_file.clicked.connect(self.start_file_test)
        layout.addWidget(self.btn_file)

        layout.addWidget(QLabel("Live:"))
        self.live_output = QTextEdit()
        self.live_output.setMaximumHeight(80)
        self.live_output.setStyleSheet("color: #2e7d32; font-weight: bold;")
        layout.addWidget(self.live_output)

        layout.addWidget(QLabel("История совещания:"))
        self.history_output = QTextEdit()
        layout.addWidget(self.history_output)

        self.btn_protocol = QPushButton("Сгенерировать протокол")
        self.btn_protocol.clicked.connect(self.generate_protocol)
        layout.addWidget(self.btn_protocol)

        self.protocol_output = QTextEdit()
        layout.addWidget(self.protocol_output)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def start_async_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_handler())

    async def ws_handler(self):
        uri = "ws://localhost:8765"
        try:
            async with websockets.connect(uri, ping_interval=None, ping_timeout=None) as websocket:
                self.ws = websocket
                self.signals.connected.emit()
                while True:
                    msg = await websocket.recv()
                    self.signals.message_received.emit(msg)
        except Exception as e:
            print(f"WS Error: {e}")
            self.signals.disconnected.emit()

    # --- ЛОГИКА ДЛЯ ФАЙЛА С РЕСЕМПЛИНГОМ ---
    def start_file_test(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть аудио", "", "Audio (*.wav *.mp3 *.m4a *.flac)")
        if path:
            self.history_output.append(f"<i>Отправка файла с ресемплингом...</i>")
            asyncio.run_coroutine_threadsafe(self.process_file(path), self.loop)

    async def process_file(self, path):
        try:
            # 1. Читаем файл как есть
            data, sr = sf.read(path, dtype='float32')
            
            # 2. Если стерео — в моно
            if len(data.shape) > 1:
                data = data.mean(axis=1)

            # 3. Ресемплинг, если частота не 16000
            if sr != self.target_sr:
                print(f"[RESAMPLE] Изменяем {sr}Гц -> {self.target_sr}Гц")
                # Используем resample_poly для качественного пересчета частоты
                data = resample_poly(data, self.target_sr, sr)
            
            # 4. Конвертация в int16
            data_int16 = (data * 32767).astype(np.int16)
            
            # 5. Отправка кусками по 0.25 сек (4000 семплов для 16кГц)
            chunk_size = 4000
            for i in range(0, len(data_int16), chunk_size):
                if not self.ws: break
                chunk = data_int16[i:i + chunk_size]
                await self.ws.send(chunk.tobytes())
                await asyncio.sleep(0.15) # Имитация реальности
            
            await self.ws.send(json.dumps({"command": "stop_audio"}))
            print("[FILE] Отправка завершена")
            
        except Exception as e:
            print(f"Ошибка обработки файла: {e}")

    # --- ЛОГИКА ДЛЯ МИКРОФОНА ---
    def toggle_recording(self):
        if not self.is_recording:
            try:
                self.is_recording = True
                self.btn_record.setText("Остановить микрофон")
                
                # Запрашиваем у системы поток СРАЗУ в 16000 Гц
                self.audio_stream = sd.InputStream(
                    samplerate=self.target_sr, 
                    channels=1, 
                    dtype='int16', 
                    callback=self.audio_callback,
                    blocksize=4000 
                )
                self.audio_stream.start()
            except Exception as e:
                print(f"Ошибка микрофона: {e}")
                self.is_recording = False
        else:
            self.is_recording = False
            self.btn_record.setText("Микрофон (Авто-16кГц)")
            if hasattr(self, 'audio_stream'):
                self.audio_stream.stop()
                self.audio_stream.close()
            self.send_command({"command": "stop_audio"})

    def audio_callback(self, indata, frames, time, status):
        if not self.is_recording or not self.ws: return
        rms = np.sqrt(np.mean(indata.astype(np.float32)**2))
        data_bytes = indata.tobytes()

        if rms > self.silence_threshold:
            if not self.is_speaking:
                self.is_speaking = True
                for old_chunk in self.pre_roll_buffer:
                    asyncio.run_coroutine_threadsafe(self.ws.send(old_chunk), self.loop)
                self.pre_roll_buffer = []
            asyncio.run_coroutine_threadsafe(self.ws.send(data_bytes), self.loop)
            self.current_silence_sec = 0.0
        else:
            if self.is_speaking:
                self.current_silence_sec += (frames / self.target_sr)
                if self.current_silence_sec < 0.5:
                    asyncio.run_coroutine_threadsafe(self.ws.send(data_bytes), self.loop)
                if self.current_silence_sec >= self.max_silence_sec:
                    self.send_command({"command": "stop_audio"})
                    self.is_speaking = False
                    self.current_silence_sec = 0.0
            else:
                self.pre_roll_buffer.append(data_bytes)
                if len(self.pre_roll_buffer) > 3: self.pre_roll_buffer.pop(0)

    def send_command(self, cmd_dict):
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(cmd_dict)), self.loop)

    def generate_protocol(self):
        self.send_command({"command": "generate_protocol"})

    def on_text_received(self, message):
        data = json.loads(message)
        status = data.get("status")
        if status == "partial":
            self.live_output.setText(data.get("text"))
        elif status == "final":
            text = data.get("text", "").strip()
            if text: self.history_output.append(f"<b>Спикер:</b> {text}")
            self.live_output.clear()
        elif status == "protocol":
            self.protocol_output.setMarkdown(data.get("text"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeetingClient()
    window.show()
    sys.exit(app.exec())