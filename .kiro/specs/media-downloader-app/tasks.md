
# Implementation Plan: Universal Media Downloader

## Overview

Este plano estende a camada Core existente (models, `Downloader`, `FormatSelector`, `FFmpegService`) de forma aditiva, cria as camadas Services e GUI do zero, e constrói a suíte de testes automatizados completa (Requisito 15) exigida pelo design.

**Nota sobre TDD estrito (decisão deste plano):** este projeto adota desenvolvimento orientado a testes de forma estrita. A **Fase 1** escreve a suíte de testes inteira — unitários, de propriedade (Hypothesis) e de exemplo (pytest) — **antes** de qualquer código de implementação novo ser escrito. Dentro da Fase 1:

- Os testes da Seção 2 (que exercitam `FormatSelector`, `Downloader.analyze`, `FFmpegService.merge`, `_get_merge_extension` e `_sanitize_filename`) exercitam código **já implementado e estável**, logo **devem passar imediatamente** ao serem escritos — isso não é "red", é verificação de comportamento existente.
- Os testes das Seções 3, 4, 5 e 6 exercitam código que **ainda não existe** (`convert_to_mp3`, `progress_hook`, `cancel_event`, integração MP3, `AppConfig`, `HistoryEntry`, `ConfigService`, `HistoryService`, `DownloadService`, componentes de GUI). É **esperado e correto** que esses testes **falhem** nesta fase, tipicamente com `ImportError`, `AttributeError` ou `NotImplementedError` — nunca por erro de lógica no próprio teste. Essa é a fase **red** do ciclo TDD.

A **Fase 2** não escreve nenhum teste novo (os testes já existem desde a Fase 1); ela implementa o código, camada por camada, na mesma ordem de dependência já estabelecida (Core estendido → Models novos → Services → GUI → Empacotamento), até que a suíte inteira fique **green**. Cada tarefa de implementação da Fase 2 indica explicitamente qual(is) tarefa(s)/arquivo(s) de teste da Fase 1 ela deve fazer passar.

As subtarefas de verificação manual/estrutural (não automatizáveis via pytest) foram realocadas da Fase 1 para os pontos da Fase 2 em que o artefato correspondente já existe, já que não há nada a inspecionar manualmente antes de uma implementação existir.

## Tasks

### Fase 1 — Escrita completa da suíte de testes (RED esperado para código novo)

