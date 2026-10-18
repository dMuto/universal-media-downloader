# Requirements Document

## Introduction

O "Universal Media Downloader" é um aplicativo desktop para análise, seleção e download de mídia (vídeo e áudio) a partir de URLs suportadas pelo `yt-dlp`, com conversão de áudio para MP3 e interface gráfica em CustomTkinter.

Este projeto **já possui uma base de código funcional parcial**. Especificamente:

- `app/models` contém os modelos de domínio já implementados e estáveis: `FormatInfo`, `MediaType`, `MediaInfo`, `DownloadType`, `DownloadStatus`, `DownloadOptions`, `DownloadProgress`, `DownloadResult` e `FormatSelection`.
- `app/core/downloader.py` já implementa `Downloader.analyze()` (extração de metadados via `yt-dlp`, sem download) e `Downloader.download()` (download de formato único ou download+merge de vídeo/áudio separados via FFmpeg).
- `app/core/format_selector.py` já implementa `FormatSelector.select()`, com lógica de pontuação e seleção de formatos de vídeo e áudio.
- `app/core/ffmpeg_service.py` já implementa `FFmpegService`, responsável por localizar o executável do FFmpeg e executar merge de vídeo+áudio sem recodificação (`-c:v copy -c:a copy`).
- `main.py` é atualmente um script de linha de comando (CLI) síncrono que exercita as camadas acima; não é uma interface gráfica.

Os requisitos abaixo descrevem o **comportamento final desejado** do aplicativo, cobrindo tanto o que já é satisfeito pela implementação atual quanto o que ainda precisa ser construído (conversão de áudio em MP3, orquestração em `app/services`, interface gráfica em `app/gui`, progresso, cancelamento, execução em background, configurações persistentes, histórico, testes automatizados e empacotamento). Cada Requisito indica uma nota de "Status atual" que resume o estado real da implementação, com base na auditoria de código realizada neste repositório.

Antes de iniciar o design e a divisão em tarefas, o spec `codebase-technical-audit` (`.kiro/specs/codebase-technical-audit/`) deve ser consultado, pois contém o inventário de arquitetura, o mapa de funcionalidades, a lista de problemas e a análise de dependências e riscos já levantados para este mesmo repositório. Isso evita descartar ou duplicar trabalho funcional já existente sem justificativa registrada.

O desenvolvimento seguirá etapas incrementais verificáveis; a ordem e a priorização dessas etapas são definidas nos documentos de design e tarefas (`tasks.md`), não neste documento.

### Restrições e notas transversais

- O aplicativo não deve depender de Docker ou de qualquer containerização para execução ou distribuição.
- A lógica de negócio (análise, seleção de formato, download, conversão, orquestração) não deve ser acoplada a componentes de GUI; a GUI deve depender da camada de Services, nunca o contrário.
- Nenhuma operação potencialmente demorada (análise de URL, download, merge, conversão) deve ser executada na thread principal/thread de interface.
- Todo uso do FFmpeg deve ser centralizado em `FFmpegService`; nenhum outro módulo deve invocar o executável do FFmpeg diretamente.
- A lógica de seleção de formatos deve permanecer centralizada em `FormatSelector`; nenhum outro módulo deve reimplementar critérios de seleção de formato.
- Nenhum requisito ou implementação deve presumir que todos os provedores de mídia retornam metadados ou formatos uniformes (ex.: nem todo formato tem altura, codec de áudio ou tamanho conhecido).
- Componentes existentes e funcionais (`app/models`, `app/core/downloader.py`, `app/core/format_selector.py`, `app/core/ffmpeg_service.py`) não devem ser apagados, reestruturados ou substituídos por versões simplificadas sem antes verificar suas dependências e sem justificativa registrada.
- Documentação de usuário ou de projeto (além dos artefatos de spec) não deve ser criada antes da etapa final de desenvolvimento.

## Glossary

