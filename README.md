# Universal Media Downloader

Aplicativo desktop para análise, seleção e download de mídia (vídeo e áudio) a partir de URLs suportadas pelo [yt-dlp](https://github.com/yt-dlp/yt-dlp), com conversão de áudio para MP3, merge de vídeo+áudio via FFmpeg e interface gráfica em [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).

## Funcionalidades

- Análise de URL com extração de título, duração, uploader, thumbnail e formatos disponíveis, sem iniciar download.
- Seleção automática do melhor formato de vídeo (respeitando uma altura máxima) ou de áudio (maximizando o bitrate).
- Download de vídeo e áudio, com merge automático via FFmpeg quando o formato escolhido exige arquivos separados.
- Conversão de áudio baixado para MP3 nos bitrates 128/192/256/320 kbps.
- Progresso e cancelamento de operações em andamento, executadas em background (fora da thread da interface).
- Configurações persistentes (destino padrão, tipo de download padrão, resolução preferida, bitrate de áudio padrão, caminho do FFmpeg, tema).
- Histórico de downloads concluídos, falhados ou cancelados.
- Interface gráfica construída com CustomTkinter, que consome apenas a camada de serviços (`app/services`) e os modelos (`app/models`), nunca os componentes de `app/core` diretamente.

## Arquitetura

```
app/
  core/      # Downloader, FormatSelector, FFmpegService (lógica de negócio)
  models/    # Modelos de domínio (dataclasses): MediaInfo, FormatInfo, AppConfig, HistoryEntry, etc.
  services/  # Camada de orquestração: ConfigService, HistoryService, DownloadService
  gui/       # Interface gráfica (CustomTkinter): MainWindow, DownloadPanel, ProgressWidget, HistoryPanel
tests/       # Suíte de testes (pytest + Hypothesis), espelhando a estrutura de app/
```

O FFmpeg é usado exclusivamente através do `FFmpegService`; nenhum outro módulo invoca o executável diretamente. A GUI nunca acessa `app/core` diretamente — toda comunicação passa por `app/services`.

## Requisitos

- Python 3.11 ou superior.
- [FFmpeg](https://ffmpeg.org/download.html) instalado e disponível no PATH (ou configurado via `ffmpeg_path` nas configurações do app). É necessário apenas para merge de vídeo+áudio e para conversão para MP3; a análise e o download de formatos únicos funcionam sem ele.

## Instalação

Clone o repositório e crie um ambiente virtual:

```bash
git clone https://github.com/<seu-usuario>/universal-media-downloader.git
cd universal-media-downloader
python -m venv .venv
```

Ative o ambiente virtual:

```bash
# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

Instale as dependências de runtime:

```bash
pip install yt-dlp customtkinter
```

Para desenvolvimento (testes e empacotamento), instale também:

```bash
pip install -r requirements-dev.txt
```

## Como executar

### Interface gráfica (GUI)

```bash
python run_gui.py
```

### CLI (script de linha de comando original, útil para depuração rápida do Core)

```bash
python main.py
```

## Testes

O projeto usa `pytest` com testes de propriedade (`hypothesis`) para validar as *Correctness Properties* descritas em `.kiro/specs/media-downloader-app/design.md`.

```bash
pytest
```

## Empacotamento (Windows)

O executável é gerado via [PyInstaller](https://pyinstaller.org/) a partir do arquivo de build `media_downloader.spec`, sem uso de Docker ou containerização:

```bash
pyinstaller media_downloader.spec
```

O executável final fica em `dist\UniversalMediaDownloader.exe`. Veja os comentários em `media_downloader.spec` para detalhes sobre dados empacotados e o comportamento esperado quando o FFmpeg não está disponível.

## Documentação do projeto

O processo de levantamento de requisitos, design e divisão em tarefas deste projeto está documentado em `.kiro/specs/media-downloader-app/` (`requirements.md`, `design.md`, `tasks.md`).