- [x] 1. Configurar infraestrutura de testes
  - Adicionar `pytest` e `hypothesis` como dependências de desenvolvimento
  - Criar `pytest.ini`/configuração equivalente e `tests/conftest.py` com fixtures básicas (ex.: fábricas de `FormatInfo`/`MediaInfo`)
  - Criar estrutura de diretórios `tests/core/`, `tests/models/`, `tests/services/`, `tests/gui/`
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 2. Escrever testes para o Core já existente e estável (`FormatSelector`, `Downloader.analyze`, `FFmpegService.merge`, `_get_merge_extension`, `_sanitize_filename`) — espera-se que todos passem imediatamente, pois o código correspondente já está implementado
  - [x] 2.1 Property test: `FormatSelector` respeita altura máxima do vídeo
    - Arquivo: `tests/core/test_format_selector.py`
    - Teste de propriedade (Hypothesis), `@settings(max_examples=100)`
    - `# Feature: media-downloader-app, Property 1: Seleção de vídeo respeita a altura máxima ou falha de forma consistente`
    - _Requirements: 2.2, 2.3_

  - [x] 2.2 Property test: vídeo sem áudio embutido resulta em seleção de áudio consistente
    - Arquivo: `tests/core/test_format_selector.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 2: Vídeo sem áudio embutido sempre resulta em seleção de áudio consistente`
    - _Requirements: 2.4, 2.5_

  - [x] 2.3 Property test: seleção de áudio maximiza o bitrate
    - Arquivo: `tests/core/test_format_selector.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 3: Seleção de áudio sempre maximiza o bitrate`
    - _Requirements: 3.1, 3.3_

  - [x] 2.4 Unit tests de exemplo para casos de borda de seleção
    - Arquivo: `tests/core/test_format_selector.py`
    - Teste de exemplo (pytest): mídia sem nenhum formato (2.6); ausência de formato exclusivamente de áudio ao solicitar áudio (3.2)
    - _Requirements: 2.6, 3.2_

  - [x] 2.5 Property test: comando de merge sempre copia os fluxos sem recodificação
    - Arquivo: `tests/core/test_ffmpeg_service.py`
    - Teste de propriedade (Hypothesis) sobre `FFmpegService.merge` (comportamento já existente)
    - `# Feature: media-downloader-app, Property 8: Comando de merge sempre copia os fluxos sem recodificação`
    - _Requirements: 5.3_

  - [x] 2.6 Property test: arquivos de entrada inexistentes nunca disparam o FFmpeg
    - Arquivo: `tests/core/test_ffmpeg_service.py`
    - Teste de propriedade (Hypothesis) sobre `FFmpegService.merge`
    - `# Feature: media-downloader-app, Property 9: Arquivos de entrada inexistentes nunca disparam o processo do FFmpeg`
    - _Requirements: 5.4_

  - [x] 2.7 Unit tests de exemplo para `FFmpegService.merge`
    - Arquivo: `tests/core/test_ffmpeg_service.py`
    - Teste de exemplo (pytest, com `subprocess.run` mockado): localização do executável via caminho explícito/PATH (5.1); erro descritivo quando FFmpeg não é localizado (5.2); erro quando `returncode != 0` (5.5); erro quando saída esperada não existe após sucesso (5.6); criação do diretório de saída antes de escrever o arquivo (5.7)
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 5.7_

  - [x] 2.8 Property test: mapeamento de metadados tolera campos ausentes
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de propriedade (Hypothesis) sobre `_build_format_info`/`_build_media_info` (comportamento já existente)
    - `# Feature: media-downloader-app, Property 4: Mapeamento de metadados tolera campos ausentes`
    - _Requirements: 1.2, 1.6_

  - [x] 2.9 Property test: URL vazia nunca invoca o yt-dlp
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de propriedade (Hypothesis) sobre `Downloader.analyze` (comportamento já existente)
    - `# Feature: media-downloader-app, Property 5: URL vazia nunca invoca o yt-dlp`
    - _Requirements: 1.3_

  - [x] 2.10 Property test: sanitização de nome de arquivo é segura e idempotente
    - Arquivo: `tests/core/test_filename_sanitization.py`
    - Teste de propriedade (Hypothesis) sobre `_sanitize_filename` (comportamento já existente)
    - `# Feature: media-downloader-app, Property 6: Sanitização de nome de arquivo é segura e idempotente`
    - _Requirements: 11.1, 11.2_

  - [x] 2.11 Property test: seleção do contêiner de merge é determinística
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de propriedade (Hypothesis) sobre `_get_merge_extension` (comportamento já existente)
    - `# Feature: media-downloader-app, Property 7: Seleção do contêiner de merge é determinística`
    - _Requirements: 4.4_

  - [x] 2.12 Unit tests de exemplo para `Downloader.analyze` e `Downloader.download` (comportamento já existente)
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de exemplo (pytest, com `yt_dlp.YoutubeDL` e `FFmpegService` mockados, sem rede real): análise com sucesso retornando `MediaInfo` completa (1.1); erro descritivo quando `yt-dlp` falha (1.4); erro quando a mídia não tem nenhum formato reconhecível (1.5); download de formato único (4.1); download com merge (4.2); remoção dos temporários após merge (4.3); erro quando o diretório de destino não pode ser criado (4.5); `DownloadResult` com `success=False` quando a seleção não tem nenhum formato (4.6); `DownloadResult` de sucesso com caminho e tamanho do arquivo (4.8)
    - _Requirements: 1.1, 1.4, 1.5, 4.1, 4.2, 4.3, 4.5, 4.6, 4.8_

