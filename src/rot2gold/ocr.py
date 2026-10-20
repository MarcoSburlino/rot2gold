"""OCR for text overlaid on photos and video frames.

Each image is preprocessed into a few variants and read with two page modes;
the reading with the most confident text wins.
"""

import cv2
import numpy as np
import pytesseract

# Photo texture produces many short low-confidence "lines"; overlaid text produces long confident ones.
MIN_LINE_CONF = 70      # mean word confidence a line needs to be kept
MIN_LINE_CHARS = 4      # letters/digits a line needs to be kept
MIN_DIGITS_CONF = 90    # lines without letters (e.g. "1300") need this confidence
EDGE_TOKEN_CONF = 60    # weak or punctuation-only tokens at the ends of a line are trimmed ("|", "==")


def variants(path: str) -> dict[str, np.ndarray]:
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError(f"cannot read image {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = 2.0 if max(gray.shape) < 2000 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    _, binary = cv2.threshold(cv2.GaussianBlur(gray, (3, 3), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return {"gray": gray, "binary": binary, "inverted": 255 - binary}


def read(img: np.ndarray, langs: str, psm: int) -> tuple[str, float, float]:
    """Return (text, mean confidence, score) for one image variant."""
    d = pytesseract.image_to_data(img, lang=langs, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[tuple[str, float]]] = {}
    for i, word in enumerate(d["text"]):
        word, conf = word.strip(), float(d["conf"][i])
        if word and conf >= 0:
            lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append((word, conf))

    def weak(tok):
        return tok[1] < EDGE_TOKEN_CONF or not any(c.isalnum() for c in tok[0])

    kept, confs, score = [], [], 0.0
    for _, words in sorted(lines.items()):
        while words and weak(words[0]):
            words = words[1:]
        while words and weak(words[-1]):
            words = words[:-1]
        if not words:
            continue
        line = " ".join(w for w, _ in words)
        conf = sum(c for _, c in words) / len(words)
        chars = sum(c.isalnum() for c in line)
        letters = sum(c.isalpha() for c in line)
        if conf < MIN_LINE_CONF or chars < MIN_LINE_CHARS or (letters < 2 and conf < MIN_DIGITS_CONF):
            continue
        kept.append(line)
        confs += [c for _, c in words]
        score += conf / 100 * chars  # rewards more text read confidently
    return "\n".join(kept), (sum(confs) / len(confs) if confs else 0.0), score


def ocr_image(path: str, langs: str) -> tuple[str, float]:
    best = ("", 0.0, 0.0)
    for img in variants(path).values():
        for psm in (6, 11):
            result = read(img, langs, psm)
            if result[2] > best[2]:
                best = result
    return best[0], round(best[1], 1)
