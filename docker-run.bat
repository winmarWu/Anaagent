@echo off
REM Anaagent Docker 快捷脚本 (Windows)

set IMAGE_NAME=anaagent
set CONTAINER_NAME=anaagent-cli

if "%1"=="" goto help
if "%1"=="build" goto build
if "%1"=="run" goto run
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="exec" goto exec_cmd
if "%1"=="shell" goto shell
if "%1"=="clean" goto clean
if "%1"=="help" goto help
goto run

:build
echo Building Anaagent Docker image...
docker build -t %IMAGE_NAME%:latest .
echo Build complete!
goto end

:run
shift
docker run -it --rm ^
    -v anaagent-data:/root/.anaagent ^
    -v "%cd%/workspace:/workspace" ^
    -w /workspace ^
    %IMAGE_NAME%:latest %*
goto end

:start
docker run -d --name %CONTAINER_NAME% ^
    -v anaagent-data:/root/.anaagent ^
    -v "%cd%/workspace:/workspace" ^
    -w /workspace ^
    --restart unless-stopped ^
    %IMAGE_NAME%:latest sleep infinity
echo Container %CONTAINER_NAME% started
goto end

:stop
docker stop %CONTAINER_NAME% 2>nul
docker rm %CONTAINER_NAME% 2>nul
echo Container stopped
goto end

:exec_cmd
shift
docker exec -it %CONTAINER_NAME% anaagent %*
goto end

:shell
docker exec -it %CONTAINER_NAME% /bin/bash
goto end

:clean
docker rmi %IMAGE_NAME%:latest 2>nul
docker volume rm anaagent-data 2>nul
echo Cleaned up
goto end

:help
echo Anaagent Docker Helper (Windows)
echo.
echo Usage: docker-run.bat [command] [args...]
echo.
echo Commands:
echo   build       Build Docker image
echo   run [cmd]   Run command in temporary container
echo   start       Start background container
echo   stop        Stop background container
echo   exec [cmd]  Execute command in running container
echo   shell       Open shell in running container
echo   clean       Remove image and volume
echo   help        Show this help
echo.
echo Examples:
echo   docker-run.bat build
echo   docker-run.bat run env list
echo   docker-run.bat run --help
echo   docker-run.bat start
echo   docker-run.bat exec env activate my_team
echo   docker-run.bat shell
goto end

:end