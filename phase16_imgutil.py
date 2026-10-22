# أدوات اختبار المرحلة 16: تولّد صور PNG صالحة فعلًا (توقيع + IHDR + IDAT مضغوط + IEND مع CRC صحيح) بلا Pillow.
# مستقل عن imgutil.py القديم (إن وُجد في مشروعك) فلا يستبدله ولا يتعارض معه. للاختبارات فقط.
import struct, zlib, os

def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

def png_bytes(w=16, h=16, color=None):
    """PNG حقيقي RGB. بلا لون محدد يُختار لون عشوائي فتختلف الصور عن بعضها."""
    color = tuple(color) if color else tuple(os.urandom(3))
    row = b"\x00" + bytes(color) * w            # filter type 0 + بكسلات الصف
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(row * h)) + _chunk(b"IEND", b""))
