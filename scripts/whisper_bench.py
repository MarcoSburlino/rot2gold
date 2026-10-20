"""Compare Whisper models on real audio: speed (real-time factor) and transcripts side by side.

Usage: .venv/bin/python scripts/whisper_bench.py OUT_DIR AUDIO.wav [AUDIO.wav ...]
Run it on fetched-but-unprocessed posts (process deletes the audio).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from rot2gold.transcribe import transcribe

MODELS = ["small", "medium", "large-v3-turbo"]


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out)


def main() -> None:
    out_dir, audios = Path(sys.argv[1]), sys.argv[2:]
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for name in MODELS:
        transcribe(audios[0], name)  # warm up: download and load the model outside the timing
        for audio in audios:
            t0 = time.time()
            segs, lang, prob = transcribe(audio, name)
            secs = time.time() - t0
            dur = duration(audio)
            text = " ".join(s["text"] for s in segs)
            results.append({"model": name, "audio": audio, "duration": round(dur, 1), "seconds": round(secs, 1),
                            "rtf": round(secs / dur, 3), "language": lang, "prob": prob, "text": text})
            print(f"{name:<15} {Path(audio).parent.name} {dur:6.1f}s audio  {secs:6.1f}s  rtf {secs / dur:.3f}  {lang}")
            (out_dir / f"{Path(audio).parent.name}-{name}.txt").write_text(text + "\n")
    (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
