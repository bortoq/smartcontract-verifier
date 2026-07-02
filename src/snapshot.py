"""snapshot.py — save/load состояния пространства для тестовых фикстур.

Адаптация DDAS ddas_snapshot_save/load (snapshot.c).

Формат:
  [tick_counter: uint64][space_data: space_bytes]

Где space_data — raw дамп памяти пространства (бит-адресуемый массив).
"""

from __future__ import annotations
import struct
from .config import Config


def save_snapshot(tick_counter: int, space_data: bytes, path: str) -> None:
    """Сохранить снапшот состояния пространства в файл.

    Args:
        tick_counter: номер текущего tick (uint64).
        space_data: дамп пространства (space_bytes байт).
        path: путь к файлу.
    """
    if len(space_data) != _get_space_bytes_from_config():
        raise ValueError(
            f"space_data size {len(space_data)} != config space_bytes"
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


def _get_space_bytes_from_config() -> int:
    """Получить размер пространства из дефолтного конфига."""
    # Используем Config без файла (дефолтные значения)
    from .config import Config
    return Config().space_bytes


def make_fixture(
    instrs: list[tuple[int, int, int]],
    slot_size: int,
    space_bytes: int,
    tick: int = 0,
) -> bytes:
    """Создать бинарный дамп пространства из списка инструкций.

    Args:
        instrs: список (n, dst, src) для каждого слота.
        slot_size: размер слота в битах.
        space_bytes: общий размер пространства в байтах.
        tick: номер tick.

    Returns:
        bytes: дамп пространства.
    """
    data = bytearray(space_bytes)

    for slot_idx, (n, dst, src) in enumerate(instrs):
        bit_offset = slot_idx * slot_size
        byte_offset = bit_offset // 8

        # Пропустить, если выходит за границы
        if byte_offset + (slot_size // 8) + 1 > space_bytes:
            continue

        # Записать n (slot_size // 3 бит на каждое поле — упрощение)
        # В реальности используем ImageReader. Но для тестов достаточно заполнить.
        _write_bits(data, byte_offset, bit_offset % 8, slot_size // 3, n)
        _write_bits(data, byte_offset, bit_offset % 8 + slot_size // 3,
                     slot_size // 3, dst)
        _write_bits(data, byte_offset, bit_offset % 8 + 2 * (slot_size // 3),
                     slot_size // 3, src)

    return bytes(data)


def _write_bits(data: bytearray, base_byte: int, bit_off: int, width: int,
                value: int) -> None:
    """Записать width бит value в data, MSB-first."""
    for i in range(width - 1, -1, -1):
        # Какой бит value пишем
        bit_val = (value >> i) & 1
        # Позиция в data
        pos = (base_byte * 8) + bit_off + (width - 1 - i)
        byte_idx = pos >> 3
        bit_idx = 7 - (pos & 7)
        if byte_idx < len(data):
            data[byte_idx] = (data[byte_idx] & ~(1 << bit_idx)) | (bit_val << bit_idx)
