"""Gera `assets/icon.ico`, um ícone placeholder para o executável Windows.

Este script não depende de bibliotecas externas (ex.: Pillow); monta o
arquivo `.ico` manualmente no formato padrão (ICONDIR + ICONDIRENTRY +
imagem 32 bpp BGRA), com um único quadro 32x32 de cor sólida.

Uso:

    python scripts/generate_icon.py

Este script é usado apenas uma vez para criar o ícone placeholder
referenciado em `media_downloader.spec`; não faz parte do runtime do
aplicativo.
"""

from __future__ import annotations

import struct
from pathlib import Path

# Cor de destaque do tema padrão do CustomTkinter (azul), usada como
# placeholder simples e profissional até que um ícone de marca definitivo
# seja fornecido.
_RGBA = (0x1F, 0x6A, 0xA5, 0xFF)  # (R, G, B, A)
_SIZE = 32


def _build_ico_bytes(size: int, rgba: tuple[int, int, int, int]) -> bytes:
    r, g, b, a = rgba

    # Dados do pixel (BGRA, 32 bpp), armazenados de baixo para cima, como
    # em um BMP comum.
    pixel_row = bytes([b, g, r, a]) * size
    xor_data = pixel_row * size

    # Máscara AND (1 bit por pixel): não utilizada quando há canal alfa,
    # mas incluída como zeros para compatibilidade com leitores legados.
    and_row_bytes = ((size + 31) // 32) * 4
    and_data = b"\x00" * and_row_bytes * size

    bitmap_info_header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size,  # biWidth
        size,  # biHeight (altura simples; imagem 32bpp usa canal alfa)
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression (BI_RGB)
        len(xor_data) + len(and_data),  # biSizeImage
        0,  # biXPelsPerMeter
        0,  # biYPelsPerMeter
        0,  # biClrUsed
        0,  # biClrImportant
    )

    image_data = bitmap_info_header + xor_data + and_data

    icon_dir = struct.pack("<HHH", 0, 1, 1)  # reserved, type=icon, count=1
    # Offset dos dados da imagem: ICONDIR (6 bytes) + 1 ICONDIRENTRY (16 bytes).
    offset = 6 + 16
    icon_dir_entry = struct.pack(
        "<BBBBHHII",
        size if size < 256 else 0,
        size if size < 256 else 0,
        0,
        0,
        1,
        32,
        len(image_data),
        offset,
    )

    return icon_dir + icon_dir_entry + image_data


def main() -> None:
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    output_path = assets_dir / "icon.ico"
    output_path.write_bytes(_build_ico_bytes(_SIZE, _RGBA))
    print(f"Ícone gerado em: {output_path}")


if __name__ == "__main__":
    main()