- **Mídia**: Recurso de vídeo e/ou áudio identificado por uma URL, representado pelo modelo `MediaInfo` (título, duração, uploader, thumbnail, URL original e lista de `Formato`).
- **Formato**: Uma variante específica de codificação/qualidade de uma Mídia, representada pelo modelo `FormatInfo` (format_id, extensão, largura, altura, fps, codec de vídeo, codec de áudio, bitrate, tamanho e `Tipo_De_Mídia`).
- **Tipo_De_Mídia**: Enumeração `MediaType` que classifica um Formato como `VIDEO`, `AUDIO` ou `VIDEO_AUDIO`.
- **Seleção_De_Formato**: Resultado da escolha de Formatos para um download, representado pelo modelo `FormatSelection` (video_format, audio_format e a propriedade `requires_merge`).
- **Opções_De_Download**: Parâmetros informados para um download, representados pelo modelo `DownloadOptions` (url, download_type, format_id, max_height, audio_bitrate, destination).
- **Tipo_De_Download**: Enumeração `DownloadType` que indica se o usuário deseja `VIDEO` ou `AUDIO`.
- **Estado_Do_Download**: Enumeração `DownloadStatus` que representa a fase atual de uma operação (PENDING, ANALYZING, DOWNLOADING, PROCESSING, COMPLETED, FAILED, CANCELLED).
- **Progresso_Do_Download**: Representação do avanço de uma operação em curso, modelo `DownloadProgress` (status, percentage, downloaded_bytes, total_bytes, speed, eta, filename).
- **Resultado_Do_Download**: Representação do desfecho final de uma operação, modelo `DownloadResult` (success, file_path, file_size, error_message).
- **Downloader**: Componente de `app/core/downloader.py` responsável por analisar URLs (`analyze`) e executar downloads (`download`), incluindo o caso de merge.
- **FormatSelector**: Componente de `app/core/format_selector.py` responsável por selecionar o(s) Formato(s) adequados a partir de uma Mídia e das Opções_De_Download.
- **FFmpegService**: Componente de `app/core/ffmpeg_service.py` responsável por localizar o executável FFmpeg e executar operações de merge e conversão de mídia.
- **Merge**: Operação de combinar um Formato de vídeo e um Formato de áudio, baixados separadamente, em um único arquivo de saída, sem recodificação.
- **Conversão_Para_MP3**: Operação de transformar um arquivo de áudio baixado no formato MP3, em um dos Bitrates_De_Áudio suportados.
- **Bitrate_De_Áudio**: Taxa de bits em kbps usada na Conversão_Para_MP3, restrita aos valores 128, 192, 256 e 320.
- **Serviço_De_Orquestração**: Componente da camada `app/services` responsável por coordenar `Downloader`, `FormatSelector` e `FFmpegService` e expor operações de alto nível para a GUI.
- **GUI**: Interface gráfica do aplicativo, construída com CustomTkinter, localizada em `app/gui`.
- **Configuração**: Conjunto de preferências persistentes do aplicativo (diretório padrão de destino, tipo de download padrão, resolução preferida, Bitrate_De_Áudio padrão, caminho do FFmpeg, preferências visuais).
- **Histórico_De_Downloads**: Registro persistente de operações de download concluídas, falhadas ou canceladas.
- **Operação_Em_Background**: Execução de análise, download, Merge ou Conversão_Para_MP3 fora da thread principal da aplicação.
- **Cancelamento**: Interrupção solicitada pelo usuário de uma Operação_Em_Background ainda não concluída.

## Requirements

### Requirement 1: Análise de URL de Mídia

**User Story:** Como usuário, eu quero informar a URL de uma mídia, para que o aplicativo me mostre título, metadados e Formatos disponíveis antes de baixar.

Status atual: já implementado em `app/core/downloader.py` (`Downloader.analyze`).

#### Acceptance Criteria

1. WHEN o usuário fornece uma URL não vazia, THE Downloader SHALL extrair as informações da Mídia sem iniciar nenhum download de conteúdo.
2. WHEN a análise é concluída com sucesso, THE Downloader SHALL retornar uma `MediaInfo` contendo título, duração (quando disponível), uploader (quando disponível), thumbnail (quando disponível), URL original e a lista de Formatos disponíveis.
3. IF a URL fornecida estiver vazia ou contiver apenas espaços, THEN THE Downloader SHALL rejeitar a análise com um erro descritivo, sem invocar o `yt-dlp`.
4. IF o `yt-dlp` falhar ao extrair informações da URL fornecida, THEN THE Downloader SHALL sinalizar um erro de análise descritivo, sem lançar uma exceção não tratada.
5. IF a extração retornar uma Mídia sem nenhum Formato de vídeo ou áudio reconhecível, THEN THE Downloader SHALL sinalizar um erro de análise descritivo.
6. THE Downloader SHALL representar cada Formato retornado pelo `yt-dlp` sem presumir que todos os campos de metadados (altura, fps, codec, bitrate, tamanho) estejam presentes.

