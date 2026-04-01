# Audio Recorder

Desktop application for recording meetings with real-time transcription, speaker diarization, and meeting minutes generation.

Records microphone and system audio simultaneously, transcribes with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and stores the full session history in a local SQLite database.

---

## Features

- **Dual-channel recording** — microphone and system audio (loopback) captured in parallel
- **Real-time transcription** — powered by faster-whisper (Whisper models: tiny → large)
- **VAD segmentation** — silero-vad splits audio on natural pauses for accurate transcription
- **Speaker diarization** (optional) — identifies who spoke when using ECAPA-TDNN embeddings
- **Time-aligned audio mix** — channels are synchronized by wall-clock timestamp and mixed into a single `merged.wav`
- **Session history** — all sessions stored in SQLite with full-text search (FTS5)
- **Playback with transcript sync** — replay any session with highlighted transcript line
- **Re-transcription** — re-run any saved session with a different Whisper model
- **Meeting minutes** — generates structured summary (executive summary + bullet points) from any session
- **CLI interface** — record, browse history, and display transcripts from the terminal

---

## Requirements

- Python 3.11+
- Windows: WASAPI loopback capture is built-in via [pyaudiowpatch](https://github.com/s0d3s/PyAudioWPatch)
- macOS: install [BlackHole](https://github.com/ExistentialAudio/BlackHole) for system audio capture
- Linux: PulseAudio monitor source (no extra setup required)

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd audio-recorder

# Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows (bash)
# or
.venv\Scripts\activate.bat      # Windows (cmd)
# or
source .venv/bin/activate        # macOS / Linux

# Install the project and all dependencies
pip install -e .
```

> **Note:** On first use, faster-whisper will download the selected Whisper model (~150 MB for `small`, ~1.5 GB for `large`). Speaker diarization downloads the ECAPA-TDNN model (~80 MB) the first time it runs.

---

## Usage

### GUI

```bash
audio-recorder-gui
```

1. Click **Gravar** to start recording
2. Click **Parar** to stop — transcription is saved automatically to history
3. Click **Histórico** to browse past sessions

### CLI

```bash
# Start a recording session (Ctrl+C to stop)
audio-recorder record

# Use a specific model and language
audio-recorder record --model medium --lang pt

# List all recorded sessions
audio-recorder history

# Show transcript of session 3
audio-recorder show 3

# Search within a session
audio-recorder show 3 --search "budget"

# List available audio devices
audio-recorder devices
```

---

## Configuration

Create a `config.toml` file in the project root to override defaults:

```toml
[transcription]
model = "small"       # tiny, base, small, medium, large
language = "auto"     # auto, pt, en, es, ...

[output]
directory = "recordings"

[diarization]
enabled = false
```

---

## Project Structure

```
src/audio_recorder/
├── capture/        # Microphone and loopback audio capture (platform-specific)
├── vad/            # Voice activity detection (silero-vad)
├── transcription/  # faster-whisper engine and pipeline
├── diarization/    # Speaker diarization (ECAPA-TDNN via simple-diarizer)
├── audio/          # WAV mixing and time alignment
├── merge/          # Transcript merging and deduplication
├── session/        # Recording session lifecycle
├── persistence/    # SQLite history (sessions, segments, meeting minutes)
├── summarization/  # Meeting minutes generation (TF-IDF)
├── config/         # Settings dataclasses and TOML loader
├── gui/            # PySide6 interface (main window, history, settings, players)
│   ├── widgets/    # Waveform indicator, transcript view
│   └── workers/    # QThread workers for background tasks
├── cli/            # Typer CLI commands
└── utils/          # Timestamp formatting, platform detection
```

---

## Tech Stack

| Layer | Library |
|---|---|
| GUI | PySide6 (Qt6) |
| Transcription | faster-whisper |
| Voice activity detection | silero-vad |
| Speaker diarization | simple-diarizer (ECAPA-TDNN) |
| Audio capture — mic | sounddevice |
| Audio capture — loopback (Windows) | pyaudiowpatch (WASAPI) |
| Audio mixing | scipy + numpy |
| History storage | SQLite (WAL + FTS5) |
| Meeting minutes | NLTK + TF-IDF |
| CLI | Typer |

---

## License

MIT
