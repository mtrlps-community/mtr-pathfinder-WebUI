FROM python:slim-bookworm

# 设置工作目录
WORKDIR /app

# 安装系统依赖，包括libraqm和其他可能需要的包
RUN apt-get update && apt-get install -y --no-install-recommends \
    libraqm-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件到容器中
COPY . /app

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露应用端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0

# 启动应用
CMD ["flask", "run"]