### Requirement 2: Seleção de Formato para Download de Vídeo

**User Story:** Como usuário, eu quero que o aplicativo escolha automaticamente o melhor Formato de vídeo compatível com a resolução máxima desejada, para que eu não precise analisar manualmente a lista de Formatos.

Status atual: já implementado em `app/core/format_selector.py` (`FormatSelector.select` e `FormatSelector._select_video`).

#### Acceptance Criteria

1. WHEN o Tipo_De_Download solicitado é `VIDEO`, THE FormatSelector SHALL selecionar, entre os Formatos com vídeo, o de maior prioridade segundo altura, presença de áudio embutido, bitrate e preferência por contêiner MP4, nessa ordem.
2. WHERE uma altura máxima é informada nas Opções_De_Download, THE FormatSelector SHALL restringir a seleção aos Formatos de vídeo cuja altura não exceda o valor informado.
3. IF nenhum Formato de vídeo atender à altura máxima informada, THEN THE FormatSelector SHALL sinalizar um erro de seleção descritivo.
4. IF o Formato de vídeo selecionado não possuir áudio embutido, THEN THE FormatSelector SHALL selecionar adicionalmente o melhor Formato de áudio disponível, compondo uma Seleção_De_Formato cuja propriedade `requires_merge` seja verdadeira.
5. IF o Formato de vídeo selecionado não possuir áudio embutido e nenhum Formato de áudio separado estiver disponível na Mídia, THEN THE FormatSelector SHALL sinalizar um erro de seleção descritivo.
6. IF a Mídia não possuir nenhum Formato, THEN THE FormatSelector SHALL sinalizar um erro de seleção descritivo antes de considerar o Tipo_De_Download.

### Requirement 3: Seleção de Formato para Download de Áudio

**User Story:** Como usuário, eu quero que o aplicativo escolha automaticamente o Formato de áudio de melhor qualidade disponível, para que eu obtenha o melhor áudio possível sem decidir manualmente.

Status atual: já implementado em `app/core/format_selector.py` (`FormatSelector._select_audio`).

#### Acceptance Criteria

1. WHEN o Tipo_De_Download solicitado é `AUDIO`, THE FormatSelector SHALL selecionar, entre os Formatos exclusivamente de áudio, o de maior bitrate, usando a compatibilidade com contêineres da família MP4 como critério de desempate.
2. IF a Mídia não possuir nenhum Formato exclusivamente de áudio, THEN THE FormatSelector SHALL sinalizar um erro de seleção descritivo.
3. THE FormatSelector SHALL compor, para download de áudio, uma Seleção_De_Formato contendo apenas o Formato de áudio selecionado.

### Requirement 4: Download de Vídeo (Formato Único ou com Merge)

**User Story:** Como usuário, eu quero baixar o vídeo selecionado, incluindo os casos em que vídeo e áudio precisam ser combinados, para que eu obtenha um único arquivo reproduzível no destino escolhido.

Status atual: já implementado em `app/core/downloader.py` (`Downloader.download`, `_download_single_format`, `_download_and_merge`); nomes de arquivo não são sanitizados no caminho de formato único (ver Requisito 11).

#### Acceptance Criteria

1. WHEN a Seleção_De_Formato não requer Merge, THE Downloader SHALL baixar o Formato único diretamente para o diretório de destino informado nas Opções_De_Download.
2. WHEN a Seleção_De_Formato requer Merge, THE Downloader SHALL baixar o Formato de vídeo e o Formato de áudio separadamente em um diretório temporário e then invocar o FFmpegService para combiná-los em um único arquivo no diretório de destino.
3. WHEN o Merge é concluído com sucesso, THE Downloader SHALL remover os arquivos temporários de vídeo e áudio utilizados na combinação.
4. THE Downloader SHALL escolher o contêiner de saída do Merge (`.mp4` ou `.mkv`) com base na extensão do vídeo e no codec de áudio, de forma a preservar os fluxos sem recodificação sempre que possível.
5. IF o diretório de destino informado não puder ser criado, THEN THE Downloader SHALL retornar um `DownloadResult` com `success` falso e uma mensagem de erro descritiva, sem iniciar o download.
6. IF nenhum Formato de vídeo nem de áudio estiver presente na Seleção_De_Formato, THEN THE Downloader SHALL retornar um `DownloadResult` com `success` falso, sem invocar o `yt-dlp`.
7. IF o download ou o Merge falhar por erro do `yt-dlp`, do FFmpegService ou de acesso a arquivos, THEN THE Downloader SHALL retornar um `DownloadResult` com `success` falso e uma mensagem de erro descritiva, sem lançar uma exceção não tratada.
8. WHEN o download é concluído com sucesso, THE Downloader SHALL retornar um `DownloadResult` com `success` verdadeiro, o caminho do arquivo final e seu tamanho em bytes, quando determinável.

