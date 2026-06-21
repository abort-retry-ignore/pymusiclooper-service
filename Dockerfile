FROM python:3.12-slim

# ffmpeg for audio probing (pymusiclooper uses it internally)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pymusiclooper

WORKDIR /app
COPY server.py .

ENV PYMUSICLOOPER_PORT=7070
EXPOSE 7070

CMD ["python", "server.py"]
