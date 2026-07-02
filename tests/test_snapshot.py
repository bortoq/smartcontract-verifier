#!/usr/bin/env python3
"""test_snapshot.py — тесты snapshot.py (save/load/fixture)."""

import sys, os, tempfile, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.snapshot import save_snapshot, load_snapshot, make_fixture, write_bits


class TestSnapshot:
    def test_save_load_roundtrip(self):
        data = b"\xAA\xBB\xCC" * 100
        tick = 42
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            save_snapshot(tick, data, path)
            loaded_tick, loaded_data = load_snapshot(path)
            assert loaded_tick == tick
            assert loaded_data == data
        finally:
            os.unlink(path)

    def test_save_with_validation_passes(self):
        data = b"\x00" * 256
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            save_snapshot(0, data, path, space_bytes=256)
            tick, loaded = load_snapshot(path)
            assert loaded == data
        finally:
            os.unlink(path)

    def test_save_with_validation_fails(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            with pytest.raises(ValueError, match="space_data size"):
                save_snapshot(0, b"\x00" * 100, path, space_bytes=256)
        finally:
            os.unlink(path)

    def test_load_empty(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(struct.pack("<Q", 999))
            path = f.name
        try:
            tick, data = load_snapshot(path)
            assert tick == 999
            assert data == b""
        finally:
            os.unlink(path)

    def test_make_fixture_single_instruction(self):
        fixture = make_fixture([(8, 100, 0)], slot_size=72, space_bytes=512)
        assert len(fixture) == 512
        assert fixture[2] == 0x08  # n=8, 24-bit MSB → low byte = 0x08

    def test_make_fixture_multiple_instructions(self):
        instrs = [(8, 100, 0), (16, 200, 50)]
        fixture = make_fixture(instrs, slot_size=72, space_bytes=1024)
        assert len(fixture) == 1024


class TestWriteBits:
    """MSB-first: bit 0 = 0x80 (MSB of byte), bit 7 = 0x01 (LSB of byte)."""

    def test_write_full_byte(self):
        buf = bytearray(4)
        write_bits(buf, 0, 8, 0xAB)
        assert buf[0] == 0xAB

    def test_write_partial_byte_mid(self):
        """4 bits (0x0F=1111) at offset 4 → byte lower nibble = 1111 = 0x0F."""
        buf = bytearray(b"\x00\x00")
        write_bits(buf, 4, 4, 0x0F)
        assert buf[0] == 0x0F

    def test_write_partial_byte_offset(self):
        """4 bits (0x0A=1010) at offset 4 → byte lower nibble = 1010 = 0x0A."""
        buf = bytearray(b"\x00\x00")
        write_bits(buf, 4, 4, 0x0A)
        assert buf[0] == 0x0A

    def test_write_cross_byte(self):
        """8 bits (0xAB) at offset 4.
        0xAB MSB-first bits: 1,0,1,0,1,0,1,1
        byte0 bits 4-7: 1010 → 0x0A
        byte1 bits 0-3: 1011 → 0xB0 (upper nibble)"""
        buf = bytearray(b"\x00\x00")
        write_bits(buf, 4, 8, 0xAB)
        assert buf[0] == 0x0A, f"byte0=0x{buf[0]:02X}"
        assert buf[1] == 0xB0, f"byte1=0x{buf[1]:02X}"

    def test_write_zero_width(self):
        buf = bytearray(b"\xFF")
        write_bits(buf, 0, 0, 0x00)
        assert buf[0] == 0xFF

    def test_write_multiple_calls(self):
        buf = bytearray(8)
        write_bits(buf, 0, 8, 0x12)
        write_bits(buf, 8, 8, 0x34)
        assert buf[0] == 0x12
        assert buf[1] == 0x34

    def test_write_24bit_value(self):
        buf = bytearray(4)
        write_bits(buf, 0, 24, 0x123456)
        assert buf[0] == 0x12
        assert buf[1] == 0x34
        assert buf[2] == 0x56

    def test_write_and_read_roundtrip(self):
        """write_bits → читаем через int.from_bytes."""
        buf = bytearray(8)
        write_bits(buf, 0, 24, 0xAABBCC)
        val = int.from_bytes(buf[:3], 'big')
        assert val == 0xAABBCC
