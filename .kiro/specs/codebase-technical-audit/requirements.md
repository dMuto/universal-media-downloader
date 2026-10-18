# Requirements Document

## Introduction

Este documento define os requisitos para a realização de uma auditoria técnica completa do projeto `universal-media-downloader` antes da continuidade de seu desenvolvimento. O objetivo é compreender, validar e documentar o estado atual do código, identificando a arquitetura existente, as funcionalidades implementadas, os problemas confirmados e as próximas etapas recomendadas.

Esta fase é **exclusivamente diagnóstica**. Nenhuma funcionalidade será implementada, nenhum código será refatorado e nenhum arquivo de código-fonte será corrigido durante a execução desta auditoria. As tarefas desta fase se limitam à inspeção, validação e documentação. Qualquer ação que exija alterações no ambiente (instalação de dependências, criação/alteração de arquivos de configuração, execução de comandos com efeitos colaterais) ou qualquer ação potencialmente destrutiva (exclusão de arquivos, modificação de dados, chamadas de rede a serviços externos) requer autorização explícita do usuário antes de ser executada. O plano de desenvolvimento priorizado, entregável desta auditoria, só poderá ser executado após aprovação do usuário, em um Spec posterior.

## Glossary

- **Auditoria**: processo estruturado de inspeção e documentação do código-fonte existente, sem alteração do código, com o objetivo de produzir um retrato fiel do estado atual do projeto.
- **Relatório_De_Auditoria**: o conjunto de documentos Markdown produzidos como saída da Auditoria (inventário de arquitetura, mapa de funcionalidades, relatório de validação, lista de problemas, análise de dependências e riscos, e plano de desenvolvimento).
- **Auditor**: o agente (humano ou IA) responsável por executar as tarefas de inspeção, validação e documentação definidas neste Spec.
- **Módulo**: um arquivo ou pacote Python dentro do Repositório_Auditado (por exemplo, `app/core/downloader.py`, `app/models`, `app/gui`).
- **Repositório_Auditado**: o conjunto de arquivos do projeto `universal-media-downloader`, incluindo `app/core`, `app/gui`, `app/models`, `app/services`, `app/utils`, `main.py`, `README.md`, arquivos de dependências, arquivos de configuração e testes, caso existam.
- **Funcionalidade**: um comportamento observável do sistema entregue ao usuário final ou a outro módulo (por exemplo, "analisar uma URL de mídia", "selecionar formato de vídeo", "fazer merge de áudio e vídeo via FFmpeg").
- **Problema**: uma inconsistência, bug, limitação, dívida técnica ou desvio em relação ao comportamento esperado, identificado durante a Auditoria.
- **Gravidade**: classificação de um Problema em um dos níveis `Crítica`, `Alta`, `Média` ou `Baixa`, conforme definido na seção de Critérios de Aceitação do Requisito 4.
- **Ação_Destrutiva**: qualquer ação que exclua, sobrescreva ou modifique permanentemente arquivos, dados ou configurações do Repositório_Auditado ou do ambiente do usuário.
- **Ação_De_Ambiente**: qualquer ação que instale, atualize ou remova dependências, pacotes, executáveis externos (como FFmpeg/FFprobe) ou que altere variáveis de ambiente, arquivos de configuração do sistema ou do projeto.
- **Verificação_Segura**: uma verificação (leitura de arquivo, inspeção estática, execução de comando somente leitura) que não requer instalação de dependências nem realiza Ação_Destrutiva.
- **Dependência_Externa**: uma biblioteca, pacote ou executável externo ao código-fonte do Repositório_Auditado necessário para sua execução (por exemplo, `yt-dlp`, `FFmpeg`, `FFprobe`).

## Requirements

### Requisito 1: Inventário de Arquitetura e Responsabilidades dos Módulos

**User Story:** Como responsável técnico pelo projeto, eu quero um inventário completo da arquitetura e das responsabilidades de cada Módulo, para que eu possa compreender como o sistema está estruturado antes de planejar novas mudanças.

#### Acceptance Criteria

