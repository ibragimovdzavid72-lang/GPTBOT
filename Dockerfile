# 1) Базовый образ
FROM python:3.11-slim

# 2) Системные пакеты (ffmpeg для TTS/STT)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 3) Рабочая директория
WORKDIR /app

# 4) Зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) Копируем проект
COPY . .

# 6) Экспонируем порт (Railway сам подставит $PORT в CMD)
EXPOSE 8080

# 7) Запуск через uvicorn (используем переменную PORT, если задана Railway)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