- [x] 3. Escrever testes para as extensões do Core ainda não implementadas (`convert_to_mp3`, integração MP3 no `Downloader`, falhas internas não tratadas) — espera-se que estes testes FALHEM (red) até a Fase 2 implementar o código correspondente
  - [x] 3.1 Property test: validação de bitrate e comando de conversão MP3
    - Arquivo: `tests/core/test_ffmpeg_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 10: Conversão para MP3 valida o bitrate antes de qualquer execução`
    - _Requirements: 6.1, 6.2, 6.3_
    - Resultado esperado nesta fase: falha (`AttributeError`/`NotImplementedError`) — `FFmpegService.convert_to_mp3` ainda não existe

  - [x] 3.2 Property test: falhas internas do `Downloader.download` nunca escapam como exceções não tratadas (nível `Downloader`)
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 11: Falhas internas nunca escapam como exceções não tratadas`
    - _Requirements: 4.7, 6.5_
    - Resultado esperado nesta fase: falha nos cenários que dependem da conversão MP3 (6.5), já que essa integração ainda não existe em `Downloader.download`

  - [x] 3.3 Unit test de exemplo: conversão para MP3 bem-sucedida remove o arquivo intermediário
    - Arquivo: `tests/core/test_downloader.py`
    - Teste de exemplo (pytest, com `FFmpegService` mockado)
    - _Requirements: 6.4_
    - Resultado esperado nesta fase: falha — `Downloader.download` ainda não invoca `convert_to_mp3`

- [x] 4. Escrever testes para os novos Models (`AppConfig`, `HistoryEntry`) — espera-se que estes testes FALHEM (red) até a Fase 2 criar os módulos
  - [x] 4.1 Unit tests de exemplo para `AppConfig`
    - Arquivo: `tests/models/test_config.py`
    - Teste de exemplo (pytest): valores padrão corretos; imutabilidade (`frozen=True`)
    - _Requirements: 13.1, 13.2_
    - Resultado esperado nesta fase: falha por `ImportError` — `app/models/config.py` ainda não existe

  - [x] 4.2 Unit tests de exemplo para `HistoryEntry.file_exists`
    - Arquivo: `tests/models/test_history.py`
    - Teste de exemplo (pytest): `file_exists` verdadeiro quando `file_path` aponta para arquivo existente; falso quando `file_path` é `None` ou o arquivo não existe
    - _Requirements: 14.1, 14.3_
    - Resultado esperado nesta fase: falha por `ImportError` — `app/models/history.py` ainda não existe

- [x] 5. Escrever testes para os novos Services (`ConfigService`, `HistoryService`, `DownloadService`) — espera-se que estes testes FALHEM (red) até a Fase 2 implementar cada serviço
  - [x] 5.1 Property test: round-trip de `AppConfig` e tolerância a corrupção
    - Arquivo: `tests/services/test_config_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 15: Round-trip de Configuração e tolerância a corrupção`
    - _Requirements: 13.3, 13.4_

  - [x] 5.2 Unit tests de exemplo para `ConfigService`
    - Arquivo: `tests/services/test_config_service.py`
    - Teste de exemplo (pytest, usando `tmp_path`): carregamento de configuração previamente persistida (13.1); uso de valores padrão quando nenhuma configuração existe (13.2); `FFmpegService` construído com `config.ffmpeg_path` utiliza esse caminho em vez de buscar no PATH (13.5)
    - _Requirements: 13.1, 13.2, 13.5_

  - [x] 5.3 Property test: toda operação finalizada gera exatamente uma entrada de histórico consistente (nível `HistoryService`)
    - Arquivo: `tests/services/test_history_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 16: Toda operação finalizada gera exatamente uma entrada de histórico consistente`
    - _Requirements: 14.1_

  - [x] 5.4 Unit tests de exemplo para `HistoryService`
    - Arquivo: `tests/services/test_history_service.py`
    - Teste de exemplo (pytest, usando `tmp_path`): consulta do histórico persistido entre instâncias/execuções simuladas (14.2); entrada cujo arquivo referenciado não existe mais é identificável via `file_exists` sem erro (14.3)
    - _Requirements: 14.2, 14.3_

  - [x] 5.5 Property test: falhas internas nunca escapam como exceções não tratadas (nível `DownloadService`)
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de propriedade (Hypothesis, com fakes de `Downloader`/`FormatSelector`/`FFmpegService`)
    - `# Feature: media-downloader-app, Property 11: Falhas internas nunca escapam como exceções não tratadas`
    - _Requirements: 9.4, 10.4_

  - [x] 5.6 Property test: progresso emitido reflete apenas os campos disponíveis
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 12: Progresso emitido reflete apenas os campos disponíveis`
    - _Requirements: 7.2, 7.5_

  - [x] 5.7 Property test: máquina de estados de progresso tem exatamente um estado terminal coerente
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 13: Máquina de estados de progresso tem exatamente um estado terminal coerente`
    - _Requirements: 7.3, 7.4, 8.3_

  - [x] 5.8 Property test: cancelamento não corrompe o destino e remove temporários
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de propriedade (Hypothesis)
    - `# Feature: media-downloader-app, Property 14: Cancelamento não corrompe o destino e remove temporários`
    - _Requirements: 8.2, 8.4_

  - [x] 5.9 Property test: toda operação finalizada gera exatamente uma entrada de histórico consistente (integração com `DownloadService`)
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de propriedade (Hypothesis, com fake de `HistoryService`)
    - `# Feature: media-downloader-app, Property 16: Toda operação finalizada gera exatamente uma entrada de histórico consistente`
    - _Requirements: 14.1_

  - [x] 5.10 Unit tests de exemplo para `DownloadService`
    - Arquivo: `tests/services/test_download_service.py`
    - Teste de exemplo (pytest, com fakes de `Downloader`/`FormatSelector`/`FFmpegService`/`ConfigService`/`HistoryService`): estado inicial emitido ao iniciar operação (7.1); `cancel()` aceito durante operação em curso (8.1); `cancel()` em operação já terminal é no-op sem erro (8.5); `analyze`/`start_download` executam fora da thread chamadora (9.1); notificação de conclusão/falha/cancelamento entregue de forma consultável pela thread principal (9.3); tradução de erro interno em mensagem amigável sem vazar exceção (10.4); aplicação do bitrate de áudio padrão da `Configuração` quando `audio_bitrate` não é informado (6.6)
    - _Requirements: 6.6, 7.1, 8.1, 8.5, 9.1, 9.3, 10.4_

  - Resultado esperado nesta seção: todos os testes de 5.1 a 5.10 falham por `ImportError` — `ConfigService`, `HistoryService` e `DownloadService` ainda não existem