1. THE Auditor SHALL produzir um documento de inventário de arquitetura listando cada Módulo (entendido como cada arquivo de código-fonte Python com extensão `.py`, incluindo arquivos `__init__.py`, e excluindo diretórios de cache `__pycache__` e arquivos compilados `.pyc`) presente em `app/core`, `app/gui`, `app/models`, `app/services`, `app/utils` e `main.py`.
2. FOR ALL Módulo listado no inventário de arquitetura, THE Auditor SHALL registrar: sua responsabilidade principal; suas classes e funções públicas (definidas como classes e funções cujo nome não inicia com underscore `_`); e suas dependências diretas de outros Módulos do Repositório_Auditado, identificadas por declarações de importação (`import` ou `from ... import`) presentes no código-fonte do Módulo.
3. THE Auditor SHALL descrever no inventário de arquitetura o fluxo de dados entre os Módulos `app/core/downloader.py`, `app/core/format_selector.py`, `app/core/ffmpeg_service.py` e os modelos em `app/models`.
4. IF um Módulo documentado em código (classe, função ou arquivo) não possuir docstring ou comentário explicativo, THEN THE Auditor SHALL inferir a responsabilidade observada a partir do comportamento do código e SHALL registrar essa responsabilidade no inventário de arquitetura indicando explicitamente que ela foi inferida, e não extraída de documentação existente.
5. IF um Módulo existir apenas como arquivo vazio (sem nenhuma linha de código executável, além de linhas em branco ou comentários) ou como placeholder (arquivo cujo conteúdo se limita a declarações de importação, à palavra-chave `pass`, ou a uma estrutura mínima sem lógica de negócio implementada), THEN THE Auditor SHALL registrá-lo no inventário de arquitetura como "vazio/placeholder" em vez de omiti-lo.
6. THE Auditor SHALL registrar o inventário de arquitetura em um arquivo Markdown dedicado e identificável (por nome de arquivo ou título que indique explicitamente "inventário de arquitetura") dentro do diretório do Spec `codebase-technical-audit`, distinto dos arquivos Markdown produzidos para os demais Requisitos desta Auditoria.

### Requisito 2: Mapa de Funcionalidades Existentes, Parciais e Ausentes

**User Story:** Como responsável técnico pelo projeto, eu quero um mapa das Funcionalidades existentes, parcialmente implementadas e ausentes, para que eu possa priorizar o que falta construir sem duplicar o que já funciona.

#### Acceptance Criteria

1. THE Auditor SHALL produzir um mapa de Funcionalidades descrevendo o comportamento esperado de cada Funcionalidade identificada no Repositório_Auditado e classificando-a como "Implementada", "Parcialmente implementada" ou "Ausente".
2. THE Auditor SHALL classificar uma Funcionalidade como "Implementada" quando todo o comportamento esperado descrito para ela estiver presente e executável no código, como "Parcialmente implementada" quando parte do comportamento esperado estiver presente no código e outra parte estiver ausente ou incompleta, e como "Ausente" quando nenhum código correspondente ao comportamento esperado for encontrado no Repositório_Auditado.
3. FOR ALL Funcionalidade classificada como "Implementada" ou "Parcialmente implementada", THE Auditor SHALL referenciar os Módulos, os arquivos e as linhas (ou intervalos de linhas) de código que a implementam.
4. FOR ALL Funcionalidade classificada como "Parcialmente implementada", THE Auditor SHALL descrever quais partes do comportamento esperado da Funcionalidade estão presentes no código e quais partes estão ausentes ou incompletas, de modo que seja possível identificar exatamente o que falta para que a Funcionalidade seja considerada completa.
5. THE Auditor SHALL incluir no mapa de Funcionalidades, no mínimo, a análise de mídia via `yt-dlp`, a seleção de formatos de vídeo e áudio, o download de formato único, o download com merge via FFmpeg, e a existência (ou ausência) de interface gráfica em `app/gui`.
6. IF o Repositório_Auditado não possuir nenhuma implementação relacionada a uma área esperada do domínio (por exemplo, interface gráfica, persistência de histórico de downloads, testes automatizados), THEN THE Auditor SHALL registrar essa área como "Ausente" no mapa de Funcionalidades, indicando os Módulos ou diretórios verificados nos quais a implementação não foi encontrada, em vez de omiti-la.
7. THE Auditor SHALL registrar o mapa de Funcionalidades em um arquivo Markdown dentro do diretório do Spec `codebase-technical-audit`.

### Requisito 3: Validação Segura do Ambiente Atual

**User Story:** Como responsável técnico pelo projeto, eu quero saber o que pode ser testado com segurança no ambiente atual, para que eu entenda os limites da validação sem correr o risco de ações destrutivas ou alterações não autorizadas no ambiente.

#### Acceptance Criteria

