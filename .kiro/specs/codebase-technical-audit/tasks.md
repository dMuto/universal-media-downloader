# Implementation Plan: Auditoria Técnica do Codebase

## Overview

Este plano converte o `design.md` em uma sequência de tarefas executáveis pelo Auditor. Este é um Spec **diagnóstico**: todas as tarefas produzem ou revisam os seis documentos Markdown definidos no design (`01-inventario-arquitetura.md` a `06-plano-desenvolvimento.md`), dentro de `.kiro/specs/codebase-technical-audit/`. Nenhuma tarefa escreve, modifica ou corrige código em `app/`, `main.py` ou qualquer arquivo de configuração/dependência do `Repositório_Auditado`, nem instala ou altera dependências do ambiente. Verificações que tocam o ambiente local são estritamente read-only (Verificação_Segura) e só ocorrem após confirmação de que nenhuma Ação_De_Ambiente ou Ação_Destrutiva será executada sem autorização explícita.

As tarefas seguem a ordem de dependência descrita no `design.md`: varredura estática primeiro, depois os entregáveis dos Requisitos 1 a 5 (nesta ordem lógica: Inventário → Mapa de Funcionalidades; Validação de Ambiente em paralelo; Lista de Problemas; Análise de Dependências e Riscos), e por fim o Plano de Desenvolvimento Priorizado (Requisito 6), que permanece em estado "Proposto" até aprovação explícita do usuário.

## Tasks

- [ ] 1. Realizar varredura estática dos Módulos do Repositório_Auditado (Componente 1 — Leitor de Módulos)
  - [ ] 1.1 Enumerar todos os Módulos (`*.py`, incluindo `__init__.py`) em `app/core`, `app/gui`, `app/models`, `app/services`, `app/utils` e `main.py`, excluindo `__pycache__` e `*.pyc`
    - Ler o conteúdo integral de cada Módulo listado, sem executar nenhum código do projeto
    - _Requirements: 1.1_
  - [ ] 1.2 Extrair, por inspeção textual/estrutural, para cada Módulo: imports internos (`app.` ou relativos), classes/funções públicas (não iniciadas por `_`) e presença de docstring/comentário explicativo
    - Registrar separadamente funções/métodos privados citados apenas para explicar comportamento interno
    - _Requirements: 1.2_
  - [ ] 1.3 Classificar cada Módulo quanto a conteúdo como "vazio", "placeholder" ou "implementado", e sinalizar onde a responsabilidade precisará ser inferida (ausência de docstring/comentário)
    - Consolidar as fichas de inspeção de todos os Módulos para uso nas tarefas 2, 3, 6 e 7
    - _Requirements: 1.4, 1.5_

- [ ] 2. Produzir o Inventário de Arquitetura (Requisito 1)
  - [ ] 2.1 Criar `01-inventario-arquitetura.md` com uma seção por diretório (`app/core`, `app/gui`, `app/models`, `app/services`, `app/utils`, `main.py`), listando cada Módulo da tarefa 1 com responsabilidade (marcando `(responsabilidade inferida)` quando aplicável), classes/funções públicas, dependências internas e status "vazio/placeholder" quando aplicável
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6_
  - [ ] 2.2 Adicionar ao mesmo arquivo a seção de fluxo de dados entre `app/core/downloader.py`, `app/core/format_selector.py`, `app/core/ffmpeg_service.py` e os modelos em `app/models`
    - _Requirements: 1.3_

- [ ] 3. Produzir o Mapa de Funcionalidades (Requisito 2)
  - [ ] 3.1 Descrever o comportamento esperado de cada Funcionalidade mínima exigida (análise via `yt-dlp`, seleção de formatos, download de formato único, download com merge via FFmpeg, interface gráfica em `app/gui`), com base na varredura da tarefa 1 e no uso em `main.py`
    - _Requirements: 2.1, 2.5_
  - [ ] 3.2 Classificar cada Funcionalidade como "Implementada", "Parcialmente implementada" ou "Ausente" aplicando os critérios objetivos do design, citando Módulo, arquivo e linhas/intervalos exatos
    - _Requirements: 2.2, 2.3_
  - [ ] 3.3 Para Funcionalidades "Parcialmente implementada", descrever explicitamente o que está presente e o que falta; para áreas totalmente ausentes (GUI, persistência de histórico, testes automatizados), registrar como "Ausente" indicando os diretórios/padrões verificados
    - _Requirements: 2.4, 2.6_
  - [ ] 3.4 Consolidar os achados das tarefas 3.1 a 3.3 em `02-mapa-funcionalidades.md`
    - _Requirements: 2.7_