- [x] 6. Escrever testes para a GUI, usando fakes de Services — espera-se que estes testes FALHEM (red) até a Fase 2 construir os componentes
  - [x] 6.1 Unit tests de exemplo para `DownloadPanel`/`ProgressWidget` com fake de `DownloadService`
    - Arquivo: `tests/gui/test_download_panel.py`
    - Teste de exemplo (pytest, com `DownloadService` fake/stub, sem abrir uma janela real): exibição de metadados após análise (12.3); seleção de tipo de download/altura/bitrate/destino refletida nas `DownloadOptions` enviadas (12.4); atualização da barra/rótulo de progresso a partir de `DownloadProgress` sintético (12.5); acionamento de `cancel()` pelo botão "Cancelar" (12.6); exibição de `error_message` em caso de falha (12.7)
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 6.2 Unit tests de exemplo para `HistoryPanel` com fake de `HistoryService`
    - Arquivo: `tests/gui/test_history_panel.py`
    - Teste de exemplo (pytest, com `HistoryService` fake): listagem de entradas persistidas; indicação de ausência de arquivo sem erro
    - _Requirements: 14.2, 14.3_

  - Resultado esperado nesta seção: falha por `ImportError` — os componentes de `app/gui` ainda não existem

- [x] 7. Checkpoint — executar a suíte completa e confirmar o estado RED esperado antes de iniciar a Fase 2
  - Executar `pytest` na suíte inteira
  - Confirmar que todos os testes da Seção 2 (Core já existente) passam
  - Confirmar que os testes das Seções 3, 4, 5 e 6 falham apenas por ausência de implementação (`ImportError`, `AttributeError` ou `NotImplementedError`), nunca por erro de lógica no teste em si
  - Ensure all tests pass for existing code and fail only due to missing implementation for new/extended code; apresentar o relatório ao usuário antes de avançar para a Fase 2, ask the user if questions arise.

### Fase 2 — Implementação para fazer os testes passarem (GREEN), camada por camada

