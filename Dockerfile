
ARG PYTHON_VERSION=3.12.1
FROM python:${PYTHON_VERSION}-slim AS base

RUN apt-get update && \
    apt-get install -y pipenv && \
    apt-get install -y \
    fontconfig \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    fonts-noto \
    git && \
    rm -rf /var/lib/apt/lists/*

ENV PORT=7860

ENV PIPENV_VENV_IN_PROJECT=1

WORKDIR /app

# COPY requirements.txt .

# RUN pipenv install --dev --ignore-pipfile

COPY . .

EXPOSE 7860

RUN pipenv run pip install \
    blinker==1.8.2 \
    click==8.1.7 \
    emoji==2.14.0 \
    flask==3.0.3 \
    itsdangerous==2.2.0 \
    pillow==11.0.0 \
    requests==2.32.3 \
    urllib3==1.26.20 \
    werkzeug==3.0.6 \
    fastapi \
    uvicorn \
    git+https://github.com/jay3332/pilmoji@6ff436fe0a28362bd1d411863347face33e3b6ac


# CMD pipenv run python update.py
# CMD pipenv run python -m gunicorn main:app -b 0.0.0.0:7860 -w 8 --timeout 600
# CMD ["sh", "-c", "pipenv run python -m gunicorn main:app -b 0.0.0.0:7860 -w 8 --timeout 600"]

CMD [ "pipenv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "8", "--timeout-keep-alive", "600" ]