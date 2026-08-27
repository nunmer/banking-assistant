#!/usr/bin/env python3
"""Transcribe an audio file using the speech service STT engine.

Usage:
  python scripts/transcribe.py audio.wav
  python scripts/transcribe.py audio.wav --lang kk-KZ
  python scripts/transcribe.py audio.wav --speakers
  python scripts/transcribe.py audio.wav --engine yandex
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="STT: audio → text")
    parser.add_argument("file", help="Path to audio file")
    parser.add_argument("--lang", default="ru-RU")
    parser.add_argument("--speakers", action="store_true", help="Enable speaker diarization")
    parser.add_argument("--engine", default=None, help="STT engine (default from config)")
    args = parser.parse_args()

    data = Path(args.file).read_bytes()

    from app.engines import create_stt_engine
    from app.utils.audio import to_pcm_wav

    data = to_pcm_wav(data)
    stt = create_stt_engine(args.engine)

    if args.speakers:
        channels = stt.transcribe(data, lang=args.lang)
        for ch in channels:
            print(f"\n[Speaker {ch['speaker']}]")
            for utt in ch["utterances"]:
                print(f"  {utt['start_ms']}ms - {utt['end_ms']}ms: {utt['text']}")
    else:
        text = stt.recognize(data, lang=args.lang)
        print(text)


if __name__ == "__main__":
    main()
