@echo off
rem Double-click to open the local NXDESK stacks in Chrome (see open-nxdesk-local.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-nxdesk-local.ps1" %*