- [ ] 8. Estender `FFmpegService` com `convert_to_mp3`
  - Implementar `SUPPORTED_MP3_BITRATES` e `FFmpegService.convert_to_mp3(audio_path, output_path, bitrate)` em `app/core/ffmpeg_service.py`
  - Validar o bitrate contra `SUPPORTED_MP3_BITRATES` antes de qualquer chamada a `subprocess.run`
  - Reaproveitar `_validate_input_file`, `is_available` e a criação do diretório de saída já usados por `merge`
  - Gerar o comando `ffmpeg -y -i {audio_path} -c:a libmp3lame -b:a {bitrate}k {output_path}`
  - Faz passar: tarefa 3.1 (`tests/core/test_ffmpeg_service.py`)
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 9. Estender `Downloader` com `progress_hook`, `cancel_event`, sanitização unificada e integração de MP3
  - [x] 9.1 Adicionar parâmetro opcional `progress_hook: Callable[[DownloadProgress], None] | None` a `download()`, adaptando o dicionário de `progress_hooks` do `yt-dlp` para `DownloadProgress`, preenchendo apenas os campos presentes
    - Contribui para fazer passar: tarefa 5.6 (`Property 12`), a ser verificada na Fase 2 de Services (tarefa 15)
    - _Requirements: 7.1, 7.2, 7.5_

  - [ ] 9.2 Adicionar `cancel_event: threading.Event | None` cooperativo a `download()`, `_download_single_format`, `_download_to_directory` e `_download_and_merge`
    - Verificar o evento antes de iniciar cada stream, dentro do `progress_hook` do `yt-dlp` e antes de iniciar o merge
    - Remover arquivos temporários/parciais da operação quando o cancelamento é confirmado, sem sobrescrever nenhum arquivo final no destino
    - Contribui para fazer passar: tarefa 5.8 (`Property 14`), a ser verificada na Fase 2 de Services (tarefa 15)
    - _Requirements: 8.2, 8.4_

  - [ ] 9.3 Unificar sanitização de nome de arquivo no caminho de formato único
    - Aplicar `_sanitize_filename` também em `_download_single_format`, igual ao já feito em `_download_and_merge`
    - Mantém passando: tarefa 2.12 (download de formato único, requisito 4.1); `_sanitize_filename` em si já é coberto pela tarefa 2.10
    - _Requirements: 11.1, 11.2_

  - [ ] 9.4 Integrar `convert_to_mp3` ao fluxo de download de áudio
    - Quando `options.download_type == DownloadType.AUDIO` e `options.audio_bitrate is not None`, invocar `FFmpegService.convert_to_mp3` sobre o áudio baixado antes de retornar o `DownloadResult`, removendo o arquivo intermediário não convertido
    - Faz passar: tarefa 3.3 (`tests/core/test_downloader.py`)
    - _Requirements: 6.1, 6.4_

  - [ ] 9.5 Garantir que falhas internas nunca escapem como exceções não tratadas em `download()`
    - Capturar `yt_dlp.utils.DownloadError`, `FFmpegError`, `FormatSelectionError`, `OSError` e `Exception` genérica, retornando sempre `DownloadResult(success=False, error_message=...)`
    - Faz passar: tarefa 3.2 (`Property 11`, nível `Downloader`)
    - _Requirements: 4.7, 6.5_

- [ ] 10. Checkpoint — revisar extensões do Core
  - Ensure all tests pass (Seções 2 e 3 completas), ask the user if questions arise.

- [ ] 11. Criar modelos de suporte `AppConfig` e `HistoryEntry`
  - [ ] 11.1 Criar `app/models/config.py` com `AppConfig` (`default_destination`, `default_download_type`, `preferred_resolution`, `default_audio_bitrate`, `ffmpeg_path`, `theme`) como `dataclass(frozen=True)` com valores padrão
    - Faz passar: tarefa 4.1 (`tests/models/test_config.py`)
    - _Requirements: 13.1, 13.2_

  - [ ] 11.2 Criar `app/models/history.py` com `HistoryEntry` (`url`, `title`, `download_type`, `status`, `file_path`, `timestamp`, `error_message`) e propriedade calculada `file_exists`
    - Faz passar: tarefa 4.2 (`tests/models/test_history.py`)
    - _Requirements: 14.1, 14.3_