1. THE Auditor SHALL identificar e listar quais verificações sobre o Repositório_Auditado podem ser realizadas como Verificação_Segura, sem necessidade de Ação_De_Ambiente ou Ação_Destrutiva.
2. IF uma verificação exigir Ação_De_Ambiente (por exemplo, instalar uma Dependência_Externa ausente) ou Ação_Destrutiva, THEN THE Auditor SHALL registrar essa verificação como pendente de autorização, sem executá-la.
3. IF o usuário não tiver concedido autorização explícita para uma Ação_De_Ambiente ou Ação_Destrutiva, THEN THE Auditor SHALL abster-se de executá-la e SHALL documentar o motivo pelo qual não foi executada.
4. WHILE realiza qualquer Verificação_Segura, THE Auditor SHALL abster-se de realizar chamadas de rede a serviços externos, incluindo testes de conectividade, análise de URLs de mídia reais ou downloads de teste.
5. THE Auditor SHALL verificar, por meio de Verificação_Segura, a presença ou ausência de arquivos de definição de dependências (por exemplo, `requirements.txt`, `pyproject.toml`) no Repositório_Auditado.
6. THE Auditor SHALL verificar, por meio de Verificação_Segura, a presença ou ausência de arquivos de teste automatizado no Repositório_Auditado, identificados como arquivos cujo nome corresponde ao padrão `test_*.py` ou `*_test.py`, ou que estejam localizados em um diretório denominado `tests` ou `test`.
7. THE Auditor SHALL verificar, por meio de Verificação_Segura, se o ambiente Python local (`.venv`) já possui instalados os pacotes listados nos arquivos de definição de dependências identificados no Critério 5 (por exemplo, `yt-dlp`, caso listado em `requirements.txt` ou `pyproject.toml`), sem instalar ou atualizar pacotes.
8. THE Auditor SHALL verificar, por meio de Verificação_Segura, se os executáveis FFmpeg e FFprobe estão disponíveis no PATH do sistema, sem instalá-los ou modificá-los.
9. THE Auditor SHALL registrar os resultados da validação segura, incluindo o que foi verificado, o que não pôde ser verificado e o que requer autorização adicional, em um arquivo Markdown dentro do diretório do Spec `codebase-technical-audit`.

### Requisito 4: Lista de Problemas com Evidências, Gravidade e Localização

**User Story:** Como responsável técnico pelo projeto, eu quero uma lista de problemas confirmados com evidências, gravidade e localização no código, para que eu possa decidir quais corrigir primeiro com base em dados concretos.

#### Acceptance Criteria

1. THE Auditor SHALL produzir uma lista de Problema identificados no Repositório_Auditado durante a Auditoria.
2. FOR ALL Problema listado, THE Auditor SHALL registrar a evidência observada (incluindo a descrição do comportamento observado ou o trecho de código relevante e, quando aplicável, o resultado da Verificação_Segura executada), o arquivo e a linha ou intervalo de linhas onde o Problema ocorre, e a Gravidade atribuída.
3. THE Auditor SHALL classificar a Gravidade de cada Problema em um dos níveis `Crítica`, `Alta`, `Média` ou `Baixa`, definidos como: `Crítica` para falhas que impedem a execução básica do sistema ou causam perda de dados; `Alta` para falhas que comprometem funcionalidades centrais em cenários comuns; `Média` para falhas que afetam cenários secundários ou degradam a qualidade sem impedir o uso; `Baixa` para inconsistências estéticas, de estilo ou de manutenibilidade sem impacto funcional observável.
4. IF um Problema não puder ser confirmado por evidência direta no código ou por execução de uma Verificação_Segura, THEN THE Auditor SHALL registrá-lo em uma seção separada intitulada "hipóteses a confirmar", incluindo a localização suspeita (arquivo e, quando identificável, linha ou intervalo de linhas) e a justificativa de por que a confirmação não foi possível, distinguindo-o dos Problemas confirmados.
5. THE Auditor SHALL, para cada Módulo em `app/core`, registrar na lista de problemas o resultado de, no mínimo, uma verificação quanto a tratamento de exceções, codificação de caracteres, nomes de arquivo inválidos, concorrência/bloqueio de interface e limpeza de arquivos temporários, incluindo, para cada uma dessas cinco categorias, um Problema identificado ou uma declaração explícita de que nenhum Problema foi identificado nessa categoria para o Módulo.
6. THE Auditor SHALL registrar a lista de Problema em um arquivo Markdown dentro do diretório do Spec `codebase-technical-audit`, com os Problemas confirmados ordenados por Gravidade da mais alta (`Crítica`) para a mais baixa (`Baixa`) e, dentro de uma mesma Gravidade, ordenados pelo caminho do arquivo em ordem alfabética, seguidos por uma seção separada contendo as entradas classificadas como "hipótese a confirmar".

### Requisito 5: Análise de Dependências entre Módulos e Riscos Técnicos

**User Story:** Como responsável técnico pelo projeto, eu quero uma análise das dependências entre módulos e dos riscos técnicos envolvendo yt-dlp, FFmpeg e FFprobe, para que eu possa entender onde o sistema é mais frágil antes de expandi-lo.