### Requirement 5: Combinação de Vídeo e Áudio via FFmpeg

**User Story:** Como usuário, eu quero que vídeo e áudio baixados separadamente sejam combinados automaticamente, para que eu obtenha um único arquivo sem perda de qualidade por recodificação.

Status atual: já implementado em `app/core/ffmpeg_service.py` (`FFmpegService.merge`).

#### Acceptance Criteria

1. THE FFmpegService SHALL localizar o executável do FFmpeg a partir de um caminho explícito fornecido ou, na ausência deste, a partir do PATH do sistema.
2. IF nenhum executável de FFmpeg válido for localizado, THEN THE FFmpegService SHALL sinalizar um erro descritivo ao ser solicitado a localizar o executável.
3. WHEN solicitado a combinar um arquivo de vídeo e um arquivo de áudio, THE FFmpegService SHALL executar a combinação copiando os fluxos de vídeo e áudio sem recodificação.
4. IF o arquivo de vídeo ou o arquivo de áudio informado para o Merge não existir, THEN THE FFmpegService SHALL sinalizar um erro descritivo antes de invocar o executável do FFmpeg.
5. IF a execução do FFmpeg retornar código de saída diferente de zero, THEN THE FFmpegService SHALL sinalizar um erro descritivo contendo a saída de erro do processo, quando disponível.
6. IF a execução do FFmpeg for concluída com código de saída zero mas o arquivo de saída não existir, THEN THE FFmpegService SHALL sinalizar um erro descritivo.
7. WHEN o Merge é concluído com sucesso, THE FFmpegService SHALL criar os diretórios necessários do caminho de saída antes de escrever o arquivo final, caso ainda não existam.

### Requirement 6: Conversão de Áudio para MP3 com Bitrate Selecionável

**User Story:** Como usuário, eu quero baixar e converter áudio para MP3 em um bitrate de minha escolha, para que eu obtenha um arquivo de áudio compatível com qualquer player, no tamanho e qualidade desejados.

Status atual: ausente — requer um novo método de conversão em `FFmpegService` (hoje só existe `merge`) e o uso do campo `DownloadOptions.audio_bitrate`, que existe no modelo mas não é lido em nenhum lugar do código atual.

#### Acceptance Criteria

1. WHERE o Tipo_De_Download é `AUDIO` e um Bitrate_De_Áudio é informado nas Opções_De_Download, THE FFmpegService SHALL converter o áudio baixado para o formato MP3 codificado no Bitrate_De_Áudio informado.
2. THE FFmpegService SHALL restringir o Bitrate_De_Áudio aceito para Conversão_Para_MP3 aos valores 128, 192, 256 e 320 kbps.
3. IF um valor de Bitrate_De_Áudio fora do conjunto suportado for informado, THEN THE FFmpegService SHALL rejeitar a Conversão_Para_MP3 com um erro descritivo, sem invocar o executável do FFmpeg.
4. WHEN a Conversão_Para_MP3 é concluída com sucesso, THE Downloader SHALL retornar um `DownloadResult` com `success` verdadeiro referenciando o arquivo MP3 final, removendo o arquivo de áudio intermediário não convertido.
5. IF a Conversão_Para_MP3 falhar por erro do FFmpeg, THEN THE Downloader SHALL retornar um `DownloadResult` com `success` falso e uma mensagem de erro descritiva, sem lançar uma exceção não tratada.
6. WHERE o Tipo_De_Download é `AUDIO` e nenhum Bitrate_De_Áudio é informado, THE Downloader SHALL aplicar um Bitrate_De_Áudio padrão definido pela Configuração para a Conversão_Para_MP3.

### Requirement 7: Progresso e Estados de Download

**User Story:** Como usuário, eu quero ver o progresso de análise, download, Merge e conversão em andamento, para que eu saiba o que está acontecendo e quanto falta.

