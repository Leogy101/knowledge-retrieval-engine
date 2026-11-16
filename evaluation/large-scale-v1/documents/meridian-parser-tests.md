# Meridian frame parser examples

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

The byte sequence 4d 46 00 03 61 62 63 00 00 has total length nine and declares a three-byte payload. decode_frame returns the bytes 61 62 63 for this example.

Removing the final byte leaves total length eight while the declared payload remains three; the function raises "length mismatch".

A successful length check is not a statement that the checksum is correct.

