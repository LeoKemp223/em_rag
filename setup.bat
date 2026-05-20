@echo off
setlocal
set "ROOT_DIR=%~dp0"
set "PROJECT_DIR=%cd%"
if defined PYTHONPATH (
  set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%ROOT_DIR%"
)
cd /d "%PROJECT_DIR%"
if defined EM_RAG_PYTHON (
  "%EM_RAG_PYTHON%" -m src.bootstrap_launcher %*
) else (
  py -3.11 -m src.bootstrap_launcher %*
  if errorlevel 1 python -m src.bootstrap_launcher %*
)