Status atual: ausente — o modelo `DownloadProgress` existe em `app/models/download.py`, mas não há `progress_hooks` do `yt-dlp` nem qualquer código que popule ou emita instâncias de `DownloadProgress` durante análise, download, Merge ou Conversão_Para_MP3.

#### Acceptance Criteria

1. WHEN uma análise, download, Merge ou Conversão_Para_MP3 é iniciado, THE Serviço_De_Orquestração SHALL emitir um Progresso_Do_Download com Estado_Do_Download refletindo a fase em curso (ANALYZING, DOWNLOADING ou PROCESSING).
2. WHILE um download de Formato está em andamento, THE Serviço_De_Orquestração SHALL atualizar o Progresso_Do_Download com a porcentagem concluída, os bytes baixados, o total de bytes (quando conhecido), a velocidade e o tempo estimado restante, quando essas informações estiverem disponíveis.
3. WHEN uma operação é concluída com sucesso, THE Serviço_De_Orquestração SHALL emitir um Progresso_Do_Download final com Estado_Do_Download igual a `COMPLETED`.
4. IF uma operação falhar, THEN THE Serviço_De_Orquestração SHALL emitir um Progresso_Do_Download final com Estado_Do_Download igual a `FAILED`.
5. IF o total de bytes de um download não for conhecido antecipadamente, THEN THE Serviço_De_Orquestração SHALL emitir o Progresso_Do_Download sem presumir um valor para `total_bytes`.

### Requirement 8: Cancelamento de Operações em Andamento

**User Story:** Como usuário, eu quero cancelar uma análise, download, Merge ou conversão em andamento, para que eu não precise esperar uma operação que não desejo mais concluir.

Status atual: ausente — não existe nenhum mecanismo de cancelamento no código atual.

#### Acceptance Criteria

1. WHILE uma Operação_Em_Background está em curso, THE Serviço_De_Orquestração SHALL aceitar uma solicitação de Cancelamento.
2. WHEN um Cancelamento é solicitado, THE Serviço_De_Orquestração SHALL interromper a Operação_Em_Background correspondente na primeira oportunidade segura, sem corromper arquivos já existentes no diretório de destino.
3. WHEN uma Operação_Em_Background é interrompida por Cancelamento, THE Serviço_De_Orquestração SHALL emitir um Progresso_Do_Download final com Estado_Do_Download igual a `CANCELLED`.
4. WHEN uma Operação_Em_Background é interrompida por Cancelamento, THE Serviço_De_Orquestração SHALL remover os arquivos temporários parciais criados por essa operação.
5. IF um Cancelamento é solicitado para uma operação já concluída ou já cancelada, THEN THE Serviço_De_Orquestração SHALL ignorar a solicitação sem sinalizar erro.

### Requirement 9: Execução em Background sem Bloquear a Interface

**User Story:** Como usuário, eu quero que a interface permaneça responsiva durante análises e downloads, para que eu possa interagir com o aplicativo enquanto uma operação está em andamento.

Status atual: ausente — `main.py` é síncrono e bloqueante; não há execução em thread/processo separado em nenhuma camada do código atual.

#### Acceptance Criteria

1. WHEN a GUI solicita uma análise, download, Merge ou Conversão_Para_MP3, THE Serviço_De_Orquestração SHALL executar a Operação_Em_Background fora da thread principal da aplicação.
2. WHILE uma Operação_Em_Background está em curso, THE GUI SHALL permanecer capaz de processar eventos de interface do usuário.
3. WHEN uma Operação_Em_Background é concluída, falha ou é cancelada, THE Serviço_De_Orquestração SHALL notificar a GUI de forma segura para atualização da interface a partir da thread principal.
4. IF uma exceção não tratada ocorrer dentro de uma Operação_Em_Background, THEN THE Serviço_De_Orquestração SHALL capturá-la e traduzi-la em um Progresso_Do_Download ou `DownloadResult` de falha, sem encerrar o processo do aplicativo.

### Requirement 10: Camada de Orquestração em Services

**User Story:** Como desenvolvedor da GUI, eu quero chamar operações de alto nível (analisar, baixar, cancelar) sem conhecer os detalhes de `Downloader`, `FormatSelector` e `FFmpegService`, para que a interface permaneça desacoplada da lógica de negócio.

Status atual: ausente — `app/services/__init__.py` está vazio; não existe nenhuma classe ou função de orquestração hoje.

