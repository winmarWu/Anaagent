# Anaagent Docker Image
# Agent Team Management Platform

FROM python:3.11-slim

LABEL maintainer="Anaagent Team"
LABEL description="Agent Team Management Platform"
LABEL version="0.1.0"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_TIMEOUT=120 \
    NODE_VERSION=20

# 设置工作目录
WORKDIR /app

# 安装系统依赖和常用工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    git \
    curl \
    wget \
    # 编辑器
    vim \
    nano \
    # 文件操作
    less \
    tree \
    htop \
    # 网络工具
    net-tools \
    iputils-ping \
    # 压缩工具
    zip \
    unzip \
    # 进程管理
    procps \
    # Node.js (for Claude Code)
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# 安装 Anaagent claude wrapper（替换原始claude命令）
COPY scripts/claude-wrapper /usr/local/bin/claude-wrapper
RUN chmod +x /usr/local/bin/claude-wrapper && \
    mv /usr/bin/claude /usr/bin/claude-real && \
    mv /usr/local/bin/claude-wrapper /usr/bin/claude && \
    chmod +x /usr/bin/claude

# 复制依赖文件
COPY pyproject.toml README.md ./

# 安装Python依赖（使用官方源，代理会生效）
RUN pip install --upgrade pip && \
    pip install typer rich pydantic pyyaml jinja2 sqlite-vec

# 复制源代码
COPY src/anaagent/ ./src/anaagent/

# 复制refer目录（skill和mcp资源）
COPY refer/ ./refer/

# 安装项目
RUN pip install -e .

# 配置bashrc，默认显示 (base) 环境
COPY scripts/docker-bashrc /root/.bashrc

# 创建数据目录
RUN mkdir -p /root/.anaagent/environments /root/.anaagent/marketplace

# 设置数据卷
VOLUME ["/root/.anaagent"]

# 设置入口点
ENTRYPOINT ["agent"]

# 默认命令
CMD ["--help"]