- [ ] 4. Checkpoint — revisar Inventário de Arquitetura e Mapa de Funcionalidades
  - Apresentar `01-inventario-arquitetura.md` e `02-mapa-funcionalidades.md` ao usuário; confirmar que cobrem todos os Módulos e Funcionalidades mínimas antes de prosseguir, e perguntar ao usuário caso surjam dúvidas ou pedidos de ajuste.

- [ ] 5. Produzir a Validação Segura do Ambiente (Requisito 3)
  - [ ] 5.1 Confirmar e registrar que todas as verificações desta tarefa são Verificação_Segura (estritamente read-only, sem instalar/atualizar/remover pacotes, sem chamadas de rede); nenhuma verificação é iniciada antes desta confirmação
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 5.2 Verificar, por listagem do diretório raiz, a presença ou ausência de arquivos de definição de dependências (`requirements.txt`, `pyproject.toml`, `Pipfile`, `setup.py`/`setup.cfg`)
    - _Requirements: 3.5_
  - [ ] 5.3 Verificar, por busca de padrão de nome, a presença ou ausência de arquivos de teste automatizado (`test_*.py`, `*_test.py`) ou diretórios `tests`/`test`
    - _Requirements: 3.6_
  - [ ] 5.4 Verificar, de forma read-only, os pacotes de fato instalados no ambiente `.venv`, documentando explicitamente a ausência de uma lista declarada de dependências esperadas para contraste (consequência da tarefa 5.2)
    - _Requirements: 3.7_
  - [ ] 5.5 Verificar, de forma read-only (equivalente a `shutil.which`/`Get-Command`), se os executáveis FFmpeg e FFprobe estão disponíveis no PATH do sistema, sem instalar ou executar merge real
    - _Requirements: 3.8_
  - [ ] 5.6 Consolidar os resultados das tarefas 5.1 a 5.5 em `03-validacao-ambiente.md`, incluindo uma seção explícita do que requereria Ação_De_Ambiente ou Ação_Destrutiva e não foi executado, com justificativa
    - _Requirements: 3.9_

- [ ] 6. Produzir a Lista de Problemas (Requisito 4)
  - [ ] 6.1 Para cada Módulo em `app/core`, verificar as cinco categorias obrigatórias (tratamento de exceções, codificação de caracteres, nomes de arquivo inválidos, concorrência/bloqueio de interface, limpeza de arquivos temporários) com base na varredura da tarefa 1, registrando um Problema encontrado ou a declaração explícita de ausência para cada categoria
    - _Requirements: 4.5_
  - [ ] 6.2 Para cada Problema identificado nesta tarefa e nos achados do Inventário (tarefa 2), do Mapa de Funcionalidades (tarefa 3) e da Validação de Ambiente (tarefa 5), registrar evidência, arquivo e linha(s), e atribuir Gravidade (`Crítica`/`Alta`/`Média`/`Baixa`) conforme os critérios objetivos do design
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ] 6.3 Mover para a seção "Hipóteses a Confirmar" qualquer suspeita sem evidência direta de código nem resultado de Verificação_Segura, incluindo localização suspeita e justificativa da impossibilidade de confirmação
    - _Requirements: 4.4_
  - [ ] 6.4 Consolidar `04-lista-problemas.md`, ordenando os Problemas confirmados por Gravidade decrescente e, dentro da mesma Gravidade, por caminho de arquivo em ordem alfabética, seguidos pela seção de hipóteses
    - _Requirements: 4.6_

- [ ] 7. Produzir a Análise de Dependências e Riscos (Requisito 5)
  - [ ] 7.1 Montar, a partir dos imports internos extraídos na tarefa 1 e consolidados no Inventário (tarefa 2), a lista/diagrama de dependências diretas entre todos os Módulos
    - _Requirements: 5.1_
  - [ ] 7.2 Identificar todos os pontos de integração com `yt-dlp`, `FFmpeg` e `FFprobe` (Módulo e função/método), registrando como achado factual a ausência de integração direta com `FFprobe`, caso confirmada
    - _Requirements: 5.2_
  - [ ] 7.3 Descrever o risco técnico de cada ponto de integração (indisponibilidade, incompatibilidade de versão, alteração de comportamento) e registrar como risco técnico a ausência de checagem prévia de disponibilidade ou de captura de exceção específica, quando aplicável
    - _Requirements: 5.3, 5.4_
  - [ ] 7.4 Avaliar o acoplamento entre `downloader.py`, `format_selector.py` e `ffmpeg_service.py`, indicando por par de Módulos se a dependência ocorre por injeção ou por instanciação direta, e citando os trechos exatos que impedem substituição por fake/mock em teste automatizado
    - _Requirements: 5.5_
  - [ ] 7.5 Consolidar os achados das tarefas 7.1 a 7.4 em `05-analise-dependencias-riscos.md`
    - _Requirements: 5.6_

