FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 安装系统依赖
# ffmpeg: 多媒体处理
# fonts-*: 字体支持
# build-essential: 编译依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        fonts-arphic-uming \
        fonts-arphic-ukai \
        fonts-noto-cjk \
        fonts-liberation \
        fonts-dejavu \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 1. 先复制依赖文件 (利用 Docker 缓存)
COPY requirements.txt .

# 2. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 3. 下载 spaCy 模型
RUN python -m spacy download zh_core_web_sm && \
    python -m spacy download en_core_web_sm

# 4. 最后复制项目代码
COPY . .

# 5. 设置启动脚本权限
RUN chmod +x scripts/entrypoint.sh

CMD ["./scripts/entrypoint.sh"]