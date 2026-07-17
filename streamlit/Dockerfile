# Build from the repo root so main.py, images/, fonts/, wrap.py, and
# requirements.txt are in the build context, e.g.:
#   docker build -f streamlit/Dockerfile -t miaq-streamlit .
ARG PYTHON_VERSION=3.12.1
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && \
    apt-get install -y \
    fontconfig \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    fonts-noto \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8501
EXPOSE 8501

CMD ["sh", "-c", "streamlit run streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true"]
