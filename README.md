# Motion Guard (心率守护)

A real-time heart rate monitoring and emotional intervention system that combines physiological monitoring with AI-powered emotional support.

## Overview

Motion Guard monitors users' heart rates in real-time and provides timely emotional intervention when abnormal patterns are detected. The system integrates:

- **Real-time Heart Rate Monitoring** - Continuous health data collection and analysis
- **AI-Powered Emotional Consulting** - Intelligent psychological support using DeepSeek API
- **Text-to-Speech Integration** - Voice-based interaction using ChatTTS service
- **MCP (Model Context Protocol)** - Tool integration for enhanced AI capabilities

## Features

- 🔴 **Heart Rate Monitoring** - Real-time heart rate tracking with configurable thresholds
- ⚠️ **Anomaly Detection** - Automatic detection of abnormal heart rate patterns (too high/too low)
- 🤖 **AI Intervention** - Emotional care assistant (EmoGuard) activated during health emergencies
- 💬 **Psychological Counseling** - Professional-level emotional consulting with session logging
- 🔊 **Voice Synthesis** - Text-to-speech for auditory feedback
- 📧 **Email Notifications** - Alert system integration via MCP tools

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Motion Guard System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ Heart Rate       │───▶│ LLM Intervention │                  │
│  │ Monitor          │    │ Service          │                  │
│  │ (motion_guard.py)│    │ (LLM_inter.py)   │                  │
│  └──────────────────┘    └────────┬─────────┘                  │
│                                   │                             │
│                    ┌──────────────┴──────────────┐             │
│                    ▼                              ▼             │
│          ┌──────────────────┐        ┌──────────────────┐      │
│          │ Emotional        │        │ TTS Service      │      │
│          │ Consulting       │        │ (ChatTTS)        │      │
│          │ System           │        │                  │      │
│          └──────────────────┘        └──────────────────┘      │
│                    │                                            │
│                    ▼                                            │
│          ┌──────────────────┐                                   │
│          │ MCP Client       │                                   │
│          │ (Tools/Email)    │                                   │
│          └──────────────────┘                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| Heart Rate Monitor | `motion_guard.py` | Python implementation for heart rate monitoring |
| Heart Rate Monitor (Rust) | `motion_gurad.rs` | Rust implementation for heart rate monitoring |
| LLM Intervention | `LLM_inter.py` | Flask service for AI-powered emotional intervention |
| Emotional Consulting | `emotional_consulting.py` | Professional emotional counseling system |
| MCP Client | `mcp_client_servers.py` | Model Context Protocol client wrapper |
| TTS Client | `TTS.py` | Text-to-speech request client |
| Audio Client | `audio.py` | Audio generation client with streaming support |
| Audio Player | `audio_player.py` | Real-time audio stream player |
| Text to MP3 | `text2mp3` | Text-to-MP3 conversion utility |

## Prerequisites

- Python 3.8+
- Rust (for Rust implementation)
- ChatTTS service running (for voice synthesis)
- DeepSeek API key (for AI consulting)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/bionobelprize/Motion_guard.git
   cd Motion_guard
   ```

2. Install Python dependencies:
   ```bash
   pip install asyncio aiohttp flask requests pydub playsound pyaudio openai python-dotenv mcp
   ```

3. Set up environment variables:
   ```bash
   export DEEPSEEK_API_KEY="your-deepseek-api-key"
   export CHATTTS_SERVICE_HOST="localhost"
   export CHATTTS_SERVICE_PORT="8000"
   ```

## Usage

### Start the Heart Rate Monitor

```bash
python motion_guard.py
```

### Start the LLM Intervention Service

```bash
python LLM_inter.py
```

This starts the intervention service on `http://127.0.0.1:5005/intervene`.

### Use the Emotional Consulting System

```python
from emotional_consulting import EmotionalConsultingSystem

user_info = {
    "name": "User",
    "age": "28",
    "topic": "Emotional Support",
    "session_count": 1
}

consultant = EmotionalConsultingSystem(user_info)
response = consultant.consult("How can I manage stress better?")
print(response)
```

### Audio Player

```bash
python audio_player.py
```

Choose between interactive mode (manual text input) or demo mode (automatic playback).

## Configuration

### Heart Rate Thresholds

In `motion_guard.py`:
```python
self.emergency_threshold = 120  # BPM for emergency alert
self.warning_threshold = 100    # BPM for warning alert
```

### Monitoring Interval

```python
self.monitoring_interval = 5  # seconds between checks
```

### API Endpoints

- Heart Rate Device API: `http://192.168.1.104:8080/heart-rate`
- LLM Intervention API: `http://127.0.0.1:5005/intervene`
- ChatTTS Service: `http://localhost:8000/generate_voice`

## Session Logs

Emotional consulting sessions are automatically saved as JSON files:
```
consulting_session_YYYYMMDD_HHMMSS.json
```

## License

This project is open source. Please check with the repository owner for specific licensing terms.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
