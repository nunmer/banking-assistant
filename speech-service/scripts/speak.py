#!/usr/bin/env python3
"""Synthesize text to WAV using the speech service TTS engine.

Usage:
  python scripts/speak.py "Сәлем, қалайсыз?" --voice amira --out out/amira.wav
  python scripts/speak.py "Привет"
  python scripts/speak.py "Текст" --engine yandex
  python scripts/speak.py --list-voices
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="TTS: text → WAV")
    parser.add_argument("text", nargs="?", help="Text to synthesize")
    parser.add_argument("--voice", default="marina")
    parser.add_argument("--lang", default="ru-RU")
    parser.add_argument("--out", default="out/speak.wav")
    parser.add_argument("--engine", default=None, help="TTS engine (default from config)")
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    from app.engines import create_tts_engine
    tts = create_tts_engine(args.engine)

    if args.list_voices:
        for v in tts.list_voices():
            print(v)
        return

    if not args.text:
        parser.print_help()
        sys.exit(1)

    audio = tts.synthesize(args.text, voice=args.voice, lang=args.lang)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    print(f"saved {len(audio)} bytes -> {out.resolve()}")

    if sys.platform == "win32":
        os.startfile(str(out.resolve()))
    elif sys.platform == "darwin":
        os.system(f"afplay '{out}'")
    else:
        os.system(f"aplay '{out}' 2>/dev/null || paplay '{out}' 2>/dev/null")


if __name__ == "__main__":
    main()
