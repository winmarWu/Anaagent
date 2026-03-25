#!/bin/bash
# Anaagent Docker 快捷脚本

IMAGE_NAME="anaagent"
CONTAINER_NAME="anaagent-cli"

# 构建镜像
build() {
    echo "Building Anaagent Docker image..."
    docker build -t ${IMAGE_NAME}:latest .
    echo "Build complete!"
}

# 运行容器（交互模式）
run() {
    docker run -it --rm \
        -v anaagent-data:/root/.anaagent \
        -v "$(pwd)/workspace:/workspace" \
        -w /workspace \
        ${IMAGE_NAME}:latest "$@"
}

# 启动后台容器
start() {
    docker run -d --name ${CONTAINER_NAME} \
        -v anaagent-data:/root/.anaagent \
        -v "$(pwd)/workspace:/workspace" \
        -w /workspace \
        --restart unless-stopped \
        ${IMAGE_NAME}:latest sleep infinity
    echo "Container ${CONTAINER_NAME} started"
}

# 停止容器
stop() {
    docker stop ${CONTAINER_NAME} 2>/dev/null
    docker rm ${CONTAINER_NAME} 2>/dev/null
    echo "Container stopped"
}

# 在运行中的容器执行命令
exec_cmd() {
    docker exec -it ${CONTAINER_NAME} anaagent "$@"
}

# 进入容器shell
shell() {
    docker exec -it ${CONTAINER_NAME} /bin/bash
}

# 清理
clean() {
    docker rmi ${IMAGE_NAME}:latest 2>/dev/null
    docker volume rm anaagent-data 2>/dev/null
    echo "Cleaned up"
}

# 帮助
help() {
    echo "Anaagent Docker Helper"
    echo ""
    echo "Usage: ./docker-run.sh [command] [args...]"
    echo ""
    echo "Commands:"
    echo "  build       Build Docker image"
    echo "  run [cmd]   Run command in temporary container"
    echo "  start       Start background container"
    echo "  stop        Stop background container"
    echo "  exec [cmd]  Execute command in running container"
    echo "  shell       Open shell in running container"
    echo "  clean       Remove image and volume"
    echo "  help        Show this help"
    echo ""
    echo "Examples:"
    echo "  ./docker-run.sh build"
    echo "  ./docker-run.sh run env list"
    echo "  ./docker-run.sh run --help"
    echo "  ./docker-run.sh start"
    echo "  ./docker-run.sh exec env activate my_team"
    echo "  ./docker-run.sh shell"
}

# 主入口
case "$1" in
    build) build ;;
    run) shift; run "$@" ;;
    start) start ;;
    stop) stop ;;
    exec) shift; exec_cmd "$@" ;;
    shell) shell ;;
    clean) clean ;;
    help|--help|-h) help ;;
    *) run "$@" ;;
esac