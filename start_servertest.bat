@echo off
echo Starting PDF to PowerPoint Converter (Unified Version)...
echo.

cd /d "%~dp0"

REM Activate virtual environment if exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Set Gemini API Key (replace with your key for normal mode)
set GEMINI_API_KEY=AIzaSyABkSxjhUkkWzRbZ4YVilntb9fJOiIklxA

REM Start the server
echo Starting server on http://localhost:8000
echo Open http://localhost:8000/static/index.html in your browser
echo.
python server.py

pause
