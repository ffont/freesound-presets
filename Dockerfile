FROM python:3.9
ENV PYTHONUNBUFFERED 1
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.0/dumb-init_1.2.0_amd64 && chmod +x /usr/local/bin/dumb-init
RUN mkdir /app
WORKDIR /app
RUN apt-get update && apt-get install -y ffmpeg
ADD requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
ADD ./ /app/
ENTRYPOINT [ "python", "/app/freesound-presets.py" ]