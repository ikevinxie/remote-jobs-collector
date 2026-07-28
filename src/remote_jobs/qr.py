"""纯标准库 QR 码生成器(见 SPEC.md §26)。

范围刻意收窄以保证正确性:byte 模式、纠错级 L、版本 1–5(单 RS 块,容量 ≤106 字节)、
固定掩码 0。用于把站点固定 URL 编成 SVG 内嵌页面,发布时生成一次,无运行时依赖。
实现遵循 ISO/IEC 18004;结构与 Project Nayuki 的参考实现对齐,便于对拍验证。
"""
from __future__ import annotations

# 版本 → (总码字数, ECC 码字数),纠错级 L、单块
_VERSIONS = {1: (26, 7), 2: (44, 10), 3: (70, 15), 4: (100, 20), 5: (134, 26)}

# ---- GF(256) 与 Reed-Solomon(本原多项式 0x11D)----
_EXP = [0] * 512
_LOG = [0] * 256
_value = 1
for _i in range(255):
    _EXP[_i] = _value
    _LOG[_value] = _i
    _value <<= 1
    if _value & 0x100:
        _value ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _generator_poly(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        factor = [1, _EXP[i]]
        result = [0] * (len(poly) + 1)
        for j, a in enumerate(poly):
            if a:
                for k, b in enumerate(factor):
                    result[j + k] ^= _EXP[(_LOG[a] + _LOG[b]) % 255]
        poly = result
    return poly


def _rs_ecc(data: list[int], degree: int) -> list[int]:
    generator = _generator_poly(degree)
    remainder = list(data) + [0] * degree
    for i in range(len(data)):
        factor = remainder[i]
        if factor:
            for j in range(1, len(generator)):
                remainder[i + j] ^= _EXP[(_LOG[generator[j]] + _LOG[factor]) % 255]
            remainder[i] = 0
    return remainder[-degree:]


# ---- 编码 ----

def _choose_version(byte_count: int) -> int:
    for version, (total, ecc) in _VERSIONS.items():
        if byte_count <= (total - ecc) - 2:  # 模式指示 4bit + 长度 8bit ≈ 2 码字
            return version
    raise ValueError(f"内容过长({byte_count} 字节),超出 v5-L 容量 106 字节")


def _data_codewords(payload: bytes, version: int) -> list[int]:
    total, ecc = _VERSIONS[version]
    data_capacity = total - ecc
    bits: list[int] = []

    def push(value: int, length: int) -> None:
        bits.extend((value >> (length - 1 - i)) & 1 for i in range(length))

    push(0b0100, 4)              # byte 模式
    push(len(payload), 8)        # 版本 1–9 的 byte 模式长度域为 8 位
    for byte in payload:
        push(byte, 8)
    push(0, min(4, data_capacity * 8 - len(bits)))  # 终止符
    while len(bits) % 8:
        bits.append(0)
    codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    for index in range(data_capacity - len(codewords)):
        codewords.append(0xEC if index % 2 == 0 else 0x11)
    return codewords


def format_bits(mask: int) -> int:
    """15 位格式信息(纠错级 L=0b01),含 BCH 与固定 XOR 掩码。"""
    data = (0b01 << 3) | mask
    remainder = data
    for _ in range(10):
        remainder = (remainder << 1) ^ (((remainder >> 9) & 1) * 0x537)
    return ((data << 10) | remainder) ^ 0x5412


# ---- 矩阵 ----

def build_matrix(text: str) -> list[list[int]]:
    """返回 0/1 矩阵(1=深色)。"""
    payload = text.encode("utf-8")
    version = _choose_version(len(payload))
    total, ecc = _VERSIONS[version]
    data = _data_codewords(payload, version)
    codewords = data + _rs_ecc(data, ecc)
    size = 21 + 4 * (version - 1)

    matrix = [[0] * size for _ in range(size)]
    is_function = [[False] * size for _ in range(size)]

    def set_module(row: int, col: int, dark: bool) -> None:
        matrix[row][col] = 1 if dark else 0
        is_function[row][col] = True

    def draw_finder(row0: int, col0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                row, col = row0 + dr, col0 + dc
                if 0 <= row < size and 0 <= col < size:
                    distance = max(abs(dr - 3), abs(dc - 3))
                    set_module(row, col, distance <= 1 or distance == 3)

    draw_finder(0, 0)
    draw_finder(0, size - 7)
    draw_finder(size - 7, 0)

    for i in range(8, size - 8):  # 时序线
        if not is_function[6][i]:
            set_module(6, i, i % 2 == 0)
        if not is_function[i][6]:
            set_module(i, 6, i % 2 == 0)

    if version >= 2:  # v2–5 仅一个对位图形
        center = size - 7
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                set_module(center + dr, center + dc, max(abs(dr), abs(dc)) != 1)

    mask = 0
    bits_value = format_bits(mask)
    bit = lambda i: (bits_value >> i) & 1  # noqa: E731

    for i in range(6):                       # 格式信息第一份
        set_module(i, 8, bit(i))
    set_module(7, 8, bit(6))
    set_module(8, 8, bit(7))
    set_module(8, 7, bit(8))
    for i in range(9, 15):
        set_module(8, 14 - i, bit(i))
    for i in range(8):                       # 第二份
        set_module(8, size - 1 - i, bit(i))
    for i in range(8, 15):
        set_module(size - 15 + i, 8, bit(i))
    set_module(size - 8, 8, True)            # 固定深色模块

    data_bits = [(codeword >> (7 - j)) & 1 for codeword in codewords for j in range(8)]
    index = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right -= 1
        for vertical in range(size):
            for horizontal in range(2):
                col = right - horizontal
                upward = ((right + 1) & 2) == 0
                row = (size - 1 - vertical) if upward else vertical
                if not is_function[row][col]:
                    module = data_bits[index] if index < len(data_bits) else 0
                    if (row + col) % 2 == 0:  # 掩码 0
                        module ^= 1
                    matrix[row][col] = module
                    index += 1
        right -= 2
    return matrix


def qr_svg(text: str, *, quiet_zone: int = 4) -> str:
    """把文本编码为自包含 SVG(深浅色主题下均可扫:白底黑码)。"""
    matrix = build_matrix(text)
    size = len(matrix)
    dimension = size + 2 * quiet_zone
    cells = "".join(
        f"M{col + quiet_zone} {row + quiet_zone}h1v1h-1z"
        for row in range(size) for col in range(size) if matrix[row][col]
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dimension} {dimension}" '
            f'shape-rendering="crispEdges" role="img" aria-label="QR code">'
            f'<rect width="{dimension}" height="{dimension}" fill="#ffffff"/>'
            f'<path d="{cells}" fill="#000000"/></svg>')
