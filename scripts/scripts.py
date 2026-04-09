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
import gc
import tempfile
import soundfile as sf
import torch
from faster_whisper import WhisperModel
from openai import AsyncOpenAI
from pyannote.audio import Pipeline
import warnings
from static_ffmpeg import add_paths
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.core.io")

try:
    add_paths()
    print("[DEBUG] Пути FFmpeg добавлены")
except Exception as e:
    print(f"[DEBUG] Ошибка при добавлении путей FFmpeg: {e}")

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# --- НАСТРОЙКИ ---
MODEL_SIZE = "medium"
SAMPLE_RATE = 16000 
LLM_API_KEY = os.getenv("LLM_API_KEY", "-") 
LLM_BASE_URL = "https://api.groq.com/openai/v1"
LLM_MODEL = "llama-3.3-70b-versatile"        

HF_TOKEN = "-" 

print(f"[INIT] Загрузка модели STT ({MODEL_SIZE})...")
model = WhisperModel(MODEL_SIZE, device="auto", compute_type="float16")
print(f"Модель загружена на устройство: {model.model.device}")

print("[INIT] Загрузка модели диаризации (Pyannote)...")
try:
    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=HF_TOKEN
    )
    
    if diarization_pipeline is None:
        print("[ERROR] Не удалось загрузить модель диаризации. Проверь токен и доступ к Hugging Face.")
        exit(1)
    
    device = torch.device("cpu" if torch.cuda.is_available() else "cpu")
    diarization_pipeline.to(device)
    print("[INIT] Модель диаризации загружена на", device)
except Exception as e:
    print(f"[ERROR] Ошибка загрузки Pyannote. Проверь токен HF и принятие соглашений: {e}")
    exit(1)

llm_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

async def generate_protocol_via_llm(transcribed_text: str) -> str:
    if not transcribed_text or len(transcribed_text) < 10:
        return "Текст совещания слишком короткий или пустой."

    print("[LLM] Отправка запроса на генерацию протокола...")
    system_prompt = (
        "Ты — бизнес-ассистент. Составь протокол совещания на основе расшифровки аудио. "
        "В расшифровке указаны спикеры (SPEAKER_00, SPEAKER_01 и т.д.). "
        "Пойми, кто есть кто по контексту (если возможно, дай им роли: Директор, Менеджер и т.д.).\n"
        "Формат Markdown:\n"
        "## Протокол совещания\n"
        "**Краткое содержание:** [1-2 предложения]\n\n"
        "### 📌 Основные темы:\n- [Тема 1]\n\n"
        "### ✅ Принятые решения:\n- [Решение 1]\n\n"
        "### 📝 Задачи и поручения:\n- [Задача] (кто исполняет)"
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
        return response.choices[0].message.content or "Ошибка: Модель вернула пустой ответ."
    except Exception as e:
        return f"Ошибка при обращении к LLM: {str(e)}"

def process_full_audio_with_speakers(audio_np_array):
    """Синхронная функция: прогоняет всё аудио через Whisper и Pyannote, объединяет результат."""
    print("[DIARIZATION] Начало обработки всего совещания...")
    
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        waveform = torch.from_numpy(audio_np_array).float().unsqueeze(0).to(device)
        
        audio_in_memory = {"waveform": waveform, "sample_rate": 16000}

        print("[DIARIZATION] Распознавание голосов (Pyannote)...")
        diarization_result = diarization_pipeline(audio_in_memory)

        if hasattr(diarization_result, "annotation"):
            annotation = diarization_result.annotation
        else:
            annotation = diarization_result

        print("[DIARIZATION] Транскрибация текста (Whisper)...")
        segments, _ = model.transcribe(
            audio_np_array, 
            beam_size=5, 
            language="ru", 
            vad_filter=True
        )

        transcript_with_speakers = []

        for segment in segments:
            mid = segment.start + (segment.end - segment.start) / 2
            speaker = "Unknown"

            try:
                for turn, _, spk in annotation.itertracks(yield_label=True):
                    if turn.start <= mid <= turn.end:
                        speaker = spk
                        break
            except Exception:
                pass
            
            transcript_with_speakers.append(f"[{speaker}]: {segment.text.strip()}")

        final_text = "\n".join(transcript_with_speakers)
        
        if not final_text.strip():
            return "Голоса не распознаны или запись пуста."
            
        return final_text

    except Exception as e:
        print(f"[ERROR] Ошибка диаризации: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Ошибка обработки: {str(e)}"
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

async def handle_connection(websocket):
    print("[SERVER] Клиент подключился.")
    
    phrase_buffer = np.array([], dtype=np.float32)
    full_meeting_chunks = []
    
    processing_live = False

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                chunk = np.frombuffer(message, np.int16).flatten().astype(np.float32) / 32768.0
                phrase_buffer = np.concatenate((phrase_buffer, chunk))
                full_meeting_chunks.append(chunk)
                
                if not processing_live and len(phrase_buffer) >= SAMPLE_RATE * 1.5:
                    processing_live = True
                    try:
                        audio_to_show = phrase_buffer[-(SAMPLE_RATE * 5):]
                        segments, _ = await asyncio.to_thread(
                            model.transcribe, 
                            audio_to_show, 
                            beam_size=5, 
                            language="ru",
                            vad_filter=True,
                            no_speech_threshold=0.6,
                            condition_on_previous_text=False
                        )
                        text = " ".join([s.text for s in segments]).strip()
                        if text:
                            await websocket.send(json.dumps({"status": "partial", "text": text}))
                    finally:
                        processing_live = False
            
            elif isinstance(message, str):
                data = json.loads(message)
                if data.get("command") == "stop_audio":
                    print(f"[SERVER] Финализация фразы (длина: {len(phrase_buffer)/SAMPLE_RATE:.1f} сек)")
                    
                    if len(phrase_buffer) > SAMPLE_RATE * 0.5:
                        segments, _ = await asyncio.to_thread(
                            model.transcribe, 
                            phrase_buffer, 
                            beam_size=5, 
                            language="ru",
                            vad_filter=True,
                            no_speech_threshold=0.6,
                            condition_on_previous_text=False
                        )
                        final_text = " ".join([s.text for s in segments]).strip()
                        
                        if final_text:
                            await websocket.send(json.dumps({"status": "final", "text": final_text}))
                    
                    phrase_buffer = np.array([], dtype=np.float32)
                
                elif data.get("command") == "generate_protocol":
                    await websocket.send(json.dumps({
                        "status": "processing", 
                        "message": "Генерация протокола..."
                    }))
                    
                    if full_meeting_chunks:
                        full_meeting_buffer = np.concatenate(full_meeting_chunks)
                        
                        text_with_speakers = await asyncio.to_thread(
                            process_full_audio_with_speakers, 
                            full_meeting_buffer
                        )
                        
                        protocol_markdown = await generate_protocol_via_llm(text_with_speakers)
                        await websocket.send(json.dumps({
                            "status": "protocol", 
                            "text": protocol_markdown
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "status": "error", 
                            "message": "Нет данных для обработки"
                        }))

    except websockets.exceptions.ConnectionClosed:
        print("[SERVER] Клиент отключился.")
    except Exception as e:
        print(f"[SERVER] Ошибка: {str(e)}")

async def main():
    print("[SERVER] Запуск WebSocket сервера на ws://localhost:8765")
    async with websockets.serve(
        handle_connection, 
        "localhost", 
        8765,
        ping_interval=None, 
        ping_timeout=None
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())