# -*- mode: python ; coding: utf-8 -*-
"""
Arquivo de build do PyInstaller — Universal Media Downloader (Windows).

Empacota a GUI (CustomTkinter) e as camadas Core/Services/Models do
aplicativo em um único executável Windows ("onefile"), sem uso de Docker
ou qualquer containerização em nenhuma etapa do processo (Requisito 16.5).

Como gerar o executável
------------------------
A partir da raiz do repositório, com o ambiente virtual do projeto ativo
(mesmo ambiente onde `customtkinter` e `yt-dlp` estão instalados) e com
`pyinstaller==6.22.3` instalado (ver `requirements-dev.txt`):

    pyinstaller media_downloader.spec

ou, sem ativar o venv, usando o Python do `.venv` diretamente:

    .venv\\Scripts\\python.exe -m PyInstaller media_downloader.spec

O executável final é gerado em `dist\\UniversalMediaDownloader.exe`.
Para refazer um build do zero (ignorando o cache do PyInstaller), use:

    pyinstaller --clean media_downloader.spec

Sobre o FFmpeg (Requisito 16.4)
--------------------------------
Este build NÃO empacota `ffmpeg.exe`. `FFmpegService` localiza o FFmpeg em
tempo de execução via PATH ou via `AppConfig.ffmpeg_path` configurado pelo
usuário, e já trata a ausência do executável como um erro descritivo (em
vez de falha silenciosa) nas operações de Merge e Conversão_Para_MP3 —
esse comportamento é responsabilidade do `FFmpegService`/`DownloadService`
em tempo de execução, não do empacotamento.

Compatibilidade (Requisito 16.1): este build assume Python 3.11+, a mesma
versão mínima suportada pelo aplicativo.

Metadados do executável (ícone e version-info)
-----------------------------------------------
O executável gerado inclui metadados padrão do Windows (ícone exibido no
Explorer/barra de tarefas e as informações da aba "Detalhes" das
propriedades do arquivo), configurados via `icon=`/`version=` em `EXE(...)`:

- `assets/icon.ico`: ícone do aplicativo (placeholder; gerado por
  `scripts/generate_icon.py`, sem dependências externas).
- `version_info.txt`: arquivo de version-info no formato de
  `PyInstaller.utils.win32.versioninfo` (nome do produto, versão, empresa,
  descrição), lido automaticamente pelo PyInstaller a partir do caminho
  informado em `version=`.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# `customtkinter` distribui temas/assets (JSON, imagens) como dados do
# pacote que a análise estática do PyInstaller não detecta sozinha, e
# `yt-dlp` também inclui dados de pacote (ex.: metadados de extratores).
datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("yt_dlp")

# A GUI resolve `app.services`/`app.models` dinamicamente, e os próprios
# services importam `app.core` internamente; `collect_submodules` garante
# que todos os submódulos de cada camada sejam incluídos mesmo que a
# análise estática do PyInstaller não os encontre via import direto.
hiddenimports = []
hiddenimports += collect_submodules("app.gui")
hiddenimports += collect_submodules("app.core")
hiddenimports += collect_submodules("app.services")
hiddenimports += collect_submodules("app.models")
hiddenimports += collect_submodules("customtkinter")
hiddenimports += collect_submodules("yt_dlp")

a = Analysis(
    ["run_gui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Passar `a.binaries`/`a.datas` diretamente para `EXE` (em vez de usar
# `exclude_binaries=True` + `COLLECT`) é o que produz um único executável
# ("onefile"), em vez de uma pasta com o executável e suas dependências
# ("onedir").
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="UniversalMediaDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    version="version_info.txt",
)
