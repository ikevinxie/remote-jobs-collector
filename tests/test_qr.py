import pytest

from remote_jobs.qr import build_matrix, format_bits, qr_svg


def test_format_bits_known_vectors():
    """已知向量:纠错级 L、掩码 0 的 15 位格式信息(ISO 18004 / thonky 表)。"""
    assert format_bits(0) == 0b111011111000100
    # 自洽校验:去掉固定 XOR 后,高 5 位应还原出数据位(L=01, mask=000)
    assert (format_bits(0) ^ 0b101010000010010) >> 10 == 0b01000


def test_version_selection_and_size():
    assert len(build_matrix("hi")) == 21                       # v1
    assert len(build_matrix("x" * 40)) == 29                   # v3
    assert len(build_matrix("x" * 100)) == 37                  # v5
    with pytest.raises(ValueError):
        build_matrix("x" * 107)                                # 超出 v5-L 容量


def test_structural_invariants():
    matrix = build_matrix("https://ikevinxie.github.io/remote-jobs-board/")
    size = len(matrix)
    # 三角定位图形的角落是深色
    for row, col in ((0, 0), (0, size - 1), (size - 1, 0)):
        assert matrix[row][col] == 1
    # 定位图形中心 3×3 深色
    assert all(matrix[3 + dr][3 + dc] == 1 for dr in (-1, 0, 1) for dc in (-1, 0, 1))
    # 时序线交替
    assert [matrix[6][i] for i in range(8, 13)] == [1, 0, 1, 0, 1]
    # 固定深色模块
    assert matrix[size - 8][8] == 1


def test_svg_output():
    svg = qr_svg("https://example.com/")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'fill="#ffffff"' in svg and 'fill="#000000"' in svg, "白底黑码保证可扫"
    assert qr_svg("https://example.com/") == svg, "输出确定性"
    assert qr_svg("https://other.example/") != svg


def test_matrix_matches_reference_library():
    """存在 qrcode 包时与之逐位对拍(开发期验证,不是运行时依赖)。"""
    qrcode = pytest.importorskip("qrcode")
    from qrcode.util import MODE_8BIT_BYTE, QRData

    for text in ("hi", "https://ikevinxie.github.io/remote-jobs-board/", "x" * 90):
        mine = build_matrix(text)
        reference = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,
                                  border=0, mask_pattern=0)
        reference.add_data(QRData(text.encode(), mode=MODE_8BIT_BYTE))
        reference.make(fit=True)
        theirs = [[1 if cell else 0 for cell in row] for row in reference.modules]
        assert mine == theirs, f"与参考实现不一致: {text!r}"
