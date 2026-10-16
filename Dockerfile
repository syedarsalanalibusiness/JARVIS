FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
RUN useradd --create-home jarvis && mkdir -p /app/data /app/user_files && chown -R jarvis:jarvis /app
USER jarvis
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