#### Acceptance Criteria

1. THE Serviço_De_Orquestração SHALL expor operações de análise de Mídia, seleção de Formato, download, Merge, Conversão_Para_MP3 e Cancelamento como uma API única consumível pela GUI.
2. THE Serviço_De_Orquestração SHALL internamente compor `Downloader`, `FormatSelector` e `FFmpegService` sem exigir que a GUI instancie ou conheça essas classes diretamente.
3. WHEN a GUI invoca uma operação do Serviço_De_Orquestração, THE Serviço_De_Orquestração SHALL traduzir os parâmetros recebidos para os modelos existentes (`DownloadOptions`, `FormatSelection`) sem duplicar a lógica de seleção já implementada em `FormatSelector`.
4. IF uma camada de Core (Downloader, FormatSelector ou FFmpegService) sinalizar um erro, THEN THE Serviço_De_Orquestração SHALL traduzi-lo em um resultado ou Progresso_Do_Download de falha compreensível pela GUI, sem expor exceções internas de `yt-dlp` ou `subprocess` diretamente à GUI.

### Requirement 11: Sanitização Consistente de Nomes de Arquivo

**User Story:** Como usuário, eu quero que arquivos baixados tenham sempre nomes válidos no meu sistema operacional, para que nenhum download falhe por causa de caracteres inválidos no título da mídia.

Status atual: parcialmente implementado — a sanitização existe em `Downloader._sanitize_filename` e é aplicada apenas no caminho de Merge; o caminho de download de Formato único usa o padrão `%(title)s.%(ext)s` do `yt-dlp` diretamente, sem sanitização.

#### Acceptance Criteria

1. WHEN um arquivo é salvo no diretório de destino, independentemente de ter passado por download de Formato único, Merge ou Conversão_Para_MP3, THE Downloader SHALL garantir que o nome do arquivo final não contenha caracteres inválidos para o sistema de arquivos do sistema operacional em uso.
2. IF o título da Mídia, após sanitização, resultar em uma cadeia vazia, THEN THE Downloader SHALL usar um nome de arquivo padrão não vazio.

### Requirement 12: Interface Gráfica com CustomTkinter

**User Story:** Como usuário, eu quero usar uma interface gráfica para informar a URL, escolher o tipo de download e acompanhar o progresso, para que eu não precise usar a linha de comando.

Status atual: ausente — `app/gui/__init__.py` está vazio e `main.py` é um script de linha de comando; CustomTkinter não está em uso em nenhum arquivo do repositório.

#### Acceptance Criteria

1. THE GUI SHALL ser construída utilizando a biblioteca CustomTkinter.
2. THE GUI SHALL fornecer um campo para o usuário informar a URL da Mídia e iniciar a análise através do Serviço_De_Orquestração.
3. WHEN a análise é concluída com sucesso, THE GUI SHALL exibir título, uploader e thumbnail (quando disponíveis) da Mídia analisada.
4. THE GUI SHALL permitir que o usuário escolha o Tipo_De_Download (vídeo ou áudio), a altura máxima desejada (para vídeo) ou o Bitrate_De_Áudio desejado (para áudio), e o diretório de destino.
5. WHILE uma Operação_Em_Background está em curso, THE GUI SHALL exibir o Progresso_Do_Download atual, incluindo porcentagem e Estado_Do_Download.
6. THE GUI SHALL fornecer um controle para solicitar o Cancelamento de uma Operação_Em_Background em curso.
7. IF uma operação falhar, THEN THE GUI SHALL exibir a mensagem de erro retornada pelo Serviço_De_Orquestração ao usuário.
8. THE GUI SHALL depender exclusivamente do Serviço_De_Orquestração para executar análise, download, Merge, Conversão_Para_MP3 e Cancelamento, sem importar diretamente `Downloader`, `FormatSelector` ou `FFmpegService`.

### Requirement 13: Configurações Persistentes

**User Story:** Como usuário, eu quero que minhas preferências (diretório padrão, tipo de download padrão, resolução preferida, bitrate padrão, caminho do FFmpeg, preferências visuais) sejam lembradas entre execuções, para que eu não precise reconfigurá-las a cada uso.

Status atual: ausente — não existe nenhum módulo de configuração persistente; `app/utils/__init__.py` está vazio.

#### Acceptance Criteria