#### Acceptance Criteria

1. THE Auditor SHALL produzir um diagrama ou descrição textual estruturada das dependências diretas entre todos os Módulos listados no inventário de arquitetura do Requisito 1, registrando para cada Módulo os demais Módulos que ele importa ou invoca diretamente.
2. FOR ALL Dependência_Externa entre `yt-dlp`, `FFmpeg` e `FFprobe`, THE Auditor SHALL identificar e descrever todos os pontos de integração dessa Dependência_Externa com o Repositório_Auditado, indicando o Módulo e a função ou método onde cada integração ocorre.
3. FOR ALL ponto de integração identificado com uma Dependência_Externa, THE Auditor SHALL descrever o risco técnico associado, incluindo cenários de indisponibilidade, incompatibilidade de versão ou alteração de comportamento da Dependência_Externa.
4. IF um Módulo invocar uma Dependência_Externa sem que o código realize uma verificação prévia de disponibilidade (como uma checagem de existência do executável ou da instalação do pacote) nem capture uma exceção específica decorrente da falha dessa Dependência_Externa, THEN THE Auditor SHALL registrar essa ausência como um risco técnico na análise, indicando o Módulo, a função e o trecho de código onde a chamada ocorre.
5. THE Auditor SHALL avaliar o acoplamento entre `app/core/downloader.py`, `app/core/format_selector.py` e `app/core/ffmpeg_service.py`, indicando para cada par de Módulos se a dependência ocorre por injeção (parâmetro ou construtor substituível) ou por instanciação direta dentro do código, e apontando os trechos específicos de código que impedem a substituição da Dependência_Externa ou de outro Módulo por uma versão simulada (fake/mock) durante um teste automatizado.
6. THE Auditor SHALL registrar a análise de dependências e riscos técnicos em um arquivo Markdown dentro do diretório do Spec `codebase-technical-audit`.

### Requisito 6: Plano de Desenvolvimento Priorizado Sujeito a Aprovação

**User Story:** Como responsável técnico pelo projeto, eu quero um plano de desenvolvimento priorizado com etapas pequenas e critérios de aceitação, para que eu possa aprovar e conduzir a continuidade do projeto de forma controlada.

#### Acceptance Criteria

1. THE Auditor SHALL produzir um plano de desenvolvimento priorizado com base nos achados dos Requisitos 1 a 5 desta Auditoria.
2. FOR ALL etapa listada no plano de desenvolvimento, THE Auditor SHALL descrever um escopo delimitado a uma única Funcionalidade, Problema ou risco técnico identificado nos Requisitos 1 a 5, de modo que a etapa possa ser implementada e verificada de forma independente das demais etapas, e SHALL descrever seus critérios de aceitação verificáveis.
3. THE Auditor SHALL atribuir a cada etapa do plano de desenvolvimento um nível de prioridade dentre `Crítica`, `Alta`, `Média` ou `Baixa`, correspondendo à Gravidade do Problema relacionado quando a etapa decorrer de um Problema do Requisito 4, ou a uma Gravidade equivalente justificada por escrito no plano quando a etapa decorrer de uma Funcionalidade classificada como "Ausente" ou "Parcialmente implementada" no Requisito 2, ou de um risco técnico identificado no Requisito 5.
4. THE Auditor SHALL ordenar as etapas do plano de desenvolvimento da prioridade `Crítica` para a `Baixa`, salvo quando uma dependência técnica entre etapas exigir ordem diferente, caso em que a exceção SHALL ser justificada por escrito no plano de desenvolvimento.
5. THE Auditor SHALL registrar o plano de desenvolvimento em um arquivo Markdown dentro do diretório do Spec `codebase-technical-audit`.
6. IF o usuário não tiver manifestado, em resposta ao Auditor, concordância explícita com o plano de desenvolvimento como um todo, THEN THE Auditor SHALL manter todas as etapas do plano em estado "proposto" e SHALL abster-se de iniciar a implementação de qualquer etapa.
7. IF o usuário solicitar alterações ao plano de desenvolvimento ou manifestar discordância com ele, THEN THE Auditor SHALL revisar o plano com base no retorno recebido e SHALL manter as etapas revisadas em estado "proposto" até nova manifestação de concordância explícita.
8. WHEN o usuário manifestar, em resposta ao Auditor, concordância explícita com o plano de desenvolvimento como um todo, THE Auditor SHALL tratar a implementação das etapas aprovadas como um trabalho a ser conduzido em um Spec subsequente, e não dentro desta Auditoria.
