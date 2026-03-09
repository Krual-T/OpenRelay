from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


WIRE_VARINT = 0
WIRE_LEN = 2
WIRE_64BIT = 1
WIRE_32BIT = 5


@dataclass(slots=True)
class Header:
    key: str
    value: str


@dataclass(slots=True)
class Frame:
    seq_id: int = 0
    log_id: int = 0
    service: int = 0
    method: int = 0
    headers: List[Header] = field(default_factory=list)
    payload_encoding: str = ""
    payload_type: str = ""
    payload: bytes = b""
    log_id_new: str = ""



def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varint not supported")
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)



def _decode_varint(data: bytes, index: int) -> Tuple[int, int]:
    shift = 0
    value = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, index
        shift += 7
    raise ValueError("unterminated varint")



def _encode_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)



def _encode_string(field_number: int, value: str) -> bytes:
    payload = value.encode("utf-8")
    return _encode_key(field_number, WIRE_LEN) + _encode_varint(len(payload)) + payload



def _encode_bytes(field_number: int, value: bytes) -> bytes:
    return _encode_key(field_number, WIRE_LEN) + _encode_varint(len(value)) + value



def _encode_uint(field_number: int, value: int) -> bytes:
    return _encode_key(field_number, WIRE_VARINT) + _encode_varint(value)



def encode_header(header: Header) -> bytes:
    return _encode_string(1, header.key) + _encode_string(2, header.value)



def _read_length_delimited(data: bytes, index: int) -> Tuple[bytes, int]:
    length, index = _decode_varint(data, index)
    end = index + length
    if end > len(data):
        raise ValueError("invalid length-delimited field")
    return data[index:end], end



def _skip_field(data: bytes, index: int, wire_type: int) -> int:
    if wire_type == WIRE_VARINT:
        _, index = _decode_varint(data, index)
        return index
    if wire_type == WIRE_LEN:
        _, index = _read_length_delimited(data, index)
        return index
    if wire_type == WIRE_64BIT:
        return index + 8
    if wire_type == WIRE_32BIT:
        return index + 4
    raise ValueError(f"unsupported wire type: {wire_type}")



def decode_header(data: bytes) -> Header:
    index = 0
    key = ""
    value = ""
    while index < len(data):
        tag, index = _decode_varint(data, index)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 1 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            key = payload.decode("utf-8", errors="replace")
        elif field_number == 2 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            value = payload.decode("utf-8", errors="replace")
        else:
            index = _skip_field(data, index, wire_type)
    return Header(key=key, value=value)



def encode_frame(frame: Frame) -> bytes:
    out = bytearray()
    out.extend(_encode_uint(1, frame.seq_id))
    out.extend(_encode_uint(2, frame.log_id))
    out.extend(_encode_uint(3, frame.service))
    out.extend(_encode_uint(4, frame.method))
    for header in frame.headers:
        encoded = encode_header(header)
        out.extend(_encode_key(5, WIRE_LEN))
        out.extend(_encode_varint(len(encoded)))
        out.extend(encoded)
    if frame.payload_encoding:
        out.extend(_encode_string(6, frame.payload_encoding))
    if frame.payload_type:
        out.extend(_encode_string(7, frame.payload_type))
    if frame.payload:
        out.extend(_encode_bytes(8, frame.payload))
    if frame.log_id_new:
        out.extend(_encode_string(9, frame.log_id_new))
    return bytes(out)



def decode_frame(data: bytes) -> Frame:
    index = 0
    frame = Frame()
    while index < len(data):
        tag, index = _decode_varint(data, index)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 1 and wire_type == WIRE_VARINT:
            frame.seq_id, index = _decode_varint(data, index)
        elif field_number == 2 and wire_type == WIRE_VARINT:
            frame.log_id, index = _decode_varint(data, index)
        elif field_number == 3 and wire_type == WIRE_VARINT:
            frame.service, index = _decode_varint(data, index)
        elif field_number == 4 and wire_type == WIRE_VARINT:
            frame.method, index = _decode_varint(data, index)
        elif field_number == 5 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            frame.headers.append(decode_header(payload))
        elif field_number == 6 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            frame.payload_encoding = payload.decode("utf-8", errors="replace")
        elif field_number == 7 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            frame.payload_type = payload.decode("utf-8", errors="replace")
        elif field_number == 8 and wire_type == WIRE_LEN:
            frame.payload, index = _read_length_delimited(data, index)
        elif field_number == 9 and wire_type == WIRE_LEN:
            payload, index = _read_length_delimited(data, index)
            frame.log_id_new = payload.decode("utf-8", errors="replace")
        else:
            index = _skip_field(data, index, wire_type)
    return frame
