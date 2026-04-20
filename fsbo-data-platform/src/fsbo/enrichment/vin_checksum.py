"""VIN check-digit validator.

Per SAE J1853 / NHTSA. The 9th character of a VIN is a check digit
computed from the other 16 characters. Rejects the standard illegal
letters (I, O, Q) and verifies length.

Reference: johndcook.com/blog/2022/09/04/computing-vin-checksums
"""

_VIN_MAP = {
    **{str(i): i for i in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def valid_vin(vin: str | None) -> bool:
    if not vin:
        return False
    vin = vin.upper().strip()
    if len(vin) != 17:
        return False
    if any(c in vin for c in "IOQ"):
        return False
    if not all(c in _VIN_MAP for c in vin):
        return False
    total = sum(_VIN_MAP[c] * _WEIGHTS[i] for i, c in enumerate(vin))
    check = total % 11
    expected = "X" if check == 10 else str(check)
    return vin[8] == expected
