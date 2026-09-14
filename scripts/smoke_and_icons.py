import json
import struct
import urllib.request
import zlib
from pathlib import Path

BASES = [
    "https://justthis.co.kr",
    "https://www.justthis.co.kr",
]


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "just-here-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status, r.read()


def smoke():
    for base in BASES:
        for path in ("/health", "/v1/meta", "/"):
            url = base + path
            try:
                status, body = get(url)
                snippet = body[:120].decode("utf-8", "replace").replace("\n", " ")
                print(f"OK {status} {url} :: {snippet}")
            except Exception as e:
                print(f"FAIL {url} :: {e}")


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_icon(path: Path, size: int, rgb=(255, 106, 61)):
    # Solid orange square with simple white circle pin mark (no external deps)
    raw = bytearray()
    r, g, b = rgb
    cx = cy = size // 2
    pin_r = size // 5
    for y in range(size):
        raw.append(0)  # filter
        for x in range(size):
            dx, dy = x - cx, y - (cy - size // 12)
            in_pin = dx * dx + dy * dy <= pin_r * pin_r
            # stem triangle-ish
            in_stem = (abs(dx) < pin_r // 3) and (dy > 0) and (dy < pin_r * 2)
            if in_pin or in_stem:
                raw.extend((255, 255, 255))
            else:
                raw.extend((r, g, b))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + png_chunk(b"IEND", b"")
    path.write_bytes(data)
    print(f"wrote {path} ({len(data)} bytes)")


if __name__ == "__main__":
    smoke()
    icons = Path(__file__).resolve().parents[1] / "web" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    write_icon(icons / "icon-192.png", 192)
    write_icon(icons / "icon-512.png", 512)
    write_icon(icons / "apple-touch-icon.png", 180)
