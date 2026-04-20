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
    PIP_TIMEOUT=120

# 设置工作目录
WORKDIR /app

# 安装系统依赖和常用工具（带重试）
RUN for i in 1 2 3; do \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            git curl wget vim nano less tree zip unzip procps net-tools iputils-ping && \
        rm -rf /var/lib/apt/lists/* && \
        break || \
        (echo "Retry $i failed, waiting..."; sleep 10); \
    done

# 安装 Node.js (使用 NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

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

# 复制源代码与元数据（editable 安装需完整包路径）
COPY src/anaagent/ ./src/anaagent/

# 复制refer目录（skill和mcp资源）
COPY refer/ ./refer/

# 安装项目（依赖以 pyproject.toml 为准）
RUN pip install --upgrade pip && pip install -e .

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