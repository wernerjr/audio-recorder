# Roadmap de Reescrita — Audio Recorder

## Tecnologias Escolhidas

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | Python 3.11+ | Ecossistema de áudio e ML maduro, sem necessidade de trocar |
| Captura de áudio | `pyaudiowpatch` | Mantido — único que faz WASAPI loopback no Windows de forma simples |
| Transcrição | `faster-whisper` | Drop-in replacement do `openai-whisper`, 4x mais rápido, menos VRAM |
| Diarização | `pyannote-audio` | Identifica quem está falando por canal |
| CLI | `typer` | Argumentos tipados, help automático, muito menos boilerplate que `argparse` |
| Config | `TOML` + `tomllib` (stdlib 3.11) | Sem dependência extra, legível por humanos |
| Concorrência | `threading` + `queue` | Transcrição paralela dos dois canais sem overhead de multiprocessing |
| Empacotamento | `pyproject.toml` + `uv` | Gerenciamento moderno de dependências e ambientes virtuais |
| Testes | `pytest` | Padrão do ecossistema |

---

## Fase 1 — Fundação

### 1.1 Estrutura do Projeto
- [ ] Criar estrutura de pacote Python (`src/audio_recorder/`)
- [ ] Configurar `pyproject.toml` com dependências e entry points
- [ ] Criar `config.toml` com todos os parâmetros configuráveis:
  - nome/índice do microfone
  - modelo Whisper (`tiny` → `large`)
  - idioma (ou `auto`)
  - diretório de saída
  - formato de saída (`txt`, `srt`, `json`)

### 1.2 Módulo de Captura (`recorder.py`)
- [ ] Abstrair captura em uma classe `AudioRecorder` com interface comum para mic e sistema
- [ ] Descoberta automática do microfone padrão (sem hardcode de nome)
- [ ] Listar dispositivos disponíveis via flag `--list-devices`
- [ ] Gravação paralela real usando `threading` (ao invés de subprocessos separados)
- [ ] Sinal de parada limpo via evento (`threading.Event`) ao invés de depender de `Ctrl+C` nos filhos
- [ ] Salvar em diretório configurável com timestamp no nome do arquivo (`reuniao_2026-04-01_14-30.wav`)

### 1.3 CLI Principal (`cli.py`)
- [ ] Comando `record` — inicia gravação, para com `Ctrl+C`
- [ ] Comando `transcribe <arquivo_ou_pasta>` — transcreve arquivo(s) existente(s)
- [ ] Comando `devices` — lista microfones e dispositivos de loopback disponíveis
- [ ] Flag `--model` para escolher modelo Whisper sem editar código
- [ ] Flag `--lang` para forçar idioma

---

## Fase 2 — Transcrição e Merge Melhorados

### 2.1 Módulo de Transcrição (`transcriber.py`)
- [ ] Migrar de `openai-whisper` para `faster-whisper`
- [ ] Transcrever mic e sistema **em paralelo** (duas threads simultâneas)
- [ ] Progresso em tempo real com barra (`tqdm` ou print de porcentagem)
- [ ] Suporte a `word_timestamps` para granularidade de palavra (útil para diarização)
- [ ] Detectar e pular arquivos já transcritos (hash do `.wav`)

### 2.2 Módulo de Merge (`merger.py`)
- [ ] Deduplicação: remover segmentos com >80% de similaridade textual e overlap de timestamp
- [ ] Manter label de fonte `[MIC]`/`[SISTEMA]` na saída
- [ ] Saída em múltiplos formatos:
  - `merged_transcript.txt` (formato atual)
  - `merged_transcript.srt` (formato legenda padrão)
  - `merged_transcript.json` (estruturado, para integração com outras ferramentas)

### 2.3 Diarização (identificação de falantes)
- [ ] Integrar `pyannote-audio` para separar falantes dentro de cada canal
- [ ] Enriquecer o merge com labels de falante: `[FALANTE_1]`, `[FALANTE_2]`
- [ ] Documentar necessidade de token HuggingFace para `pyannote`

---

## Fase 3 — Qualidade e Robustez

### 3.1 Configuração
- [ ] `config.toml` com valores padrão documentados
- [ ] Override via variáveis de ambiente (`AUDIO_RECORDER_MODEL`, etc.)
- [ ] Validação de config na inicialização com erros claros

### 3.2 Tratamento de Erros
- [ ] Dispositivo de áudio não encontrado → mensagem clara + sugerir `devices`
- [ ] Arquivo `.wav` corrompido → pular com aviso, não travar tudo
- [ ] Modelo Whisper não baixado → baixar automaticamente com progresso
- [ ] Interrupção durante gravação → garantir que o `.wav` seja fechado corretamente (já existe, melhorar)

### 3.3 Testes
- [ ] Testes unitários para `merger.py` (lógica de parse, ordenação, deduplicação)
- [ ] Testes unitários para formatação de timestamp
- [ ] Teste de integração para o fluxo completo usando um `.wav` de fixture
- [ ] Mock de dispositivos de áudio para CI (sem hardware real)

### 3.4 Logging
- [ ] Substituir `print()` por `logging` com níveis (`DEBUG`, `INFO`, `WARNING`)
- [ ] Flag `--verbose` / `--quiet` na CLI

---

## Fase 4 — Experiência de Uso (pós-MVP)

- [ ] Modo `record-and-transcribe`: gravar e já enfileirar transcrição ao parar
- [ ] Suporte a múltiplos microfones simultâneos (ex: participantes com headsets diferentes)
- [ ] Exportação para formato de ata de reunião via LLM (resumo + action items)
- [ ] Suporte a transcrição de arquivos `.mp3`, `.mp4`, `.m4a` (não só `.wav`)
- [ ] Interface TUI simples com `textual` (status de gravação, nível de volume, tempo decorrido)

---

## Ordem de Implementação Recomendada (MVP)

```
1.1 Estrutura do projeto
    ↓
1.3 CLI esqueleto (comandos vazios)
    ↓
1.2 Módulo de captura (recorder.py)
    ↓
2.1 Módulo de transcrição (transcriber.py) com faster-whisper
    ↓
2.2 Módulo de merge (merger.py) com deduplicação básica
    ↓
1.1 config.toml + validação
    ↓
3.2 Tratamento de erros
    ↓
3.4 Logging
    ↓
3.3 Testes mínimos (merger + integração)
```

> **MVP entregável**: `uv run audio-recorder record` grava, `uv run audio-recorder transcribe` transcreve em paralelo, `uv run audio-recorder merge` gera `.txt` e `.srt`. Tudo configurável via `config.toml` sem editar código.
