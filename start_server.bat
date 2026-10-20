@echo off

@REM cd /d "%~dp0third_party\MeloTTS-main"
@REM start "MOMO TTS" cmd /c "start_melo_server.bat"

@REM cd /d "%~dp0third_party\Funasr"
@REM start "MOMO funASR" cmd /c "start_server.bat"

cd /d "%~dp0third_party\PDF"
start "MOMO Reader" cmd /c "start_server.bat"

cd /d "%~dp0third_party\blivedm-dev\momo"
start "MOMO blivedm" cmd /c "start_server.bat"

cd /d "%~dp0third_party\Submit\desktop"
start "MOMO subtitle" cmd /c "start_momo_sub.bat"