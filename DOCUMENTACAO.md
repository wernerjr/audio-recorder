# Audio Recorder — Documentação do Projeto Legado

## Visão Geral

Ferramenta Python para **gravar reuniões** capturando simultaneamente dois canais de áudio (microfone e som do sistema) e depois **transcrever** cada canal via Whisper, gerando uma transcrição unificada com timestamps.

---

## Arquitetura

```
iniciar_gravacoes.py          ← ponto de entrada (orquestrador)
    ├── subprocess → gravar_mic.py        → microfone.wav
    └── subprocess → gravar_sistema.py   → sistema.wav

transcrever_arquivos.py       ← transcrição (roda depois da gravação)
    ├── microfone.wav → microfone.txt
    └── sistema.wav   → sistema.txt

merge_transcripts.py          ← unifica as duas transcrições
    ├── microfone.txt
    ├── sistema.txt
    └── → merged_transcript.txt

test.py                       ← benchmark de modelos Whisper (utilitário)
```

---

## Fluxo de Uso (passo a passo)

### Etapa 1 — Gravação

```bash
python iniciar_gravacoes.py
# Ctrl+C para parar ambos os processos
```

- Dispara `gravar_sistema.py` e `gravar_mic.py` como **subprocessos independentes**
- Ambos gravam em loop contínuo até receber `KeyboardInterrupt`
- O processo pai captura o `Ctrl+C` e chama `proc.terminate()` nos filhos
- Saída: `sistema.wav` e `microfone.wav` na raiz do projeto

### Etapa 2 — Transcrição

```bash
python transcrever_arquivos.py
```

- Carrega o modelo Whisper (`large` por padrão — configurável via `MODEL_NAME`)
- Transcreve cada `.wav` em sequência, **uma de cada vez**
- Formato de saída por linha: `[HH:MM:SS.mmm --> HH:MM:SS.mmm] texto`
- Saída: `sistema.txt` e `microfone.txt`

### Etapa 3 — Merge

```bash
python merge_transcripts.py
```

- Lê os dois `.txt`, faz parse dos timestamps com regex
- Ordena todos os segmentos cronologicamente por `start`
- Adiciona label de fonte em cada linha: `[MICROFONE]` ou `[SISTEMA]`
- Saída: `merged_transcript.txt`

---

## Scripts em Detalhe

### `gravar_sistema.py`
- Usa **WASAPI loopback** via `pyaudiowpatch` para capturar o som que sai pelos alto-falantes
- Dispositivo: `p.get_default_wasapi_loopback()` (sem configuração manual)
- Formato: PCM Int16, sample rate e canais detectados automaticamente do dispositivo
- Chunk: 1024 frames por leitura

### `gravar_mic.py`
- Localiza o microfone por **substring do nome** (`MIC_DEVICE_NAME = "USB Microphone"`)
- Mesma lógica de gravação que `gravar_sistema.py`
- **Ponto fraco**: nome do mic está hardcoded — precisa ser ajustado manualmente

### `transcrever_arquivos.py`
- Modelo padrão: `large` (maior qualidade, mais lento)
- Não usa `word_timestamps`, apenas timestamps por segmento
- Não há detecção de idioma explícita — Whisper detecta automaticamente
- Processamento **sequencial** (sistema → microfone), sem paralelismo

### `merge_transcripts.py`
- Regex de parse: `\[HH:MM:SS.mmm --> HH:MM:SS.mmm\] texto`
- Ordenação por `start` apenas — sem lógica de sobreposição ou deduplicação
- Linhas vazias são ignoradas

### `test.py`
- Roda todos os modelos Whisper (`tiny`, `base`, `small`, `medium`, `large`) nos primeiros 5 minutos de cada arquivo
- Útil para escolher o trade-off qualidade/velocidade
- Gera arquivos `sistema_<modelo>_5min.txt` e `microfone_<modelo>_5min.txt`

---

## Dependências

| Pacote | Uso |
|---|---|
| `pyaudiowpatch` | Captura de áudio (microfone + WASAPI loopback) |
| `openai-whisper` | Transcrição local via modelos Whisper |
| `wave` (stdlib) | Escrita de arquivos `.wav` |
| `subprocess` (stdlib) | Paralelismo entre gravações |

---

## Arquivos de Dados

| Arquivo | Gerado por | Descrição |
|---|---|---|
| `microfone.wav` | `gravar_mic.py` | Áudio do microfone |
| `sistema.wav` | `gravar_sistema.py` | Áudio do sistema (loopback) |
| `microfone.txt` | `transcrever_arquivos.py` | Transcrição do mic com timestamps |
| `sistema.txt` | `transcrever_arquivos.py` | Transcrição do sistema com timestamps |
| `merged_transcript.txt` | `merge_transcripts.py` | Transcrição unificada e ordenada |
| `meeting_transcript.txt` | manual/externo | Exemplo de saída final (já existe no repo) |
| `teste/reuniaox.wav` | manual | Arquivo de teste/exemplo |

---

## Limitações e Problemas Conhecidos

1. **Nome do microfone hardcoded** — `MIC_DEVICE_NAME = "USB Microphone"` em `gravar_mic.py` precisa ser alterado manualmente para cada máquina.
2. **Sem interface** — operação 100% via terminal; nenhum controle visual de status.
3. **Transcrição sequencial** — `transcrever_arquivos.py` processa um arquivo por vez; para gravações longas, isso dobra o tempo de espera.
4. **Sem deduplicação no merge** — se mic e sistema capturam o mesmo áudio simultaneamente, aparece duplicado no `merged_transcript.txt`.
5. **Sem separação de falantes (diarização)** — não identifica quem está falando, apenas de qual canal veio.
6. **Arquivos de saída fixos na raiz** — não há configuração de diretório de saída; todos os `.wav` e `.txt` ficam no mesmo lugar dos scripts.
7. **Sem tratamento de erro em transcrição** — se o modelo falhar num segmento, não há retry ou fallback.
8. **Modelo `large` padrão** — consome bastante VRAM/RAM; sem opção via argumento CLI.

---

## Pontos Fortes a Preservar na Reescrita

- Captura dupla simultânea (mic + loopback) é o diferencial principal
- Formato de timestamp `[HH:MM:SS.mmm --> HH:MM:SS.mmm]` é compatível com SRT/VTT
- Merge com label de fonte (`[MICROFONE]`/`[SISTEMA]`) facilita leitura
- `test.py` como benchmark de modelos é uma boa prática a manter

---

## Sugestões para a Reescrita

- **Config file** (TOML/YAML) para nome do mic, modelo Whisper, diretório de saída
- **Transcrição em paralelo** dos dois arquivos após gravação
- **Diarização** via `pyannote-audio` para identificar falantes
- **CLI com argparse** para controlar modelo, duração máxima, idioma forçado
- **Watch mode**: transcrever em tempo real ou logo após parar a gravação
- **Deduplicação** no merge baseada em similaridade de texto + overlap de timestamps
