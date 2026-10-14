# video-notes — spec and decisions

## Purpose

Turn every post in Marco's TikTok collection "Material" into a note in his brain (`~/Projects/brain/Resources/commonplace/videos/`). Two halves:

1. **`vn`, a local pipeline** that lists the posts, downloads media, runs OCR and speech-to-text, and stores everything in SQLite. It uses no AI reasoning: only local utility models (Tesseract, Whisper).
2. **Note writing**, done by an agent (Claude Code or Codex, on Marco's subscriptions) following `docs/note-writing.md`. No pay-per-use API keys, no local LLMs.

Everything runs locally. Captions, hashtags and comments are never fetched into the database or the notes.

## Commands

| Command | What it does |
|---|---|
| `vn sync` | List the collection; add new posts (id, URL, creator, upload date, type) |
| `vn fetch [N]` | Download media for up to N new posts, pausing 3–10 s between posts |
| `vn process [N]` | OCR and transcribe up to N fetched posts; mark empty ones skipped ("no content") |
| `vn run [N]` | sync + fetch N + process N |
| `vn pending [N]` | Show processed posts waiting for a note (`--id`, `--json`, `--ids`) |
| `vn done <id> <note-path>` | Mark a post as written up |
| `vn skip <id> <reason>` | Skip a post with a reason |
| `vn status` | Counts by status, type and skip reason |

`vn` is `.venv/bin/vn`, linked as `~/.local/bin/vn`.

## Data

`data/` is gitignored:

- `data/vn.sqlite`: all state.
- `data/media/<post id>/`: `frame.png` (videos) or `slide-01.jpg`, … (slideshows). Kept so note writers can look at them. Videos and audio are deleted after use.
- `data/links.txt`: manual fallback list of post URLs, one per line.
- `data/tools/`: fallback Tesseract (see Decisions).

Tables (`src/video_notes/db.py`):

- `posts`: id, url, creator, upload_date, type (`video` | `slideshow`), status, skip_reason, note_path, language and language_prob (Whisper), whisper_model, transcribed, fetch_attempts, last_error, timestamps.
  - Status flows `new → fetched → processed → done`, or to `skipped` from any point.
- `images`: post_id, idx (0 = the video frame, 1.. = slides), kind, path, ocr_text, ocr_conf (mean word confidence 0–100).
- `segments`: post_id, idx, start, end, text.
- `meta`: `sync_source`, `cookies`.

Every stage selects only rows in its input status and commits after each post (OCR: after each image), so any command can be stopped and rerun.

## Pipeline

**sync** (`sync.py`). Sources are tried in this order:

1. yt-dlp's `tiktok:collection` extractor, anonymously.
2. The same with `--cookies-from-browser firefox`.
3. `data/links.txt`.

The flat listing doesn't say whether a post is a slideshow (every URL is `/video/<id>`), so sync reads each *new* post's metadata once with yt-dlp, pausing 1–3 s between posts. A post whose formats are all audio-only is a slideshow.

**fetch** (`fetch.py`):

- **Video**: yt-dlp, best format with short side ≤ 720 px (`format_sort res:720`). ffmpeg then extracts the frame at 0.5 s and 16 kHz mono WAV audio, and the video is deleted.
- **Slideshow**: gallery-dl with audio filtered out; images saved as `slide-NN.<ext>` in post order.
- **Failures**: a failed post is retried on the next run, and skipped with "fetch failed: …" after 3 attempts. Five failures in a row stop the run, which usually means TikTok is blocking: update yt-dlp and gallery-dl.

**process** (`process.py`, `ocr.py`, `transcribe.py`):

- **OCR**: Tesseract `eng+ita+spa`, 8 images in parallel (one thread each).
  - Preprocessing: grayscale, 2× upscale (images under 2000 px), and CLAHE contrast. Three variants are read: gray, Otsu binary, and inverted binary. Each is read with page segmentation modes 6 and 11, and the reading with the most confidently-read characters wins.
  - Line filter: a line is kept if its mean word confidence is ≥ 70 and it has ≥ 4 letters or digits. Lines without letters need ≥ 90. Weak or punctuation-only tokens are trimmed from line ends.
  - Stored: the text and the mean confidence of the kept words.
- **Speech**: faster-whisper on the CPU, int8, beam 5, VAD filter, language detected automatically. Segments that are probably silence (no_speech_prob > 0.6 and avg_logprob < −1) are dropped. Segments, language and its probability are stored, then the WAV is deleted.
- **No content**: a post with no speech segments and no image with ≥ 3 letters or digits is skipped with reason "no content".

## Decisions

- **Python 3.14 venv via uv** (2026-10-15). All dependencies have 3.14 wheels, so no older Python was needed.
- **yt-dlp and gallery-dl from pip**, so `uv pip install -U` can update them quickly. yt-dlp is installed with `curl-cffi` so it can impersonate a browser.
- **yt-dlp's collection extractor works anonymously**. The collection is public, so cookies weren't needed. A direct call to TikTok's `/api/collection/item_list` also worked in testing but wasn't needed, so it isn't implemented.
- **Slideshows with gallery-dl.** For photo posts, yt-dlp returns only the background audio; gallery-dl returns the images at their original upload size (e.g. 643×1254). The `imagePost` URLs from TikTok's API are the same files, but they would need custom code.
- **We decode the WAV ourselves** (`transcribe.load_wav`) instead of letting faster-whisper do it. faster-whisper 1.2.1 calls PyAV with `metadata_errors=`, which PyAV 19 removed (TypeError). Reading the 16 kHz WAV with the standard `wave` module avoids PyAV entirely.
- **`OMP_THREAD_LIMIT=1` is set only when OCR starts.** Set at import time, it was also picked up by faster-whisper's OpenMP runtime, and transcription slowed down about 3×.
- **Fallback Tesseract in `data/tools/`.** The system `tesseract` wasn't installed when the pipeline was built, and installing it needs sudo. `vn` uses the system `tesseract` if it's on PATH. Otherwise it uses a copy unpacked, without installing, from Fedora's own signed RPMs:
  ```
  dnf download tesseract tesseract-langpack-ita tesseract-langpack-spa
  rpm2cpio <rpm> | cpio -idm
  ```
  The binary goes in `data/tools/root/usr/bin/`, and the eng/ita/spa models in `data/tools/tessdata/`. It links against the system's `libtesseract` and `leptonica`, which were already installed. Once `sudo dnf install tesseract tesseract-langpack-ita tesseract-langpack-spa` has run, `data/tools/` can be deleted.
- **OCR line filter, not word filter.** Keeping every word with confidence ≥ 40 filled the output with "words" read from photo texture (dozens of 1–3 letter fragments per frame). Overlaid captions come out as long, confident lines, so filtering whole lines removed almost all noise and kept the captions in testing.
- **The video frame at 0.5 s is often a poor sample**: karaoke-style captions show a single word at that moment, and picture details get misread. That's why note writers always open the frame image (see `note-writing.md`).
- **Whisper model: `medium`** (2026-10-15). Tested on 3 real videos (82 s Italian, 40 s and 87 s English); numbers in `docs/whisper-bench.json`, produced by `scripts/whisper_bench.py`.

  | Model | Real-time factor (CPU, int8) | Accuracy |
  |---|---|---|
  | small | 0.10–0.25 | Several mishearings ("dis-police" for "disbelief", "entrust" for "impress", "extremo"); invented a closing "Alla prossima. Buon appetito." |
  | **medium** | 0.25–0.33 | Essentially error-free; got "Anthropic" right; one slip ("equiti") |
  | large-v3-turbo | 0.21–0.48 | Accurate on speech, but fell into a ~25× repetition loop ("you're not going to be…") on a music tail; "Antropic" |

  medium was the most accurate and never hallucinated. At ~0.3× real time, the whole collection (~80 min of audio) transcribes in under half an hour.
- **Type detection costs one metadata request per new post at sync time.** The alternative, detecting it at fetch time, would leave `type` empty in `vn status` until download.
- **Note-writing review (5 test posts, 2026-10-15).** These rules were added to `note-writing.md`:
  - always open the video frame;
  - only short italic labels may be added to Content;
  - wording-changing grammar fixes get `[?]`.

## Results

See the project note `~/Projects/brain/Projects/video-notes.md` (Log) for the run on the full collection.
