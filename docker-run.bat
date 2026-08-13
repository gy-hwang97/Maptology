@echo off
REM Stop, rebuild, and start the Maptology Streamlit container.

setlocal EnableExtensions

if not defined MAPTOLOGY_PORT set "MAPTOLOGY_PORT=8501"
if not defined BIOPORTAL_APIKEY set "BIOPORTAL_APIKEY=<YOUR_API_KEY>"
if not defined MAPTOLOGY_DOWNLOAD_ALL set "MAPTOLOGY_DOWNLOAD_ALL=yes"

set "IMAGE_NAME=maptology"
set "CONTAINER_NAME=maptology"

if "%BIOPORTAL_APIKEY%"=="<YOUR_API_KEY>" (
  echo BIOPORTAL_APIKEY is still set to the placeholder ^<YOUR_API_KEY^>.
  echo Get a free key at https://bioportal.bioontology.org/accounts, then either:
  echo   set BIOPORTAL_APIKEY=your-key-here
  echo or replace ^<YOUR_API_KEY^> with your key in docker-run.bat, and run this script again.
  exit /b 1
)

if not "%MAPTOLOGY_DOWNLOAD_ALL%"=="yes" if not "%MAPTOLOGY_DOWNLOAD_ALL%"=="no" (
  echo MAPTOLOGY_DOWNLOAD_ALL must be "yes" or "no" ^(got: "%MAPTOLOGY_DOWNLOAD_ALL%"^).
  echo Either:
  echo   set MAPTOLOGY_DOWNLOAD_ALL=yes
  echo or set MAPTOLOGY_DOWNLOAD_ALL to "yes" or "no" in docker-run.bat.
  exit /b 1
)

cd /d "%~dp0"

docker ps -a --format "{{.Names}}" | findstr /x /c:"%CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo Stopping and removing existing container '%CONTAINER_NAME%'...
  docker stop "%CONTAINER_NAME%" >nul 2>&1
  docker rm "%CONTAINER_NAME%" >nul 2>&1
)

echo Building image '%IMAGE_NAME%'...
docker build -t "%IMAGE_NAME%" .
if errorlevel 1 (
  echo Build failed; container was not started.
  exit /b 1
)

if not exist "ontology_cache" mkdir ontology_cache
if not exist "tfidf_cache" mkdir tfidf_cache

echo Starting container '%CONTAINER_NAME%' on port %MAPTOLOGY_PORT%...
docker run -d ^
  --name "%CONTAINER_NAME%" ^
  -p "%MAPTOLOGY_PORT%:8501" ^
  -e "BIOPORTAL_APIKEY=%BIOPORTAL_APIKEY%" ^
  -e "MAPTOLOGY_DOWNLOAD_ALL=%MAPTOLOGY_DOWNLOAD_ALL%" ^
  -v "%cd%\ontology_cache:/app/ontology_cache" ^
  -v "%cd%\tfidf_cache:/app/tfidf_cache" ^
  "%IMAGE_NAME%"
if errorlevel 1 (
  echo Failed to start container.
  exit /b 1
)

echo Maptology is running at http://localhost:%MAPTOLOGY_PORT%
endlocal
