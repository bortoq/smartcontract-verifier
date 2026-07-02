"""snapshot.py — save/load состояния пространства для тестовых фикстур.

Формат:
  [tick_counter: uint64][space_data: ...]
"""

from __future__ import annotations
import struct

__all__ = [
    "save_snapshot",
    "load_snapshot",
    "make_fixture",
    "write_bits",
]


def save_snapshot(
    tick_counter: int,
    space_data: bytes,
    path: str,
    *,
    space_bytes: int | None = None,
) -> None:
    """Сохранить снапшот состояния пространства в файл.

    Args:
        tick_counter: номер текущего tick (uint64).
        space_data: дамп пространства (байты).
        path: путь к файлу.
        space_bytes: ожидаемый размер (если задан — проверяется).
    """
    if space_bytes is not None and len(space_data) != space_bytes:
        raise ValueError(
            f"space_data size {len(space_data)} != expected {space_bytes}"
        )

    header = struct.pack("<Q", tick_counter)
    with open(path, "wb") as f:
        f.write(header)
        f.write(space_data)


def load_snapshot(path: str) -> tuple[int, bytes]:
    """Загрузить снапшот состояния пространства из файла.

    Returns:
        (tick_counter, space_data)
    """
    with open(path, "rb") as f:
        header = f.read(8)
        tick_counter = struct.unpack("<Q", header)[0]
        space_data = f.read()
    return tick_counter, space_data


def write_bits(
    data: bytearray,
    bit_offset: int,
    width: int,
    value: int,
) -> None:
    """Записать width бит value в data, MSB-first.

    MSB-first: бит value (width-1) → позиция bit_offset.
    Использует прямой побитовый доступ — корректен для fixture generation.
    """
    if width == 0:
        return

    for i in range(width):
        bit_val = (value >> (width - 1 - i)) & 1
        pos = bit_offset + i
        byte_idx = pos >> 3
        if byte_idx >= len(data):
            break
        bit_mask = 1 << (7 - (pos & 7))
        if bit_val:
            data[byte_idx] |= bit_mask
        else:
            data[byte_idx] &= ~bit_mask


def make_fixture(
    instrs: list[tuple[int, int, int]],
    slot_size: int,
    space_bytes: int,
) -> bytes:
    """Создать бинарный дамп пространства из списка инструкций.

    Args:
        instrs: список (n, dst, src) для каждого слота.
        slot_size: размер слота в битах.
        space_bytes: общий размер пространства в байтах.

    Returns:
        bytes: дамп пространства.
    """
    data = bytearray(space_bytes)
    field_w = slot_size // 3

    for slot_idx, (n, dst, src) in enumerate(instrs):
        bit_offset = slot_idx * slot_size
        if bit_offset + slot_size > space_bytes * 8:
            continue
        write_bits(data, bit_offset + 0 * field_w, field_w, n)
        write_bits(data, bit_offset + 1 * field_w, field_w, dst)
        write_bits(data, bit_offset + 2 * field_w, field_w, src)

    return bytes(data)