- [ ] 8. Checkpoint — revisar Lista de Problemas e Análise de Dependências e Riscos
  - Apresentar `04-lista-problemas.md` e `05-analise-dependencias-riscos.md` ao usuário; confirmar rastreabilidade (arquivo:linha real) de cada item antes de prosseguir ao plano de desenvolvimento, e perguntar ao usuário caso surjam dúvidas ou pedidos de ajuste.

- [ ] 9. Produzir o Plano de Desenvolvimento Priorizado (Requisito 6)
  - [ ] 9.1 Criar uma etapa candidata para cada Problema confirmado (tarefa 6), cada Funcionalidade "Ausente"/"Parcialmente implementada" (tarefa 3) e cada risco técnico (tarefa 7), com escopo limitado a um único item de origem e critérios de aceitação verificáveis
    - _Requirements: 6.1, 6.2_
  - [ ] 9.2 Atribuir a cada etapa a prioridade correspondente à Gravidade do Problema de origem, ou uma Gravidade equivalente justificada por escrito quando a etapa decorrer de uma Funcionalidade ou de um risco técnico
    - _Requirements: 6.3_
  - [ ] 9.3 Ordenar as etapas de `Crítica` para `Baixa`, documentando por escrito qualquer exceção motivada por dependência técnica entre etapas
    - _Requirements: 6.4_
  - [ ] 9.4 Marcar o cabeçalho do documento e cada etapa com o estado "Proposto", sem iniciar nenhuma etapa nem alterar código do `Repositório_Auditado` como consequência do plano
    - _Requirements: 6.6_
  - [ ] 9.5 Consolidar as tarefas 9.1 a 9.4 em `06-plano-desenvolvimento.md`
    - _Requirements: 6.5_

- [ ] 10. Apresentar o Relatório_De_Auditoria completo ao usuário para revisão final
  - [ ] 10.1 Apresentar os seis documentos produzidos (`01` a `06`) ao usuário e registrar explicitamente sua manifestação sobre o Plano de Desenvolvimento: concordância explícita com o plano como um todo, pedido de ajustes, ou discordância
    - Caso haja concordância explícita, registrar no documento que a implementação das etapas aprovadas é trabalho de um Spec subsequente, nunca executado dentro desta Auditoria
    - _Requirements: 6.6, 6.8_
  - [ ] 10.2 Caso o usuário solicite ajustes ou manifeste discordância em relação a qualquer um dos seis documentos, revisar o(s) documento(s) correspondente(s) com base no retorno recebido, mantendo as etapas do plano revisadas em estado "Proposto" até nova manifestação de concordância explícita
    - _Requirements: 6.7_

## Notes

- Este Spec é exclusivamente diagnóstico: nenhuma tarefa acima escreve, modifica ou corrige código em `app/`, `main.py`, arquivos de configuração/dependência do `Repositório_Auditado`, nem instala ou altera pacotes/dependências do ambiente.
- Não há subtarefas marcadas como opcionais (`*`): este Spec não produz código testável por testes automatizados de software nem possui uma seção de Correctness Properties no `design.md`; a verificação da qualidade dos entregáveis é feita por conferência manual/estrutural contra os Critérios de Aceitação, conforme descrito na "Testing Strategy" do `design.md`.
- Qualquer necessidade de Ação_De_Ambiente ou Ação_Destrutiva identificada durante a execução das tarefas 5.x é registrada em `03-validacao-ambiente.md` como "pendente de autorização" e não é executada sem consentimento explícito do usuário.
- O Plano de Desenvolvimento Priorizado (tarefa 9) permanece em estado "Proposto" até que o usuário manifeste concordância explícita (tarefa 10.1); a implementação das etapas aprovadas ocorre apenas em um Spec subsequente, fora do escopo desta Auditoria.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "5.2"] },
    { "id": 2, "tasks": ["1.3", "5.3"] },
    { "id": 3, "tasks": ["2.1", "3.1", "5.4"] },
    { "id": 4, "tasks": ["2.2", "3.2", "5.5"] },
    { "id": 5, "tasks": ["3.3", "5.6"] },
    { "id": 6, "tasks": ["3.4"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2"] },
    { "id": 9, "tasks": ["6.3"] },
    { "id": 10, "tasks": ["6.4"] },
    { "id": 11, "tasks": ["7.1"] },
    { "id": 12, "tasks": ["7.2"] },
    { "id": 13, "tasks": ["7.3"] },
    { "id": 14, "tasks": ["7.4"] },
    { "id": 15, "tasks": ["7.5"] },
    { "id": 16, "tasks": ["9.1"] },
    { "id": 17, "tasks": ["9.2"] },
    { "id": 18, "tasks": ["9.3"] },
    { "id": 19, "tasks": ["9.4"] },
    { "id": 20, "tasks": ["9.5"] },
    { "id": 21, "tasks": ["10.1"] },
    { "id": 22, "tasks": ["10.2"] }
  ]
}
```