1. WHEN o aplicativo é iniciado, THE Serviço_De_Orquestração SHALL carregar a Configuração persistida, quando existente.
2. IF nenhuma Configuração persistida existir, THEN THE Serviço_De_Orquestração SHALL utilizar valores padrão definidos para diretório de destino, Tipo_De_Download, resolução preferida, Bitrate_De_Áudio e caminho do FFmpeg.
3. WHEN o usuário altera uma preferência na GUI, THE Serviço_De_Orquestração SHALL persistir a Configuração atualizada.
4. IF o arquivo de Configuração persistida estiver corrompido ou ilegível, THEN THE Serviço_De_Orquestração SHALL utilizar os valores padrão sem interromper a inicialização do aplicativo.
5. WHERE um caminho de FFmpeg é definido na Configuração, THE FFmpegService SHALL utilizar esse caminho em vez de buscar no PATH do sistema.

### Requirement 14: Histórico de Downloads

**User Story:** Como usuário, eu quero consultar os downloads realizados anteriormente, para que eu possa localizar arquivos já baixados ou repetir uma operação.

Status atual: ausente — não existe nenhum mecanismo de persistência de histórico no código atual.

#### Acceptance Criteria

1. WHEN uma operação de download, Merge ou Conversão_Para_MP3 é concluída, falha ou é cancelada, THE Serviço_De_Orquestração SHALL registrar uma entrada no Histórico_De_Downloads contendo URL original, título (quando disponível), Tipo_De_Download, Estado_Do_Download final, caminho do arquivo (quando aplicável) e data/hora.
2. THE GUI SHALL permitir a consulta do Histórico_De_Downloads persistido entre execuções do aplicativo.
3. IF o arquivo final referenciado por uma entrada do Histórico_De_Downloads não existir mais no sistema de arquivos, THEN THE GUI SHALL indicar essa ausência ao exibir a entrada, sem sinalizar erro de execução.

### Requirement 15: Testes Automatizados

**User Story:** Como desenvolvedor, eu quero testes unitários e de integração com mocks para as camadas Core e Services, para que regressões sejam detectadas antes da entrega.

Status atual: ausente — não há nenhum arquivo `test_*.py`/`*_test.py` nem diretório `tests` no repositório.

#### Acceptance Criteria

1. THE conjunto de testes SHALL incluir testes unitários para `FormatSelector`, cobrindo seleção de vídeo com e sem áudio embutido, seleção de áudio e os casos de erro de seleção.
2. THE conjunto de testes SHALL incluir testes unitários para `FFmpegService`, cobrindo merge bem-sucedido, Conversão_Para_MP3 bem-sucedida e os respectivos casos de erro, sem depender de um executável real de FFmpeg instalado.
3. THE conjunto de testes SHALL incluir testes de integração com mocks para `Downloader`, cobrindo análise, download de Formato único e download com Merge, sem realizar chamadas de rede reais nem executar o `yt-dlp` ou o FFmpeg reais.
4. THE conjunto de testes SHALL incluir testes para o Serviço_De_Orquestração, cobrindo emissão de Progresso_Do_Download e tratamento de Cancelamento, utilizando substitutos (fakes/mocks) para `Downloader`, `FormatSelector` e `FFmpegService`.
5. IF um teste depender de FFmpeg, `yt-dlp` ou acesso à rede, THEN THE conjunto de testes SHALL substituir essa dependência por um mock ou fake, em vez de ignorar o teste silenciosamente.

### Requirement 16: Compatibilidade e Empacotamento

**User Story:** Como usuário, eu quero instalar e executar o aplicativo no Windows como um executável único, para que eu não precise instalar Python ou dependências manualmente.

Status atual: ausente — não há configuração de empacotamento (PyInstaller) no repositório.

#### Acceptance Criteria

1. THE aplicativo SHALL ser compatível com Python 3.11 ou superior.
2. THE aplicativo SHALL ser executável no sistema operacional Windows.
3. THE processo de empacotamento SHALL gerar um executável Windows utilizando PyInstaller, incluindo as dependências necessárias para execução da GUI e das camadas Core/Services.
4. IF o executável do FFmpeg não estiver disponível no ambiente de destino, THEN THE aplicativo empacotado SHALL informar ao usuário que o FFmpeg é necessário para operações de Merge e Conversão_Para_MP3, em vez de falhar silenciosamente.
5. THE processo de empacotamento SHALL ser realizado sem o uso de Docker ou containerização.
</content>
</file>