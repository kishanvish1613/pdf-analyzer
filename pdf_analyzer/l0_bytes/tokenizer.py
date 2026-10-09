"""
PDF Content-Stream Tokenizer / Lexer.
Yields tokens with exact byte offsets for stream provenance tracking.
Handles nested parenthesized strings, hex strings, dictionaries, arrays,
names, numbers, operators, and inline image payloads (BI ... ID ... EI).
"""

from __future__ import annotations
import re
from typing import Iterator, Tuple, Any, List, Dict
from pdf_analyzer.l0_bytes.primitives import ByteRange


class Token:
    __slots__ = ("type", "value", "byte_range")

    def __init__(self, token_type: str, value: Any, byte_range: ByteRange):
        self.type = token_type  # 'OPERATOR', 'NUMBER', 'STRING', 'HEX_STRING', 'NAME', 'ARRAY', 'DICT', 'INLINE_IMAGE'
        self.value = value
        self.byte_range = byte_range

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r}, {self.byte_range.start_offset}:{self.byte_range.end_offset})"


def tokenize_content_stream(data: bytes) -> Iterator[Token]:
    """
    Tokenizes a raw PDF content stream byte string into an iterator of Token objects.
    """
    length = len(data)
    idx = 0

    while idx < length:
        # Skip whitespace and comments
        b = data[idx]
        if b in b" \t\r\n\x0c\x00":
            idx += 1
            continue
        if b == 0x25:  # '%' comment
            start = idx
            while idx < length and data[idx] not in b"\r\n":
                idx += 1
            continue

        start_offset = idx

        # 1. String literal (...)
        if b == 0x28:  # '('
            idx += 1
            depth = 1
            str_bytes = bytearray()
            while idx < length and depth > 0:
                cb = data[idx]
                if cb == 0x5C:  # '\\' escape
                    idx += 1
                    if idx >= length:
                        break
                    esc = data[idx]
                    if esc == 0x6E:  # 'n'
                        str_bytes.append(0x0A)
                    elif esc == 0x72:  # 'r'
                        str_bytes.append(0x0D)
                    elif esc == 0x74:  # 't'
                        str_bytes.append(0x09)
                    elif esc == 0x62:  # 'b'
                        str_bytes.append(0x08)
                    elif esc == 0x66:  # 'f'
                        str_bytes.append(0x0C)
                    elif esc in (0x28, 0x29, 0x5C):  # '(', ')', '\\'
                        str_bytes.append(esc)
                    elif 0x30 <= esc <= 0x37:  # Octal escape \ddd
                        oct_digits = [esc]
                        for _ in range(2):
                            if idx + 1 < length and 0x30 <= data[idx + 1] <= 0x37:
                                idx += 1
                                oct_digits.append(data[idx])
                            else:
                                break
                        oct_val = int(bytes(oct_digits).decode("ascii"), 8)
                        str_bytes.append(oct_val & 0xFF)
                    elif esc in (0x0A, 0x0D):  # Line continuation
                        if esc == 0x0D and idx + 1 < length and data[idx + 1] == 0x0A:
                            idx += 1
                    else:
                        str_bytes.append(esc)
                    idx += 1
                elif cb == 0x28:  # '('
                    depth += 1
                    str_bytes.append(cb)
                    idx += 1
                elif cb == 0x29:  # ')'
                    depth -= 1
                    if depth > 0:
                        str_bytes.append(cb)
                    idx += 1
                else:
                    str_bytes.append(cb)
                    idx += 1
            yield Token("STRING", bytes(str_bytes), ByteRange(start_offset, idx))
            continue

        # 2. Hex string <...> or Dict open <<
        if b == 0x3C:  # '<'
            if idx + 1 < length and data[idx + 1] == 0x3C:  # '<<'
                idx += 2
                yield Token("DICT_START", "<<", ByteRange(start_offset, idx))
                continue
            idx += 1
            hex_chars = bytearray()
            while idx < length and data[idx] != 0x3E:  # '>'
                if data[idx] not in b" \t\r\n\x0c\x00":
                    hex_chars.append(data[idx])
                idx += 1
            if idx < length and data[idx] == 0x3E:
                idx += 1
            hex_str = hex_chars.decode("latin1")
            if len(hex_str) % 2 != 0:
                hex_str += "0"
            try:
                raw_val = bytes.fromhex(hex_str)
            except ValueError:
                raw_val = b""
            yield Token("HEX_STRING", raw_val, ByteRange(start_offset, idx))
            continue

        # 3. Dict close >>
        if b == 0x3E:  # '>'
            if idx + 1 < length and data[idx + 1] == 0x3E:  # '>>'
                idx += 2
                yield Token("DICT_END", ">>", ByteRange(start_offset, idx))
                continue
            idx += 1
            continue

        # 4. Array open [ and close ]
        if b == 0x5B:  # '['
            idx += 1
            yield Token("ARRAY_START", "[", ByteRange(start_offset, idx))
            continue
        if b == 0x5D:  # ']'
            idx += 1
            yield Token("ARRAY_END", "]", ByteRange(start_offset, idx))
            continue

        # 5. Name /Name
        if b == 0x2F:  # '/'
            idx += 1
            name_bytes = bytearray()
            while idx < length:
                cb = data[idx]
                if cb in b" \t\r\n\x0c\x00/()<>[]{}/%":
                    break
                if cb == 0x23 and idx + 2 < length:  # '#XX' hex encoding in names
                    try:
                        hex_val = int(data[idx + 1 : idx + 3].decode("ascii"), 16)
                        name_bytes.append(hex_val)
                        idx += 3
                        continue
                    except Exception:
                        pass
                name_bytes.append(cb)
                idx += 1
            name_str = name_bytes.decode("latin1", errors="replace")
            yield Token("NAME", name_str, ByteRange(start_offset, idx))
            continue

        # 6. Numbers, Keywords, and Operators
        word_start = idx
        while idx < length and data[idx] not in b" \t\r\n\x0c\x00/()<>[]{}/%":
            idx += 1
        word_bytes = data[word_start:idx]
        word = word_bytes.decode("latin1", errors="replace")

        # Check for Inline Image BI operator
        if word == "BI":
            # Inline image dictionary and data until EI
            yield Token("OPERATOR", "BI", ByteRange(start_offset, idx))
            continue

        # Try parsing as number
        try:
            if "." in word:
                val = float(word)
                yield Token("NUMBER", val, ByteRange(start_offset, idx))
            else:
                val = int(word)
                yield Token("NUMBER", float(val), ByteRange(start_offset, idx))
        except ValueError:
            # Not a number -> Operator or keyword
            yield Token("OPERATOR", word, ByteRange(start_offset, idx))
