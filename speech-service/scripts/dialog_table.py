#!/usr/bin/env python3
"""Convert STT response JSON to a chronological dialog table.

Usage:
  python scripts/dialog_table.py response_*.json
  python scripts/dialog_table.py response_*.json --format md
  python scripts/dialog_table.py response_*.json --format csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path


def load_utterances(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for speaker in data.get("speakers", []):
        sid = speaker["speaker"]
        for utt in speaker.get("utterances", []):
            text = utt.get("text", "").strip()
            rows.append({
                "start_ms": utt["start_ms"],
                "time": utt.get("start", ""),
                "speaker": f"S{sid}",
                "text": text if text else "(silence)",
            })
    rows.sort(key=lambda r: r["start_ms"])
    return rows


def print_markdown(rows: list[dict], meta: dict, left_label: str = "S0", right_label: str = "S1"):
    lang = meta.get("lang", "")
    duration = meta.get("duration_seconds", 0)
    mins, secs = divmod(int(duration), 60)
    print(f"**Lang:** {lang} | **Duration:** {mins}:{secs:02d}\n")
    print(f"| Time | {left_label} | {right_label} |")
    print("|------|------|------|")
    for r in rows:
        time = r["time"].split(".")[0]
        left = r["text"] if r["speaker"] == left_label else ""
        right = r["text"] if r["speaker"] == right_label else ""
        print(f"| {time} | {left} | {right} |")


def print_csv(rows: list[dict]):
    writer = csv.writer(sys.stdout)
    writer.writerow(["time", "speaker", "text"])
    for r in rows:
        writer.writerow([r["time"], r["speaker"], r["text"]])


def print_plain(rows: list[dict]):
    for r in rows:
        time = r["time"].split(".")[0]
        print(f"[{time}] {r['speaker']}: {r['text']}")


def main():
    parser = argparse.ArgumentParser(description="STT JSON → dialog table")
    parser.add_argument("files", nargs="+", help="response_*.json files")
    parser.add_argument(
        "--format", choices=["md", "csv", "plain"], default="md",
        help="Output format (default: md)"
    )
    args = parser.parse_args()

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        rows = load_utterances(path)

        if len(args.files) > 1:
            print(f"\n# {path.name}\n")

        if args.format == "md":
            print_markdown(rows, data, left_label="S0", right_label="S1")
        elif args.format == "csv":
            print_csv(rows)
        else:
            print_plain(rows)


if __name__ == "__main__":
    main()
