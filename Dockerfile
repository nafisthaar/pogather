FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# The database and the generated secret key live in /app/instance, so mount a volume there.
RUN useradd --create-home pogather && mkdir -p /app/instance && chown pogather /app/instance
USER pogather

EXPOSE 5000
VOLUME /app/instance
CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000"]