- [ ] 12. Criar `ConfigService`
  - Implementar `app/services/config_service.py` com `ConfigService.load()` e `ConfigService.save(config)`, persistindo `AppConfig` em JSON no diretório de configuração do usuário
  - `load()` SHALL retornar `AppConfig` com valores padrão quando o arquivo não existir, estiver corrompido ou for ilegível, sem lançar exceção
  - Faz passar: tarefas 5.1 e 5.2 (`tests/services/test_config_service.py`)
  - _Requirements: 13.1, 13.2, 13.4_

- [ ] 13. Criar `HistoryService`
  - Implementar `app/services/history_service.py` com `HistoryService.add_entry(entry)` e `HistoryService.list_entries()`, persistindo uma lista de `HistoryEntry` em JSON no diretório de dados do usuário
  - `list_entries()` SHALL retornar as entradas em ordem cronológica de inserção
  - Faz passar: tarefas 5.3 e 5.4 (`tests/services/test_history_service.py`)
  - _Requirements: 14.1, 14.2, 14.3_

- [ ] 14. Checkpoint — revisar Models novos e Services base (`ConfigService`, `HistoryService`)
  - Ensure all tests pass (tarefas 4.1, 4.2, 5.1 a 5.4), ask the user if questions arise.

- [ ] 15. Criar `DownloadService`: composição, orquestração e background
  - [ ] 15.1 Implementar `DownloadService.__init__` compondo `Downloader`, `FormatSelector`, `FFmpegService`, `ConfigService` e `HistoryService`, sem exigir que a GUI conheça essas classes
    - _Requirements: 10.1, 10.2_

  - [ ] 15.2 Implementar `analyze(url, on_complete)` retornando `DownloadHandle` e executando a análise em uma worker thread via `ThreadPoolExecutor`
    - Contribui para fazer passar: parte de 5.10 (execução fora da thread chamadora, 9.1)
    - _Requirements: 9.1, 10.1_

  - [ ] 15.3 Implementar `start_download(media, options, on_progress, on_complete)`
    - Selecionar formato(s) via `FormatSelector` (sem reimplementar sua lógica), disparar o download em background com `operation_id` próprio e `cancel_event` associado, publicando `DownloadProgress` por fila/estrutura compartilhada e via `on_progress`
    - Emitir estados na ordem `PENDING → ANALYZING/DOWNLOADING → PROCESSING → estado terminal`
    - Faz passar: tarefas 5.6 e 5.7 (`Property 12` e `Property 13`)
    - _Requirements: 7.1, 7.3, 7.4, 10.3_

  - [ ] 15.4 Implementar `cancel(operation_id)`
    - Sinalizar o `cancel_event` da operação; ser no-op silencioso quando a operação já está em estado terminal (`COMPLETED`, `FAILED`, `CANCELLED`)
    - Faz passar: tarefa 5.8 (`Property 14`); contribui para parte de 5.10 (8.1, 8.5)
    - _Requirements: 8.1, 8.3, 8.5_

  - [ ] 15.5 Capturar exceções não tratadas dentro do worker e traduzi-las em `DownloadProgress`/`DownloadResult` com estado `FAILED`, sem propagar e sem expor exceções de `yt_dlp`/`subprocess`/`threading` à GUI
    - Faz passar: tarefa 5.5 (`Property 11`, nível `DownloadService`); contribui para parte de 5.10 (10.4)
    - _Requirements: 9.4, 10.4_

  - [ ] 15.6 Aplicar valores padrão de `ConfigService` quando não informados nas `DownloadOptions` (destino, tipo de download, bitrate de áudio) antes de chamar `Downloader.download`
    - Contribui para fazer passar: parte de 5.10 (bitrate padrão aplicado, 6.6)
    - _Requirements: 6.6, 13.1_

  - [ ] 15.7 Registrar uma `HistoryEntry` via `HistoryService.add_entry` ao concluir, falhar ou cancelar cada operação de download/merge/conversão
    - Faz passar: tarefa 5.9 (`Property 16`, integração com `DownloadService`)
    - _Requirements: 14.1_

  - [ ]* 15.8 Verificação manual/estrutural (não automatizável como teste unitário): revisar por leitura de código que `DownloadService` expõe análise, download, Merge, Conversão_Para_MP3 e Cancelamento como API única, e que compõe `Downloader`/`FormatSelector`/`FFmpegService` internamente sem exigir que a GUI os conheça
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 16. Checkpoint — revisar camada de Services completa
  - Ensure all tests pass (tarefas 5.5 a 5.10 integralmente), ask the user if questions arise.

