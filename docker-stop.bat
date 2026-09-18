@echo off
REM Stop the Maptology Streamlit container if it is running.

setlocal EnableExtensions

set "CONTAINER_NAME=maptology"

docker ps -a --format "{{.Names}}" | findstr /x /c:"%CONTAINER_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Container '%CONTAINER_NAME%' is not present.
  exit /b 0
)

docker ps --format "{{.Names}}" | findstr /x /c:"%CONTAINER_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Container '%CONTAINER_NAME%' is already stopped.
  exit /b 0
)

echo Stopping container '%CONTAINER_NAME%'...
docker stop "%CONTAINER_NAME%"
if errorlevel 1 (
  echo Failed to stop container '%CONTAINER_NAME%'.
  exit /b 1
)

echo Container '%CONTAINER_NAME%' stopped.
endlocal
