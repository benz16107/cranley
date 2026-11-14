"""Kua number and the Eight Mansions (Ba Zhai) directions, from the standard formula. Pure, no plan needed.

Formula, with Y the birth year in the Chinese solar calendar (it starts about 4 February, so a January birth uses
the year before):  men  Kua = (11 - Y) mod 9,  women  Kua = (Y + 4) mod 9,  a 0 counts as 9. Kua 5 does not take a
direction, so it becomes 2 for men and 8 for women. This is the common "add the digits" method written for any
year: adding the digits of the year leaves the same remainder mod 9.
"""
from __future__ import annotations

DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
WORD = {"N": "north", "NE": "north-east", "E": "east", "SE": "south-east", "S": "south", "SW": "south-west",
        "W": "west", "NW": "north-west"}

GOOD = [("success", "Sheng Qi"), ("health", "Tian Yi"), ("relationships", "Yan Nian"), ("personal growth", "Fu Wei")]
BAD = [("mishaps", "Huo Hai"), ("five ghosts", "Wu Gui"), ("six killings", "Liu Sha"), ("total loss", "Jue Ming")]
# Kua -> (four favourable, best first; four unfavourable, mildest first), the standard Eight Mansions table
TABLE = {
    1: (["SE", "E", "S", "N"], ["W", "NE", "NW", "SW"]),
    2: (["NE", "W", "NW", "SW"], ["E", "SE", "S", "N"]),
    3: (["S", "N", "SE", "E"], ["SW", "NW", "NE", "W"]),
    4: (["N", "S", "E", "SE"], ["NW", "SW", "W", "NE"]),
    6: (["W", "NE", "SW", "NW"], ["SE", "E", "N", "S"]),
    7: (["NW", "SW", "NE", "W"], ["N", "S", "SE", "E"]),
    8: (["SW", "NW", "W", "NE"], ["S", "N", "E", "SE"]),
    9: (["E", "SE", "N", "S"], ["NE", "W", "SW", "NW"]),
}
FORMULA = ("Kua = (11 - year) mod 9 for men, (year + 4) mod 9 for women, 0 counts as 9, and 5 becomes 2 for men and 8 "
           "for women; the year is the Chinese solar year, which starts about 4 February.")


def kua(year: int, gender: str) -> int:
    k = ((11 - year) if gender == "male" else (year + 4)) % 9 or 9
    return (2 if gender == "male" else 8) if k == 5 else k


def group(k: int) -> str:
    return "East" if k in (1, 3, 4, 9) else "West"


def directions(k: int) -> dict[str, tuple[bool, str, str]]:
    """Direction -> (favourable, meaning, Chinese name) for all eight directions."""
    good, bad = TABLE[k]
    return {**{d: (True, *GOOD[i]) for i, d in enumerate(good)}, **{d: (False, *BAD[i]) for i, d in enumerate(bad)}}


def compass8(az: float) -> str:
    return DIRS[int(((az + 22.5) % 360) // 45)]
