"""
Твоя задача — захватывать звук с микрофона и пересылать его сюда по веб-сокетам.
Сервер всё переварит и вернет тебе текст или готовый отчет.

1. ЧТО ТЕБЕ НУЖНО В QT:
-----------------------
В .pro файле (или CMake) добавь модули: websockets, multimedia, network.
Для работы с сокетами используй класс `QWebSocket`.

2. КАК НАСТРОИТЬ АУДИО (ЭТО ВАЖНО!):
------------------------------------
Whisper — привередливый. Ему нужен звук строго в формате PCM 16кГц, моно, 16 бит.
Настрой `QAudioFormat` так:
    format.setSampleRate(16000);
    format.setChannelCount(1);
    format.setSampleFormat(QAudioFormat::Int16); // Это PCM 16-bit

Для захвата используй `QAudioSource` (в Qt6) или `QAudioInput` (в Qt5).
Читай данные через `readAll()` и сразу кидай их в сокет.

3. КАК ОБЩАТЬСЯ С СЕРВЕРОМ:
---------------------------
Адрес: ws://localhost:8765

А) ШЛЁШЬ ЗВУК:
   Просто отправляй сырые байты как бинарное сообщение:
   `socket->sendBinaryMessage(audioByteArray);`
   Делай это часто (раз в 100-200 мс), чтобы юзер видел текст почти сразу.

Б) ШЛЁШЬ КОМАНДЫ (JSON):
   Когда нужно что-то сделать, шли текстовое сообщение:
   - Чтобы завершить текущую фразу и очистить буфер: 
     {"command": "stop_audio"}
   - Чтобы получить финальный отчет по всему совещанию: 
     {"command": "generate_protocol", "text": "ТУТ_ВЕСЬ_НАКОПЛЕННЫЙ_ТЕКСТ"}

4. ЧТО СЕРВЕР ПРИШЛЕТ ТЕБЕ:
---------------------------
Лови сигнал `textMessageReceived` и парси JSON. Смотри на поле "status":

   - "status": "partial" — Это промежуточный текст. Выводи его в UI каким-нибудь 
     светлым цветом. Он будет постоянно обновляться, пока человек говорит.
     
   - "status": "final" — Человек закончил фразу. Этот текст уже окончательный. 
     Сохраняй его в общую переменную совещания и выводи в основной лог.
     
   - "status": "processing" — ИИ начал генерировать отчет. Покажи юзеру какую-то 
     анимацию загрузки, чтобы он не скучал.
     
   - "status": "protocol" — В поле "text" лежит готовый Markdown-отчет. 
     Можешь сразу закинуть его в `QTextBrowser` — Qt отлично рендерит Markdown.

5. ПРИМЕРНЫЙ ПЛАН РАБОТЫ (WORKFLOW):
------------------------------------
1. Запускаешь этот сервер из C++ через `QProcess`.
2. Жмешь "Старт": открываешь сокет, запускаешь микрофон, шлешь байты.
3. Сервер шлет "partial" -> ты обновляешь временную строчку в UI.
4. Раз в 5-10 секунд или по тишине шлешь "stop_audio" -> сервер шлет "final" 
   -> ты добавляешь это в общую историю совещания.
5. Жмешь "Стоп": останавливаешь микрофон, шлешь "generate_protocol" + всю историю.
6. Получаешь отчет.
=========================================================================================
"""

import asyncio
import websockets
import json
import numpy as np
import os
from faster_whisper import WhisperModel
from openai import AsyncOpenAI

# --- НАСТРОЙКИ STT (Whisper) ---
MODEL_SIZE = "small"
SAMPLE_RATE = 16000 

# --- НАСТРОЙКИ LLM (DeepSeek / Groq) ---
LLM_API_KEY = os.getenv("LLM_API_KEY", "api_ключ") 
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"        

print(f"[INIT] Загрузка модели STT ({MODEL_SIZE})...")
model = WhisperModel(MODEL_SIZE, device="auto", compute_type="int8")
print("[INIT] STT Модель загружена.")

llm_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

async def generate_protocol_via_llm(transcribed_text: str) -> str:
    """Асинхронно отправляет текст в LLM и возвращает протокол."""
    if not transcribed_text or len(transcribed_text) < 10:
        return "Текст совещания слишком короткий или пустой."

    print("[LLM] Отправка запроса на генерацию протокола...")
    
    system_prompt = (
        "Ты — бизнес-ассистент. Составь протокол совещания на основе расшифровки аудио. "
        "Исправляй опечатки и игнорируй слова-паразиты.\n"
        "Формат Markdown:\n"
        "## Протокол совещания\n"
        "**Краткое содержание:** [1-2 предложения]\n\n"
        "### 📌 Основные темы:\n- [Тема 1]\n\n"
        "### ✅ Принятые решения:\n- [Решение 1]\n\n"
        "### 📝 Задачи и поручения:\n- [Задача] (исполнитель)"
    )

    try:
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Текст совещания:\n{transcribed_text}"}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        print("[LLM] Протокол успешно сгенерирован.")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] Ошибка: {e}")
        return f"Ошибка при обращении к LLM: {str(e)}"

async def handle_connection(websocket):
    print("[SERVER] Клиент (C++) подключился.")
    audio_buffer = np.array([], dtype=np.float32)
    
    try:
        async for message in websocket:
            
            if isinstance(message, bytes):
                chunk = np.frombuffer(message, np.int16).flatten().astype(np.float32) / 32768.0
                audio_buffer = np.concatenate((audio_buffer, chunk))
                
                if len(audio_buffer) >= SAMPLE_RATE * 1.5: 
                    segments, _ = model.transcribe(
                        audio_buffer, beam_size=1, language="ru", condition_on_previous_text=False
                    )
                    text = " ".join([segment.text for segment in segments]).strip()
                    
                    if text:
                        await websocket.send(json.dumps({"status": "partial", "text": text}))
            
            elif isinstance(message, str):
                data = json.loads(message)
                command = data.get("command")
                
                if command == "stop_audio":
                    if len(audio_buffer) > 0:
                        segments, _ = model.transcribe(audio_buffer, beam_size=5, language="ru")
                        final_text = " ".join([segment.text for segment in segments]).strip()
                        await websocket.send(json.dumps({"status": "final", "text": final_text}))
                        audio_buffer = np.array([], dtype=np.float32)
                
                elif command == "generate_protocol":
                    full_meeting_text = data.get("text", "")
                    
                    await websocket.send(json.dumps({"status": "processing", "message": "Генерация отчета..."}))
                    
                    protocol_markdown = await generate_protocol_via_llm(full_meeting_text)
                    
                    await websocket.send(json.dumps({"status": "protocol", "text": protocol_markdown}))

    except websockets.exceptions.ConnectionClosed:
        print("[SERVER] Клиент (C++) отключился.")
    except Exception as e:
        print(f"[SERVER] Ошибка: {str(e)}")

async def main():
    print("[SERVER] Запуск WebSocket сервера на ws://localhost:8765")
    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())