- [ ] 17. Criar GUI CustomTkinter consumindo exclusivamente `app/services` e `app/models`
  - [ ] 17.1 Implementar `MainWindow` com o laço `.after(ms, callback)` que drena progresso/resultados das operações ativas periodicamente na thread principal
    - _Requirements: 9.2, 9.3_

  - [ ] 17.2 Implementar `DownloadPanel`
    - Campo de URL, botão "Analisar" (chama `DownloadService.analyze`), exibição de título/uploader/thumbnail quando disponíveis, seletor de Tipo_De_Download, altura máxima (vídeo) ou Bitrate_De_Áudio (áudio) e diretório de destino, botão "Baixar" e botão "Cancelar"
    - _Requirements: 12.2, 12.3, 12.4, 12.6_

  - [ ] 17.3 Implementar `ProgressWidget`
    - Barra de progresso e rótulo de estado atualizados a partir de `DownloadProgress` (percentual e `Estado_Do_Download`)
    - _Requirements: 12.5_

  - [ ] 17.4 Implementar `HistoryPanel`
    - Lista as entradas de `HistoryService.list_entries()`, indicando visualmente quando o arquivo referenciado não existe mais, sem sinalizar erro de execução
    - _Requirements: 14.3_

  - [ ] 17.5 Exibir mensagens de erro no `DownloadPanel`
    - Ao receber falha do `DownloadService`, exibir apenas a string `error_message` ao usuário, nunca stack traces ou exceções internas
    - Faz passar: parte de tarefa 6.1 (12.7)
    - _Requirements: 12.7_

  - [ ] 17.6 Revisar imports da GUI
    - Garantir que nenhum módulo em `app/gui` importa `Downloader`, `FormatSelector` ou `FFmpegService` diretamente; apenas `app.services` e `app.models`
    - _Requirements: 12.8_

  - [ ]* 17.7 Verificação manual/estrutural (não automatizável como teste unitário): confirmar visualmente que a GUI é construída com CustomTkinter (12.1); confirmar que `app/gui` não importa `Downloader`/`FormatSelector`/`FFmpegService` (12.8); confirmar que a interface permanece responsiva a eventos durante uma Operação_Em_Background real (9.2)
    - _Requirements: 9.2, 12.1, 12.8_

  - Faz passar: tarefas 6.1 e 6.2 (`tests/gui/test_download_panel.py`, `tests/gui/test_history_panel.py`)

- [ ] 18. Checkpoint — revisar GUI e fluxo completo
  - Ensure all tests pass (tarefas 6.1 e 6.2), ask the user if questions arise.

- [ ] 19. Preparar empacotamento com PyInstaller
  - Criar o arquivo de build (`.spec` ou script equivalente) incluindo `app/` (GUI, Core, Services, Models) e as dependências necessárias (CustomTkinter, yt-dlp), sem uso de Docker ou containerização em nenhuma etapa
  - _Requirements: 16.1, 16.2, 16.3, 16.5_

  - [ ]* 19.1 Verificação manual (smoke test, não automatizável via pytest): gerar o executável Windows via PyInstaller a partir do arquivo de build e confirmar que o aplicativo inicia e executa um fluxo básico de análise/download
    - _Requirements: 16.2, 16.3_

  - [ ]* 19.2 Verificação manual (smoke test, não automatizável via pytest): em ambiente sem FFmpeg no PATH e sem `ffmpeg_path` configurado, confirmar que o aplicativo empacotado informa ao usuário que o FFmpeg é necessário para Merge/Conversão_Para_MP3, em vez de falhar silenciosamente
    - _Requirements: 16.4_

