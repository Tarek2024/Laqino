# صور اختبار صالحة (PNG حقيقية 1×1) بدون أي آثار جانبية؛ الرفع صار يرفض الصور التالفة بعد إزالة بيانات EXIF.
import os, base64, struct, zlib
def _ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
def png_bytes(extra=()):
    rgb = os.urandom(3)  # لون عشوائي ليختلف كل ملف
    return b"\x89PNG\r\n\x1a\n" + _ch(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + b"".join(extra) + _ch(b"IDAT", zlib.compress(b"\x00" + rgb)) + _ch(b"IEND", b"")
def png(): return base64.b64encode(png_bytes()).decode()
