@echo off
setlocal
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
if defined EM_RAG_PYTHON (
  "%EM_RAG_PYTHON%" -m src.bootstrap_launcher %*
) else (
  py -3.11 -m src.bootstrap_launcher %*
  if errorlevel 1 python -m src.bootstrap_launcher %*
)
