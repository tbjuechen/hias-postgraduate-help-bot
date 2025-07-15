FROM python:3.11-slim

WORKDIR /app

COPY . .

# 安装依赖、ffmpeg、字体，清理缓存
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        fonts-arphic-uming \
        fonts-arphic-ukai \
        fonts-noto-cjk \
        fonts-liberation \
        fonts-dejavu && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "bot.py"]