- [ ] 20. Revisão final de cobertura de testes e execução completa da suíte
  - Confirmar, por inspeção dos comentários `# Feature: media-downloader-app, Property N: ...` em `tests/`, que as 16 Correctness Properties do design.md possuem ao menos um teste de propriedade associado
  - Confirmar que todos os Requisitos 1 a 16 (incluindo os casos de borda citados na Testing Strategy) possuem ao menos um teste automatizado ou, quando explicitamente não automatizável, um item de verificação manual/estrutural correspondente
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ] 20.1 Executar a suíte de testes completa (`pytest`) e garantir que todos os testes passam (GREEN final)
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

## Notes

- **TDD estrito**: a Fase 1 escreve toda a suíte de testes antes de qualquer implementação nova. Testes sobre código já existente (Seção 2) devem passar de imediato; testes sobre código ainda não implementado (Seções 3 a 6) devem falhar nesta fase por ausência de implementação (`ImportError`/`AttributeError`/`NotImplementedError`), nunca por erro de lógica de teste. A Fase 2 não escreve nenhum teste novo — apenas implementa código até a suíte inteira ficar verde.
- Tarefas marcadas com `*` (15.8, 17.7, 19.1, 19.2) são verificações manuais/estruturais não automatizáveis via pytest; foram posicionadas na Fase 2, no ponto em que o artefato correspondente já existe para ser inspecionado.
- Nenhuma tarefa reescreve `app/models`, `app/core/downloader.py`, `app/core/format_selector.py` ou `app/core/ffmpeg_service.py` do zero — apenas estende aditivamente os pontos descritos em "Components and Interfaces" do design.md.
- `FormatSelector` não é alterado por nenhuma tarefa; apenas recebe testes para o comportamento já existente (Requisito 15).
- Testes de propriedade usam Hypothesis com no mínimo 100 exemplos por propriedade, conforme a Testing Strategy do design.md.
- Os checkpoints (tarefas 7, 10, 14, 16, 18) marcam pontos de revisão com o usuário: o 7 encerra a Fase 1 (RED confirmado); os demais marcam o fim de cada camada implementada na Fase 2.
- Cada tarefa de implementação da Fase 2 indica, em "Faz passar"/"Contribui para fazer passar", qual(is) tarefa(s) de teste da Fase 1 ela deve satisfazer.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.5", "2.8", "2.10", "4.1", "4.2", "6.1", "6.2"] },
    { "id": 1, "tasks": ["2.2", "2.6", "2.9", "5.1", "5.3"] },
    { "id": 2, "tasks": ["2.3", "2.7", "2.11", "5.2", "5.4"] },
    { "id": 3, "tasks": ["2.4", "3.1", "2.12"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["5.5"] },
    { "id": 7, "tasks": ["5.6"] },
    { "id": 8, "tasks": ["5.7"] },
    { "id": 9, "tasks": ["5.8"] },
    { "id": 10, "tasks": ["5.9"] },
    { "id": 11, "tasks": ["5.10"] },
    { "id": 12, "tasks": ["9.1"] },
    { "id": 13, "tasks": ["9.2"] },
    { "id": 14, "tasks": ["9.3"] },
    { "id": 15, "tasks": ["9.4"] },
    { "id": 16, "tasks": ["9.5"] },
    { "id": 17, "tasks": ["11.1", "11.2"] },
    { "id": 18, "tasks": ["15.1"] },
    { "id": 19, "tasks": ["15.2"] },
    { "id": 20, "tasks": ["15.3"] },
    { "id": 21, "tasks": ["15.4"] },
    { "id": 22, "tasks": ["15.5"] },
    { "id": 23, "tasks": ["15.6"] },
    { "id": 24, "tasks": ["15.7"] },
    { "id": 25, "tasks": ["15.8"] },
    { "id": 26, "tasks": ["17.1"] },
    { "id": 27, "tasks": ["17.2", "17.3", "17.4"] },
    { "id": 28, "tasks": ["17.5"] },
    { "id": 29, "tasks": ["17.6"] },
    { "id": 30, "tasks": ["17.7"] },
    { "id": 31, "tasks": ["19.1"] },
    { "id": 32, "tasks": ["19.2"] },
    { "id": 33, "tasks": ["20.1"] }
  ]
}
```
