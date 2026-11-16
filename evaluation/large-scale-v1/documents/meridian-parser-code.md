# Meridian frame parser contract

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

```python
def decode_frame(blob):
    if len(blob) < 6:
        raise ValueError("short frame")
    payload_len = int.from_bytes(blob[2:4], "big")
    if len(blob) != payload_len + 6:
        raise ValueError("length mismatch")
    return blob[4:4 + payload_len]
```

A frame contains a two-byte marker, a two-byte unsigned big-endian payload length, the payload and a two-byte checksum. The shown function checks length only; it does not verify the marker or checksum.

This excerpt is documentation. Benchmark respondents must explain it without executing generated or supplied code.

