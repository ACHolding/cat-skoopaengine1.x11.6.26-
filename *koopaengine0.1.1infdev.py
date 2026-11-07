#!/usr/bin/env python3
# cat's mario forever worker 0.1
# Super Mario Worker-style level editor GUI • Mario Forever physics
# files = off  (all art + audio generated at runtime, zero external assets)
# 640×480 • 60 fps • single-file Python + pygame
# A.C Holdings / Team Flames
#
#   python program.py                 -> title screen
#   python program.py level.kenigne   -> open level in the editor
#   python program.py --play level    -> play a level directly
#   python program.py --demo          -> play the built-in demo level

import os
import sys
import math
import json
import zlib
import array
import struct
import random

try:
    import pygame
except ImportError:
    sys.stderr.write("Koopa Engine needs pygame: pip install pygame-ce\n")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
APP_NAME = "Koopa Engine"
APP_VERSION = "4K"
APP_TITLE = "Koopa Engine 4K"
WIN_W, WIN_H = 640, 480
TS = 32                      # tile size (Mario Forever / Mario Worker 32px grid)
FPS = 60
LEVEL_EXT = ".kenigne"
KEN_MAGIC = b"KENG"          # koopa worker / Mario Worker native container
KEN_VERSION = 2
FILES_OFF = True

MIN_W, MAX_W = 20, 1000      # level width in tiles
MIN_H, MAX_H = 15, 60        # level height in tiles

THEMES = ["overworld", "underground", "castle", "underwater", "night", "snow"]
THEME_LABELS = {
    "overworld": "Overworld", "underground": "Underground", "castle": "Castle",
    "underwater": "Underwater", "night": "Night", "snow": "Snow",
}
MUSIC_LABELS = ["Auto (theme)", "Overworld", "Underground", "Castle",
                "Underwater", "Athletic", "None"]

# ---------------------------------------------------------------------------
# MARIO FOREVER PHYSICS (px / frame @ 60 fps, 32px tiles)
# ---------------------------------------------------------------------------
PHYS = dict(
    walk_acc=0.12, run_acc=0.18, release_dec=0.14, skid_dec=0.32, air_acc=0.12,
    walk_max=3.2, run_max=5.6,
    jump_v=10.0, jump_run_bonus=0.22,
    grav_hold=0.38, grav=1.05, max_fall=10.0,
    stomp_bounce=7.5, stomp_bounce_hold=10.0,
    swim_grav=0.12, swim_max_fall=2.4, swim_kick=3.8, swim_max=2.2,
    npc_grav=0.5, npc_max_fall=8.0,
)

# Selectable gameplay rulesets. These are original approximations, not ROM emulation.
GAME_STYLES = ("SMB1", "SMB3", "SMW")
STYLE_PHYS = {
    "SMB1": dict(walk_acc=.10, run_acc=.15, release_dec=.11, skid_dec=.28,
                 air_acc=.075, walk_max=2.8, run_max=5.0, jump_v=9.3,
                 jump_run_bonus=.19, grav_hold=.36, grav=.95, max_fall=9.0),
    "SMB3": dict(walk_acc=.13, run_acc=.19, release_dec=.13, skid_dec=.34,
                 air_acc=.11, walk_max=3.2, run_max=5.6, jump_v=10.4,
                 jump_run_bonus=.22, grav_hold=.39, grav=1.0, max_fall=10.0),
    "SMW": dict(walk_acc=.15, run_acc=.21, release_dec=.12, skid_dec=.32,
                air_acc=.13, walk_max=3.5, run_max=5.8, jump_v=11.0,
                jump_run_bonus=.23, grav_hold=.36, grav=.93, max_fall=10.5),
}

def physics_for(style):
    return dict(PHYS, **STYLE_PHYS.get(style, STYLE_PHYS["SMB1"]))

# Automatically selected visual identity for each gameplay ruleset.
ACTIVE_STYLE = "SMB1"
STYLE_COLORS = {
    "SMB1": dict(sky=(92, 148, 252), ground=(200, 76, 12), highlight=(252, 188, 176),
                 brick=(200, 76, 12), question=(252, 152, 56), pipe=(0, 168, 0)),
    "SMB3": dict(sky=(104, 176, 248), ground=(184, 112, 48), highlight=(248, 208, 128),
                 brick=(200, 112, 56), question=(248, 184, 48), pipe=(40, 176, 56)),
    "SMW": dict(sky=(104, 184, 248), ground=(184, 128, 80), highlight=(248, 216, 160),
                brick=(208, 144, 88), question=(248, 208, 64), pipe=(24, 168, 80)),
}

def activate_style(style):
    global ACTIVE_STYLE
    ACTIVE_STYLE = style if style in GAME_STYLES else "SMB1"

def visual_palette(theme):
    base = dict(THEME_PAL[theme])
    style = STYLE_COLORS[ACTIVE_STYLE]
    if theme == "overworld":
        base.update(bg=style['sky'], B=style['ground'], H=style['highlight'])
    elif theme in ("night", "snow"):
        base.update(B=style['ground'], H=style['highlight'])
    return base

SMALL, BIG, FIRE = 0, 1, 2
P_W, P_H_SMALL, P_H_BIG = 22, 30, 58

# ---------------------------------------------------------------------------
# NES-ish master palette
# ---------------------------------------------------------------------------
C = dict(
    black=(0, 0, 0), white=(252, 252, 252), red=(216, 40, 0), dred=(136, 20, 0),
    orange=(252, 152, 56), brown=(200, 76, 12), dbrown=(124, 52, 0),
    tan=(252, 188, 176), skin=(252, 188, 140), yellow=(252, 216, 40),
    green=(0, 168, 0), lgreen=(128, 208, 16), dgreen=(0, 96, 0),
    blue=(0, 88, 248), sky=(92, 148, 252), gray=(188, 188, 188), dgray=(116, 116, 116),
    teal=(0, 128, 136), lteal=(156, 252, 240), pink=(252, 160, 180),
)

THEME_PAL = {
    "overworld":   dict(bg=(92, 148, 252),  B=(200, 76, 12),  H=(252, 188, 176), K=(0, 0, 0)),
    "underground": dict(bg=(0, 0, 0),       B=(0, 128, 136),  H=(156, 252, 240), K=(0, 40, 48)),
    "castle":      dict(bg=(0, 0, 0),       B=(150, 150, 150), H=(252, 252, 252), K=(60, 60, 60)),
    "underwater":  dict(bg=(36, 72, 200),   B=(0, 136, 104),  H=(160, 240, 200), K=(0, 48, 32)),
    "night":       dict(bg=(8, 8, 32),      B=(200, 76, 12),  H=(252, 188, 176), K=(0, 0, 0)),
    "snow":        dict(bg=(164, 200, 252), B=(150, 176, 228), H=(252, 252, 252), K=(60, 80, 140)),
}

# ---------------------------------------------------------------------------
# 5×7 BITMAP FONT (Mario Forever HUD style, FILES=OFF)
# ---------------------------------------------------------------------------
_GLYPHS = {
    'A': "01110 10001 10001 11111 10001 10001 10001", 'B': "11110 10001 10001 11110 10001 10001 11110",
    'C': "01110 10001 10000 10000 10000 10001 01110", 'D': "11110 10001 10001 10001 10001 10001 11110",
    'E': "11111 10000 10000 11110 10000 10000 11111", 'F': "11111 10000 10000 11110 10000 10000 10000",
    'G': "01110 10001 10000 10111 10001 10001 01111", 'H': "10001 10001 10001 11111 10001 10001 10001",
    'I': "01110 00100 00100 00100 00100 00100 01110", 'J': "00111 00010 00010 00010 00010 10010 01100",
    'K': "10001 10010 10100 11000 10100 10010 10001", 'L': "10000 10000 10000 10000 10000 10000 11111",
    'M': "10001 11011 10101 10101 10001 10001 10001", 'N': "10001 11001 10101 10011 10001 10001 10001",
    'O': "01110 10001 10001 10001 10001 10001 01110", 'P': "11110 10001 10001 11110 10000 10000 10000",
    'Q': "01110 10001 10001 10001 10101 10010 01101", 'R': "11110 10001 10001 11110 10100 10010 10001",
    'S': "01111 10000 10000 01110 00001 00001 11110", 'T': "11111 00100 00100 00100 00100 00100 00100",
    'U': "10001 10001 10001 10001 10001 10001 01110", 'V': "10001 10001 10001 10001 10001 01010 00100",
    'W': "10001 10001 10001 10101 10101 10101 01010", 'X': "10001 10001 01010 00100 01010 10001 10001",
    'Y': "10001 10001 01010 00100 00100 00100 00100", 'Z': "11111 00001 00010 00100 01000 10000 11111",
    '0': "01110 10001 10011 10101 11001 10001 01110", '1': "00100 01100 00100 00100 00100 00100 01110",
    '2': "01110 10001 00001 00010 00100 01000 11111", '3': "11111 00010 00100 00010 00001 10001 01110",
    '4': "00010 00110 01010 10010 11111 00010 00010", '5': "11111 10000 11110 00001 00001 10001 01110",
    '6': "00110 01000 10000 11110 10001 10001 01110", '7': "11111 00001 00010 00100 01000 01000 01000",
    '8': "01110 10001 10001 01110 10001 10001 01110", '9': "01110 10001 10001 01111 00001 00010 01100",
    '-': "00000 00000 00000 11111 00000 00000 00000", '.': "00000 00000 00000 00000 00000 01100 01100",
    ':': "00000 01100 01100 00000 01100 01100 00000", '!': "00100 00100 00100 00100 00100 00000 00100",
    '?': "01110 10001 00001 00010 00100 00000 00100", '/': "00001 00010 00010 00100 01000 01000 10000",
    ',': "00000 00000 00000 00000 01100 00100 01000", "'": "00100 00100 01000 00000 00000 00000 00000",
    '(': "00010 00100 01000 01000 01000 00100 00010", ')': "01000 00100 00010 00010 00010 00100 01000",
    '+': "00000 00100 00100 11111 00100 00100 00000", '=': "00000 00000 11111 00000 11111 00000 00000",
    '*': "00000 00000 10001 01010 00100 01010 10001", '>': "01000 00100 00010 00001 00010 00100 01000",
    '<': "00010 00100 01000 10000 01000 00100 00010", '_': "00000 00000 00000 00000 00000 00000 11111",
    '#': "01010 11111 01010 01010 01010 11111 01010", ' ': "00000 00000 00000 00000 00000 00000 00000",
}
_font_cache = {}


def _glyph(ch, scale, color):
    key = (ch, scale, color)
    s = _font_cache.get(key)
    if s is None:
        rows = _GLYPHS.get(ch, _GLYPHS['?']).split()
        s = pygame.Surface((5 * scale, 7 * scale), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, bit in enumerate(row):
                if bit == '1':
                    s.fill(color, (x * scale, y * scale, scale, scale))
        _font_cache[key] = s
    return s


def btext(surf, text, x, y, scale=2, color=(252, 252, 252), shadow=True, center=False):
    """Draw text with the built-in pixel font. Returns width in px."""
    text = str(text).upper()
    adv = 6 * scale
    w = len(text) * adv - scale
    if center:
        x -= w // 2
    for i, ch in enumerate(text):
        if shadow:
            surf.blit(_glyph(ch, scale, (0, 0, 0)), (x + i * adv + scale // 2 + 1, y + scale // 2 + 1))
        surf.blit(_glyph(ch, scale, color), (x + i * adv, y))
    return w


# ---------------------------------------------------------------------------
# PIXEL ART (16×N char grids, rendered 2× → 32px)
# ---------------------------------------------------------------------------
MARIO_PAL = {'R': (216, 40, 0), 'B': (0, 88, 248), 'K': (92, 48, 0), 'S': (252, 188, 140),
             'D': (124, 52, 0), 'Y': (252, 216, 40), 'W': (252, 252, 252)}
FIRE_PAL = dict(MARIO_PAL, R=(252, 252, 252), B=(216, 40, 0))

M_S_STAND = [
    "....RRRRR.......", "...RRRRRRRRR....", "...KKKSSKS......", "..KSKSSSKSSS....",
    "..KSKKSSSKSSS...", "..KKSSSSKKKK....", "....SSSSSSS.....", "...RRBRRR.......",
    "..RRRBRRBRRR....", ".RRRRBBBBRRRR...", ".SSRBYBBYBRSS...", ".SSSBBBBBBSSS...",
    ".SSBBBBBBBBSS...", "...BBB..BBB.....", "..DDD....DDD....", ".DDDD....DDDD...",
]
M_S_WALK1 = [
    "....RRRRR.......", "...RRRRRRRRR....", "...KKKSSKS......", "..KSKSSSKSSS....",
    "..KSKKSSSKSSS...", "..KKSSSSKKKK....", "....SSSSSSS.....", "..RRRRBRR.......",
    ".RRRRRBBRRSS....", "SSRRRRBYBBSSS...", "SSS.BBBBBBSS....", "S..BBBBBBBB.....",
    "..BBBBBBBBB.....", ".BBBB..BBBB.....", ".DDD....DDD.....", ".DDDD....DDDD...",
]
M_S_WALK2 = [
    "....RRRRR.......", "...RRRRRRRRR....", "...KKKSSKS......", "..KSKSSSKSSS....",
    "..KSKKSSSKSSS...", "..KKSSSSKKKK....", "....SSSSSSS.....", "....RRBRR.......",
    "...RRRRBBRR.....", "...RRRBBYBB.....", "...RRRBBBBB.....", "...SSSBBBBB.....",
    "...SSBBBBB......", "....BBBDDD......", "....DDDDDD......", "....DDDD........",
]
M_S_JUMP = [
    "..........SSS...", "....RRRRR.SSS...", "...RRRRRRRRRS...", "...KKKSSKS.RR...",
    "..KSKSSSKSSRR...", "..KSKKSSSKSRR...", "..KKSSSSKKKRR...", "....SSSSSSRR....",
    "..RRRRBRRRBR....", ".RRRRRRBRRRB..DD", "SSRRRRRBBBBB..DD", "SSS.BBBYBBYBBDD.",
    "S..BBBBBBBBBBDD.", "..BBBBBBBBBBB...", ".DDBBBB.........", ".DDD............",
]
M_S_SKID = [
    ".....RRRRR......", "...RRRRRRRRR....", ".....SKSSKKK....", "....SSSKSSSKSK..",
    "...SSSKSSSKKSK..", "....KKKKSSSSKK..", ".....SSSSSSS....", "SS..RRBRRRR.....",
    "SSRRRRBBRRRR....", ".RRRRRBBBBRR....", "..BBBBYBBBBRS...", "..BBBBBBBBBSSS..",
    "DDBBBBBBBBBSS...", "DDDBBBBB..BB....", ".DD.......DDD...", "..........DDDD..",
]
M_S_DEAD = [
    "......RRRR......", "..S.RRRRRRRR.S..", ".SSSKSSKKSSKSSS.", ".SSKKSKKKKSKKSS.",
    ".SSSKSSSSSSKSSS.", "..SSKKSSSSKKSS..", "...SSSKKKKSSS...", "....SSSSSSSS....",
    "...RRBRRRRBRR...", "..RRRBBRRBBRRR..", ".SSRBYBBBBYBRSS.", ".SSSBBBBBBBBSSS.",
    "..SBBBBBBBBBBS..", "...BBBB..BBBB...", "..DDDD....DDDD..", "..DDDD....DDDD..",
]
M_S_SWIM = M_S_JUMP

_HEAD = [
    "................", ".....RRRRR......", "....RRRRRRRRR...", "....RRRRRRRRRR..",
    "....KKKSSKS.....", "...KSKSSSKSSSS..", "...KSKKSSSKSSSS.", "...KKSSSSSKKKK..",
    "......SSSSSSSS..",
]
M_B_STAND = _HEAD + [
    "....RRRBRRR.....", "...RRRRBRRRBR...", "..RRRRRBRRRBRR..", "..RRRRRBBBBBRR..",
    ".RRRRRBYBBYBRRR.", ".SSRRRBBBBBBRSS.", ".SSSSBBBBBBBBSSS", ".SSSBBBBBBBBBBSS",
    "..SSBBBBBBBBBBS.", "....BBBBBBBBBB..", "....BBBBBBBBBB..", "....BBBBBBBBBB..",
    "...BBBBB..BBBBB.", "...BBBB....BBBB.", "...BBBB....BBBB.", "...BBBB....BBBB.",
    "..DDDDD....DDDDD", ".DDDDDD....DDDDD", ".DDDDDD....DDDDD", "................",
    "................", "................", "................",
]
M_B_WALK1 = _HEAD + [
    "....RRRBRRR.....", "...RRRRBBRRR....", "..RRRRRBBBRRSS..", ".SRRRRBBYBBBSSS.",
    "SSSRRRBBBBBBSS..", "SSS.BBBBBBBBB...", "SS.BBBBBBBBBB...", "...BBBBBBBBBB...",
    "...BBBBBBBBBBB..", "..BBBBBB.BBBBB..", "..BBBBB...BBBB..", ".BBBBB.....BBBB.",
    ".BBBB......BBBB.", ".DDDD.......DDD.", "DDDDD.......DDDD", "DDDD........DDDD",
    "................", "................", "................", "................",
    "................", "................", "................",
]
M_B_WALK2 = _HEAD + [
    ".....RRBRR......", "....RRRBBRR.....", "....RRRBBBRR....", "....RRBBYBBR....",
    "....RRBBBBBB....", "....SSBBBBBB....", "....SSSBBBBB....", "....SSBBBBBB....",
    ".....BBBBBBB....", ".....BBBBBB.....", ".....BBBBBB.....", "......BBBBB.....",
    "......BBBBD.....", "......DDDDD.....", ".....DDDDDD.....", ".....DDDDD......",
    "................", "................", "................", "................",
    "................", "................", "................",
]
M_B_JUMP = [
    "...........SSS..", ".....RRRRR.SSS..", "....RRRRRRRRRSS.", "....RRRRRRRRRRR.",
    "....KKKSSKS.RRR.", "...KSKSSSKSSRRR.", "...KSKKSSSKSRRR.", "...KKSSSSSKKRR..",
    "......SSSSSSRR..", "....RRRBRRRBR...", "...RRRRBRRRBR...", "..RRRRRBBBBBR...",
    ".SRRRRBYBBYBB...", "SSSRRRBBBBBBB...", "SSS.BBBBBBBBBBDD", "SS.BBBBBBBBBBBDD",
    "...BBBBBBBBBBBDD", "...BBBBBBBBBBBD.", "..BBBBBB..BBB...", "..BBBBB.........",
    ".DDDDD..........", ".DDDDD..........", ".DDDD...........", "................",
    "................", "................", "................", "................",
    "................", "................", "................", "................",
]
M_B_DUCK = ["................"] * 14 + _HEAD[1:] + [
    "...RRRRBBBBRRR..", "..SSRRBYBBYBRSS.", ".SSSBBBBBBBBBSSS", ".SSBBBBBBBBBBBSS",
    "..DDDDD....DDDDD", ".DDDDDD....DDDDD", "................", "................",
    "................", "................",
]
M_B_SKID = _HEAD[:4] + [
    ".....SKSSKKK....", "....SSSKSSSKSK..", "...SSSKSSSKKSK..", "....KKKKSSSSKK..",
    ".....SSSSSSS....",
    ".SS.RRRBRRR.....", "SSSRRRRBBRRR....", "SSRRRRRBBBBRR...", ".RRRRRBBYBBYB...",
    "..RRBBBBBBBBRS..", "...BBBBBBBBBSSS.", "...BBBBBBBBBSS..", "..BBBBBBBBBB....",
    "..BBBBB..BBBB...", ".BBBBB....BBBB..", "DDBBB......BBB..", "DDDD.......DDD..",
    ".DD........DDDD.", "...........DDDD.", "................", "................",
    "................", "................", "................",
]

GOOMBA = [
    "......DDDD......", ".....DDDDDD.....", "....DDDDDDDD....", "...DDDDDDDDDD...",
    "..DDKKDDDDKKDD..", ".DDDWKKDDKKWDDD.", ".DDDWKWDDWKWDDD.", "DDDDWWWDDWWWDDDD",
    "DDDDDDDDDDDDDDDD", "DDDDDDDDDDDDDDDD", ".DDDDLLLLLLDDDD.", "....LLLLLLLL....",
    "....LLLLLLLLKK..", "..KKKLLLLLLKKKK.", ".KKKKKLLLLKKKKK.", "..KKKKK...KKKK..",
]
GOOMBA_FLAT = [
    "................", "................", "................", "................",
    "................", "................", "................", "................",
    "...DDDDDDDDDD...", ".DDDKKDDDDKKDDD.", "DDDWWKWDDWKWWDDD", "DDDDDDDDDDDDDDDD",
    ".DDDLLLLLLLLDDD.", "..KKKKK..KKKKK..", "................", "................",
]
GOOMBA_PALS = {
    "overworld": {'D': (172, 80, 20), 'L': (252, 188, 140), 'W': (252, 252, 252), 'K': (0, 0, 0)},
    "underground": {'D': (0, 88, 136), 'L': (156, 220, 252), 'W': (252, 252, 252), 'K': (0, 0, 40)},
    "castle": {'D': (100, 100, 100), 'L': (200, 200, 200), 'W': (252, 252, 252), 'K': (0, 0, 0)},
}

KOOPA_1 = [
    "....YYY.........", "...YYYYY........", "..YYKKYYY.......", "..YYKWYYY.......",
    ".YYYYYYYY.......", ".YYYYYYYY.......", "..YYYYYYY.......", "...YYYYY........",
    "....YYYY.WWWW...", ".....YYWWGGGGW..", ".....YWGGGGGGGW.", "....YYWGKGGKGGGW",
    "....YYWGGGGGGGGW", "....YYWGGKGGKGGW", ".....YWGGGGGGGGW", ".....YWGKGGKGGGW",
    "......WGGGGGGGW.", ".......WWWWWWW..", "......YYY..YYY..", ".....YYYY..YYYY.",
    ".....YYY....YYY.", "....KKKK....KKKK", "....KKKKK...KKKK", "................",
]
KOOPA_2 = KOOPA_1[:17] + [
    ".......WWWWWWW..", ".......YYYYYY...", "......YYYYYYY...", "......YYYYYY....",
    ".....KKKKKK.....", ".....KKKKKKK....", "................",
]
SHELL = [
    "................", "................", "....WWWWWWWW....", "...WGGGGGGGGW...",
    "..WGGKGGGGKGGW..", "..WGGGGGGGGGGW..", ".WGKGGGKKGGGKGW.", ".WGGGGGGGGGGGGW.",
    ".WGGKGGGGGGKGGW.", ".WWWWWWWWWWWWWW.", ".YYYYYYYYYYYYYY.", "..YYYYYYYYYYYY..",
    "...WWWWWWWWWW...", "................", "................", "................",
]
KOOPA_PALS = {
    "g": {'Y': (252, 200, 60), 'G': (0, 168, 0), 'W': (252, 252, 252), 'K': (0, 0, 0)},
    "r": {'Y': (252, 200, 60), 'G': (216, 40, 0), 'W': (252, 252, 252), 'K': (0, 0, 0)},
    "b": {'Y': (100, 100, 160), 'G': (40, 60, 180), 'W': (180, 200, 252), 'K': (0, 0, 0)},
}
BUZZY = [
    "................", "................", "................", ".....GGGGGG.....",
    "...GGWGGGGWGG...", "..GGGGGGGGGGGG..", ".GGWGGGGGGGWGGG.", ".GGGGGGGGGGGGGG.",
    "GGGGGWGGGGWGGGGG", "GGGGGGGGGGGGGGGG", "KKKKKKKKKKKKKKKK", "YYKWKKKKKKKKKK..",
    "YYYYYKKKKKKKK...", ".YYYY.....YYY...", "..KKKK....KKKK..", "................",
]
BUZZY_PAL = {'G': (40, 60, 180), 'W': (180, 200, 252), 'K': (0, 0, 0), 'Y': (252, 188, 140)}
SPINY = [
    "................", "...W....W...W...", "...WW..WWW.WW...", "..RWWRRRWRRWWR..",
    ".RRRWRRRWRRRWRR.", "WWRRRRRRRRRRRRWW", ".RRRRRRRRRRRRRR.", "WRRRRRRRRRRRRRRW",
    ".RRRRRRRRRRRRRRR", "YYKYYRRRRRRRRRR.", "YKWKYYYRRRRRR...", "YYYYYYYYYYY.....",
    ".YYYY...YYYY....", "..WWW....WWW....", "................", "................",
]
SPINY_PAL = {'R': (216, 40, 0), 'W': (252, 252, 252), 'Y': (252, 160, 68), 'K': (0, 0, 0)}
SPINY_EGG = [
    "................", "................", "......WWWW......", "....WWRRRRWW....",
    "...WRRRRRRRRW...", "..WRRRWRRWRRRW..", "..RRRWWRRWWRRR..", ".WRRRRRRRRRRRRW.",
    ".RRRRRRRRRRRRRR.", ".RRRWWRRRRWWRRR.", "..RRRRRRRRRRRR..", "..WRRRRRRRRRRW..",
    "...RRRRRRRRRR...", "....WWRRRRWW....", "......WWWW......", "................",
]
MUSHROOM = [
    "......RRRR......", "....RRWWWWRR....", "...RRRWWWWRRR...", "..RRRRWWWWRRRR..",
    ".RWWRRRRRRRRWWR.", ".WWWWRRRRRRWWWW.", "RWWWWRRRRRRWWWWR", "RWWWWRRRRRRWWWWR",
    "RRWWRRRRRRRRWWRR", "RRRRKWWWWWWKRRRR", ".RRKWWKWWKWWKRR.", "...WWWKWWKWWW...",
    "...WWWWWWWWWWW..", "...WWWWWWWWWWW..", "....WWWWWWWWW...", ".....WWWWWWW....",
]
MUSHROOM_PAL = {'R': (216, 40, 0), 'W': (252, 252, 252), 'K': (0, 0, 0)}
ONEUP_PAL = {'R': (0, 168, 0), 'W': (252, 252, 252), 'K': (0, 0, 0)}
FLOWER = [
    "......YYYY......", "....YYRRRRYY....", "..YYRRWWWWRRYY..", ".YRRWWWWWWWWRRY.",
    "..YYRRWWWWRRYY..", "....YYRRRRYY....", "......YYYY......", ".......GG.......",
    ".GGG...GG...GGG.", "GGGGG..GG..GGGGG", ".GGGGG.GG.GGGGG.", "..GGGGGGGGGGGG..",
    "...GGGGGGGGGG...", ".....GGGGGG.....", ".......GG.......", ".......GG.......",
]
FLOWER_PAL = {'Y': (252, 152, 56), 'R': (216, 40, 0), 'W': (252, 252, 152), 'G': (0, 168, 0)}
STAR = [
    ".......YY.......", ".......YY.......", "......YYYY......", "......YYYY......",
    "YYYYYYYYYYYYYYYY", ".YYYYYKYYKYYYYY.", "..YYYYKYYKYYYY..", "...YYYKYYKYYY...",
    "....YYYYYYYYY...", "....YYYYYYYYYY..", "...YYYYYYYYYYY..", "...YYYYY..YYYYY.",
    "..YYYY......YYYY", "..YYY........YYY", ".YY............Y", "................",
]
STAR_PAL = {'Y': (252, 216, 40), 'K': (0, 0, 0)}
PIRANHA_HEAD = [
    "......RRRR......", "....RRRWWRRR....", "...RRWWRRRRWR...", "..RRRRRRRWRRRR..",
    "..RWRRRRRRRRWR..", ".RRRRWRRRRRRRRR.", ".RRRRRRRRRWRRRR.", ".WWWWWWWWWWWWWW.",
    ".W.W.W.W.W.W.W..", "................", ".W.W.W.W.W.W.W..", ".WWWWWWWWWWWWWW.",
    "..RRRRRRRRRRRR..", "...RRRWRRRRRR...", ".....RRRRRR.....", "......GGGG......",
]
PIRANHA_PAL = {'R': (216, 40, 0), 'W': (252, 252, 252), 'G': (0, 168, 0)}
HAMMER_BRO = [
    "....GGGGGG......", "...GGGWGGGGG....", "..GGGGGGGGGGG...", "..KKKKKKKKKKK...",
    "..YYKWYYYYY.....", ".YYYKKYYYYYY....", ".YYYYYYYYYY.....", "..YYYYYYY.......",
    "....YYYYWWWW....", "...YYYWWGGGGW...", "..YYYWGGKGGKGW..", "..YYYWGGGGGGGW..",
    "...YYWGKGGKGGW..", "....YWGGGGGGGW..", ".....WGGKGGKW...", "......WWWWWW....",
    "......YY..YY....", ".....YYY..YYY...", "....KKKK..KKKK..", "................",
    "................", "................", "................", "................",
]
HAMMER_PAL = {'G': (0, 168, 0), 'W': (252, 252, 252), 'K': (0, 0, 0), 'Y': (252, 200, 60)}
LAKITU = [
    ".....YYYYYY.....", "....YYYYYYYY....", "...YYKWYYKWYY...", "...YYKKYYKKYY...",
    "...YYYYYYYYYY...", "....YYYYYYYY....", "...WGGGGGGGGW...", "..WGGKGGGGKGGW..",
    "..WWWWWWWWWWWW..", "..WWWWWWWWWWWW..", ".WWWKWWWWWWKWWW.", "WWWWKWWWWWWKWWWW",
    "WWWWWWWWWWWWWWWW", ".WWWWWWWWWWWWWW.", "..WWWW....WWWW..", "................",
]
LAKITU_PAL = {'Y': (252, 200, 60), 'G': (0, 168, 0), 'K': (0, 0, 0), 'W': (252, 252, 252)}
CHEEP = [
    "................", "................", ".......RRRR.....", ".W...RRRRRRRR...",
    ".WW.RRRWRRRRWRR.", ".WWWRRRRRRWKKWR.", ".WWWRRRWRRRWKWRR", ".WWWRRRRRRRRRRRR",
    ".WWWRRRWRRRRWWWW", ".WW.RRRRRRRRRRR.", ".W...RRRRRRRRR..", ".......RRRRR....",
    "................", "................", "................", "................",
]
CHEEP_PAL = {'R': (216, 40, 0), 'W': (252, 252, 252), 'K': (0, 0, 0)}
BLOOPER = [
    "......WWWW......", ".....WWWWWW.....", "....WWWWWWWW....", "....WWWWWWWW....",
    "...WWWWWWWWWW...", "...WKKWWWWKKW...", "...WKKWWWWKKW...", "...WWWWWWWWWW...",
    "....WWWWWWWW....", "....W.W..W.W....", "...W..W..W..W...", "...W..W..W..W...",
    "..W...W..W...W..", "..W...W..W...W..", "................", "................",
]
BLOOPER_PAL = {'W': (252, 252, 252), 'K': (0, 0, 0)}
PODOBOO = [
    "................", "......YYYY......", ".....YYYYYY.....", "....YYOOOOYY....",
    "...YYOOOOOOYY...", "...YOOWOOWOOY...", "..YYOOKOOKOOYY..", "..YOOOOOOOOOOY..",
    "..YOOOOOOOOOOY..", "..YYOOOOOOOOYY..", "...YOOOOOOOOY...", "...YYO.OO.OYY...",
    "....Y..OO..Y....", ".......O........", "................", "................",
]
PODOBOO_PAL = {'Y': (252, 216, 40), 'O': (228, 92, 16), 'W': (252, 252, 252), 'K': (0, 0, 0)}
BULLET = [
    "................", "......GGGGGGGWW.", "....GGGGGGGGGWWK", "...GGWWGGGGGGWWK",
    "..GGWKKWGGGGGWWK", ".GGGWKKWGGGGGWWK", ".GGGGWWGGGGGGWWK", "GGGGGGGGGGGGGWWK",
    "GGGGGGGGGGGGGWWK", ".GGGGGGGGGGGGWWK", ".GGGGGGGGGGGGWWK", "..GGGGGGGGGGGWWK",
    "...GGGGGGGGGGWWK", "....GGGGGGGGGWWK", "......GGGGGGGWW.", "................",
]
BULLET_PAL = {'G': (40, 40, 40), 'W': (180, 180, 180), 'K': (0, 0, 0)}
COIN_F = [
    ["....YYYYYY......", "...YOOOOOOY.....", "..YOOYYYYOOY....", "..YOYOOOOYOY....",
     "..YOYOOOOYOY....", "..YOYOOOOYOY....", "..YOYOOOOYOY....", "..YOYOOOOYOY....",
     "..YOYOOOOYOY....", "..YOYOOOOYOY....", "..YOYOOOOYOY....", "..YOYOOOOYOY....",
     "..YOOYYYYOOY....", "...YOOOOOOY.....", "....YYYYYY......", "................"],
    ["......YYYY......", ".....YOOOOY.....", ".....YOYYOY.....", ".....YOYOOY.....",
     ".....YOYOOY.....", ".....YOYOOY.....", ".....YOYOOY.....", ".....YOYOOY.....",
     ".....YOYOOY.....", ".....YOYOOY.....", ".....YOYOOY.....", ".....YOYOOY.....",
     ".....YOYYOY.....", ".....YOOOOY.....", "......YYYY......", "................"],
    [".......YY.......", "......YOOY......", "......YOOY......", "......YOOY......",
     "......YOOY......", "......YOOY......", "......YOOY......", "......YOOY......",
     "......YOOY......", "......YOOY......", "......YOOY......", "......YOOY......",
     "......YOOY......", "......YOOY......", ".......YY.......", "................"],
]
COIN_PAL = {'Y': (252, 216, 40), 'O': (200, 120, 0)}

T_GROUND = [
    "HBBBBBBBBKHBBBBK", "BHBBBBBBBKBHBBBK", "BBBBBBBBBKBBBBBK", "BBBBBBBBBKBBBBBK",
    "BBBBBBBBBKHBBBBK", "BBBBBBBBBKBKKBBK", "BBBBBBBBBKHHHKKH", "BBBBBBBBBKBBBHBK",
    "BBBBBBBBBKBBBBBK", "KKBBBBBBKBBBBBBK", "HHKKBBBKBBBBBBBK", "BBHHKKKBBBBBBBBK",
    "BBBBHHKBBBBBBBBK", "BBBBBBKBBBBBBBKK", "BBBBBBKBBBBBBBKK", "BKKKKKKHKKKKKKKK",
]
T_BRICK = [
    "HHHHHHHHHHHHHHHH", "BBBBBBBKBBBBBBBK", "BBBBBBBKBBBBBBBK", "KKKKKKKKKKKKKKKK",
    "BBBKBBBBBBBKBBBB", "BBBKBBBBBBBKBBBB", "KKKKKKKKKKKKKKKK", "BBBBBBBKBBBBBBBK",
    "BBBBBBBKBBBBBBBK", "KKKKKKKKKKKKKKKK", "BBBKBBBBBBBKBBBB", "BBBKBBBBBBBKBBBB",
    "KKKKKKKKKKKKKKKK", "BBBBBBBKBBBBBBBK", "BBBBBBBKBBBBBBBK", "KKKKKKKKKKKKKKKK",
]
T_QBLOCK = [
    "DHHHHHHHHHHHHHHD", "HOKOOOOOOOOOOKOK", "HOOOODDDDDOOOOOK", "HOOODDKKKDDOOOOK",
    "HOOODDKOODDKOOOK", "HOOOKKKOODDKOOOK", "HOOOOOOODDKKOOOK", "HOOOOOODDKKOOOOK",
    "HOOOOOODDKOOOOOK", "HOOOOOOOKKOOOOOK", "HOOOOOODDOOOOOOK", "HOOOOOODDKOOOOOK",
    "HOOOOOOOKKOOOOOK", "HOKOOOOOOOOOOKOK", "HOOOOOOOOOOOOOOK", "KKKKKKKKKKKKKKKK",
]
T_USED = [
    "KKKKKKKKKKKKKKKK", "KDKDDDDDDDDDDKDK", "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK", "KDDDDDDDDDDDDDDK",
    "KDDDDDDDDDDDDDDK", "KDKDDDDDDDDDDKDK", "KDDDDDDDDDDDDDDK", "KKKKKKKKKKKKKKKK",
]


def _rock_grid():
    rows = []
    for y in range(16):
        row = ''
        for x in range(16):
            d = min(x, y, 15 - x, 15 - y)
            if d >= 4:
                row += 'B'
            elif (y <= x and y <= 15 - x) or (x < y and x <= 15 - y):
                row += 'H'
            else:
                row += 'K'
        rows.append(row)
    return rows


T_ROCK = _rock_grid()


# big-Mario walk cycle built from the standing torso so the head never bobs
_B_TORSO = M_B_STAND[:18]
M_B_STAND = _B_TORSO + [
    "....BBBBBBBBBB..", "....BBBBBBBBBB..", "....BBBBBBBBBB..", "...BBBBB..BBBBB.",
    "...BBBB....BBBB.", "...BBBB....BBBB.", "...BBBB....BBBB.", "..DDDDD....DDDDD",
    ".DDDDDD....DDDDD", ".DDDDDD....DDDDD",
]
M_B_WALK1 = _B_TORSO + [
    "...BBBBBBBBBB...", "...BBBBBBBBBBB..", "..BBBBBB.BBBBB..", "..BBBBB...BBBB..",
    ".BBBBB.....BBBB.", ".BBBB......BBBB.", ".BBBB.......BBB.", ".DDDD.......DDD.",
    "DDDDD.......DDDD", "DDDD........DDDD",
]
M_B_WALK2 = _B_TORSO + [
    ".....BBBBBBB....", ".....BBBBBBB....", ".....BBBBBB.....", "......BBBBB.....",
    "......BBBBB.....", "......BBBBB.....", "......DDDDD.....", ".....DDDDDD.....",
    ".....DDDDDD.....", ".....DDDDD......",
]


# ---------------------------------------------------------------------------
# ART BAKER
# ---------------------------------------------------------------------------
def grid_surf(grid, pal, scale=2, rows=None, flip=False):
    """Char grid -> Surface. Trailing blank rows trimmed, padded on top to `rows`."""
    g = list(grid)
    while g and not g[-1].strip('.'):
        g.pop()
    w = max((len(r) for r in g), default=16)
    rows = rows or len(g)
    if len(g) < rows:
        g = ['.' * w] * (rows - len(g)) + g
    surf = pygame.Surface((w * scale, rows * scale), pygame.SRCALPHA)
    for y, row in enumerate(g):
        if flip:
            row = row.ljust(w, '.')[::-1]
        for x, ch in enumerate(row):
            if ch == '.' or ch == ' ':
                continue
            col = pal.get(ch)
            if col:
                surf.fill(col, (x * scale, y * scale, scale, scale))
    return surf


def _shade(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)



# ---------------------------------------------------------------------------
# STYLE ART PACKS (SMB3 / SMW) — Mario Worker Remake-style skin swap
# Each game style gets its own tile set, sprite treatment, scenery and sky.
# SMB1 uses the original grids above; SMB3/SMW are redrawn here (FILES=OFF).
# ---------------------------------------------------------------------------
_OUTLINED_SPRITES = ('mario', 'goomba', 'koopa_', 'para_', 'shell_', 'buzzy', 'spiny', 'mushroom',
                     '1up', 'flower', 'star', 'piranha', 'hammer_bro', 'lakitu', 'cheep', 'blooper',
                     'podoboo', 'bullet', 'bowser', 'coin')


def _outline(src, col=(0, 0, 0), t=2):
    """Black SMB3/SMW-style outline around every opaque pixel (kept inside the surface)."""
    mask = pygame.mask.from_surface(src, 8)
    sil = mask.to_surface(setcolor=col + (255,), unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    for dx, dy in ((-t, 0), (t, 0), (0, -t), (0, t), (-t, -t), (t, t), (-t, t), (t, -t)):
        out.blit(sil, (dx, dy))
    out.blit(src, (0, 0))
    return out


def _stripes(s, step, width, mul=(185, 185, 185), vertical=True):
    """Darken stripes inside the opaque area only (alpha untouched)."""
    w, h = s.get_size()
    if vertical:
        for x in range(step // 2, w, step):
            s.fill(mul, (x, 0, width, h), special_flags=pygame.BLEND_RGB_MULT)
    else:
        for y in range(step // 2, h, step):
            s.fill(mul, (0, y, w, width), special_flags=pygame.BLEND_RGB_MULT)


def _style_dirt(theme):
    """(base, light, dark) dirt colours for the active style + scene."""
    if theme == 'underground':
        b = (40, 112, 152) if ACTIVE_STYLE == 'SMB3' else (88, 96, 160)
    elif theme == 'castle':
        b = (140, 140, 148) if ACTIVE_STYLE == 'SMB3' else (120, 120, 136)
    elif theme == 'underwater':
        b = (24, 136, 120) if ACTIVE_STYLE == 'SMB3' else (40, 120, 160)
    elif theme == 'snow':
        b = (176, 200, 240) if ACTIVE_STYLE == 'SMB3' else (200, 216, 248)
    else:
        b = (232, 156, 72) if ACTIVE_STYLE == 'SMB3' else (192, 120, 64)
    return b, _shade(b, 48), _shade(b, -64)


def _qmark(s, col, ox=0, scale=3):
    btext(s, '?', TS // 2 + ox, 6, scale, col, True, center=True)


def style_tile(art, tid, theme, frame):
    st = ACTIVE_STYLE
    K = (0, 0, 0)
    s = pygame.Surface((TS, TS), pygame.SRCALPHA)
    base, light, dark = _style_dirt(theme)
    if tid in ('ground', 'grass'):
        s.fill(base)
        if st == 'SMB3':
            # SMB3: diagonal hatched dirt
            for i in range(-TS, TS * 2, 8):
                pygame.draw.line(s, dark, (i, TS), (i + TS, 0), 2)
            for (x, y) in ((6, 9), (21, 4), (13, 22), (26, 25)):
                s.fill(light, (x, y, 3, 2))
        else:
            # SMW: dotted soil lattice
            for y in range(4, TS, 8):
                for x in range(4 if (y // 8) % 2 else 0, TS, 8):
                    s.fill(dark, (x, y, 3, 3))
                    s.fill(light, (x, y, 1, 1))
        if tid == 'grass':
            top = (252, 252, 252) if theme == 'snow' else ((32, 200, 64) if st == 'SMB3' else (64, 208, 72))
            hi = (252, 252, 252) if theme == 'snow' else ((168, 248, 120) if st == 'SMB3' else (176, 248, 136))
            edge = (120, 140, 200) if theme == 'snow' else (0, 88, 24)
            s.fill(top, (0, 0, TS, 10))
            if st == 'SMW':
                for x in range(0, TS, 8):
                    pygame.draw.circle(s, top, (x + 4, 10), 4)
                    pygame.draw.arc(s, edge, (x, 6, 8, 8), math.pi, 2 * math.pi, 2)
            else:
                pygame.draw.line(s, edge, (0, 10), (TS, 10), 2)
            s.fill(hi, (0, 2, TS, 2))
            pygame.draw.line(s, edge, (0, 0), (TS, 0), 1)
        return s
    if tid == 'rock':
        s.fill(dark)
        pygame.draw.rect(s, base, (2, 2, TS - 4, TS - 4), border_radius=6 if st == 'SMW' else 2)
        pygame.draw.rect(s, light, (4, 4, TS - 12, 4), border_radius=2)
        pygame.draw.rect(s, K, (0, 0, TS, TS), 2, border_radius=6 if st == 'SMW' else 2)
        return s
    if tid == 'brick' or tid in ('bcoin', 'bpower', 'bstar', 'b1up'):
        if st == 'SMB3':
            b = (216, 128, 40) if theme not in ('underground', 'castle') else _style_dirt(theme)[0]
            s.fill(_shade(b, -110))
            for row in range(4):
                off = 0 if row % 2 == 0 else -8
                for col in range(-1, 3):
                    r = pygame.Rect(off + col * 16 + 1, row * 8 + 1, 14, 6)
                    pygame.draw.rect(s, b, r)
                    pygame.draw.line(s, _shade(b, 60), r.topleft, (r.right - 1, r.top))
                    pygame.draw.line(s, _shade(b, -50), (r.left, r.bottom - 1), (r.right - 1, r.bottom - 1))
            return s
        # SMW turn block
        y0 = (248, 200, 48) if theme not in ('underground', 'castle') else (200, 176, 120)
        pygame.draw.rect(s, y0, (1, 1, TS - 2, TS - 2), border_radius=6)
        pygame.draw.rect(s, _shade(y0, 50), (4, 4, TS - 12, 6), border_radius=3)
        pygame.draw.rect(s, _shade(y0, -70), (8, 12, TS - 16, TS - 16), 2, border_radius=3)
        pygame.draw.rect(s, K, (0, 0, TS, TS), 2, border_radius=6)
        return s
    if tid.startswith('q'):
        if st == 'SMB3':
            body = [(248, 160, 32), (252, 188, 80), (232, 128, 16)][frame % 3]
            pygame.draw.rect(s, (88, 40, 0), (3, 3, TS - 3, TS - 3), border_radius=4)   # drop shadow
            pygame.draw.rect(s, body, (0, 0, TS - 3, TS - 3), border_radius=4)
            pygame.draw.rect(s, K, (0, 0, TS - 3, TS - 3), 2, border_radius=4)
            for (x, y) in ((4, 4), (TS - 9, 4), (4, TS - 9), (TS - 9, TS - 9)):
                s.fill(K, (x, y, 2, 2))
            _qmark(s, (252, 252, 252), -1)
            return s
        # SMW: spinning yellow prize block (squeezes on animation frames)
        full = pygame.Surface((TS, TS), pygame.SRCALPHA)
        y0 = (248, 216, 48)
        pygame.draw.rect(full, y0, (1, 1, TS - 2, TS - 2), border_radius=7)
        pygame.draw.rect(full, (252, 248, 176), (4, 3, TS - 10, 4), border_radius=2)
        pygame.draw.rect(full, (200, 136, 0), (2, TS - 7, TS - 4, 5), border_radius=3)
        pygame.draw.rect(full, K, (0, 0, TS, TS), 2, border_radius=7)
        _qmark(full, (252, 252, 252))
        w = [TS, 22, 10][frame % 3]
        if w == TS:
            return full
        sq = pygame.transform.scale(full, (w, TS))
        s.blit(sq, ((TS - w) // 2, 0))
        return s
    if tid == 'used':
        c = (176, 104, 40) if st == 'SMB3' else (160, 96, 48)
        pygame.draw.rect(s, c, (0, 0, TS, TS), border_radius=4 if st == 'SMB3' else 7)
        pygame.draw.rect(s, _shade(c, 40), (3, 3, TS - 8, 3))
        pygame.draw.rect(s, K, (0, 0, TS, TS), 2, border_radius=4 if st == 'SMB3' else 7)
        for (x, y) in ((5, 5), (TS - 8, 5), (5, TS - 8), (TS - 8, TS - 8)):
            pygame.draw.circle(s, K, (x + 1, y + 1), 2)
        return s
    if tid == 'semi':
        col = ((248, 120, 160) if st == 'SMB3' else (248, 184, 64)) if theme != 'snow' else (200, 220, 252)
        pygame.draw.rect(s, col, (0, 0, TS, 12))
        pygame.draw.rect(s, _shade(col, 60), (0, 2, TS, 2))
        pygame.draw.rect(s, _shade(col, -80), (0, 10, TS, 3))
        if st == 'SMB3':
            for x in range(6, TS, 12):
                s.fill(K, (x, 5, 2, 2))
        pygame.draw.line(s, K, (0, 0), (TS, 0), 2)
        return s
    if tid == 'bridge':
        wood = (200, 120, 48) if st == 'SMB3' else (176, 112, 64)
        for x in range(0, TS, 8):
            pygame.draw.rect(s, wood, (x, 0, 8, 14))
            pygame.draw.rect(s, _shade(wood, 50), (x + 1, 1, 6, 3))
            pygame.draw.rect(s, K, (x, 0, 8, 14), 1)
        return s
    return None


def style_spr(art, name, frame, flip, theme):
    """Style-specific sprite, or None to fall back to the SMB1 grid (then outlined)."""
    st = ACTIVE_STYLE
    K = (0, 0, 0)
    gp = GOOMBA_PALS.get(theme, GOOMBA_PALS['overworld'])
    if name.startswith('mario'):
        _, size, pose, fire = name.split('_')
        if st == 'SMB3':
            pal = dict(MARIO_PAL, R=(216, 40, 0), B=(40, 40, 40), K=(0, 0, 0), D=(136, 72, 16),
                       S=(252, 196, 148))
            if fire == '1':
                pal.update(R=(252, 252, 252), B=(216, 40, 0))
        else:
            pal = dict(MARIO_PAL, R=(232, 48, 48), B=(56, 96, 232), K=(104, 56, 16), D=(120, 64, 24),
                       S=(248, 200, 160), Y=(252, 232, 96))
            if fire == '1':
                pal.update(R=(252, 252, 252), B=(232, 48, 48))
        if size == 's':
            g = {'stand': M_S_STAND, 'walk1': M_S_WALK1, 'walk2': M_S_WALK2, 'jump': M_S_JUMP,
                 'skid': M_S_SKID, 'dead': M_S_DEAD, 'swim': M_S_SWIM, 'duck': M_S_STAND}[pose]
            return _outline(grid_surf(g, pal, rows=16, flip=flip))
        g = {'stand': M_B_STAND, 'walk1': M_B_WALK1, 'walk2': M_B_WALK2, 'jump': M_B_JUMP,
             'skid': M_B_SKID, 'duck': M_B_DUCK, 'swim': M_B_JUMP, 'dead': M_B_STAND}[pose]
        return _outline(grid_surf(g, pal, rows=32, flip=flip))
    if name in ('goomba', 'goomba_flat'):
        flat = name == 'goomba_flat'
        body = gp['D']
        if st == 'SMB3':
            body = _shade(body, 12)
            s = grid_surf(GOOMBA_FLAT if flat else GOOMBA, dict(gp, D=body, K=(40, 16, 0)),
                          rows=16, flip=bool(frame) and not flat)
            if not flat:      # angry SMB3 brows
                pygame.draw.line(s, K, (6, 6), (13, 9), 2)
                pygame.draw.line(s, K, (25, 6), (18, 9), 2)
            return _outline(s)
        # SMW Galoomba: round body, big eyes
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        if flat:
            pygame.draw.ellipse(s, body, (2, 20, 28, 12))
            pygame.draw.line(s, K, (9, 25), (14, 25), 2)
            pygame.draw.line(s, K, (18, 25), (23, 25), 2)
            return _outline(s)
        pygame.draw.ellipse(s, body, (3, 3, 26, 24))
        pygame.draw.ellipse(s, _shade(body, 50), (8, 6, 12, 5))
        for ex in (10, 18):
            pygame.draw.ellipse(s, (252, 252, 252), (ex, 9, 6, 9))
            pygame.draw.ellipse(s, K, (ex + (1 if frame else 3), 12, 3, 5))
        fx = (2, 18) if frame else (5, 15)
        for x in fx:
            pygame.draw.ellipse(s, (96, 48, 16), (x, 25, 12, 7))
        return _outline(s)
    if name == 'coin' and st == 'SMW':
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        w = [20, 12, 4, 12][frame % 4]
        r = pygame.Rect(16 - w // 2, 2, w, 28)
        pygame.draw.ellipse(s, (248, 200, 32), r)
        if w > 6:
            pygame.draw.ellipse(s, (252, 240, 160), r.inflate(-w // 2, -8))
            pygame.draw.line(s, (200, 128, 0), (16, 8), (16, 23), 2)
        return _outline(s)
    if name in ('mushroom', '1up') and st == 'SMB3':
        pal = dict(MUSHROOM_PAL if name == 'mushroom' else ONEUP_PAL)
        pal['W'] = (252, 232, 200)
        return _outline(grid_surf(MUSHROOM, pal))
    if name.startswith(('koopa_', 'para_', 'shell_')):
        k = name[-1]
        pal = dict(KOOPA_PALS[k])
        if st == 'SMW':
            pal['Y'] = (248, 216, 88)
            pal['G'] = {'g': (24, 184, 72), 'r': (232, 56, 56), 'b': (64, 96, 232)}.get(k, pal['G'])
        else:
            pal['Y'] = (252, 184, 96)
        bak = KOOPA_PALS[k]
        KOOPA_PALS[k] = pal
        try:
            s = art._make_spr(name, frame, flip, theme, _plain=True)
        finally:
            KOOPA_PALS[k] = bak
        return _outline(s)
    return None


def style_scenery(art, sid, theme):
    st = ACTIVE_STYLE
    snow = theme == 'snow'
    dark = theme in ('night', 'underground', 'castle')
    K = (0, 0, 0)
    if sid in ('hill_big', 'hill_small'):
        w, h = (160, 76) if sid == 'hill_big' else (96, 44)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        if st == 'SMB3':
            body = (252, 252, 252) if snow else (88, 208, 80)
            pygame.draw.rect(s, body, (0, h // 3, w, h))
            pygame.draw.ellipse(s, body, (0, 0, w, h * 2 // 3 + 4))
            _stripes(s, 16, 4, (150, 190, 150) if not snow else (200, 210, 240))
            return _outline(s)
        body = (236, 244, 252) if snow else (104, 200, 96)
        pygame.draw.ellipse(s, body, (0, 0, w, h * 2))
        pygame.draw.ellipse(s, _shade(body, 40), (w // 5, h // 6, w // 4, h // 5))
        cx = w // 2
        for ex in (cx - 12, cx + 6):           # SMW hill eyes
            pygame.draw.ellipse(s, K, (ex, h // 3, 6, 14))
            s.fill((252, 252, 252), (ex + 1, h // 3 + 2, 2, 3))
        return _outline(s)
    if sid.startswith('bush') or sid.startswith('cloud'):
        n = int(sid[-1])
        w = 32 * (n + 1)
        cloud = sid.startswith('cloud')
        h = 48 if cloud else 32
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        if cloud:
            body = (252, 252, 252) if not dark else (170, 176, 210)
        else:
            body = (252, 252, 252) if snow else ((56, 192, 72) if st == 'SMB3' else (80, 216, 88))
        base_y = h - (10 if cloud else 0)
        for i in range(n + 1):
            pygame.draw.circle(s, body, (16 + 32 * i, base_y - 14), 16)
        pygame.draw.rect(s, body, (2, base_y - 16, w - 4, 16 if cloud else 16), border_radius=8)
        if st == 'SMB3' and not cloud:
            _stripes(s, 10, 3, (170, 210, 170))
        if st == 'SMW':
            cx = w // 2
            for ex in (cx - 9, cx + 4):
                pygame.draw.ellipse(s, K, (ex, base_y - 20, 5, 10))
        return _outline(s)
    return None


_SKY_CACHE = {}


def style_background(surf, theme, cam_x, cam_y, frame, rect):
    """Extra SMB3 / SMW sky layers drawn after the flat sky fill."""
    st = ACTIVE_STYLE
    if st == 'SMB1':
        return
    key = (st, theme, rect.w, rect.h)
    sky = _SKY_CACHE.get(key)
    if sky is None:
        sky = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        top = visual_palette(theme)['bg']
        if st == 'SMW' and theme in ('overworld', 'snow'):
            bot = (232, 248, 252)
            for y in range(rect.h):
                t = y / max(1, rect.h - 1)
                sky.fill(tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,),
                         (0, y, rect.w, 1))
        _SKY_CACHE[key] = sky
        if len(_SKY_CACHE) > 32:
            _SKY_CACHE.clear()
    surf.blit(sky, rect.topleft)
    if theme not in ('overworld', 'snow', 'night'):
        return
    # distant parallax hills
    hk = ('hills', st, theme)
    strip = _SKY_CACHE.get(hk)
    if strip is None:
        strip = pygame.Surface((640, 140), pygame.SRCALPHA)
        if theme == 'night':
            col = (24, 48, 72) if st == 'SMB3' else (32, 64, 96)
        elif theme == 'snow':
            col = (212, 228, 252)
        else:
            col = (152, 224, 168) if st == 'SMW' else (120, 200, 232)
        for (x, w, h) in ((-40, 220, 120), (150, 160, 80), (280, 240, 130), (480, 200, 100), (600, 220, 120)):
            pygame.draw.ellipse(strip, col, (x, 140 - h, w, h * 2))
            if st == 'SMW':
                pygame.draw.ellipse(strip, _shade(col, -40), (x, 140 - h, w, h * 2), 2)
                cx = x + w // 2
                for ex in (cx - 10, cx + 6):
                    pygame.draw.ellipse(strip, _shade(col, -90), (ex, 140 - h + 26, 5, 12))
        if st == 'SMB3':
            _stripes(strip, 18, 4, (215, 215, 215))
        _SKY_CACHE[hk] = strip
    ox = int(cam_x * 0.25) % 640
    y = rect.bottom - 140 - 48
    for x in (-ox, 640 - ox, 1280 - ox):
        if x < rect.right:
            surf.blit(strip, (rect.x + x, y))


class Art:
    """Lazy, cached FILES=OFF sprite factory."""

    def __init__(self):
        self.c = {}

    def get(self, key, maker):
        s = self.c.get(key)
        if s is None:
            s = maker()
            self.c[key] = s
        return s

    # ----- tiles ---------------------------------------------------------
    def tile(self, tid, theme, frame=0):
        return self.get(('t', ACTIVE_STYLE, tid, theme, frame), lambda: self._make_tile(tid, theme, frame))

    def _make_tile(self, tid, theme, frame):
        if ACTIVE_STYLE != 'SMB1':
            styled = style_tile(self, tid, theme, frame)
            if styled is not None:
                return styled
        tp = visual_palette(theme)
        pal = {'B': tp['B'], 'H': tp['H'], 'K': tp['K']}
        s = pygame.Surface((TS, TS), pygame.SRCALPHA)
        if tid in ('ice', 'spring', 'conveyor_l', 'conveyor_r', 'spikes'):
            dark = (36, 56, 88)
            if tid == 'ice':
                s.fill((124, 204, 248))
                pygame.draw.rect(s, (224, 248, 255), (2, 2, 28, 6))
                pygame.draw.line(s, (52, 140, 216), (4, 26), (26, 10), 3)
                pygame.draw.rect(s, dark, (0, 0, 32, 32), 2)
            elif tid == 'spring':
                pygame.draw.rect(s, (80, 80, 104), (2, 25, 28, 7))
                pygame.draw.rect(s, (248, 64, 64), (2, 3, 28, 8))
                pygame.draw.lines(s, (248, 216, 80), False,
                                  [(6, 25), (13, 18), (6, 11), (20, 11), (13, 18), (25, 25)], 3)
            elif tid.startswith('conveyor'):
                s.fill((90, 100, 120))
                for x in range(0, 32, 8):
                    pygame.draw.rect(s, (170, 180, 196), (x + 1, 5, 6, 22))
                pygame.draw.rect(s, dark, (0, 0, 32, 32), 2)
                arrow = '<' if tid.endswith('_l') else '>'
                btext(s, arrow, 16, 10, 2, (255, 224, 80), False, center=True)
            else:
                pygame.draw.rect(s, (100, 110, 124), (0, 25, 32, 7))
                for x in range(0, 32, 8):
                    pygame.draw.polygon(s, (224, 232, 244), [(x, 25), (x + 4, 3), (x + 8, 25)])
                    pygame.draw.lines(s, dark, False, [(x, 25), (x + 4, 3), (x + 8, 25)], 1)
            return s
        if tid == 'ground':
            return grid_surf(T_GROUND, pal)
        if tid == 'grass':
            s = grid_surf(T_GROUND, pal)
            top = (0, 168, 0) if theme != 'snow' else (252, 252, 252)
            dark = (0, 104, 0) if theme != 'snow' else (180, 200, 240)
            s.fill(top, (0, 0, TS, 8))
            for x in range(0, TS, 8):
                pygame.draw.rect(s, top, (x + 1, 8, 6, 3))
            pygame.draw.line(s, dark, (0, 10), (TS, 10))
            return s
        if tid == 'rock':
            return grid_surf(T_ROCK, pal)
        if tid == 'brick' or tid in ('bcoin', 'bpower', 'bstar', 'b1up'):
            return grid_surf(T_BRICK, dict(pal, B=STYLE_COLORS[ACTIVE_STYLE]['brick']))
        if tid == 'used':
            return grid_surf(T_USED, {'D': (200, 76, 12) if theme not in ('castle',) else (150, 100, 60),
                                      'K': (0, 0, 0)})
        if tid.startswith('q'):
            shine = [STYLE_COLORS[ACTIVE_STYLE]['question'], _shade(STYLE_COLORS[ACTIVE_STYLE]['question'], -24), _shade(STYLE_COLORS[ACTIVE_STYLE]['question'], -48)][frame % 3]
            return grid_surf(T_QBLOCK, {'O': shine, 'H': (252, 188, 176), 'D': (200, 76, 12),
                                        'K': (0, 0, 0)})
        if tid in ('hcoin', 'h1up'):
            return s  # invisible in game
        if tid.startswith('pipe'):
            return self._pipe(tid)
        if tid == 'semi':
            col = (252, 152, 56) if theme != 'snow' else (200, 220, 252)
            pygame.draw.rect(s, col, (0, 0, TS, 12))
            pygame.draw.rect(s, _shade(col, -70), (0, 10, TS, 4))
            for x in range(4, TS, 8):
                pygame.draw.circle(s, _shade(col, -50), (x, 5), 2)
            return s
        if tid == 'bridge':
            pygame.draw.rect(s, (200, 76, 12), (0, 0, TS, 14))
            pygame.draw.rect(s, (252, 152, 56), (0, 2, TS, 4))
            for x in range(0, TS, 8):
                pygame.draw.line(s, (0, 0, 0), (x, 0), (x, 13))
            pygame.draw.rect(s, (0, 0, 0), (0, 0, TS, 14), 1)
            for y in range(16, TS, 6):
                pygame.draw.circle(s, (180, 180, 180), (TS - 6, y), 3, 1)
            return s
        if tid == 'lava':
            base = (228, 60, 0)
            s.fill(base)
            ph = frame * 4
            for x in range(TS):
                h = 4 + int(3 * math.sin((x + ph) * 0.4))
                pygame.draw.line(s, (252, 216, 40), (x, 0), (x, h))
            pygame.draw.rect(s, (252, 152, 56), (0, 10, TS, 4))
            return s
        if tid == 'water':
            s.fill((60, 120, 252, 110))
            for x in range(0, TS, 8):
                pygame.draw.arc(s, (200, 230, 252), (x, -3, 8, 8), math.pi, 2 * math.pi, 2)
            return s
        if tid == 'cannon':
            s.fill((24, 24, 24))
            pygame.draw.rect(s, (90, 90, 90), (2, 2, TS - 4, 10))
            pygame.draw.circle(s, (200, 200, 200), (TS // 2, 20), 7)
            pygame.draw.circle(s, (24, 24, 24), (TS // 2, 20), 4)
            pygame.draw.rect(s, (0, 0, 0), (0, 0, TS, TS), 2)
            return s
        if tid == 'cannon_base':
            s.fill((60, 60, 60))
            pygame.draw.rect(s, (110, 110, 110), (4, 0, 8, TS))
            pygame.draw.rect(s, (0, 0, 0), (0, 0, TS, TS), 2)
            return s
        if tid == 'coin':
            return self.spr('coin', frame % 3, False)
        s.fill((255, 0, 255))
        return s

    def _pipe(self, tid):
        s = pygame.Surface((TS, TS), pygame.SRCALPHA)
        G = STYLE_COLORS[ACTIVE_STYLE]['pipe']
        L, D, K = _shade(G, 65), _shade(G, -65), (0, 0, 0)
        left = tid.endswith('l')
        top = '_t' in tid
        x0 = 0 if top else (4 if left else 0)
        x1 = TS if top else (TS if left else TS - 4)
        for x in range(x0, x1):
            gx = x if left else x + TS          # position across the 64px pipe
            span = 64 if top else 56
            rel = (gx - (0 if top else 4)) / span
            col = L if 0.12 < rel < 0.30 else (D if rel > 0.72 else G)
            pygame.draw.line(s, col, (x, 0), (x, TS - 1))
        if top:
            pygame.draw.line(s, K, (0, 0), (TS, 0), 2)
            pygame.draw.line(s, K, (0, TS - 2), (TS, TS - 2), 2)
            if left:
                pygame.draw.line(s, K, (0, 0), (0, TS), 2)
            else:
                pygame.draw.line(s, K, (TS - 2, 0), (TS - 2, TS), 2)
        else:
            if left:
                pygame.draw.line(s, K, (4, 0), (4, TS), 2)
            else:
                pygame.draw.line(s, K, (TS - 6, 0), (TS - 6, TS), 2)
        return s

    # ----- sprites -------------------------------------------------------
    def spr(self, name, frame=0, flip=False, theme='overworld'):
        return self.get(('s', ACTIVE_STYLE, name, frame, flip, theme),
                        lambda: self._make_spr(name, frame, flip, theme))

    def _make_spr(self, name, frame, flip, theme, _plain=False):
        if not _plain and ACTIVE_STYLE != 'SMB1':
            styled = style_spr(self, name, frame, flip, theme)
            if styled is not None:
                return styled
            s = self._make_spr(name, frame, flip, theme, _plain=True)
            return _outline(s) if name.startswith(_OUTLINED_SPRITES) else s
        gp = GOOMBA_PALS.get(theme, GOOMBA_PALS['overworld'])
        if name.startswith('mario'):
            # mario_<size>_<pose>_<fire>
            _, size, pose, fire = name.split('_')
            pal = dict(FIRE_PAL if fire == '1' else MARIO_PAL)
            if ACTIVE_STYLE == 'SMW':
                pal['B'] = (64, 96, 216)
                pal['R'] = (232, 48, 48) if fire == '0' else (252, 252, 252)
            elif ACTIVE_STYLE == 'SMB3':
                pal['B'] = (40, 88, 208)
            if size == 's':
                g = {'stand': M_S_STAND, 'walk1': M_S_WALK1, 'walk2': M_S_WALK2,
                     'jump': M_S_JUMP, 'skid': M_S_SKID, 'dead': M_S_DEAD,
                     'swim': M_S_SWIM, 'duck': M_S_STAND}[pose]
                return grid_surf(g, pal, rows=16, flip=flip)
            g = {'stand': M_B_STAND, 'walk1': M_B_WALK1, 'walk2': M_B_WALK2,
                 'jump': M_B_JUMP, 'skid': M_B_SKID, 'duck': M_B_DUCK,
                 'swim': M_B_JUMP, 'dead': M_B_STAND}[pose]
            return grid_surf(g, pal, rows=32, flip=flip)
        if name == 'goomba':
            return grid_surf(GOOMBA, gp, flip=bool(frame))
        if name == 'goomba_flat':
            return grid_surf(GOOMBA_FLAT, gp, rows=16)
        if name.startswith('koopa_'):
            k = name[-1]
            return grid_surf(KOOPA_1 if frame == 0 else KOOPA_2, KOOPA_PALS[k], rows=24, flip=flip)
        if name.startswith('para_'):
            k = name[-1]
            s = grid_surf(KOOPA_1 if frame == 0 else KOOPA_2, KOOPA_PALS[k], rows=24)
            wing = pygame.Surface((14, 18), pygame.SRCALPHA)
            pts = [(0, 18), (2, 4), (8, 0), (14, 2), (10, 10), (6, 18)] if frame == 0 else \
                  [(0, 12), (4, 6), (10, 6), (14, 10), (8, 16), (2, 18)]
            pygame.draw.polygon(wing, (252, 252, 252), pts)
            pygame.draw.polygon(wing, (0, 0, 0), pts, 1)
            s.blit(wing, (20, 8))
            return pygame.transform.flip(s, True, False) if flip else s
        if name.startswith('shell_'):
            k = name[-1]
            s = grid_surf(SHELL, KOOPA_PALS[k], rows=16)
            if frame:
                s = pygame.transform.flip(s, True, False)
            return s
        if name == 'buzzy':
            return grid_surf(BUZZY, BUZZY_PAL, flip=not flip)
        if name == 'buzzy_shell':
            return pygame.transform.flip(grid_surf(BUZZY, BUZZY_PAL), False, frame == 1)
        if name == 'spiny':
            return grid_surf(SPINY, SPINY_PAL, flip=flip if frame == 0 else not flip)
        if name == 'spiny_egg':
            s = grid_surf(SPINY_EGG, SPINY_PAL)
            return pygame.transform.rotate(s, 90 * frame)
        if name == 'mushroom':
            return grid_surf(MUSHROOM, MUSHROOM_PAL)
        if name == '1up':
            return grid_surf(MUSHROOM, ONEUP_PAL)
        if name == 'flower':
            pal = dict(FLOWER_PAL)
            if frame % 2:
                pal['Y'], pal['R'] = (216, 40, 0), (252, 152, 56)
            return grid_surf(FLOWER, pal)
        if name == 'star':
            pal = dict(STAR_PAL)
            pal['Y'] = [(252, 216, 40), (252, 152, 56), (252, 252, 252), (216, 40, 0)][frame % 4]
            return grid_surf(STAR, pal)
        if name == 'coin':
            g = COIN_F[[0, 1, 2, 1][frame % 4]]
            return grid_surf(g, COIN_PAL)
        if name == 'piranha':
            s = pygame.Surface((32, 48), pygame.SRCALPHA)
            head = grid_surf(PIRANHA_HEAD, PIRANHA_PAL)
            if frame:
                head = pygame.transform.flip(head, False, False)
                head = pygame.transform.scale(head, (32, 28))
                s.blit(head, (0, 2))
            else:
                s.blit(head, (0, 0))
            pygame.draw.rect(s, (0, 168, 0), (14, 30, 4, 18))
            pygame.draw.ellipse(s, (0, 168, 0), (2, 34, 12, 8))
            pygame.draw.ellipse(s, (0, 168, 0), (18, 34, 12, 8))
            pygame.draw.ellipse(s, (0, 104, 0), (2, 34, 12, 8), 1)
            pygame.draw.ellipse(s, (0, 104, 0), (18, 34, 12, 8), 1)
            return s
        if name == 'hammer_bro':
            s = grid_surf(HAMMER_BRO, HAMMER_PAL, rows=24, flip=not flip)
            if frame:
                s = pygame.transform.flip(s, False, False)
                s2 = pygame.Surface(s.get_size(), pygame.SRCALPHA)
                s2.blit(s, (0, 2))
                return s2
            return s
        if name == 'lakitu':
            return grid_surf(LAKITU, LAKITU_PAL, flip=flip)
        if name == 'cheep':
            pal = dict(CHEEP_PAL)
            if frame:
                pal['W'] = (252, 188, 176)
            return grid_surf(CHEEP, pal, rows=16, flip=flip)
        if name == 'blooper':
            g = BLOOPER if frame == 0 else BLOOPER[:9] + ["....W.W..W.W...."] * 3
            return grid_surf(g, BLOOPER_PAL, rows=16)
        if name == 'podoboo':
            return pygame.transform.flip(grid_surf(PODOBOO, PODOBOO_PAL, rows=16), False, bool(frame))
        if name == 'bullet':
            return grid_surf(BULLET, BULLET_PAL, rows=16, flip=flip)
        if name == 'fireball':
            s = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.circle(s, (228, 92, 16), (8, 8), 7)
            pygame.draw.circle(s, (252, 216, 40), (8, 8), 4)
            a = frame * math.pi / 2
            pygame.draw.circle(s, (252, 252, 252), (8 + int(3 * math.cos(a)), 8 + int(3 * math.sin(a))), 2)
            return s
        if name == 'puff':
            s = pygame.Surface((24, 24), pygame.SRCALPHA)
            r = 4 + frame * 3
            pygame.draw.circle(s, (252, 252, 252), (12, 12), r, 2)
            return s
        if name == 'hammer':
            s = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.rect(s, (200, 120, 40), (9, 6, 3, 13))
            pygame.draw.rect(s, (160, 160, 160), (3, 1, 14, 7))
            pygame.draw.rect(s, (0, 0, 0), (3, 1, 14, 7), 1)
            return pygame.transform.rotate(s, -90 * frame)
        if name == 'flame':
            s = pygame.Surface((48, 16), pygame.SRCALPHA)
            pts = [(0, 8), (10, 2), (24, 5), (48, 0), (36, 8), (48, 16), (24, 11), (10, 14)]
            pygame.draw.polygon(s, (228, 92, 16), pts)
            pygame.draw.polygon(s, (252, 216, 40), [(6, 8), (14, 5), (30, 7), (14, 11)])
            return pygame.transform.flip(s, True, False) if flip else s
        if name == 'bowser':
            return self._bowser(frame, flip)
        if name == 'debris':
            s = pygame.Surface((12, 12), pygame.SRCALPHA)
            tp = visual_palette(theme)
            pygame.draw.rect(s, tp['B'], (0, 0, 12, 12))
            pygame.draw.rect(s, tp['K'], (0, 0, 12, 12), 2)
            return pygame.transform.rotate(s, 90 * frame)
        if name == 'lift':
            s = pygame.Surface((96, 16), pygame.SRCALPHA)
            pygame.draw.rect(s, (252, 188, 176), (0, 0, 96, 16), border_radius=3)
            pygame.draw.rect(s, (200, 76, 12), (0, 0, 96, 16), 2, border_radius=3)
            for x in range(8, 96, 16):
                pygame.draw.circle(s, (200, 76, 12), (x, 8), 3)
            return s
        if name == 'axe':
            s = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.rect(s, (200, 120, 40), (14, 4, 4, 28))
            pts = [(18, 4), (30, 2), (31, 18), (18, 16)]
            pygame.draw.polygon(s, (188, 188, 220) if frame == 0 else (252, 252, 252), pts)
            pygame.draw.polygon(s, (0, 0, 0), pts, 1)
            return s
        if name == 'checkpoint':
            s = pygame.Surface((32, 64), pygame.SRCALPHA)
            pygame.draw.rect(s, (252, 252, 252), (14, 4, 4, 60))
            pygame.draw.circle(s, (252, 216, 40), (16, 4), 4)
            col = (0, 200, 0) if frame else (216, 40, 0)
            pygame.draw.polygon(s, col, [(18, 8), (32, 14), (18, 22)])
            pygame.draw.rect(s, (90, 90, 90), (8, 58, 16, 6))
            return s
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        s.fill((255, 0, 255))
        return s

    def _bowser(self, frame, flip):
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        G, D, Y, O, W, K = (0, 168, 0), (0, 96, 0), (252, 216, 40), (228, 92, 16), (252, 252, 252), (0, 0, 0)
        # shell
        pygame.draw.ellipse(s, G, (18, 14, 42, 38))
        pygame.draw.ellipse(s, K, (18, 14, 42, 38), 2)
        for i, (sx, sy) in enumerate(((30, 14), (42, 12), (54, 18), (58, 30))):
            pygame.draw.polygon(s, W, [(sx - 4, sy + 4), (sx, sy - 6), (sx + 4, sy + 4)])
            pygame.draw.polygon(s, K, [(sx - 4, sy + 4), (sx, sy - 6), (sx + 4, sy + 4)], 1)
        # belly
        pygame.draw.ellipse(s, Y, (12, 28, 26, 26))
        for y in range(32, 52, 5):
            pygame.draw.line(s, O, (16, y), (34, y))
        # head
        pygame.draw.ellipse(s, G, (0, 4, 30, 24))
        pygame.draw.ellipse(s, K, (0, 4, 30, 24), 2)
        pygame.draw.polygon(s, W, [(14, 6), (20, -2), (22, 8)])
        pygame.draw.polygon(s, O, [(16, 2), (30, 0), (24, 10)])
        pygame.draw.circle(s, W, (10, 13), 4)
        pygame.draw.circle(s, K, (9, 13), 2)
        mouth_open = frame == 2
        pygame.draw.rect(s, (216, 40, 0) if mouth_open else Y, (0, 20, 16, 6 if mouth_open else 4))
        pygame.draw.line(s, W, (2, 20), (12, 20), 2)
        # legs
        lo = 0 if frame != 1 else 3
        pygame.draw.rect(s, Y, (16 + lo, 52, 12, 12))
        pygame.draw.rect(s, Y, (40 - lo, 52, 12, 12))
        pygame.draw.rect(s, K, (16 + lo, 52, 12, 12), 1)
        pygame.draw.rect(s, K, (40 - lo, 52, 12, 12), 1)
        pygame.draw.rect(s, D, (14, 26, 10, 8))
        return pygame.transform.flip(s, True, False) if flip else s

    # ----- scenery -------------------------------------------------------
    def scenery(self, sid, theme):
        return self.get(('bg', ACTIVE_STYLE, sid, theme), lambda: self._make_scenery(sid, theme))

    def _make_scenery(self, sid, theme):
        if ACTIVE_STYLE != 'SMB1':
            styled = style_scenery(self, sid, theme)
            if styled is not None:
                return styled
        snow = theme == 'snow'
        dark = theme in ('night', 'underground', 'castle')
        G = (0, 168, 0) if not snow else (236, 244, 252)
        L = (128, 208, 16) if not snow else (252, 252, 252)
        K = (0, 0, 0) if not snow else (120, 140, 200)
        CL = (252, 252, 252) if not dark else (160, 170, 200)
        CB = (60, 188, 252) if not dark else (90, 100, 140)
        if sid in ('hill_big', 'hill_small'):
            w, h = (160, 76) if sid == 'hill_big' else (96, 44)
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            r = w // 2 - h // 3
            pts = [(0, h), (w * 0.28, h * 0.45), (w * 0.5 - r * 0.6, h * 0.22),
                   (w * 0.5 + r * 0.6, h * 0.22), (w * 0.72, h * 0.45), (w, h)]
            pygame.draw.polygon(s, G, pts)
            pygame.draw.ellipse(s, G, (w * 0.5 - r * 0.7, 0, r * 1.4, h * 0.55))
            pygame.draw.arc(s, K, (w * 0.5 - r * 0.7, 0, r * 1.4, h * 0.55), 0.35, math.pi - 0.35, 2)
            pygame.draw.line(s, K, (0, h - 1), (w * 0.28, h * 0.45), 2)
            pygame.draw.line(s, K, (w, h - 1), (w * 0.72, h * 0.45), 2)
            for (dx, dy) in ((0.42, 0.45), (0.55, 0.62), (0.36, 0.72)):
                pygame.draw.ellipse(s, _shade(G, -60), (w * dx, h * dy, 8, 14))
            return s
        if sid.startswith('bush') or sid.startswith('cloud'):
            n = int(sid[-1])
            w = 32 * (n + 1)
            cloud = sid.startswith('cloud')
            h = 48 if cloud else 32
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            body, edge = (CL, CB) if cloud else (L, K)
            base_y = h - (12 if cloud else 0)
            bumps = [(16 + 32 * i, base_y - 14, 18) for i in range(n + 1)]
            if cloud:
                bumps = [(18, base_y - 6, 14)] + [(32 + 32 * i, base_y - 18, 18) for i in range(n)] + \
                        [(w - 18, base_y - 6, 14)]
            for (bx, by, br) in bumps:
                pygame.draw.circle(s, edge, (int(bx), int(by)), br + 2)
            pygame.draw.rect(s, edge, (4, base_y - 14, w - 8, 16))
            for (bx, by, br) in bumps:
                pygame.draw.circle(s, body, (int(bx), int(by)), br)
            pygame.draw.rect(s, body, (6, base_y - 14, w - 12, 14 if cloud else 14))
            if cloud:
                pygame.draw.rect(s, edge, (8, base_y, w - 16, 2))
                for i in range(n):
                    pygame.draw.ellipse(s, edge, (26 + 32 * i, base_y - 26, 6, 10))
            return s
        if sid == 'fence':
            s = pygame.Surface((32, 32), pygame.SRCALPHA)
            fc = (252, 252, 252) if not dark else (180, 180, 180)
            for x in (4, 20):
                pygame.draw.rect(s, fc, (x, 8, 8, 24))
                pygame.draw.rect(s, (0, 0, 0), (x, 8, 8, 24), 1)
            pygame.draw.rect(s, fc, (0, 14, 32, 5))
            pygame.draw.rect(s, (0, 0, 0), (0, 14, 32, 5), 1)
            return s
        if sid in ('tree', 'tree_tall'):
            h = 64 if sid == 'tree' else 96
            s = pygame.Surface((32, h), pygame.SRCALPHA)
            pygame.draw.rect(s, (172, 100, 40), (12, h - 28, 8, 28))
            pygame.draw.rect(s, (0, 0, 0), (12, h - 28, 8, 28), 1)
            pygame.draw.ellipse(s, L, (0, 0, 32, h - 22))
            pygame.draw.ellipse(s, K, (0, 0, 32, h - 22), 2)
            pygame.draw.line(s, _shade(L, -60), (10, 12), (10, h - 34), 2)
            return s
        if sid == 'castle':
            w, h = 160, 160
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            brick = self.tile('brick', 'overworld')
            for y in range(0, h, 32):
                for x in range(0, w, 32):
                    if y < 64 and (x < 32 or x >= 128):
                        continue
                    s.blit(brick, (x, y))
            for x in range(32, 128, 32):
                pygame.draw.rect(s, (0, 0, 0, 0), (x + 8, 0, 16, 10))
            for x in range(0, w, 32):
                pygame.draw.rect(s, (0, 0, 0, 0), (x + 10, 64, 12, 8))
            pygame.draw.rect(s, (0, 0, 0), (56, 104, 48, 56))
            pygame.draw.ellipse(s, (0, 0, 0), (56, 88, 48, 32))
            pygame.draw.rect(s, (0, 0, 0), (44, 24, 16, 24))
            pygame.draw.rect(s, (0, 0, 0), (100, 24, 16, 24))
            return s
        if sid == 'castle_big':
            w, h = 288, 352
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            brick = self.tile('brick', 'overworld')
            for y in range(0, h, 32):
                for x in range(0, w, 32):
                    if (y < 96 and (x < 64 or x >= 224)) or (y < 192 and (x < 32 or x >= 256)):
                        continue
                    s.blit(brick, (x, y))
            pygame.draw.rect(s, (0, 0, 0), (112, 256, 64, 96))
            pygame.draw.ellipse(s, (0, 0, 0), (112, 232, 64, 48))
            for x in (80, 144, 208):
                pygame.draw.rect(s, (0, 0, 0), (x - 8, 120, 16, 32))
            return s
        if sid == 'flag_castle':
            s = pygame.Surface((32, 64), pygame.SRCALPHA)
            pygame.draw.rect(s, (200, 200, 200), (14, 0, 4, 64))
            pygame.draw.polygon(s, (216, 40, 0), [(18, 4), (32, 12), (18, 20)])
            return s
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        s.fill((255, 0, 255, 120))
        return s


ART = Art()

# ---------------------------------------------------------------------------
# SOUND (synthesised, FILES=OFF)
# ---------------------------------------------------------------------------
SR = 22050


def _note_hz(n):
    """MIDI-style note number -> Hz (69 = A4)."""
    return 440.0 * 2 ** ((n - 69) / 12.0)


def _render(segments, wave='square', vol=0.25, duty=0.5):
    """segments: [(freq_or_None, seconds, freq_end_or_None)] -> array('h')."""
    out = array.array('h')
    phase = 0.0
    amp = int(32767 * vol)
    for seg in segments:
        f0, dur = seg[0], seg[1]
        f1 = seg[2] if len(seg) > 2 and seg[2] else f0
        n = max(1, int(SR * dur))
        if not f0:
            out.extend([0] * n)
            continue
        for i in range(n):
            t = i / n
            f = f0 + (f1 - f0) * t
            phase = (phase + f / SR) % 1.0
            env = 1.0 if i < n - 200 else max(0.0, (n - i) / 200.0)
            if wave == 'square':
                v = 1.0 if phase < duty else -1.0
            elif wave == 'tri':
                v = 4.0 * abs(phase - 0.5) - 1.0
            elif wave == 'noise':
                v = random.uniform(-1, 1)
            else:
                v = math.sin(phase * 2 * math.pi)
            out.append(int(v * amp * env))
    return out


def _mix(*tracks):
    n = max(len(t) for t in tracks)
    out = array.array('h', [0] * n)
    for t in tracks:
        for i, v in enumerate(t):
            s = out[i] + v
            out[i] = 32767 if s > 32767 else (-32768 if s < -32768 else s)
    return out


def _seq(notes, step, wave='square', vol=0.2, duty=0.5, legato=0.9):
    """notes: list of (note_number or None, length_in_steps)."""
    segs = []
    for n, ln in notes:
        d = step * ln
        if n is None:
            segs.append((None, d))
        else:
            segs.append((_note_hz(n), d * legato))
            segs.append((None, d * (1 - legato)))
    return _render(segs, wave, vol, duty)


def _sfx_defs():
    N = _note_hz
    return {
        'jump': lambda: _render([(N(62), 0.03), (N(66), 0.18, N(78))], 'square', 0.18, 0.25),
        'jump_big': lambda: _render([(N(58), 0.03), (N(62), 0.2, N(74))], 'square', 0.18, 0.25),
        'coin': lambda: _render([(N(83), 0.06), (N(88), 0.32)], 'square', 0.16, 0.5),
        'stomp': lambda: _render([(N(60), 0.05, N(48)), (N(52), 0.07, N(40))], 'square', 0.2, 0.5),
        'kick': lambda: _render([(N(76), 0.03), (N(64), 0.05)], 'square', 0.2, 0.5),
        'bump': lambda: _render([(N(40), 0.08, N(32))], 'tri', 0.45),
        'break': lambda: _render([(800, 0.12)], 'noise', 0.25),
        'appear': lambda: _seq([(n, 1) for n in (60, 67, 72, 61, 68, 73, 62, 69, 74)], 0.035, 'square', 0.15),
        'powerup': lambda: _seq([(n, 1) for n in (60, 64, 67, 72, 62, 66, 69, 74, 64, 68, 71, 76)],
                                0.04, 'square', 0.15),
        'oneup': lambda: _seq([(76, 2), (79, 2), (88, 2), (84, 2), (86, 2), (91, 3)], 0.06, 'square', 0.15),
        'fireball': lambda: _render([(N(72), 0.02), (N(84), 0.03), (N(60), 0.03)], 'square', 0.15, 0.25),
        'pipe': lambda: _seq([(48, 1), (None, 1), (45, 1), (None, 1), (48, 1), (None, 1), (45, 1)],
                             0.06, 'square', 0.2),
        'shrink': lambda: _seq([(74, 1), (69, 1), (66, 1), (62, 1), (69, 1), (66, 1), (62, 1), (57, 1)],
                               0.04, 'square', 0.15),
        'die': lambda: _seq([(71, 1), (77, 1), (None, 1), (77, 1), (77, 2), (76, 2), (74, 2), (72, 3),
                             (64, 2), (None, 1), (64, 1), (60, 4)], 0.11, 'square', 0.18, 0.5),
        'gameover': lambda: _seq([(72, 3), (None, 1), (67, 3), (None, 1), (64, 4), (69, 2), (71, 2),
                                  (69, 2), (68, 2), (70, 2), (68, 2), (67, 2), (65, 2), (67, 6)],
                                 0.1, 'square', 0.18),
        'clear': lambda: _seq([(55, 1), (60, 1), (64, 1), (67, 1), (72, 1), (76, 1), (79, 3), (76, 3),
                               (56, 1), (60, 1), (63, 1), (68, 1), (72, 1), (75, 1), (80, 3), (75, 3),
                               (58, 1), (62, 1), (65, 1), (70, 1), (74, 1), (77, 1), (82, 3),
                               (82, 1), (82, 1), (82, 1), (84, 6)], 0.07, 'square', 0.16),
        'tick': lambda: _render([(N(96), 0.02)], 'square', 0.08, 0.5),
        'gate': lambda: _render([(N(60), 0.25, N(96))], 'square', 0.14, 0.25),
        'hurry': lambda: _seq([(84, 1), (None, 1), (84, 1), (None, 1), (84, 1), (None, 3)] * 2,
                              0.05, 'square', 0.15),
        'bowserfire': lambda: _render([(300, 0.35)], 'noise', 0.18),
        'bowserfall': lambda: _render([(N(60), 0.9, N(30))], 'square', 0.18, 0.5),
        'pause': lambda: _seq([(76, 1), (72, 1), (76, 1), (72, 2)], 0.06, 'square', 0.15),
        'checkpoint': lambda: _seq([(72, 1), (76, 1), (79, 1), (84, 2)], 0.06, 'square', 0.15),
    }


# Original chiptune loops (melody, bass) — composed for koopa worker, not ripped.
def _bgm_defs():
    def song(mel, bass, step, mw='square', duty=0.25):
        return lambda: _mix(_seq(mel, step, mw, 0.13, duty, 0.85), _seq(bass, step, 'tri', 0.22, 0.5, 0.9))
    over_m = [(72, 2), (76, 2), (79, 2), (76, 1), (77, 1), (79, 2), (None, 2), (74, 2), (77, 2),
              (81, 2), (79, 1), (77, 1), (76, 4), (72, 2), (76, 2), (79, 2), (84, 2), (83, 2), (81, 2),
              (79, 2), (77, 2), (76, 2), (74, 2), (72, 4), (None, 4)]
    over_b = [(48, 4), (55, 4), (53, 4), (55, 4), (50, 4), (57, 4), (48, 4), (55, 4),
              (45, 4), (52, 4), (53, 4), (55, 4)]
    under_m = [(60, 1), (72, 1), (57, 1), (69, 1), (58, 1), (70, 1), (None, 6),
               (53, 1), (65, 1), (50, 1), (62, 1), (51, 1), (63, 1), (None, 6)]
    under_b = [(36, 2), (None, 2), (36, 2), (None, 2), (43, 2), (None, 6),
               (41, 2), (None, 2), (41, 2), (None, 2), (38, 2), (None, 6)]
    castle_m = [(69, 1), (70, 1), (69, 1), (68, 1), (69, 1), (72, 1), (71, 1), (70, 1)] * 2 + \
               [(65, 1), (66, 1), (65, 1), (64, 1), (65, 1), (69, 1), (68, 1), (67, 1)] * 2
    castle_b = [(45, 2), (52, 2), (45, 2), (52, 2)] * 2 + [(41, 2), (48, 2), (41, 2), (48, 2)] * 2
    water_m = [(64, 3), (67, 3), (72, 6), (71, 3), (69, 3), (67, 6), (65, 3), (69, 3), (72, 6),
               (71, 3), (67, 3), (64, 6)]
    water_b = [(48, 6), (55, 6), (52, 6), (55, 6), (53, 6), (57, 6), (55, 6), (52, 6)]
    ath_m = [(79, 2), (76, 1), (79, 1), (81, 2), (79, 2), (76, 2), (74, 2), (72, 4),
             (77, 2), (74, 1), (77, 1), (79, 2), (77, 2), (74, 2), (71, 2), (72, 4)]
    ath_b = [(48, 2), (55, 2)] * 4 + [(50, 2), (57, 2)] * 2 + [(43, 2), (50, 2)] * 2
    return {
        1: song(over_m, over_b, 0.12),
        2: song(under_m, under_b, 0.12, 'square', 0.5),
        3: song(castle_m, castle_b, 0.1),
        4: song(water_m, water_b, 0.1, 'sine'),
        5: song(ath_m, ath_b, 0.13),
    }


THEME_MUSIC = {"overworld": 1, "underground": 2, "castle": 3, "underwater": 4, "night": 5, "snow": 5}


class Audio:
    _inst = None

    def __init__(self):
        self.ok = False
        self.sfx_on = True
        self.music_on = True
        self.cache = {}
        self.music_ch = None
        self.cur_music = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(SR, -16, 1, 512)
            self.ok = bool(pygame.mixer.get_init())
            if self.ok:
                pygame.mixer.set_num_channels(16)
                self.music_ch = pygame.mixer.Channel(15)
                pygame.mixer.set_reserved(1)
        except pygame.error:
            self.ok = False
        self._sfx = _sfx_defs()
        self._bgm = _bgm_defs()

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = Audio()
        return cls._inst

    def _sound(self, key, maker):
        snd = self.cache.get(key)
        if snd is None:
            try:
                snd = pygame.mixer.Sound(buffer=maker().tobytes())
            except Exception:
                snd = False
            self.cache[key] = snd
        return snd

    def play(self, name):
        if not (self.ok and self.sfx_on) or name not in self._sfx:
            return
        snd = self._sound(('sfx', name), self._sfx[name])
        if snd:
            snd.play()

    def music(self, mid):
        if not self.ok:
            return
        if not self.music_on or mid not in self._bgm:
            self.stop_music()
            return
        if self.cur_music == mid and self.music_ch.get_busy():
            return
        snd = self._sound(('bgm', mid), self._bgm[mid])
        if snd:
            self.music_ch.play(snd, loops=-1)
            self.music_ch.set_volume(0.7)
            self.cur_music = mid

    def stop_music(self):
        self.cur_music = None
        if self.ok and self.music_ch:
            self.music_ch.stop()

    def stop_all(self):
        self.stop_music()
        if self.ok:
            pygame.mixer.stop()


def level_music_id(level):
    m = int(level.music)
    if m == 0:
        return THEME_MUSIC.get(level.theme, 1)
    if m >= 6:
        return None
    return m


# ---------------------------------------------------------------------------
# OBJECT CATALOG — Mario Worker Remake categories
# kind: tile | sprite | scenery ;  foot: extra tiles placed (pipes)
# ---------------------------------------------------------------------------
SOLID_TILES = {'ground', 'grass', 'rock', 'brick', 'used', 'bridge', 'cannon', 'cannon_base',
               'qcoin', 'qpower', 'qstar', 'q1up', 'bcoin', 'bpower', 'bstar', 'b1up',
               'pipe_tl', 'pipe_tr', 'pipe_l', 'pipe_r', 'ice', 'conveyor_l', 'conveyor_r', 'spring'}
SEMI_TILES = {'semi'}
HAZARD_TILES = {'spikes'}
CONVEYOR_SPEED = 1.35
HIDDEN_TILES = {'hcoin', 'h1up'}
BUMPABLE = {'brick', 'qcoin', 'qpower', 'qstar', 'q1up', 'bcoin', 'bpower', 'bstar', 'b1up',
            'hcoin', 'h1up'}
ANIM_TILES = {'qcoin', 'qpower', 'qstar', 'q1up', 'coin', 'lava'}

CATEGORIES = ["Terrain", "Bonuses", "Common", "Hazards", "Items", "Bosses", "Marks", "Scenery"]

CATALOG = {}   # id -> dict
CAT_ITEMS = {c: [] for c in CATEGORIES}


def _reg(cat, oid, label, kind, foot=None):
    CATALOG[oid] = dict(id=oid, cat=cat, label=label, kind=kind, foot=foot)
    CAT_ITEMS[cat].append(oid)


for _a in [
    ("Terrain", "ground", "Ground", "tile"), ("Terrain", "grass", "Grass ground", "tile"),
    ("Terrain", "rock", "Hard block", "tile"), ("Terrain", "brick", "Brick", "tile"),
    ("Terrain", "used", "Empty block", "tile"), ("Terrain", "semi", "Platform (semisolid)", "tile"),
    ("Terrain", "pipe_top", "Pipe top", "tile", [(0, 0, 'pipe_tl'), (1, 0, 'pipe_tr')]),
    ("Terrain", "pipe_body", "Pipe body", "tile", [(0, 0, 'pipe_l'), (1, 0, 'pipe_r')]),
    ("Terrain", "water", "Water area", "tile"),
    ("Terrain", "ice", "Slippery ice", "tile"),
    ("Terrain", "spring", "Bounce spring", "tile"),
    ("Terrain", "conveyor_l", "Conveyor left", "tile"),
    ("Terrain", "conveyor_r", "Conveyor right", "tile"),
    ("Bonuses", "qcoin", "? Block (coin)", "tile"), ("Bonuses", "qpower", "? Block (power-up)", "tile"),
    ("Bonuses", "qstar", "? Block (star)", "tile"), ("Bonuses", "q1up", "? Block (1-UP)", "tile"),
    ("Bonuses", "bcoin", "Brick (multi-coin)", "tile"), ("Bonuses", "bpower", "Brick (power-up)", "tile"),
    ("Bonuses", "bstar", "Brick (star)", "tile"), ("Bonuses", "b1up", "Brick (1-UP)", "tile"),
    ("Bonuses", "hcoin", "Hidden block (coin)", "tile"), ("Bonuses", "h1up", "Hidden block (1-UP)", "tile"),
    ("Bonuses", "coin", "Coin", "tile"),
    ("Common", "goomba", "Goomba", "sprite"), ("Common", "koopa_g", "Koopa (green)", "sprite"),
    ("Common", "koopa_r", "Koopa (red)", "sprite"), ("Common", "para_g", "Paratroopa (green, hop)", "sprite"),
    ("Common", "para_r", "Paratroopa (red, fly)", "sprite"), ("Common", "buzzy", "Buzzy Beetle", "sprite"),
    ("Common", "spiny", "Spiny", "sprite"), ("Common", "hammer_bro", "Hammer Bro", "sprite"),
    ("Common", "lakitu", "Lakitu", "sprite"), ("Common", "cheep", "Cheep Cheep", "sprite"),
    ("Common", "blooper", "Blooper", "sprite"),
    ("Hazards", "piranha", "Piranha Plant (on pipe top)", "sprite"), ("Hazards", "podoboo", "Podoboo", "sprite"),
    ("Hazards", "firebar", "Firebar", "sprite"), ("Hazards", "firebar_l", "Long firebar", "sprite"),
    ("Hazards", "cannon", "Bill Blaster", "tile"), ("Hazards", "cannon_base", "Blaster base", "tile"),
    ("Hazards", "lava", "Lava", "tile"), ("Hazards", "spikes", "Spikes", "tile"),
    ("Items", "mushroom", "Super Mushroom", "sprite"), ("Items", "flower", "Fire Flower", "sprite"),
    ("Items", "star", "Starman", "sprite"), ("Items", "1up", "1-UP Mushroom", "sprite"),
    ("Bosses", "bowser", "Bowser", "sprite"), ("Bosses", "axe", "Axe (ends level)", "sprite"),
    ("Bosses", "bridge", "Bowser bridge", "tile"),
    ("Marks", "start", "Player start", "sprite"), ("Marks", "checkpoint", "Level progress", "sprite"),
    ("Marks", "gate", "End level gate", "sprite"), ("Marks", "plat_h", "Platform mark (horiz.)", "sprite"),
    ("Marks", "plat_v", "Platform mark (vert.)", "sprite"), ("Marks", "plat_fall", "Platform mark (falling)", "sprite"),
    ("Marks", "warp_in", "Warp pipe entrance", "sprite"), ("Marks", "warp_out", "Warp pipe exit", "sprite"),
    ("Marks", "turn", "Enemy turn mark", "sprite"),
    ("Scenery", "hill_big", "Big hill", "scenery"), ("Scenery", "hill_small", "Small hill", "scenery"),
    ("Scenery", "bush1", "Bush (1)", "scenery"), ("Scenery", "bush2", "Bush (2)", "scenery"),
    ("Scenery", "bush3", "Bush (3)", "scenery"), ("Scenery", "cloud1", "Cloud (1)", "scenery"),
    ("Scenery", "cloud2", "Cloud (2)", "scenery"), ("Scenery", "cloud3", "Cloud (3)", "scenery"),
    ("Scenery", "fence", "Fence", "scenery"), ("Scenery", "tree", "Tree", "scenery"),
    ("Scenery", "tree_tall", "Tall tree", "scenery"), ("Scenery", "castle", "Castle", "scenery"),
    ("Scenery", "castle_big", "Big castle", "scenery"), ("Scenery", "flag_castle", "Castle flag", "scenery"),
]:
    _reg(*_a)

UNIQUE_SPRITES = {'start', 'gate'}
PARAM_SPRITES = {'warp_in': "Warp ID", 'warp_out': "Warp ID", 'plat_h': "Range", 'plat_v': "Range",
                 'firebar': "Direction", 'firebar_l': "Direction"}
PARAM_DEFAULT = {'warp_in': 1, 'warp_out': 1, 'plat_h': 4, 'plat_v': 4, 'firebar': 0, 'firebar_l': 1}
PARAM_RANGE = {'warp_in': (1, 99), 'warp_out': (1, 99), 'plat_h': (1, 16), 'plat_v': (1, 16),
               'firebar': (0, 1), 'firebar_l': (0, 1)}

# sprite size (px) and how it sits in its anchor cell
SPRITE_SIZE = {
    'goomba': (28, 28), 'koopa_g': (28, 44), 'koopa_r': (28, 44), 'para_g': (28, 44), 'para_r': (28, 44),
    'buzzy': (28, 28), 'spiny': (28, 28), 'hammer_bro': (28, 44), 'lakitu': (28, 30),
    'cheep': (28, 22), 'blooper': (26, 28), 'piranha': (24, 44), 'podoboo': (24, 26),
    'mushroom': (28, 28), 'flower': (28, 28), 'star': (28, 28), '1up': (28, 28),
    'bowser': (56, 60), 'axe': (28, 30), 'checkpoint': (16, 64), 'start': (P_W, P_H_SMALL),
}


def spawn_rect(oid, cx, cy):
    """World-space rect (x, y, w, h) for a sprite anchored on cell (cx, cy)."""
    if oid == 'piranha':          # anchored on the pipe's top-left tile
        w, h = SPRITE_SIZE['piranha']
        return (cx * TS + TS - w / 2, cy * TS - h, w, h)
    if oid in ('firebar', 'firebar_l'):
        return (cx * TS + 8, cy * TS + 8, 16, 16)
    if oid in ('plat_h', 'plat_v', 'plat_fall'):
        return (cx * TS, cy * TS, 96, 16)
    if oid == 'gate':
        return (cx * TS, (cy - 8) * TS, 96, 9 * TS)
    if oid in ('cheep', 'blooper'):
        w, h = SPRITE_SIZE[oid]
        return (cx * TS + (TS - w) / 2, cy * TS + (TS - h) / 2, w, h)
    w, h = SPRITE_SIZE.get(oid, (TS, TS))
    return (cx * TS + (TS - w) / 2, (cy + 1) * TS - h, w, h)


# ---------------------------------------------------------------------------
# LEVEL
# ---------------------------------------------------------------------------
class Level:
    def __init__(self, width=200, height=15):
        self.name = "Untitled"
        self.author = ""
        self.world = 1
        self.stage = 1
        self.time = 400
        self.theme = "overworld"
        self.music = 0
        self.style = "SMB1"
        self.width = width
        self.height = height
        self.tiles = {}       # (x, y) -> id
        self.sprites = {}     # (x, y) -> [id, param]
        self.scenery = {}     # (x, y) -> id

    # -- helpers --------------------------------------------------------
    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def find_sprite(self, oid):
        for pos, (sid, _p) in self.sprites.items():
            if sid == oid:
                return pos
        return None

    def start_cell(self):
        pos = self.find_sprite('start')
        if pos is not None:
            return pos
        for x in range(3, min(self.width, 20)):
            for y in range(self.height - 1, 0, -1):
                if (self.tiles.get((x, y)) in SOLID_TILES and
                        self.tiles.get((x, y - 1)) not in SOLID_TILES and
                        self.tiles.get((x, y - 2)) not in SOLID_TILES):
                    return (x, y - 1)
        return (3, max(0, self.height - 3))

    def resize(self, w, h):
        w = max(MIN_W, min(MAX_W, int(w)))
        h = max(MIN_H, min(MAX_H, int(h)))
        dy = h - self.height          # keep the floor anchored to the bottom
        def move(d):
            return {(x, y + dy): v for (x, y), v in d.items() if 0 <= x < w and 0 <= y + dy < h}
        self.tiles = move(self.tiles)
        self.sprites = move(self.sprites)
        self.scenery = move(self.scenery)
        self.width, self.height = w, h

    def copy(self):
        return Level.from_dict(self.to_dict())

    # -- serialisation --------------------------------------------------
    def to_dict(self):
        return {
            "format": "koopa-engine-level", "version": 1,
            "name": self.name, "author": self.author, "world": self.world, "stage": self.stage,
            "time": self.time, "theme": self.theme, "music": self.music, "style": self.style,
            "width": self.width, "height": self.height,
            "tiles": sorted([x, y, t] for (x, y), t in self.tiles.items()),
            "sprites": sorted([x, y, s, p] for (x, y), (s, p) in self.sprites.items()),
            "scenery": sorted([x, y, s] for (x, y), s in self.scenery.items()),
        }

    @classmethod
    def from_dict(cls, d):
        if d.get("format") not in (None, "koopa-worker-mw", "koopa-engine-level"):
            raise ValueError("not a koopa worker / Mario Worker level")
        lv = cls(int(d.get("width", 200)), int(d.get("height", 15)))
        lv.width = max(MIN_W, min(MAX_W, lv.width))
        lv.height = max(MIN_H, min(MAX_H, lv.height))
        lv.name = str(d.get("name", "Untitled"))[:32]
        lv.author = str(d.get("author", ""))[:32]
        lv.world = max(1, min(99, int(d.get("world", 1))))
        lv.stage = max(1, min(99, int(d.get("stage", 1))))
        lv.time = max(0, min(999, int(d.get("time", 400))))
        th = d.get("theme", "overworld")
        lv.theme = th if th in THEMES else "overworld"
        lv.music = max(0, min(len(MUSIC_LABELS) - 1, int(d.get("music", 0))))
        lv.style = d.get("style", "SMB1") if d.get("style", "SMB1") in GAME_STYLES else "SMB1"
        tile_ids = {i for i, c in CATALOG.items() if c['kind'] == 'tile'} | \
                   {'pipe_tl', 'pipe_tr', 'pipe_l', 'pipe_r'}
        for x, y, t in d.get("tiles", []):
            if t in tile_ids and lv.in_bounds(int(x), int(y)):
                lv.tiles[(int(x), int(y))] = t
        for item in d.get("sprites", []):
            x, y, s = item[0], item[1], item[2]
            p = item[3] if len(item) > 3 else PARAM_DEFAULT.get(s, 0)
            if s in CATALOG and CATALOG[s]['kind'] == 'sprite' and lv.in_bounds(int(x), int(y)):
                lv.sprites[(int(x), int(y))] = [s, int(p)]
        for x, y, s in d.get("scenery", []):
            if s in CATALOG and CATALOG[s]['kind'] == 'scenery' and lv.in_bounds(int(x), int(y)):
                lv.scenery[(int(x), int(y))] = s
        return lv


def save_level(path, level):
    if not path.lower().endswith((LEVEL_EXT, ".json")):
        path += LEVEL_EXT
    data = json.dumps(level.to_dict(), separators=(',', ':')).encode('utf-8')
    if path.lower().endswith('.json'):
        blob = json.dumps(level.to_dict(), indent=1).encode('utf-8')
    else:
        blob = KEN_MAGIC + struct.pack('<HH', KEN_VERSION, 1 if FILES_OFF else 0) + zlib.compress(data, 9)
    tmp = path + ".tmp"
    try:
        with open(tmp, 'wb') as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)          # atomic: never leaves a half-written level


def load_level(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:4] in (KEN_MAGIC, b"KWMW"):
        if len(raw) < 9:
            raise ValueError("truncated .kenigne level header")
        ver, _flags = struct.unpack_from('<HH', raw, 4)
        if ver > KEN_VERSION:
            raise ValueError(f"level made with a newer koopa worker (v{ver})")
        d = json.loads(zlib.decompress(raw[8:]).decode('utf-8'))
    elif raw[:4] == b"KEN\x1a":
        raise ValueError("this is an old SMBX-based .kengine (v1); the pure Mario Worker engine "
                         "can't read SMBX data")
    else:
        try:
            d = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("unknown level file format")
    return Level.from_dict(d)


def new_level():
    lv = Level(200, 15)
    lv.name = "New Level"
    for x in range(lv.width):
        lv.tiles[(x, 13)] = 'ground'
        lv.tiles[(x, 14)] = 'ground'
    lv.sprites[(3, 12)] = ['start', 0]
    lv.sprites[(186, 12)] = ['gate', 0]
    lv.scenery[(190, 12)] = 'castle'
    return lv


def demo_level():
    """Built-in 1-1 style demo (original layout)."""
    lv = Level(220, 15)
    lv.name = "Demo Land"
    lv.world, lv.stage = 1, 1
    pits = {(69, 71), (86, 89), (153, 155)}
    for x in range(lv.width):
        if any(a <= x < b for a, b in pits):
            continue
        lv.tiles[(x, 13)] = 'ground'
        lv.tiles[(x, 14)] = 'ground'
    T = lv.tiles
    T[(16, 9)] = 'qcoin'
    for x, t in zip(range(20, 25), ['brick', 'qpower', 'brick', 'qcoin', 'brick']):
        T[(x, 9)] = t
    T[(22, 5)] = 'qcoin'
    for px, h in ((28, 2), (38, 3), (46, 4), (57, 4)):
        T[(px, 13 - h)] = 'pipe_tl'
        T[(px + 1, 13 - h)] = 'pipe_tr'
        for y in range(13 - h + 1, 13):
            T[(px, y)] = 'pipe_l'
            T[(px + 1, y)] = 'pipe_r'
    T[(64, 8)] = 'h1up'
    for x in range(77, 80):
        T[(x, 9)] = 'brick'
    T[(78, 9)] = 'qpower'
    for x in range(80, 88):
        T[(x, 5)] = 'brick'
    for x in range(91, 94):
        T[(x, 5)] = 'brick'
    T[(94, 5)] = 'qcoin'
    T[(94, 9)] = 'bcoin'
    T[(100, 9)] = 'brick'
    T[(101, 9)] = 'bstar'
    for x in (106, 109, 112):
        T[(x, 9)] = 'qcoin'
    T[(109, 5)] = 'qpower'
    T[(118, 9)] = 'brick'
    for x in range(121, 124):
        T[(x, 5)] = 'brick'
    for x, t in zip(range(128, 132), ['brick', 'qcoin', 'qcoin', 'brick']):
        T[(x, 5)] = t
    T[(129, 9)] = 'brick'
    T[(130, 9)] = 'brick'
    for i in range(4):                       # stairs
        for j in range(i + 1):
            T[(134 + i, 12 - j)] = 'rock'
            T[(143 - i, 12 - j)] = 'rock'
    for i in range(4):
        for j in range(i + 1):
            T[(148 + i, 12 - j)] = 'rock'
        T[(152, 12 - i)] = 'rock'
    for i in range(4):
        for j in range(i + 1):
            T[(155 - i + 3, 12 - j)] = 'rock'
    T[(163, 11)] = 'pipe_tl'; T[(164, 11)] = 'pipe_tr'
    T[(163, 12)] = 'pipe_l'; T[(164, 12)] = 'pipe_r'
    for x, t in zip(range(168, 172), ['brick', 'brick', 'qcoin', 'brick']):
        T[(x, 9)] = t
    T[(179, 11)] = 'pipe_tl'; T[(180, 11)] = 'pipe_tr'
    T[(179, 12)] = 'pipe_l'; T[(180, 12)] = 'pipe_r'
    for i in range(8):                        # final staircase
        for j in range(i + 1):
            T[(181 + 1 + i, 12 - j)] = 'rock'
    for (x, y) in [(40, 7), (41, 7), (42, 7), (95, 3), (96, 3), (97, 3)]:
        T[(x, y)] = 'coin'
    S = lv.sprites
    S[(3, 12)] = ['start', 0]
    for x in (22, 40, 51, 53, 80, 82, 97, 99, 114, 116, 124, 126, 128, 130, 174, 176):
        S[(x, 12 if x not in (80, 82) else 4)] = ['goomba', 0]
    S[(107, 12)] = ['koopa_g', 0]
    S[(120, 12)] = ['para_g', 0]
    S[(38, 10)] = ['piranha', 0]
    S[(57, 9)] = ['piranha', 0]
    S[(100, 12)] = ['checkpoint', 0]
    S[(200, 12)] = ['gate', 0]
    S[(46, 9)] = ['warp_in', 1]
    S[(163, 11)] = ['warp_out', 1]
    B = lv.scenery
    for base in range(0, 220, 48):
        B[(base, 12)] = 'hill_big'
        B[(base + 16, 12)] = 'hill_small'
        B[(base + 11, 12)] = 'bush3'
        B[(base + 23, 12)] = 'bush1'
        B[(base + 41, 12)] = 'bush2'
        B[(base + 8, 2)] = 'cloud1'
        B[(base + 19, 1)] = 'cloud1'
        B[(base + 27, 2)] = 'cloud3'
        B[(base + 36, 1)] = 'cloud2'
    B[(205, 12)] = 'castle'
    return lv


# ---------------------------------------------------------------------------
# WORLD + COLLISION
# ---------------------------------------------------------------------------
def _fl(v):
    return int(math.floor(v))


def cells(a, length):
    return range(_fl(a / TS), _fl((a + length - 0.001) / TS) + 1)


class Body:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.platform = None

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def bottom(self):
        return self.y + self.h

    def rect(self):
        return pygame.Rect(_fl(self.x), _fl(self.y), self.w, self.h)

    def set_height(self, h):
        """Change hitbox height keeping the feet in place."""
        self.y += self.h - h
        self.h = h


class World:
    def __init__(self, level):
        self.level = level
        self.tiles = dict(level.tiles)
        self.cw, self.ch = level.width, level.height
        self.W, self.H = level.width * TS, level.height * TS
        self.theme = level.theme
        self.all_water = level.theme == 'underwater'
        self.platforms = []
        self.turns = {pos for pos, (s, _p) in level.sprites.items() if s == 'turn'}

    def tile(self, tx, ty):
        return self.tiles.get((tx, ty))

    def solid(self, tx, ty):
        if tx < 0 or tx >= self.cw:
            return True                      # level side walls
        if ty < 0 or ty >= self.ch:
            return False
        return self.tiles.get((tx, ty)) in SOLID_TILES

    def in_water(self, px, py):
        if self.all_water:
            return True
        return self.tiles.get((_fl(px / TS), _fl(py / TS))) == 'water'


def move_body(world, b, *, semis=True, turns=False, hidden=False, platforms=True):
    """Axis-separated swept tile collision; never tunnel across a tile boundary."""
    hit = {'left': False, 'right': False, 'down': False, 'up': []}
    old_x = b.x
    b.x += b.vx
    if b.vx > 0:
        for tx in range(_fl((old_x + b.w - .001) / TS),
                        _fl((b.x + b.w - .001) / TS) + 1):
            if any(world.solid(tx, ty) or (turns and (tx, ty) in world.turns)
                   for ty in cells(b.y, b.h)):
                b.x = tx * TS - b.w
                hit['right'] = True
                break
    elif b.vx < 0:
        for tx in range(_fl(old_x / TS), _fl(b.x / TS) - 1, -1):
            if any(world.solid(tx, ty) or (turns and (tx, ty) in world.turns)
                   for ty in cells(b.y, b.h)):
                b.x = (tx + 1) * TS
                hit['left'] = True
                break
    previous_platform = b.platform
    old_top, old_bottom = b.y, b.bottom
    b.on_ground = False
    b.platform = None
    b.y += b.vy
    if b.vy >= 0:
        first = _fl((old_bottom - .001) / TS)
        last = _fl((b.bottom - .001) / TS)
        for ty in range(first, last + 1):
            top = ty * TS
            if any(world.solid(tx, ty) or
                   (semis and world.tile(tx, ty) in SEMI_TILES and old_bottom <= top + .5)
                   for tx in cells(b.x, b.w)):
                b.y = top - b.h
                b.vy = 0.0
                b.on_ground = True
                hit['down'] = True
                break
        if platforms and not b.on_ground:
            for platform in world.platforms:
                if (b.x + b.w > platform.x and b.x < platform.x + platform.w and
                        old_bottom <= platform.y + .5 <= b.bottom + .5):
                    b.y = platform.y - b.h
                    b.vy = 0.0
                    b.on_ground = True
                    b.platform = platform
                    hit['down'] = True
                    break
    else:
        first = _fl(old_top / TS)
        last = _fl(b.y / TS)
        for ty in range(first, last - 1, -1):
            touched = [(tx, ty) for tx in cells(b.x, b.w)
                       if world.solid(tx, ty) or
                       (hidden and world.tile(tx, ty) in HIDDEN_TILES and
                        old_top >= (ty + 1) * TS - .5)]
            if touched:
                hit['up'].extend(touched)
                b.y = (ty + 1) * TS
                b.vy = 0.0
                break
    return hit

# ---------------------------------------------------------------------------
# SESSION (lives / score / coins carried between deaths)
# ---------------------------------------------------------------------------
class Session:
    def __init__(self, lives=3):
        self.lives = lives
        self.score = 0
        self.coins = 0
        self.power = SMALL

    def add_coin(self, game):
        self.coins += 1
        self.score += 200
        Audio.get().play('coin')
        if self.coins >= 100:
            self.coins -= 100
            self.one_up(game)

    def one_up(self, game, x=None, y=None):
        self.lives = min(99, self.lives + 1)
        Audio.get().play('oneup')
        if x is not None:
            game.fx.append(ScorePop(x, y, "1UP"))


STOMP_CHAIN = [100, 200, 400, 500, 800, 1000, 2000, 4000, 5000, 8000]


def chain_award(game, idx, x, y):
    if idx < len(STOMP_CHAIN):
        game.session.score += STOMP_CHAIN[idx]
        game.fx.append(ScorePop(x, y, str(STOMP_CHAIN[idx])))
    else:
        game.session.one_up(game, x, y)


# ---------------------------------------------------------------------------
# EFFECTS
# ---------------------------------------------------------------------------
class ScorePop:
    def __init__(self, x, y, text):
        self.x, self.y, self.text, self.t = x, y, text, 0
        self.dead = False

    def update(self):
        self.t += 1
        self.y -= 1.2 if self.t < 30 else 0.3
        self.dead = self.t > 50

    def draw(self, surf, cx, cy):
        btext(surf, self.text, int(self.x - cx), int(self.y - cy), 1 if len(self.text) > 4 else 2,
              center=True)


class Debris:
    def __init__(self, x, y, vx, vy, theme):
        self.x, self.y, self.vx, self.vy, self.theme = x, y, vx, vy, theme
        self.t = 0
        self.dead = False

    def update(self):
        self.t += 1
        self.vy += 0.5
        self.x += self.vx
        self.y += self.vy
        self.dead = self.t > 120

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('debris', (self.t // 4) % 4, False, self.theme), (self.x - cx, self.y - cy))


class CoinPop:
    def __init__(self, game, x, y):
        self.game, self.x, self.y, self.vy, self.t = game, x, y, -9.0, 0
        self.dead = False

    def update(self):
        self.t += 1
        self.vy += 0.6
        self.y += self.vy
        if self.t >= 28:
            self.dead = True
            self.game.fx.append(ScorePop(self.x + 16, self.y, "200"))

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('coin', self.t // 2), (self.x - cx, self.y - cy))


class Puff:
    def __init__(self, x, y):
        self.x, self.y, self.t, self.dead = x, y, 0, False

    def update(self):
        self.t += 1
        self.dead = self.t > 12

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('puff', self.t // 4), (self.x - 12 - cx, self.y - 12 - cy))


# ---------------------------------------------------------------------------
# ENTITIES
# ---------------------------------------------------------------------------
class Ent(Body):
    stompable = True
    fire_kill = True
    shell_kill = True
    star_kill = True
    bump_kill = True
    hurts = True
    enemy = True
    item = False
    walker = False
    behind = False                    # drawn behind tiles (piranhas, emerging items)
    flip_spr = None                   # sprite name used when killed by flip

    def __init__(self, game, x, y, w, h):
        super().__init__(x, y, w, h)
        self.g = game
        self.dir = -1
        self.dead = False
        self.active = False
        self.t = 0

    def activate_check(self, cam_x):
        if not self.active and self.x < cam_x + WIN_W + 48 and self.x + self.w > cam_x - 48:
            self.active = True
            self.on_activate()

    def on_activate(self):
        pass

    def update(self):
        pass

    def draw(self, surf, cx, cy):
        pass

    def face_player(self):
        p = self.g.player
        self.dir = 1 if p.b.cx > self.cx else -1

    # --- reactions -------------------------------------------------------
    def stomp(self, player):
        self.kill_flip()

    def touch(self, player):
        player.hurt()

    def kill_flip(self, score=None):
        if self.dead:
            return
        self.dead = True
        surf = self.sprite_now()
        if surf is not None:
            self.g.ents.append(Corpse(self.g, self.x, self.y, surf, self.dir))
        if score:
            self.g.session.score += score
            self.g.fx.append(ScorePop(self.cx, self.y, str(score)))
        Audio.get().play('kick')

    def fire_hit(self, fb):
        if self.fire_kill:
            self.kill_flip(200)
            return True
        return self.hurts and self.enemy     # immune enemies still absorb the fireball

    def sprite_now(self):
        return None


class Corpse(Ent):
    hurts = False
    enemy = False
    bump_kill = False

    def __init__(self, game, x, y, surf, d):
        super().__init__(game, x, y, surf.get_width(), surf.get_height())
        self.surf = pygame.transform.flip(surf, False, True)
        self.vy = -6.0
        self.vx = 1.2 * (-d if d else 1)
        self.active = True

    def update(self):
        self.vy = min(self.vy + 0.45, 9)
        self.x += self.vx
        self.y += self.vy
        if self.y > self.g.world.H + 64:
            self.dead = True

    def draw(self, surf, cx, cy):
        surf.blit(self.surf, (self.x - cx, self.y - cy))


class Flat(Ent):
    hurts = False
    enemy = False
    bump_kill = False

    def __init__(self, game, x, bottom, theme):
        super().__init__(game, x, bottom - 16, 28, 16)
        self.theme = theme
        self.active = True

    def update(self):
        self.t += 1
        if self.t > 30:
            self.dead = True

    def draw(self, surf, cx, cy):
        s = ART.spr('goomba_flat', 0, False, self.theme)
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class Walker(Ent):
    walker = True
    speed = 1.0
    ledge_turn = False
    name = 'goomba'

    def walk(self):
        self.vx = self.speed * self.dir
        self.vy = min(self.vy + PHYS['npc_grav'], PHYS['npc_max_fall'])
        if self.platform is not None:
            self.x += self.platform.dx
            self.y += self.platform.dy
        was_ground = self.on_ground
        hit = move_body(self.g.world, self, turns=True)
        if hit['left'] or hit['right']:
            self.dir *= -1
        if self.ledge_turn and was_ground and self.on_ground:
            ahead = self.x + (self.w + 2 if self.dir > 0 else -2)
            tx, ty = _fl(ahead / TS), _fl((self.bottom + 2) / TS)
            w = self.g.world
            if not w.solid(tx, ty) and w.tile(tx, ty) not in SEMI_TILES and self.platform is None:
                self.dir *= -1
                self.x -= self.vx
        if self.y > self.g.world.H + 64:
            self.dead = True

    def update(self):
        self.t += 1
        self.walk()

    def frame(self):
        return (self.t // 8) % 2


class Goomba(Walker):
    def stomp(self, player):
        self.dead = True
        self.g.ents.append(Flat(self.g, self.x, self.bottom, self.g.gtheme))
        Audio.get().play('stomp')

    def sprite_now(self):
        return ART.spr('goomba', self.frame(), False, self.g.gtheme)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class Koopa(Walker):
    def __init__(self, game, x, y, color):
        super().__init__(game, x, y, 28, 44)
        self.color = color
        self.ledge_turn = color == 'r'

    def stomp(self, player):
        self.dead = True
        self.g.ents.append(Shell(self.g, self.cx - 14, self.bottom - 28, self.color))
        Audio.get().play('stomp')

    def sprite_now(self):
        return ART.spr('koopa_' + self.color, self.frame(), self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class Shell(Walker):
    fire_kill = True

    def __init__(self, game, x, y, color, buzzy=False):
        super().__init__(game, x, y, 28, 28)
        self.color = color
        self.buzzy = buzzy
        self.speed = 0.0
        self.moving = False
        self.idle_t = 0
        self.safe = 0
        self.combo = 0
        self.active = True
        if buzzy:
            self.fire_kill = False

    def kick(self, player):
        self.dir = 1 if player.b.cx < self.cx else -1
        self.moving = True
        self.speed = 7.0
        self.safe = 12
        self.combo = 0
        self.g.session.score += 400
        self.g.fx.append(ScorePop(self.cx, self.y, "400"))
        Audio.get().play('kick')

    def stomp(self, player):
        if self.moving:
            self.moving = False
            self.speed = 0.0
            self.idle_t = 0
            Audio.get().play('stomp')
        else:
            self.kick(player)

    def touch(self, player):
        if not self.moving:
            self.kick(player)
        elif self.safe <= 0:
            player.hurt()

    def update(self):
        self.t += 1
        if self.safe > 0:
            self.safe -= 1
        before = self.dir
        self.walk()
        if self.moving and before != self.dir and self.g.on_screen(self):
            Audio.get().play('bump')
        if not self.moving:
            self.idle_t += 1
            if self.idle_t > 480 and not self.buzzy:
                self.dead = True
                k = Koopa(self.g, self.cx - 14, self.bottom - 44, self.color)
                k.active = True
                k.face_player()
                self.g.ents.append(k)
        else:
            for e in self.g.ents:
                if e is self or e.dead or not e.active or not e.shell_kill or not e.enemy:
                    continue
                if self.rect().colliderect(e.rect()):
                    e.kill_flip()
                    chain_award(self.g, min(self.combo + 3, 99), e.cx, e.y)
                    self.combo += 1

    def sprite_now(self):
        if self.buzzy:
            return ART.spr('buzzy_shell', 0)
        wig = 1 if (not self.moving and self.idle_t > 400 and (self.t // 4) % 2) else 0
        return ART.spr('shell_' + self.color, wig)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class ParaGreen(Walker):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 44)

    def update(self):
        self.t += 1
        if self.on_ground:
            self.vy = -8.0
        self.walk()

    def stomp(self, player):
        self.dead = True
        k = Koopa(self.g, self.x, self.y, 'g')
        k.active, k.dir = True, self.dir
        self.g.ents.append(k)
        Audio.get().play('stomp')

    def sprite_now(self):
        return ART.spr('para_g', (self.t // 6) % 2, self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class ParaRed(Ent):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 44)
        self.oy = y

    def update(self):
        self.t += 1
        self.y = self.oy + math.sin(self.t * 0.025) * 3 * TS * 0.5 - 1.5 * TS * 0.5
        self.face_player()

    def stomp(self, player):
        self.dead = True
        k = Koopa(self.g, self.x, self.y, 'r')
        k.active, k.dir = True, self.dir
        self.g.ents.append(k)
        Audio.get().play('stomp')

    def sprite_now(self):
        return ART.spr('para_r', (self.t // 6) % 2, self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class Buzzy(Walker):
    fire_kill = False

    def stomp(self, player):
        self.dead = True
        self.g.ents.append(Shell(self.g, self.x, self.bottom - 28, 'g', buzzy=True))
        Audio.get().play('stomp')

    def sprite_now(self):
        return ART.spr('buzzy', 0, self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        bob = (self.t // 8) % 2
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy - bob))


class Spiny(Walker):
    stompable = False

    def sprite_now(self):
        return ART.spr('spiny', self.frame(), self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


class SpinyEgg(Ent):
    stompable = False

    def __init__(self, game, x, y):
        super().__init__(game, x, y, 24, 24)
        self.vy = -4.0
        self.active = True

    def update(self):
        self.t += 1
        self.vy = min(self.vy + 0.3, 7)
        move_body(self.g.world, self)
        if self.on_ground:
            self.dead = True
            s = Spiny(self.g, self.x, self.bottom - 28, 28, 28)
            s.active = True
            s.face_player()
            self.g.ents.append(s)
        if self.y > self.g.world.H + 64:
            self.dead = True

    def sprite_now(self):
        return ART.spr('spiny_egg', (self.t // 6) % 4)

    def draw(self, surf, cx, cy):
        surf.blit(self.sprite_now(), (self.cx - 16 - cx, self.cy - 16 - cy))


class HammerBro(Ent):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 44)
        self.ox = x
        self.wdir = 1
        self.throw_t = random.randint(40, 90)
        self.jump_t = random.randint(150, 260)
        self.arm = 0

    def update(self):
        self.t += 1
        self.face_player()
        if self.x > self.ox + TS:
            self.wdir = -1
        elif self.x < self.ox - TS:
            self.wdir = 1
        self.vx = 0.7 * self.wdir
        self.vy = min(self.vy + PHYS['npc_grav'], PHYS['npc_max_fall'])
        self.jump_t -= 1
        if self.jump_t <= 0 and self.on_ground:
            self.vy = -9.0
            self.jump_t = random.randint(180, 300)
        hit = move_body(self.g.world, self, turns=True)
        if hit['left'] or hit['right']:
            self.wdir *= -1
        self.throw_t -= 1
        if self.arm:
            self.arm -= 1
        p = self.g.player
        if self.throw_t <= 0:
            self.throw_t = random.randint(45, 110)
            if abs(p.b.cx - self.cx) < 480:
                self.g.ents.append(Hammer(self.g, self.cx - 8 + 6 * self.dir, self.y - 4, self.dir))
                self.arm = 10
        if self.y > self.g.world.H + 64:
            self.dead = True

    def sprite_now(self):
        return ART.spr('hammer_bro', 1 if self.arm else 0, self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))
        if self.arm:
            surf.blit(ART.spr('hammer', 0), (self.cx - 10 + 8 * self.dir - cx, self.y - 14 - cy))


class Hammer(Ent):
    stompable = False
    fire_kill = False
    shell_kill = False
    star_kill = False
    bump_kill = False

    def __init__(self, game, x, y, d):
        super().__init__(game, x, y, 14, 14)
        self.vx, self.vy, self.active, self.dir = 2.4 * d, -8.0, True, d

    def fire_hit(self, fb):
        return False

    def update(self):
        self.t += 1
        self.vy = min(self.vy + 0.35, 9)
        self.x += self.vx
        self.y += self.vy
        if self.y > self.g.world.H + 64:
            self.dead = True

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('hammer', (self.t // 4) % 4), (self.x - 3 - cx, self.y - 3 - cy))


class Lakitu(Ent):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 30)
        self.throw_t = 150

    def update(self):
        self.t += 1
        p = self.g.player
        target = p.b.cx + p.b.vx * 40 - self.w / 2
        self.vx += 0.08 if target > self.x else -0.08
        self.vx = max(-3.6, min(3.6, self.vx))
        self.x += self.vx
        self.x = max(0, min(self.g.world.W - self.w, self.x))
        self.y = self.y + math.sin(self.t * 0.05) * 0.3
        self.face_player()
        self.throw_t -= 1
        if self.throw_t <= 0:
            self.throw_t = random.randint(160, 260)
            n = sum(1 for e in self.g.ents if isinstance(e, (Spiny, SpinyEgg)) and not e.dead)
            if n < 4:
                self.g.ents.append(SpinyEgg(self.g, self.cx - 12, self.y - 8))

    def sprite_now(self):
        return ART.spr('lakitu', 0, self.dir > 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        hide = 6 if self.throw_t < 20 else 0
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy + hide))


class Cheep(Ent):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 22)
        self.oy = y
        self.speed = random.choice((0.6, 0.9))

    def on_activate(self):
        self.stompable = not self.g.world.in_water(self.cx, self.cy)

    def update(self):
        self.t += 1
        self.x += -self.speed
        self.y = self.oy + math.sin(self.t * 0.04) * 10
        if self.x < self.g.cam_x - 3 * WIN_W:
            self.dead = True

    def sprite_now(self):
        return ART.spr('cheep', (self.t // 10) % 2, False)

    def draw(self, surf, cx, cy):
        surf.blit(self.sprite_now(), (self.cx - 16 - cx, self.cy - 16 - cy))


class Blooper(Ent):
    def __init__(self, game, x, y):
        super().__init__(game, x, y, 26, 28)
        self.phase = 0
        self.pt = 0

    def on_activate(self):
        self.stompable = not self.g.world.in_water(self.cx, self.cy)

    def update(self):
        self.t += 1
        self.pt += 1
        p = self.g.player
        if self.phase == 0:          # sinking
            self.vx, self.vy = 0, 0.9
            if self.pt > 30 and (self.bottom >= p.b.y - 8 or self.pt > 70):
                self.phase, self.pt = 1, 0
                self.dir = 1 if p.b.cx > self.cx else -1
        else:                        # thrust
            self.vx, self.vy = 2.0 * self.dir, -2.4
            if self.pt > 22:
                self.phase, self.pt = 0, 0
        self.x += self.vx
        self.y = max(TS, min(self.g.world.H - self.h - TS, self.y + self.vy))

    def sprite_now(self):
        return ART.spr('blooper', 1 if self.phase == 1 else 0)

    def draw(self, surf, cx, cy):
        surf.blit(self.sprite_now(), (self.cx - 16 - cx, self.cy - 16 - cy))


class Piranha(Ent):
    stompable = False
    behind = True
    bump_kill = False

    def __init__(self, game, x, base_y):
        super().__init__(game, x, base_y, 24, 0)
        self.base = base_y
        self.out = 0.0
        self.state = 'down'
        self.wait = 60
        self.full = 44

    def update(self):
        self.t += 1
        p = self.g.player
        if self.state == 'down':
            self.wait -= 1
            near = abs(p.b.cx - self.cx) < TS * 1.6 and p.b.bottom > self.base - 3 * TS
            if self.wait <= 0 and not near:
                self.state = 'rise'
        elif self.state == 'rise':
            self.out = min(self.full, self.out + 1.0)
            if self.out >= self.full:
                self.state, self.wait = 'up', 75
        elif self.state == 'up':
            self.wait -= 1
            if self.wait <= 0:
                self.state = 'sink'
        else:
            self.out = max(0.0, self.out - 1.0)
            if self.out <= 0:
                self.state, self.wait = 'down', 75
        self.y = self.base - self.out
        self.h = max(1, int(self.out) - 2)
        self.hurts = self.out > 4

    def sprite_now(self):
        return ART.spr('piranha', (self.t // 10) % 2)

    def draw(self, surf, cx, cy):
        if self.out <= 0:
            return
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.base - self.out - 2 - cy))


class Podoboo(Ent):
    stompable = False
    fire_kill = False
    shell_kill = False
    star_kill = False
    bump_kill = False

    def __init__(self, game, x, bottom):
        super().__init__(game, x, bottom + 8, 24, 26)
        self.home = bottom + 8
        self.wait = random.randint(30, 90)

    def fire_hit(self, fb):
        return False

    def update(self):
        self.t += 1
        self.hurts = self.wait == 0
        if self.wait > 0:
            self.wait -= 1
            self.y = self.home
            if self.wait == 0:
                self.vy = -11.5
            return
        self.vy += 0.36
        self.y += self.vy
        if self.y >= self.home and self.vy > 0:
            self.y = self.home
            self.wait = random.randint(50, 110)

    def sprite_now(self):
        return ART.spr('podoboo', 1 if self.vy > 0 else 0)

    def draw(self, surf, cx, cy):
        if self.wait > 0:
            return
        surf.blit(self.sprite_now(), (self.cx - 16 - cx, self.y - 4 - cy))


class Firebar(Ent):
    stompable = False
    fire_kill = False
    shell_kill = False
    star_kill = False
    bump_kill = False

    def __init__(self, game, ccx, ccy, n, cw):
        super().__init__(game, ccx - 8, ccy - 8, 16, 16)
        self.ox, self.oy = ccx, ccy
        self.n = n
        self.ang = 0.0
        self.spd = -1.9 if cw else 1.9

    def fire_hit(self, fb):
        return False

    def balls(self):
        a = math.radians(self.ang)
        return [(self.ox + math.cos(a) * i * 16, self.oy + math.sin(a) * i * 16) for i in range(self.n)]

    def update(self):
        self.ang = (self.ang + self.spd) % 360

    def collides(self, rect):
        r = rect.inflate(-4, -4)
        for bx, by in self.balls():
            if r.colliderect(pygame.Rect(bx - 5, by - 5, 10, 10)):
                return True
        return False

    def draw(self, surf, cx, cy):
        for i, (bx, by) in enumerate(self.balls()):
            surf.blit(ART.spr('fireball', (self.g.frame // 3 + i) % 4), (bx - 8 - cx, by - 8 - cy))


class Bullet(Ent):
    fire_kill = False
    shell_kill = True
    bump_kill = False

    def __init__(self, game, x, y, d):
        super().__init__(game, x, y, 28, 26)
        self.dir = d
        self.active = True

    def fire_hit(self, fb):
        return True

    def stomp(self, player):
        self.kill_flip(200)
        Audio.get().play('stomp')

    def update(self):
        self.t += 1
        self.x += 2.6 * self.dir
        if abs(self.x - self.g.cam_x) > WIN_W * 2:
            self.dead = True

    def sprite_now(self):
        return ART.spr('bullet', 0, self.dir > 0)

    def draw(self, surf, cx, cy):
        surf.blit(self.sprite_now(), (self.cx - 16 - cx, self.cy - 16 - cy))


class Blaster:
    """Logic for a Bill Blaster tile (drawn by the tile layer)."""

    def __init__(self, game, tx, ty):
        self.g, self.tx, self.ty = game, tx, ty
        self.t = random.randint(60, 160)

    def update(self):
        self.t -= 1
        if self.t > 0:
            return
        self.t = random.randint(150, 260)
        if self.g.world.tile(self.tx, self.ty) != 'cannon':
            return
        p = self.g.player
        cx = self.tx * TS + TS / 2
        dx = p.b.cx - cx
        if abs(dx) < 56 or abs(dx) > WIN_W * 0.75:
            return
        d = 1 if dx > 0 else -1
        n = sum(1 for e in self.g.ents if isinstance(e, Bullet) and not e.dead)
        if n < 4:
            self.g.ents.append(Bullet(self.g, self.tx * TS + (TS if d > 0 else -28), self.ty * TS + 3, d))
            Audio.get().play('bump')


class Flame(Ent):
    stompable = False
    fire_kill = False
    shell_kill = False
    star_kill = False
    bump_kill = False

    def __init__(self, game, x, y, d, ty):
        super().__init__(game, x, y, 44, 12)
        self.dir, self.ty, self.active = d, ty, True

    def fire_hit(self, fb):
        return False

    def update(self):
        self.x += 2.4 * self.dir
        if abs(self.y - self.ty) > 1:
            self.y += 0.6 if self.ty > self.y else -0.6
        if abs(self.x - self.g.cam_x) > WIN_W * 2:
            self.dead = True

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('flame', (self.g.frame // 4) % 2, self.dir > 0), (self.x - 2 - cx, self.y - 2 - cy))


class Bowser(Ent):
    stompable = False
    shell_kill = False
    star_kill = False
    bump_kill = False

    def __init__(self, game, x, y):
        super().__init__(game, x, y, 56, 60)
        self.ox = x
        self.hp = 5
        self.wdir = -1
        self.fire_t = 120
        self.jump_t = 200
        self.mouth = 0
        self.hurt_t = 0
        self.falling = False

    def fire_hit(self, fb):
        if self.falling:
            return False
        self.hp -= 1
        self.hurt_t = 10
        Audio.get().play('bump')
        if self.hp <= 0:
            self.kill_flip(5000)
        return True

    def update(self):
        self.t += 1
        if self.hurt_t:
            self.hurt_t -= 1
        if self.falling:
            self.vy = min(self.vy + 0.3, 6)
            self.y += self.vy
            if self.y > self.g.world.H + 64:
                self.dead = True
            return
        self.face_player()
        if self.t % 90 == 0:
            self.wdir = random.choice((-1, 1))
        if self.x < self.ox - 2 * TS:
            self.wdir = 1
        elif self.x > self.ox + 2 * TS:
            self.wdir = -1
        self.vx = 0.8 * self.wdir
        self.vy = min(self.vy + 0.4, 8)
        self.jump_t -= 1
        if self.jump_t <= 0 and self.on_ground:
            self.vy = -6.5
            self.jump_t = random.randint(160, 280)
        move_body(self.g.world, self, turns=True)
        self.fire_t -= 1
        if self.mouth:
            self.mouth -= 1
        if self.fire_t <= 0:
            self.fire_t = random.randint(130, 210)
            p = self.g.player
            if abs(p.b.cx - self.cx) < WIN_W:
                fx = self.x - 40 if self.dir < 0 else self.x + self.w - 4
                ty = min(p.b.y + 8, self.y + 40)
                self.g.ents.append(Flame(self.g, fx, self.y + 14, self.dir, ty))
                self.mouth = 20
                Audio.get().play('bowserfire')
        if self.y > self.g.world.H + 64:
            self.dead = True

    def sprite_now(self):
        fr = 2 if self.mouth else (self.t // 16) % 2
        return ART.spr('bowser', fr, self.dir > 0)

    def draw(self, surf, cx, cy):
        if self.hurt_t and self.hurt_t % 2:
            return
        surf.blit(self.sprite_now(), (self.cx - 32 - cx, self.bottom - 64 - cy))


class Axe(Ent):
    stompable = False
    fire_kill = shell_kill = star_kill = bump_kill = False
    hurts = False
    enemy = False

    def __init__(self, game, x, y):
        super().__init__(game, x, y, 28, 30)

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('axe', (self.g.frame // 20) % 2), (self.cx - 16 - cx, self.bottom - 32 - cy))


# ----- items ---------------------------------------------------------------
class Item(Walker):
    enemy = False
    item = True
    hurts = False
    stompable = False
    fire_kill = shell_kill = star_kill = False
    kind = 'mushroom'

    def __init__(self, game, x, y, kind, emerge=False):
        super().__init__(game, x, y, 28, 28)
        self.kind = kind
        self.emerge = 32 if emerge else 0
        self.dir = 1
        self.speed = {'mushroom': 2.0, '1up': 2.0, 'star': 2.4, 'flower': 0.0}[kind]
        self.behind = bool(emerge)
        if emerge:
            self.active = True
            self.y += TS             # start inside the block

    def update(self):
        self.t += 1
        if self.emerge > 0:
            self.emerge -= 1
            self.y -= 1
            if self.emerge == 0:
                self.behind = False
                if self.kind == 'star':
                    self.vy = -5
            return
        if self.kind == 'flower':
            self.vy = min(self.vy + PHYS['npc_grav'], 8)
            self.vx = 0
            move_body(self.g.world, self)
            return
        if self.kind == 'star' and self.on_ground:
            self.vy = -7.5
        self.walk()
        if self.kind == 'star':
            self.vy -= PHYS['npc_grav'] * 0.35   # floatier arc

    def touch(self, player):
        if self.emerge > 8:
            return
        self.dead = True
        player.collect(self.kind, self)

    def sprite_now(self):
        if self.kind in ('flower', 'star'):
            return ART.spr(self.kind, self.t // 4)
        return ART.spr(self.kind, 0)

    def draw(self, surf, cx, cy):
        s = self.sprite_now()
        surf.blit(s, (self.cx - 16 - cx, self.bottom - s.get_height() - cy))


# ---------------------------------------------------------------------------
# MOVING PLATFORMS / GATE / CHECKPOINT
# ---------------------------------------------------------------------------
class Lift:
    def __init__(self, x, y, kind, rng):
        self.x, self.y, self.w, self.h = float(x), float(y), 96, 16
        self.ox, self.oy = self.x, self.y
        self.kind, self.rng = kind, rng
        self.dx = self.dy = 0.0
        self.t = 0
        self.fall = False

    def update(self, game):
        self.t += 1
        px, py = self.x, self.y
        if self.kind == 'plat_h':
            self.x = self.ox + (1 - math.cos(self.t * 0.02)) * 0.5 * self.rng * TS
        elif self.kind == 'plat_v':
            self.y = self.oy - (1 - math.cos(self.t * 0.02)) * 0.5 * self.rng * TS
        else:
            if game.player.b.platform is self:
                self.fall = True
            if self.fall:
                self.y += 2.2
        self.dx, self.dy = self.x - px, self.y - py

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('lift'), (self.x - cx, self.y - cy))


class Gate:
    def __init__(self, cx, cy):
        self.x = cx * TS
        self.bottom = (cy + 1) * TS
        self.top = self.bottom - 9 * TS
        self.bar_y = float(self.top + 24)
        self.vy = 2.0
        self.taken = False
        self.passed = False

    def bar_rect(self):
        return pygame.Rect(self.x + 16, int(self.bar_y), 64, 12)

    def update(self):
        if self.taken:
            return
        self.bar_y += self.vy
        if self.bar_y < self.top + 24 or self.bar_y > self.bottom - 40:
            self.vy = -self.vy

    def bonus(self):
        frac = 1 - (self.bar_y - (self.top + 24)) / max(1, (self.bottom - 40) - (self.top + 24))
        for lim, pts in ((0.9, 10000), (0.75, 5000), (0.55, 2000), (0.4, 1000), (0.25, 500), (0.1, 200)):
            if frac >= lim:
                return pts
        return 100

    def draw_back(self, surf, cx, cy):
        for px in (self.x, self.x + 80):
            for y in range(self.top, self.bottom, 16):
                col = (252, 216, 40) if ((y - self.top) // 16) % 2 == 0 else (200, 76, 12)
                pygame.draw.rect(surf, col, (px - cx, y - cy, 16, 16))
            pygame.draw.rect(surf, (0, 0, 0), (px - cx, self.top - cy, 16, self.bottom - self.top), 2)
            pygame.draw.circle(surf, (252, 216, 40), (px + 8 - cx, self.top - 6 - cy), 8)
            pygame.draw.circle(surf, (0, 0, 0), (px + 8 - cx, self.top - 6 - cy), 8, 2)

    def draw_bar(self, surf, cx, cy):
        if self.taken:
            return
        r = self.bar_rect().move(-cx, -cy)
        pygame.draw.rect(surf, (216, 40, 0), r)
        for i in range(0, 64, 16):
            pygame.draw.rect(surf, (252, 252, 252), (r.x + i, r.y, 8, r.h))
        pygame.draw.rect(surf, (0, 0, 0), r, 2)


class Checkpoint:
    def __init__(self, cx, cy):
        self.cell = (cx, cy)
        self.x = cx * TS + 8
        self.bottom = (cy + 1) * TS
        self.on = False

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('checkpoint', 1 if self.on else 0), (self.x - 8 - cx, self.bottom - 64 - cy))


# ---------------------------------------------------------------------------
# PLAYER FIREBALL
# ---------------------------------------------------------------------------
class PFire(Body):
    def __init__(self, game, x, y, d):
        super().__init__(x, y, 12, 12)
        self.g = game
        self.vx, self.vy = 7.0 * d, 4.0
        self.dead = False
        self.t = 0

    def update(self):
        self.t += 1
        self.vy = min(self.vy + 0.6, 6)
        hit = move_body(self.g.world, self)
        if hit['down']:
            self.vy = -4.4
        if hit['left'] or hit['right'] or hit['up']:
            self.explode()
            return
        if not self.g.on_screen(self, 32) or self.y > self.g.world.H:
            self.dead = True
            return
        r = self.rect()
        for e in self.g.ents:
            if e.dead or not e.active or not (e.enemy and e.hurts):
                continue
            if isinstance(e, Firebar):
                continue
            if r.colliderect(e.rect()):
                if e.fire_hit(self):
                    self.explode()
                    return

    def explode(self):
        self.dead = True
        self.g.fx.append(Puff(self.cx, self.cy))
        Audio.get().play('bump')

    def draw(self, surf, cx, cy):
        surf.blit(ART.spr('fireball', (self.t // 3) % 4), (self.x - 2 - cx, self.y - 2 - cy))


# ---------------------------------------------------------------------------
# PLAYER
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, game, x, y, power):
        self.g = game
        self.power = power
        self.b = Body(x, y, P_W, P_H_SMALL if power == SMALL else P_H_BIG)
        self.facing = 1
        self.inv = 0
        self.star = 0
        self.duck = False
        self.jumping = False
        self.skid = False
        self.anim = 0.0
        self.fire_cd = 0
        self.throw = 0
        self.grow = 0
        self.chain = 0
        self.star_chain = 0
        self.coyote = 0
        self.jbuf = 0
        self.prev_bottom = self.b.bottom
        self.swimming = False
        self.frozen = False

    # -- helpers ----------------------------------------------------------
    def _space_for(self, h):
        b = self.b
        top = b.bottom - h
        for ty in cells(top, h):
            for tx in cells(b.x, b.w):
                if self.g.world.solid(tx, ty):
                    return False
        return True

    def set_power(self, p):
        old = self.power
        self.power = p
        if p == SMALL:
            self.duck = False
            self.b.set_height(P_H_SMALL)
        elif old == SMALL:
            if self._space_for(P_H_BIG):
                self.b.set_height(P_H_BIG)
            else:
                self.duck = True          # stay crouched under a low ceiling
        self.g.session.power = p

    def hurt(self):
        if self.inv > 0 or self.star > 0 or self.g.state != 'play':
            return
        if self.power > SMALL:
            self.set_power(SMALL)
            self.inv = 120
            self.grow = -40
            Audio.get().play('shrink')
        else:
            self.g.die()

    def collect(self, kind, src):
        s = self.g.session
        x, y = src.cx, src.y
        if kind == 'mushroom':
            if self.power == SMALL:
                self.set_power(BIG)
                self.grow = 40
            Audio.get().play('powerup')
            s.score += 1000
            self.g.fx.append(ScorePop(x, y, "1000"))
        elif kind == 'flower':
            if self.power == SMALL:
                self.set_power(BIG)
                self.grow = 40
            elif self.power == BIG:
                self.set_power(FIRE)
            Audio.get().play('powerup')
            s.score += 1000
            self.g.fx.append(ScorePop(x, y, "1000"))
        elif kind == 'star':
            self.star = 600
            self.star_chain = 0
            Audio.get().play('powerup')
            s.score += 1000
            self.g.fx.append(ScorePop(x, y, "1000"))
        elif kind == '1up':
            s.one_up(self.g, x, y)

    # -- update -----------------------------------------------------------
    def update(self, keys, jump_pressed, fire_pressed):
        g, b, w = self.g, self.b, self.g.world
        if self.inv > 0:
            self.inv -= 1
        if self.star > 0:
            self.star -= 1
        if self.grow > 0:
            self.grow -= 1
        elif self.grow < 0:
            self.grow += 1
        if self.fire_cd > 0:
            self.fire_cd -= 1
        if self.throw > 0:
            self.throw -= 1
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        jump_held = keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_k]
        run = keys[pygame.K_x] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or keys[pygame.K_j]
        self.swimming = w.in_water(b.cx, b.y + 8)

        # ducking (big only)
        if self.power > SMALL:
            if down and b.on_ground and not self.duck:
                self.duck = True
                b.set_height(P_H_SMALL)
            elif self.duck and not down and self._space_for(P_H_BIG):
                self.duck = False
                b.set_height(P_H_BIG)
            elif self.duck and b.h != P_H_SMALL:
                b.set_height(P_H_SMALL)

        # horizontal
        dirin = (1 if right else 0) - (1 if left else 0)
        if self.duck and b.on_ground:
            dirin = 0
        maxv = self.g.physics['swim_max'] if self.swimming else (self.g.physics['run_max'] if run else self.g.physics['walk_max'])
        self.skid = False
        if dirin:
            if b.on_ground:
                if b.vx * dirin < 0:
                    b.vx += dirin * self.g.physics['skid_dec']
                    self.skid = True
                else:
                    b.vx += dirin * (self.g.physics['run_acc'] if run else self.g.physics['walk_acc'])
                self.facing = dirin
            else:
                b.vx += dirin * self.g.physics['air_acc']
                if self.swimming:
                    self.facing = dirin
            if abs(b.vx) > maxv:
                b.vx = math.copysign(max(maxv, abs(b.vx) - self.g.physics['release_dec']), b.vx)
        elif b.on_ground:
            under = w.tile(_fl(b.cx / TS), _fl((b.bottom + 1) / TS))
            friction = self.g.physics['release_dec'] * (0.12 if under == 'ice' else 1.0)
            sp = max(0.0, abs(b.vx) - friction)
            b.vx = math.copysign(sp, b.vx) if sp else 0.0

        # vertical
        self.coyote = 5 if b.on_ground else max(0, self.coyote - 1)
        if jump_pressed:
            self.jbuf = 6
        elif self.jbuf:
            self.jbuf -= 1
        if self.swimming:
            if jump_pressed:
                b.vy = -self.g.physics['swim_kick']
                Audio.get().play('stomp')
            b.vy = min(b.vy + self.g.physics['swim_grav'], self.g.physics['swim_max_fall'])
            if b.y < 8:
                b.vy = max(b.vy, 0.5)
            self.jumping = False
        else:
            if self.jbuf and self.coyote:
                b.vy = -(self.g.physics['jump_v'] + abs(b.vx) * self.g.physics['jump_run_bonus'])
                self.jumping = True
                self.jbuf = 0
                self.coyote = 0
                Audio.get().play('jump' if self.power == SMALL else 'jump_big')
            grav = self.g.physics['grav_hold'] if (self.jumping and jump_held and b.vy < 0) else self.g.physics['grav']
            b.vy = min(b.vy + grav, self.g.physics['max_fall'])
            if b.vy >= 0:
                self.jumping = False

        # fireballs
        if fire_pressed and self.power == FIRE and not self.duck and self.fire_cd == 0:
            n = sum(1 for f in g.pfire if not f.dead)
            if n < 2:
                g.pfire.append(PFire(g, b.cx - 6 + self.facing * 10, b.y + 12, self.facing))
                self.fire_cd = 8
                self.throw = 8
                Audio.get().play('fireball')

        # ride platforms
        if b.platform is not None:
            b.x += b.platform.dx
            b.y += b.platform.dy

        # head-corner correction (Mario Forever-style forgiveness)
        if b.vy < 0:
            ty = _fl((b.y + b.vy) / TS)
            hits = [tx for tx in cells(b.x, b.w) if w.solid(tx, ty)]
            if len(hits) == 1 and 0 <= ty < w.ch:
                tx = hits[0]
                tl = tx * TS
                ov = min(b.x + b.w, tl + TS) - max(b.x, tl)
                if ov <= 7:
                    nx = tl - b.w if b.cx < tl + TS / 2 else tl + TS
                    side = tx - 1 if b.cx < tl + TS / 2 else tx + 1
                    if not w.solid(side, ty) and w.tile(tx, ty) not in BUMPABLE:
                        b.x = nx

        self.prev_bottom = b.bottom
        hit = move_body(w, b, hidden=True)
        if b.on_ground:
            feet = _fl((b.bottom + 1) / TS)
            under = w.tile(_fl(b.cx / TS), feet)
            if under in ('conveyor_l', 'conveyor_r'):
                speed = -CONVEYOR_SPEED if under == 'conveyor_l' else CONVEYOR_SPEED
                b.x += speed
                # Re-resolve horizontal walls before accepting belt displacement.
                if any(w.solid(tx, ty) for tx in cells(b.x, b.w) for ty in cells(b.y + 2, b.h - 4)):
                    b.x -= speed
            elif under == 'spring':
                b.vy = -15.0
                b.on_ground = False
                self.jumping = True
                Audio.get().play('jump_big')
        if hit['left'] or hit['right']:
            b.vx = 0.0
        if hit['up']:
            hx, hy = min(hit['up'], key=lambda c: abs(c[0] * TS + TS / 2 - b.cx))
            g.bump(hx, hy, from_player=True)
            b.vy = 1.0
            self.jumping = False
        if b.on_ground:
            self.chain = 0
        if b.y < -TS * 3:
            b.y = -TS * 3
            b.vy = max(b.vy, 0)

        # anim
        if b.on_ground and abs(b.vx) > 0.1:
            self.anim += abs(b.vx) * 0.09 + 0.05
        elif b.on_ground:
            self.anim = 0

    # -- draw -------------------------------------------------------------
    def pose(self):
        b = self.b
        if self.g.state == 'dying':
            return 'dead'
        if self.duck:
            return 'duck'
        if not b.on_ground:
            return 'swim' if self.swimming else 'jump'
        if self.skid:
            return 'skid'
        if abs(b.vx) > 0.1:
            return ('walk1', 'walk2', 'stand')[int(self.anim) % 3]
        return 'stand'

    def sprite(self):
        pose = self.pose()
        size_big = self.power > SMALL
        if self.grow:
            size_big = (abs(self.grow) // 4) % 2 == 0
        if pose == 'dead':
            size_big = False
        if pose == 'duck' and not size_big:
            pose = 'stand'
        fire = '1' if self.power == FIRE else '0'
        if self.star > 0:
            fire = '1' if (self.star // 3) % 2 else '0'
        return ART.spr(f"mario_{'b' if size_big else 's'}_{pose}_{fire}", 0, self.facing < 0)

    def draw(self, surf, cx, cy):
        if self.inv > 0 and (self.inv // 3) % 2 == 0 and self.g.state == 'play':
            return
        s = self.sprite()
        b = self.b
        surf.blit(s, (int(b.cx - s.get_width() / 2 - cx), int(b.bottom - s.get_height() - cy + 1)))


# ---------------------------------------------------------------------------
# RENDER HELPERS (shared with editor)
# ---------------------------------------------------------------------------
def draw_background(surf, theme, cam_x, cam_y, frame, rect=None):
    rect = rect or surf.get_rect()
    tp = visual_palette(theme)
    surf.fill(tp['bg'], rect)
    style_background(surf, theme, cam_x, cam_y, frame, rect)
    if theme == 'night':
        rnd = random.Random(7)
        for i in range(60):
            sx = (rnd.randint(0, 2000) - cam_x * 0.2) % rect.w + rect.x
            sy = rnd.randint(0, rect.h // 2) + rect.y
            if (i + frame // 20) % 5:
                surf.fill((252, 252, 220), (sx, sy, 2, 2))
    elif theme == 'underwater':
        for x in range(rect.x - int(cam_x * 0.5) % 32, rect.right, 32):
            pygame.draw.arc(surf, (120, 170, 252), (x, rect.y + 36 - cam_y, 32, 12), math.pi, 2 * math.pi, 2)
    elif theme == 'snow':
        rnd = random.Random(3)
        for i in range(40):
            sx = (rnd.randint(0, 2000) - cam_x * 0.3 + math.sin((frame + i * 20) * 0.02) * 10) % rect.w + rect.x
            sy = (rnd.randint(0, 2000) + frame * 0.6) % rect.h + rect.y
            surf.fill((252, 252, 252), (sx, sy, 3, 3))


def draw_scenery_layer(surf, scenery, theme, cam_x, cam_y, view_w, view_h):
    for (x, y), sid in scenery.items():
        s = ART.scenery(sid, theme)
        px = x * TS - cam_x
        py = (y + 1) * TS - s.get_height() - cam_y
        if px > view_w or px + s.get_width() < 0 or py > view_h or py + s.get_height() < 0:
            continue
        surf.blit(s, (px, py))


def draw_tile_layer(surf, tiles, theme, cam_x, cam_y, view_w, view_h, frame, editor=False,
                    bumps=None, skip=('water',)):
    x0, x1 = _fl(cam_x / TS), _fl((cam_x + view_w) / TS) + 1
    y0, y1 = _fl(cam_y / TS), _fl((cam_y + view_h) / TS) + 1
    qf = (frame // 10) % 6
    qf = [0, 0, 0, 1, 2, 1][qf]
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            t = tiles.get((tx, ty))
            if not t or t in skip:
                continue
            if t in HIDDEN_TILES:
                if editor:
                    r = pygame.Rect(tx * TS - cam_x, ty * TS - cam_y, TS, TS)
                    pygame.draw.rect(surf, (255, 255, 255), r, 1)
                    btext(surf, '?' if t == 'hcoin' else '1', r.x + 11, r.y + 9, 2, (200, 200, 255))
                continue
            fr = 0
            if t.startswith('q'):
                fr = qf
            elif t == 'coin':
                fr = [0, 0, 1, 2, 1, 0][(frame // 8) % 6]
            elif t == 'lava':
                fr = (frame // 8) % 8
            s = ART.tile(t, theme, fr)
            oy = 0
            if bumps and (tx, ty) in bumps:
                f = bumps[(tx, ty)]
                oy = -int(math.sin(math.pi * f / 12) * 10)
            surf.blit(s, (tx * TS - cam_x, ty * TS - cam_y + oy))


def draw_water_layer(surf, tiles, cam_x, cam_y, view_w, view_h):
    x0, x1 = _fl(cam_x / TS), _fl((cam_x + view_w) / TS) + 1
    y0, y1 = _fl(cam_y / TS), _fl((cam_y + view_h) / TS) + 1
    s = ART.tile('water', 'overworld')
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if tiles.get((tx, ty)) == 'water':
                surf.blit(s, (tx * TS - cam_x, ty * TS - cam_y))


# ---------------------------------------------------------------------------
# GAME
# ---------------------------------------------------------------------------
class Game:
    """Plays one level. run() returns 'cleared' | 'gameover' | 'exit' | 'quit'."""

    def __init__(self, level, session=None, start_cell=None, test=True):
        self.src = level
        activate_style(level.style)
        self.physics = physics_for(level.style)
        self.session = session or Session()
        self.start_override = start_cell
        self.test = test
        self.checkpoint = None
        self.frame = 0
        self.gtheme = level.theme if level.theme in GOOMBA_PALS else 'overworld'
        self.surf = pygame.Surface((WIN_W, WIN_H))
        self.paused = False
        self.reset()
        self.state = 'intro'
        self.state_t = 0

    # -- world build ------------------------------------------------------
    def reset(self):
        lv = self.src
        self.world = World(lv)
        self.ents, self.fx, self.pfire, self.blasters = [], [], [], []
        self.bumps, self.multicoin = {}, {}
        self.gate = None
        self.checkpoints = []
        self.axes = []
        self.warps_out = {}
        self.warps_in = {}
        for (x, y), (sid, prm) in lv.sprites.items():
            self.spawn(sid, prm, x, y)
        for (x, y), t in self.world.tiles.items():
            if t == 'cannon':
                self.blasters.append(Blaster(self, x, y))
        if self.checkpoint:
            for c in self.checkpoints:
                if c.cell == self.checkpoint:
                    c.on = True
        if self.checkpoint:
            sx, sy = self.checkpoint
        elif self.start_override:
            sx, sy = self.start_override
        else:
            sx, sy = lv.start_cell()
        power = self.session.power
        self.player = Player(self, sx * TS + (TS - P_W) / 2, 0, power)
        self.player.b.y = (sy + 1) * TS - self.player.b.h
        self.time = lv.time if lv.time > 0 else 0
        self.time_t = 0
        self.hurried = False
        self.cam_x = self.cam_y = 0.0
        self.castle_done_t = None
        self.bridge_cells = []
        self.pipe_phase, self.pipe_target, self.pit_death = None, None, False
        self.snap_camera()

    def spawn(self, sid, prm, x, y):
        rx, ry, rw, rh = spawn_rect(sid, x, y)
        e = None
        if sid == 'goomba':
            e = Goomba(self, rx, ry, rw, rh)
        elif sid in ('koopa_g', 'koopa_r'):
            e = Koopa(self, rx, ry, sid[-1])
        elif sid == 'para_g':
            e = ParaGreen(self, rx, ry)
        elif sid == 'para_r':
            e = ParaRed(self, rx, ry)
        elif sid == 'buzzy':
            e = Buzzy(self, rx, ry, rw, rh)
        elif sid == 'spiny':
            e = Spiny(self, rx, ry, rw, rh)
        elif sid == 'hammer_bro':
            e = HammerBro(self, rx, ry)
        elif sid == 'lakitu':
            e = Lakitu(self, rx, ry)
        elif sid == 'cheep':
            e = Cheep(self, rx, ry)
        elif sid == 'blooper':
            e = Blooper(self, rx, ry)
        elif sid == 'piranha':
            e = Piranha(self, rx, y * TS)
        elif sid == 'podoboo':
            e = Podoboo(self, rx, (y + 1) * TS)
        elif sid in ('firebar', 'firebar_l'):
            e = Firebar(self, x * TS + TS / 2, y * TS + TS / 2, 6 if sid == 'firebar' else 12, prm == 1)
        elif sid == 'bowser':
            e = Bowser(self, rx, ry)
        elif sid == 'axe':
            e = Axe(self, rx, ry)
            self.axes.append(e)
        elif sid in ('mushroom', 'flower', 'star', '1up'):
            e = Item(self, rx, ry, sid)
        elif sid in ('plat_h', 'plat_v', 'plat_fall'):
            self.world.platforms.append(Lift(x * TS, y * TS, sid, max(1, prm or 4)))
        elif sid == 'gate':
            self.gate = Gate(x, y)
        elif sid == 'checkpoint':
            self.checkpoints.append(Checkpoint(x, y))
        elif sid == 'warp_in':
            self.warps_in[(x, y)] = prm
        elif sid == 'warp_out':
            self.warps_out[prm] = (x, y)
        if e is not None:
            self.ents.append(e)

    # -- camera -------------------------------------------------------------
    def snap_camera(self):
        b = self.player.b
        self.cam_x = max(0, min(self.world.W - WIN_W, b.cx - 240))
        self.cam_y = max(0, min(self.world.H - WIN_H, b.cy - 260))

    def update_camera(self):
        b = self.player.b
        if b.cx - self.cam_x > 320:
            self.cam_x = b.cx - 320
        elif b.cx - self.cam_x < 200:
            self.cam_x = b.cx - 200
        self.cam_x = max(0, min(self.world.W - WIN_W, self.cam_x))
        if self.world.H > WIN_H:
            ty = b.cy - 260
            self.cam_y += (ty - self.cam_y) * 0.15
            self.cam_y = max(0, min(self.world.H - WIN_H, self.cam_y))
        else:
            self.cam_y = 0

    def on_screen(self, body, margin=0):
        return (self.cam_x - margin < body.x + body.w and body.x < self.cam_x + WIN_W + margin and
                self.cam_y - margin < body.y + body.h and body.y < self.cam_y + WIN_H + margin)

    # -- blocks -------------------------------------------------------------
    def bump(self, tx, ty, from_player=False):
        w = self.world
        t = w.tile(tx, ty)
        a = Audio.get()
        if t not in BUMPABLE:
            a.play('bump')
            return
        px, py = tx * TS, ty * TS
        big = self.player.power > SMALL
        content = None
        if t == 'brick':
            if big:
                del w.tiles[(tx, ty)]
                self.bumps.pop((tx, ty), None)
                for vx, vy, ox, oy in ((-2, -9, 0, 0), (2, -9, 16, 0), (-2, -6, 0, 16), (2, -6, 16, 16)):
                    self.fx.append(Debris(px + ox, py + oy, vx, vy, w.theme))
                self.session.score += 50
                a.play('break')
                self._bump_effects(tx, ty)
                return
            a.play('bump')
        elif t == 'bcoin':
            first = self.multicoin.setdefault((tx, ty), [self.frame, 0])
            first[1] += 1
            content = 'coin'
            if first[1] >= 10 or self.frame - first[0] > 300:
                w.tiles[(tx, ty)] = 'used'
        else:
            content = {'qcoin': 'coin', 'hcoin': 'coin', 'qpower': 'power', 'bpower': 'power',
                       'qstar': 'star', 'bstar': 'star', 'q1up': '1up', 'b1up': '1up',
                       'h1up': '1up'}[t]
            w.tiles[(tx, ty)] = 'used'
        self.bumps[(tx, ty)] = 0
        self._bump_effects(tx, ty)
        if content == 'coin':
            self.fx.append(CoinPop(self, px, py - TS))
            self.session.add_coin(self)
        elif content:
            kind = content
            if content == 'power':
                kind = 'mushroom' if self.player.power == SMALL else 'flower'
            self.ents.append(Item(self, px + 2, py - 28, kind, emerge=True))
            a.play('appear')

    def _bump_effects(self, tx, ty):
        top = ty * TS
        r = pygame.Rect(tx * TS, top - 6, TS, 8)
        for e in self.ents:
            if e.dead or not e.active:
                continue
            er = e.rect()
            if not er.colliderect(r) or e.bottom > top + 4:
                continue
            if e.item and not getattr(e, 'emerge', 0):
                e.vy = -6.0
                e.dir = 1 if e.cx > tx * TS + TS / 2 else -1
            elif e.enemy and e.bump_kill and e.hurts:
                e.kill_flip(100)
        if self.world.tile(tx, ty - 1) == 'coin':
            del self.world.tiles[(tx, ty - 1)]
            self.fx.append(CoinPop(self, tx * TS, (ty - 2) * TS))
            self.session.add_coin(self)

    # -- state changes ------------------------------------------------------
    def die(self, pit=False):
        if self.state != 'play':
            return
        self.state = 'dying'
        self.state_t = 0
        self.pit_death = pit
        self.player.b.vx = 0
        self.player.b.vy = 0
        self.player.star = 0
        self.player.duck = False
        self.session.power = SMALL
        Audio.get().stop_music()
        Audio.get().play('die')

    def level_clear(self, gate_bonus=0):
        self.state = 'clear'
        self.state_t = 0
        Audio.get().stop_music()
        Audio.get().play('clear')
        if gate_bonus:
            self.session.score += gate_bonus
            self.fx.append(ScorePop(self.player.b.cx, self.player.b.y - 16, str(gate_bonus)))

    def castle_clear(self):
        self.state = 'castle'
        self.state_t = 0
        Audio.get().stop_music()
        ax = self.axes[0].x if self.axes else self.player.b.x
        self.bridge_cells = sorted((pos for pos, t in self.world.tiles.items()
                                    if t == 'bridge' and ax - 24 * TS < pos[0] * TS < ax),
                                   key=lambda p: -p[0])
        for e in self.axes:
            e.dead = True

    # -- main update --------------------------------------------------------
    def step(self, keys, jump_pressed, fire_pressed):
        self.frame += 1
        self.state_t += 1
        st = self.state
        a = Audio.get()
        if st == 'intro':
            if self.state_t == 1:
                a.stop_music()
            if self.state_t > 150:
                self.state = 'play'
                self.state_t = 0
                mid = level_music_id(self.src)
                if mid:
                    a.music(mid)
                else:
                    a.stop_music()
            return None
        if st == 'gameover':
            if self.state_t == 1:
                a.play('gameover')
            return 'gameover' if self.state_t > 240 else None
        if st == 'dying':
            p = self.player
            if self.state_t > 30 and not self.pit_death:
                if self.state_t == 31:
                    p.b.vy = -10
                p.b.vy = min(p.b.vy + 0.45, 10)
                p.b.y += p.b.vy
            if self.state_t > 190:
                self.session.lives -= 1
                if self.session.lives <= 0:
                    self.state = 'gameover'
                    self.state_t = 0
                else:
                    self.reset()
                    self.state = 'intro'
                    self.state_t = 0
            return None
        if st == 'pipe':
            return self._step_pipe()
        if st == 'castle':
            return self._step_castle()
        if st in ('clear', 'tally'):
            return self._step_clear(keys)

        # ---- play ----
        p = self.player
        for lift in self.world.platforms:
            lift.update(self)
        p.update(keys, jump_pressed, fire_pressed)
        b = p.b

        # pipes (warp entrance under the player's feet)
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        if down and b.on_ground and b.platform is None:
            ty = _fl((b.bottom + 1) / TS)
            for (wx, wy), wid in self.warps_in.items():
                if wy == ty and self.world.tile(wx, wy) == 'pipe_tl' and \
                        wx * TS + 6 <= b.x and b.x + b.w <= wx * TS + 2 * TS - 6 and wid in self.warps_out:
                    self.state, self.state_t = 'pipe', 0
                    self.pipe_phase = 'down'
                    self.pipe_target = self.warps_out[wid]
                    p.b.vx = 0
                    a.play('pipe')
                    return None

        self.update_camera()
        for e in self.ents:
            e.activate_check(self.cam_x)
        for e in list(self.ents):
            if e.active and not e.dead:
                e.update()
        for bl in self.blasters:
            bl.update()
        self._enemy_turns()
        for f in self.pfire:
            if not f.dead:
                f.update()
        self.pfire = [f for f in self.pfire if not f.dead]

        # player vs entities
        pr = b.rect()
        for e in self.ents:
            if e.dead or not e.active or self.state != 'play':
                continue
            if isinstance(e, Firebar):
                if e.collides(pr):
                    p.hurt()
                continue
            if isinstance(e, Axe):
                if pr.colliderect(e.rect()):
                    self.castle_clear()
                    return None
                continue
            if not pr.colliderect(e.rect()):
                continue
            if e.item:
                e.touch(p)
                continue
            if not e.hurts:
                continue
            if p.star > 0 and e.star_kill:
                e.kill_flip()
                chain_award(self, min(p.star_chain, 99), e.cx, e.y)
                p.star_chain += 1
                continue
            stomp_ok = e.stompable and not p.swimming and b.vy > 0 and \
                p.prev_bottom <= e.y + max(10, e.h * 0.5)
            if stomp_ok:
                e.stomp(p)
                held = keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_k]
                b.vy = -(PHYS['stomp_bounce_hold'] if held else PHYS['stomp_bounce'])
                p.jumping = held
                chain_award(self, p.chain, e.cx, e.y)
                p.chain += 1
            else:
                e.touch(p)

        # tiles: coins + lava
        for ty in cells(b.y + 2, b.h - 4):
            for tx in cells(b.x + 2, b.w - 4):
                t = self.world.tile(tx, ty)
                if t == 'coin':
                    del self.world.tiles[(tx, ty)]
                    self.session.add_coin(self)
                elif t in ('lava', 'spikes') and b.bottom > ty * TS + (10 if t == 'lava' else 5):
                    p.inv = p.star = 0
                    self.die()

        for c in self.checkpoints:
            if not c.on and b.cx >= c.x:
                c.on = True
                self.checkpoint = c.cell
                a.play('checkpoint')

        if self.gate:
            self.gate.update()
            g = self.gate
            if self.state == 'play' and not g.taken and pr.colliderect(g.bar_rect()):
                g.taken = True
                self.level_clear(g.bonus())
                a.play('gate')
            elif self.state == 'play' and b.cx > g.x + 48 and b.bottom > g.top:
                self.level_clear(0)

        for k in list(self.bumps):
            self.bumps[k] += 1
            if self.bumps[k] >= 12:
                del self.bumps[k]

        # timer
        if self.src.time > 0 and self.state == 'play':
            self.time_t += 1
            if self.time_t >= 24:
                self.time_t = 0
                self.time -= 1
                if self.time == 100 and not self.hurried:
                    self.hurried = True
                    a.play('hurry')
                if self.time <= 0:
                    self.time = 0
                    p.inv = p.star = 0
                    self.die()

        if b.y > self.world.H + 8 and self.state == 'play':
            self.die(pit=True)

        self._update_fx()
        self.ents = [e for e in self.ents if not e.dead and
                     not (e.active and abs(e.x - self.cam_x) > WIN_W * 4)]
        return None

    def _update_fx(self):
        for f in self.fx:
            f.update()
        self.fx = [f for f in self.fx if not f.dead]

    def _enemy_turns(self):
        ws = [e for e in self.ents if e.walker and e.enemy and e.active and not e.dead and e.on_ground
              and not (isinstance(e, Shell) and e.moving)]
        for i, a in enumerate(ws):
            ra = a.rect()
            for bb in ws[i + 1:]:
                if ra.colliderect(bb.rect()):
                    if (a.cx < bb.cx and a.dir > 0) or (a.cx > bb.cx and a.dir < 0):
                        a.dir *= -1
                    if (bb.cx < a.cx and bb.dir > 0) or (bb.cx > a.cx and bb.dir < 0):
                        bb.dir *= -1

    def _step_pipe(self):
        p = self.player
        b = p.b
        if self.pipe_phase == 'down':
            b.y += 1.0
            if self.state_t >= b.h + 2:
                ox, oy = self.pipe_target
                if self.world.tile(ox, oy) == 'pipe_tl':
                    b.x = ox * TS + TS - b.w / 2
                    b.y = oy * TS + 2
                    self.pipe_phase = 'up'
                    self.state_t = 0
                    Audio.get().play('pipe')
                else:
                    b.x = ox * TS + (TS - b.w) / 2
                    b.y = (oy + 1) * TS - b.h
                    self.pipe_phase = 'done'
                b.vx = b.vy = 0
                self.snap_camera()
        elif self.pipe_phase == 'up':
            b.y -= 1.0
            ox, oy = self.pipe_target
            if b.bottom <= oy * TS:
                b.y = oy * TS - b.h
                self.pipe_phase = 'done'
        if self.pipe_phase == 'done':
            self.state = 'play'
            self.state_t = 0
        self.update_camera()
        return None

    def _step_castle(self):
        t = self.state_t
        if self.bridge_cells and t % 3 == 0:
            pos = self.bridge_cells.pop(0)
            self.world.tiles.pop(pos, None)
            Audio.get().play('break')
            if not self.bridge_cells:
                Audio.get().play('bowserfall')
                for e in self.ents:
                    if isinstance(e, Bowser) and not e.dead:
                        e.falling = True
        if not self.bridge_cells:
            for e in self.ents:
                if isinstance(e, Bowser) and not e.dead:
                    e.falling = True
                    e.update()
            if self.castle_done_t is None:
                self.castle_done_t = t
            if t - self.castle_done_t > 90:
                self.level_clear(0)
        self._update_fx()
        return None

    def _step_clear(self, keys):
        p = self.player
        b = p.b
        if self.state == 'clear':
            if b.on_ground:
                b.vx = 2.0
                p.facing = 1
            p.anim += 0.25
            b.vy = min(b.vy + self.physics['grav'], self.physics['max_fall'])
            move_body(self.world, b)
            self.update_camera()
            if self.gate:
                self.gate.update()
            self._update_fx()
            if self.state_t > 230:
                self.state = 'tally'
                self.state_t = 0
            return None
        # tally time bonus
        if self.time > 0:
            step = min(self.time, 2)
            self.time -= step
            self.session.score += 50 * step
            if self.frame % 3 == 0:
                Audio.get().play('tick')
            self.state_t = 0
        elif self.state_t > 90:
            return 'cleared'
        self._update_fx()
        return None

    # -- draw ---------------------------------------------------------------
    def draw(self):
        activate_style(self.src.style)
        s = self.surf
        if self.state in ('intro', 'gameover'):
            s.fill((0, 0, 0))
            if self.state == 'intro':
                btext(s, f"{self.src.style} WORLD {self.src.world}-{self.src.stage}", WIN_W // 2, 170, 3, center=True)
                if self.src.name:
                    btext(s, self.src.name, WIN_W // 2, 210, 2, (252, 216, 40), center=True)
                m = ART.spr('mario_s_stand_0')
                s.blit(m, (WIN_W // 2 - 70, 252))
                btext(s, f"* {self.session.lives}", WIN_W // 2 - 20, 262, 3)
            else:
                btext(s, "GAME OVER", WIN_W // 2, 220, 3, center=True)
            self.draw_hud(s)
            return s
        cx, cy = int(self.cam_x), int(self.cam_y)
        w = self.world
        draw_background(s, w.theme, cx, cy, self.frame)
        draw_scenery_layer(s, self.src.scenery, w.theme, cx, cy, WIN_W, WIN_H)
        if self.gate:
            self.gate.draw_back(s, cx, cy)
        for c in self.checkpoints:
            c.draw(s, cx, cy)
        for e in self.ents:
            if e.active and e.behind:
                e.draw(s, cx, cy)
        if self.state == 'pipe':
            self.player.draw(s, cx, cy)
        draw_tile_layer(s, w.tiles, w.theme, cx, cy, WIN_W, WIN_H, self.frame, bumps=self.bumps)
        for lift in w.platforms:
            lift.draw(s, cx, cy)
        for e in self.ents:
            if e.active and not e.behind:
                e.draw(s, cx, cy)
        for f in self.pfire:
            f.draw(s, cx, cy)
        if self.state != 'pipe':
            self.player.draw(s, cx, cy)
        if self.gate:
            self.gate.draw_bar(s, cx, cy)
        draw_water_layer(s, w.tiles, cx, cy, WIN_W, WIN_H)
        for f in self.fx:
            f.draw(s, cx, cy)
        self.draw_hud(s)
        if self.paused:
            pr = pygame.Rect(WIN_W // 2 - 100, 196, 200, 60)
            wbox(s, pr, W_SHEET, 9, shadow=True, gloss=False)
            tb = wbox(s, (pr.x + 3, pr.y + 3, pr.w - 6, 20), W_BAR, 7)
            otext(s, "PAUSE", tb.center, W_GOLD_TXT, FONT_BOLD, True)
            draw_text(s, "P / Enter resume  -  Esc exit", (pr.centerx, pr.y + 41), W_INK, FONT_SMALL, True)
        return s

    def draw_hud(self, s):
        ss = self.session
        btext(s, self.src.style, 40, 14)
        btext(s, f"{ss.score:06d}", 40, 32)
        s.blit(pygame.transform.scale(ART.spr('coin', (self.frame // 8) % 4), (16, 16)), (220, 30))
        btext(s, f"*{ss.coins:02d}", 238, 32)
        btext(s, "WORLD", 360, 14)
        btext(s, f" {self.src.world}-{self.src.stage}", 360, 32)
        btext(s, "TIME", 520, 14)
        if self.src.time > 0 and self.state not in ('intro', 'gameover'):
            btext(s, f" {max(0, self.time):03d}", 520, 32)

    # -- loop ---------------------------------------------------------------
    def run(self, screen, clock):
        result = None
        while result is None:
            jump_p = fire_p = False
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.mixer.unpause() if Audio.get().ok else None
                    Audio.get().stop_all()
                    return 'quit'
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.mixer.unpause() if Audio.get().ok else None
                        Audio.get().stop_all()
                        return 'exit'
                    if ev.key in (pygame.K_RETURN, pygame.K_p) and self.state == 'play':
                        self.paused = not self.paused
                        Audio.get().play('pause')
                        if Audio.get().ok:
                            (pygame.mixer.pause if self.paused else pygame.mixer.unpause)()
                    if ev.key in (pygame.K_z, pygame.K_SPACE, pygame.K_UP, pygame.K_k):
                        jump_p = True
                    if ev.key in (pygame.K_x, pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_j):
                        fire_p = True
            if not self.paused:
                result = self.step(pygame.key.get_pressed(), jump_p, fire_p)
            screen.blit(self.draw(), (0, 0))
            pygame.display.flip()
            clock.tick(FPS)
        pygame.mixer.unpause() if Audio.get().ok else None
        Audio.get().stop_all()
        return result


# ---------------------------------------------------------------------------
# EDITOR UI — cat's mario forever worker chrome (Super Mario Worker layout)
#   top:    glossy blue menu strip + title caption
#   middle: full-width level canvas
#   bottom: element panel — category tabs, 2-row element tray, tool deck
# ---------------------------------------------------------------------------
MENU_H = 22
PANEL_H = 132
PANEL = pygame.Rect(0, WIN_H - PANEL_H, WIN_W, PANEL_H)
CANVAS = pygame.Rect(0, MENU_H, WIN_W, WIN_H - MENU_H - PANEL_H)

W_NAVY = (14, 34, 92)
W_INK = (18, 34, 82)
W_WHITE = (255, 255, 255)
W_DIM = (92, 112, 160)
W_RED = (196, 24, 16)
W_GOLD_TXT = (255, 236, 120)
W_BAR = ((84, 140, 236), (22, 58, 160))
W_PANEL = ((206, 232, 255), (122, 176, 238))
W_SHEET = ((242, 249, 255), (198, 224, 250))
W_FIELD = (255, 255, 255)
BTN_STYLES = {               # top, bottom, ink/outline
    'blue':  ((132, 188, 255), (40, 92, 208), (12, 36, 110)),
    'gold':  ((255, 240, 136), (238, 150, 16), (122, 64, 0)),
    'green': ((150, 240, 110), (28, 150, 36), (8, 72, 12)),
    'red':   ((255, 150, 120), (204, 40, 20), (104, 12, 4)),
    'light': ((252, 254, 255), (184, 212, 246), (60, 88, 150)),
}
# legacy names (kept so older patches still resolve)
SYS_BG, SYS_FACE = W_PANEL[1], W_SHEET[0]
SYS_LIGHT, SYS_DARK, SYS_DKSHD = W_WHITE, W_DIM, W_NAVY
SYS_TEXT, SYS_HI = W_INK, W_RED
FONT = FONT_SMALL = FONT_BOLD = FONT_BIG = None


def init_ui_fonts():
    global FONT, FONT_SMALL, FONT_BOLD, FONT_BIG
    FONT = pygame.font.SysFont("arial", 13)
    FONT_SMALL = pygame.font.SysFont("arial", 11, bold=True)
    FONT_BOLD = pygame.font.SysFont("arial", 13, bold=True)
    FONT_BIG = pygame.font.SysFont("arial", 16, bold=True)


def _lerp_c(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _lift(c, d):
    return tuple(max(0, min(255, v + d)) for v in c[:3])


_GRAD = {}


def grad_surf(w, h, top, bot, radius=6, gloss=True):
    """Cached vertical gradient with Worker-style glossy upper half and rounded corners."""
    w, h = max(1, int(w)), max(1, int(h))
    key = (w, h, top, bot, radius, gloss)
    s = _GRAD.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            col = _lerp_c(top, bot, y / max(1, h - 1))
            if gloss and y < h * 0.48:
                col = _lerp_c(col, (255, 255, 255), 0.28)
            pygame.draw.line(s, col, (0, y), (w - 1, y))
        if radius:
            m = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(m, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
            s.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        if len(_GRAD) > 600:
            _GRAD.clear()
        _GRAD[key] = s
    return s


def wbox(surf, rect, colors, radius=6, border=W_NAVY, gloss=True, shadow=False):
    r = pygame.Rect(rect)
    if r.w <= 0 or r.h <= 0:
        return r
    if shadow:
        sh = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 90), (0, 0, r.w, r.h), border_radius=radius)
        surf.blit(sh, (r.x + 4, r.y + 4))
    surf.blit(grad_surf(r.w, r.h, colors[0], colors[1], radius, gloss), r.topleft)
    if border:
        pygame.draw.rect(surf, border, r, 1, border_radius=radius)
        if r.w > 2 * radius + 4 and r.h > 6:
            pygame.draw.line(surf, _lerp_c(colors[0], W_WHITE, .6),
                             (r.x + max(radius, 2), r.y + 1), (r.right - max(radius, 2) - 1, r.y + 1))
    return r


_TXT = {}


def otext(surf, text, pos, color=W_WHITE, font=None, center=False, outline=W_NAVY, right=False):
    """Outlined text (Mario Worker button captions). Cached per string/colour/font."""
    font = font or FONT_BOLD
    text = str(text)
    key = (text, color, id(font), outline)
    t = _TXT.get(key)
    if t is None:
        base = font.render(text, True, color)
        if outline:
            o = font.render(text, True, outline)
            t = pygame.Surface((base.get_width() + 2, base.get_height() + 2), pygame.SRCALPHA)
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (2, 2), (2, 0), (0, 2)):
                t.blit(o, (dx, dy))
            t.blit(base, (1, 1))
        else:
            t = base
        if len(_TXT) > 1500:
            _TXT.clear()
        _TXT[key] = t
    r = t.get_rect()
    if center:
        r.center = pos
    elif right:
        r.topright = pos
    else:
        r.topleft = pos
    surf.blit(t, r)
    return r


def draw_edge(surf, rect, raised=True):
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, W_NAVY, r, 1, border_radius=4 if raised else 3)
    if not raised:
        pygame.draw.line(surf, (150, 176, 220), (r.x + 3, r.y + 1), (r.right - 4, r.y + 1))


def draw_text(surf, text, pos, color=W_INK, font=None, center=False):
    font = font or FONT
    t = font.render(str(text), True, color)
    r = t.get_rect(center=pos) if center else t.get_rect(topleft=pos)
    surf.blit(t, r)
    return r


def wfield(surf, rect, focus=False):
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, W_FIELD, r, border_radius=4)
    pygame.draw.line(surf, (206, 220, 242), (r.x + 3, r.y + 1), (r.right - 4, r.y + 1))
    pygame.draw.rect(surf, (238, 150, 16) if focus else W_NAVY, r, 2 if focus else 1, border_radius=4)
    return r


def wbutton(surf, rect, label=None, style='blue', hover=False, down=False, font=None,
            disabled=False, radius=6):
    a, b, ink = BTN_STYLES[style]
    if disabled:
        a, b = _lerp_c(a, (176, 180, 196), .75), _lerp_c(b, (128, 132, 148), .75)
        ink = (72, 76, 92)
    elif down:
        a, b = b, a
    elif hover:
        a, b = _lift(a, 18), _lift(b, 24)
    r = wbox(surf, rect, (a, b), radius, border=_lerp_c(ink, (0, 0, 0), .3))
    if label is not None:
        if style == 'light':
            otext(surf, label, (r.centerx, r.centery + (1 if down else 0)),
                  (150, 154, 170) if disabled else W_INK, font or FONT_BOLD, center=True, outline=None)
        else:
            otext(surf, label, (r.centerx, r.centery + (1 if down else 0)), W_WHITE,
                  font or FONT_BOLD, center=True, outline=ink)
    return r


def _btn_style(label):
    if label in ("OK", "Yes", "Save", "Open"):
        return 'green'
    if label in ("Cancel", "No"):
        return 'red'
    if label == "Discard":
        return 'gold'
    return 'blue'


_MINI = {}


def mini_icon(kind):
    """14px list icons for the file browser: folder / level (? block)."""
    s = _MINI.get(kind)
    if s is None:
        if kind == 'level':
            s = pygame.transform.smoothscale(ART.tile('qcoin', 'overworld'), (14, 14))
        else:
            s = pygame.Surface((14, 14), pygame.SRCALPHA)
            pygame.draw.rect(s, (200, 140, 20), (0, 2, 6, 3), border_radius=1)
            pygame.draw.rect(s, (252, 200, 60), (0, 4, 14, 9), border_radius=2)
            pygame.draw.rect(s, (140, 90, 0), (0, 4, 14, 9), 1, border_radius=2)
        _MINI[kind] = s
    return s


# ----- toolbar icons -------------------------------------------------------
def _ic_new(s, r, c):
    rr = r.inflate(-10, -6)
    pygame.draw.rect(s, W_WHITE, rr)
    pygame.draw.rect(s, c, rr, 1)
    pygame.draw.line(s, c, (rr.right - 4, rr.y), (rr.right - 1, rr.y + 3))


def _ic_open(s, r, c):
    x, y = r.x + 4, r.y + 7
    pygame.draw.rect(s, (252, 200, 60), (x, y + 2, 15, 10))
    pygame.draw.rect(s, c, (x, y + 2, 15, 10), 1)
    pygame.draw.line(s, c, (x, y + 2), (x + 4, y - 1))
    pygame.draw.line(s, c, (x + 4, y - 1), (x + 8, y - 1))


def _ic_save(s, r, c):
    rr = r.inflate(-8, -8)
    pygame.draw.rect(s, (40, 92, 208), rr, border_radius=2)
    pygame.draw.rect(s, c, rr, 1, border_radius=2)
    pygame.draw.rect(s, W_WHITE, (rr.x + 3, rr.y + 1, rr.w - 6, 5))
    pygame.draw.rect(s, (200, 200, 210), (rr.x + 4, rr.bottom - 6, rr.w - 8, 5))


def _ic_undo(s, r, c):
    pygame.draw.arc(s, c, r.inflate(-8, -8), 0.3, 3.0, 2)
    pygame.draw.polygon(s, c, [(r.x + 4, r.centery), (r.x + 9, r.centery), (r.x + 6, r.centery + 4)])


def _ic_redo(s, r, c):
    pygame.draw.arc(s, c, r.inflate(-8, -8), 0.1, 2.8, 2)
    pygame.draw.polygon(s, c, [(r.right - 4, r.centery), (r.right - 9, r.centery), (r.right - 6, r.centery + 4)])


def _ic_pencil(s, r, c):
    cx, cy = r.center
    pygame.draw.line(s, c, (cx - 5, cy + 5), (cx + 5, cy - 5), 4)
    pygame.draw.line(s, (255, 200, 0), (cx - 4, cy + 4), (cx + 4, cy - 4), 2)
    pygame.draw.line(s, (255, 150, 170), (cx + 4, cy - 4), (cx + 5, cy - 5), 3)


def _ic_eraser(s, r, c):
    rr = r.inflate(-8, -12)
    pygame.draw.rect(s, (255, 160, 180), rr, border_radius=2)
    pygame.draw.rect(s, (90, 140, 230), (rr.x, rr.y, rr.w // 3, rr.h), border_radius=2)
    pygame.draw.rect(s, c, rr, 1, border_radius=2)


def _ic_rect(s, r, c):
    rr = r.inflate(-8, -8)
    pygame.draw.rect(s, (200, 76, 12), rr)
    pygame.draw.line(s, (252, 188, 176), rr.topleft, (rr.right - 1, rr.top))
    pygame.draw.line(s, (0, 0, 0), (rr.x, rr.centery), (rr.right - 1, rr.centery))
    pygame.draw.rect(s, c, rr, 1)


def _ic_play(s, r, c):
    cx, cy = r.center
    pygame.draw.polygon(s, (0, 140, 0), [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 6, cy)])


def _ic_props(s, r, c):
    pygame.draw.circle(s, (40, 92, 208), r.center, 8)
    pygame.draw.circle(s, c, r.center, 8, 1)
    otext(s, "i", r.center, W_WHITE, FONT_BOLD, True, outline=None)


def _ic_grid(s, r, c):
    rr = r.inflate(-8, -8)
    for i in range(0, rr.w + 1, rr.w // 2):
        pygame.draw.line(s, c, (rr.x + i, rr.y), (rr.x + i, rr.bottom))
    for i in range(0, rr.h + 1, rr.h // 2):
        pygame.draw.line(s, c, (rr.x, rr.y + i), (rr.right, rr.y + i))


def _ic_zoom(s, r, c):
    cx, cy = r.center
    pygame.draw.circle(s, (220, 236, 255), (cx - 2, cy - 2), 5)
    pygame.draw.circle(s, c, (cx - 2, cy - 2), 5, 1)
    pygame.draw.line(s, c, (cx + 2, cy + 2), (cx + 6, cy + 6), 3)


def _ic_help(s, r, c):
    q = pygame.transform.smoothscale(ART.tile('qcoin', 'overworld'), (16, 16))
    s.blit(q, (r.centerx - 8, r.centery - 8))


ICONS = {'new': _ic_new, 'open': _ic_open, 'save': _ic_save, 'undo': _ic_undo, 'redo': _ic_redo,
         'pencil': _ic_pencil, 'eraser': _ic_eraser, 'rect': _ic_rect, 'play': _ic_play,
         'props': _ic_props, 'grid': _ic_grid, 'zoom': _ic_zoom, 'help': _ic_help}


# ----- editor previews of objects -----------------------------------------
def sprite_preview(oid, param, theme):
    """Return list of (surface, (dx, dy)) relative to the spawn rect top-left."""
    gth = theme if theme in GOOMBA_PALS else 'overworld'
    rx, ry, rw, rh = spawn_rect(oid, 0, 0)
    names = {'goomba': ('goomba', gth), 'koopa_g': ('koopa_g',), 'koopa_r': ('koopa_r',),
             'para_g': ('para_g',), 'para_r': ('para_r',), 'buzzy': ('buzzy',), 'spiny': ('spiny',),
             'hammer_bro': ('hammer_bro',), 'lakitu': ('lakitu',), 'cheep': ('cheep',),
             'blooper': ('blooper',), 'piranha': ('piranha',), 'podoboo': ('podoboo',),
             'mushroom': ('mushroom',), 'flower': ('flower',), 'star': ('star',), '1up': ('1up',),
             'bowser': ('bowser',), 'axe': ('axe',), 'checkpoint': ('checkpoint',),
             'start': ('mario_s_stand_0',)}
    if oid in names:
        n = names[oid]
        s = ART.spr(n[0], 0, False, n[1] if len(n) > 1 else 'overworld')
        if oid in ('cheep', 'blooper'):
            return [(s, (rw / 2 - s.get_width() / 2, rh / 2 - s.get_height() / 2))]
        return [(s, (rw / 2 - s.get_width() / 2, rh - s.get_height()))]
    if oid in ('firebar', 'firebar_l'):
        n = 6 if oid == 'firebar' else 12
        out = [(ART.spr('fireball', 0), (i * 16, 0)) for i in range(n)]
        arr = pygame.Surface((16, 16), pygame.SRCALPHA)
        btext(arr, '<' if param else '>', 3, 1, 2, (252, 252, 252))
        return out + [(arr, (0, -16))]
    if oid in ('plat_h', 'plat_v', 'plat_fall'):
        lift = ART.spr('lift')
        tag = pygame.Surface((96, 16), pygame.SRCALPHA)
        txt = {'plat_h': f"<> {param}", 'plat_v': f"UD {param}", 'plat_fall': "FALL"}[oid]
        btext(tag, txt, 48, 4, 1, (0, 0, 0), False, center=True)
        return [(lift, (0, 0)), (tag, (0, 0))]
    if oid == 'gate':
        s = pygame.Surface((96, 9 * TS + 16), pygame.SRCALPHA)
        g = Gate(0, 8)
        g.top += 16
        g.bottom += 16
        g.bar_y = g.top + 60
        g.draw_back(s, 0, 0)
        g.draw_bar(s, 0, 0)
        return [(s, (0, -16))]
    s = pygame.Surface((TS, TS), pygame.SRCALPHA)
    if oid in ('warp_in', 'warp_out'):
        col = (0, 200, 255) if oid == 'warp_in' else (255, 160, 0)
        pygame.draw.rect(s, col + (150,), (0, 0, TS, TS))
        pygame.draw.rect(s, (0, 0, 0), (0, 0, TS, TS), 2)
        btext(s, 'IN' if oid == 'warp_in' else 'OUT', 16, 4, 1, (0, 0, 0), False, center=True)
        btext(s, str(param), 16, 16, 1, (0, 0, 0), False, center=True)
    elif oid == 'turn':
        pygame.draw.rect(s, (255, 0, 0, 110), (0, 0, TS, TS))
        pygame.draw.rect(s, (255, 0, 0), (0, 0, TS, TS), 2)
        btext(s, "<>", 16, 12, 1, (255, 255, 255), False, center=True)
    return [(s, (0, 0))]


def draw_sprite_marks(surf, level, cam_x, cam_y, view_w, view_h, behind=None):
    for (x, y), (sid, prm) in level.sprites.items():
        if behind is not None and (sid == 'piranha') != behind:
            continue
        rx, ry, rw, rh = spawn_rect(sid, x, y)
        if rx - cam_x > view_w + 400 or rx + rw - cam_x < -400 or ry - cam_y > view_h + 64 or \
                ry + rh - cam_y < -320:
            continue
        for s, (dx, dy) in sprite_preview(sid, prm, level.theme):
            surf.blit(s, (rx + dx - cam_x, ry + dy - cam_y))


_icon_cache = {}


def item_icon(oid, theme):
    key = (ACTIVE_STYLE, oid, theme)
    if key in _icon_cache:
        return _icon_cache[key]
    c = CATALOG[oid]
    if c['kind'] == 'tile':
        if c['foot']:
            src = pygame.Surface((64, 32), pygame.SRCALPHA)
            for dx, dy, t in c['foot']:
                src.blit(ART.tile(t, theme), (dx * TS, dy * TS))
        elif oid in HIDDEN_TILES:
            src = pygame.Surface((TS, TS), pygame.SRCALPHA)
            pygame.draw.rect(src, (255, 255, 255), (0, 0, TS, TS), 2)
            btext(src, '?' if oid == 'hcoin' else '1', 11, 9, 2, (60, 60, 200), False)
        else:
            src = ART.tile(oid, theme)
            if oid in ('bcoin', 'bpower', 'bstar', 'b1up'):
                src = src.copy()
                tag = {'bcoin': 'C', 'bpower': 'M', 'bstar': '*', 'b1up': '1'}[oid]
                btext(src, tag, 20, 18, 1, (252, 252, 0))
    elif c['kind'] == 'scenery':
        src = ART.scenery(oid, theme)
    else:
        parts = sprite_preview(oid, PARAM_DEFAULT.get(oid, 0), theme)
        minx = min(dx for _s, (dx, dy) in parts)
        miny = min(dy for _s, (dx, dy) in parts)
        maxx = max(dx + s.get_width() for s, (dx, dy) in parts)
        maxy = max(dy + s.get_height() for s, (dx, dy) in parts)
        src = pygame.Surface((max(1, int(maxx - minx)), max(1, int(maxy - miny))), pygame.SRCALPHA)
        for s, (dx, dy) in parts:
            src.blit(s, (dx - minx, dy - miny))
    w, h = src.get_size()
    k = min(32 / w, 32 / h, 1.0)
    ic = pygame.transform.smoothscale(src, (max(1, int(w * k)), max(1, int(h * k)))) if k < 1 else src
    out = pygame.Surface((32, 32), pygame.SRCALPHA)
    out.blit(ic, ((32 - ic.get_width()) // 2, (32 - ic.get_height()) // 2))
    _icon_cache[key] = out
    return out


# ----- menu bar (glossy Worker strip) --------------------------------------
class MenuBar:
    IH, SEP, PAD = 20, 8, 4

    def __init__(self, menus):
        self.menus = menus          # [(title, [(label, cb, shortcut) | None])]
        self.open = -1
        self.title_rects = []
        self.caption = ""
        x = 6
        for title, _items in menus:
            w = FONT_BOLD.size(title)[0] + 18
            self.title_rects.append(pygame.Rect(x, 2, w, MENU_H - 5))
            x += w + 2
        self.hover = -1

    def _h(self, it):
        return self.IH if it else self.SEP

    def _drop_rect(self, i):
        items = self.menus[i][1]
        w = max(FONT.size(it[0])[0] + FONT.size(it[2] or '')[0] + 48 if it else 0 for it in items)
        h = sum(self._h(it) for it in items) + self.PAD * 2
        return pygame.Rect(self.title_rects[i].x, MENU_H + 1, max(160, w), h)

    def _item_at(self, pos):
        dr = self._drop_rect(self.open)
        if not dr.collidepoint(pos):
            return -1
        y = dr.y + self.PAD
        for j, it in enumerate(self.menus[self.open][1]):
            h = self._h(it)
            if it and y <= pos[1] < y + h:
                return j
            y += h
        return -1

    def handle(self, ev):
        """Returns True if the event was consumed."""
        if ev.type == pygame.MOUSEMOTION:
            if self.open >= 0:
                for i, r in enumerate(self.title_rects):
                    if r.collidepoint(ev.pos):
                        self.open = i
                self.hover = self._item_at(ev.pos)
                return True
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i, r in enumerate(self.title_rects):
                if r.collidepoint(ev.pos):
                    self.open = -1 if self.open == i else i
                    self.hover = -1
                    return True
            if self.open >= 0:
                j = self._item_at(ev.pos)
                cb = self.menus[self.open][1][j][1] if j >= 0 else None
                self.open = -1
                if cb:
                    cb()
                return True
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and self.open >= 0:
            self.open = -1
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and self.open >= 0:
            self.open = -1
            return True
        return False

    def draw(self, surf):
        wbox(surf, (0, 0, WIN_W, MENU_H), W_BAR, 0, border=None)
        pygame.draw.line(surf, W_NAVY, (0, MENU_H - 1), (WIN_W, MENU_H - 1))
        mp = pygame.mouse.get_pos()
        for i, (title, _items) in enumerate(self.menus):
            r = self.title_rects[i]
            if i == self.open:
                wbutton(surf, r, title, 'gold', radius=5)
            else:
                if r.collidepoint(mp):
                    wbox(surf, r, BTN_STYLES['blue'][:2], 5, border=BTN_STYLES['blue'][2])
                otext(surf, title, r.center, W_WHITE, FONT_BOLD, True)
        if self.caption:
            avail = WIN_W - 10 - (self.title_rects[-1].right + 14)
            cap = self.caption
            while FONT_BOLD.size(cap)[0] > avail and len(cap) > 4:
                cap = cap[:-2] + "~"
            otext(surf, cap, (WIN_W - 8, 2), W_GOLD_TXT, FONT_BOLD, right=True)
        if self.open >= 0:
            dr = self._drop_rect(self.open)
            wbox(surf, dr, W_SHEET, 5, shadow=True, gloss=False)
            y = dr.y + self.PAD
            for j, it in enumerate(self.menus[self.open][1]):
                if it is None:
                    pygame.draw.line(surf, (140, 170, 220), (dr.x + 8, y + 3), (dr.right - 9, y + 3))
                    pygame.draw.line(surf, W_WHITE, (dr.x + 8, y + 4), (dr.right - 9, y + 4))
                    y += self.SEP
                    continue
                if j == self.hover:
                    wbox(surf, (dr.x + 3, y, dr.w - 6, self.IH), BTN_STYLES['gold'][:2], 4,
                         border=BTN_STYLES['gold'][2])
                    otext(surf, it[0], (dr.x + 18, y + 2), W_WHITE, FONT_BOLD, outline=BTN_STYLES['gold'][2])
                    if it[2]:
                        otext(surf, it[2], (dr.right - 10, y + 2), W_WHITE, FONT, right=True,
                              outline=BTN_STYLES['gold'][2])
                else:
                    draw_text(surf, it[0], (dr.x + 19, y + 3), W_INK)
                    if it[2]:
                        tw = FONT.size(it[2])[0]
                        draw_text(surf, it[2], (dr.right - tw - 11, y + 3), W_DIM)
                y += self.IH


# ----- modal dialogs (rounded Worker panels) -------------------------------
class Dialog:
    def __init__(self, title, w, h):
        self.title = title
        self.rect = pygame.Rect((WIN_W - w) // 2, (WIN_H - h) // 2, w, h)
        self.result = None
        self.done = False
        self.buttons = []         # (rect, label, value)

    def add_button(self, label, value, x, y, w=72):
        self.buttons.append((pygame.Rect(self.rect.x + x, self.rect.y + y - 1, w, 24), label, value))

    def frame(self, surf):
        r = self.rect
        wbox(surf, r, W_SHEET, 9, shadow=True, gloss=False)
        tb = wbox(surf, (r.x + 3, r.y + 3, r.w - 6, 20), W_BAR, 7)
        q = pygame.transform.smoothscale(ART.tile('qcoin', 'overworld', (pygame.time.get_ticks() // 160) % 3), (16, 16))
        surf.blit(q, (tb.x + 4, tb.y + 2))
        otext(surf, self.title, (tb.x + 26, tb.y + 2), W_GOLD_TXT, FONT_BOLD)
        mp = pygame.mouse.get_pos()
        for br, label, _v in self.buttons:
            wbutton(surf, br, label, _btn_style(label), hover=br.collidepoint(mp))

    def draw(self, surf):
        self.frame(surf)

    def event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for br, _l, v in self.buttons:
                if br.collidepoint(ev.pos):
                    self.finish(v)
                    return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.finish(None)

    def finish(self, v):
        self.result, self.done = v, True

    def run(self, screen, clock):
        bg = screen.copy()
        shade = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        shade.fill((0, 12, 48, 110))
        bg.blit(shade, (0, 0))
        while not self.done:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                    self.finish(None)
                    break
                self.event(ev)
            screen.blit(bg, (0, 0))
            self.draw(screen)
            pygame.display.flip()
            clock.tick(FPS)
        return self.result


class MessageBox(Dialog):
    def __init__(self, title, text, buttons=("OK",)):
        self.lines = text.split("\n")
        h = 74 + 16 * len(self.lines)
        w = max(260, max(FONT.size(l)[0] for l in self.lines) + 40)
        super().__init__(title, w, h)
        bx = (w - (80 * len(buttons) - 8)) // 2
        for i, b in enumerate(buttons):
            self.add_button(b, b, bx + i * 80, h - 34)

    def draw(self, surf):
        self.frame(surf)
        for i, l in enumerate(self.lines):
            draw_text(surf, l, (self.rect.x + 16, self.rect.y + 32 + i * 16))

    def event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN:
            self.finish(self.buttons[0][2])
            return
        super().event(ev)


class InputBox(Dialog):
    def __init__(self, title, prompt, initial="", maxlen=200):
        super().__init__(title, 420, 114)
        self.prompt, self.text, self.maxlen = prompt, initial, maxlen
        self.add_button("OK", "ok", 250, 82)
        self.add_button("Cancel", None, 330, 82)

    def finish(self, v):
        super().finish(self.text if v == "ok" else None)

    def event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_RETURN:
                self.finish("ok")
                return
            if ev.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                return
            if ev.key != pygame.K_ESCAPE and ev.unicode and ev.unicode.isprintable() and \
                    len(self.text) < self.maxlen:
                self.text += ev.unicode
                return
        super().event(ev)

    def draw(self, surf):
        self.frame(surf)
        r = self.rect
        draw_text(surf, self.prompt, (r.x + 12, r.y + 30))
        box = wfield(surf, (r.x + 12, r.y + 48, r.w - 24, 24), True)
        t = self.text
        while FONT.size(t)[0] > box.w - 10 and t:
            t = t[1:]
        cursor = "|" if (pygame.time.get_ticks() // 400) % 2 else ""
        draw_text(surf, t + cursor, (box.x + 5, box.y + 4))


class PropertiesDialog(Dialog):
    FIELDS = [("name", "Level name"), ("world", "World"), ("stage", "Stage"), ("time", "Time (0 = none)"),
              ("style", "Game style"), ("theme", "Scene"), ("music", "Music"), ("width", "Width (tiles)"),
              ("height", "Height (tiles)")]

    def __init__(self, level):
        super().__init__("Level Settings", 360, 334)
        self.lv = level
        self.v = dict(name=level.name, world=level.world, stage=level.stage, time=level.time,
                      theme=THEMES.index(level.theme), music=level.music, width=level.width,
                      height=level.height, style=GAME_STYLES.index(level.style)
                      if level.style in GAME_STYLES else 0)
        self.add_button("OK", True, 190, 300)
        self.add_button("Cancel", False, 274, 300)
        self.editing_name = False
        self.ctrls = []
        for i, (k, _lbl) in enumerate(self.FIELDS):
            y = self.rect.y + 34 + i * 28
            if k == 'name':
                self.name_rect = pygame.Rect(self.rect.x + 130, y, 210, 22)
                continue
            self.ctrls.append((k, pygame.Rect(self.rect.x + 130, y, 22, 22),
                               pygame.Rect(self.rect.x + 318, y, 22, 22)))

    STEP = {'world': 1, 'stage': 1, 'time': 50, 'theme': 1, 'music': 1, 'width': 10, 'height': 1, 'style': 1}
    LIM = {'world': (1, 99), 'stage': (1, 99), 'time': (0, 999), 'theme': (0, len(THEMES) - 1),
           'music': (0, len(MUSIC_LABELS) - 1), 'width': (MIN_W, MAX_W), 'height': (MIN_H, MAX_H),
           'style': (0, len(GAME_STYLES) - 1)}

    def _label(self, k):
        v = self.v[k]
        if k == 'theme':
            return THEME_LABELS[THEMES[v]]
        if k == 'music':
            return MUSIC_LABELS[v]
        if k == 'style':
            return GAME_STYLES[v]
        return str(v)

    def event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.editing_name = self.name_rect.collidepoint(ev.pos)
            for k, minus, plus in self.ctrls:
                d = -1 if minus.collidepoint(ev.pos) else (1 if plus.collidepoint(ev.pos) else 0)
                if d:
                    lo, hi = self.LIM[k]
                    step = self.STEP[k] * (5 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1)
                    nv = self.v[k] + d * step
                    if k in ('theme', 'music', 'style'):
                        nv = lo + (nv - lo) % (hi - lo + 1)
                    self.v[k] = max(lo, min(hi, nv))
        if ev.type == pygame.KEYDOWN and self.editing_name:
            if ev.key == pygame.K_BACKSPACE:
                self.v['name'] = self.v['name'][:-1]
                return
            if ev.key == pygame.K_RETURN:
                self.editing_name = False
                return
            if ev.unicode and ev.unicode.isprintable() and len(self.v['name']) < 32:
                self.v['name'] += ev.unicode
                return
        super().event(ev)

    def finish(self, v):
        if v:
            lv = self.lv
            lv.name = self.v['name'].strip() or "Untitled"
            lv.world, lv.stage, lv.time = self.v['world'], self.v['stage'], self.v['time']
            lv.theme = THEMES[self.v['theme']]
            lv.style = GAME_STYLES[self.v['style']]
            activate_style(lv.style)
            lv.music = self.v['music']
            if (self.v['width'], self.v['height']) != (lv.width, lv.height):
                lv.resize(self.v['width'], self.v['height'])
        super().finish(bool(v))

    def draw(self, surf):
        self.frame(surf)
        r = self.rect
        mp = pygame.mouse.get_pos()
        for i, (k, lbl) in enumerate(self.FIELDS):
            draw_text(surf, lbl, (r.x + 14, r.y + 37 + i * 28), W_INK, FONT_BOLD)
        nr = wfield(surf, self.name_rect, self.editing_name)
        cur = "|" if self.editing_name and (pygame.time.get_ticks() // 400) % 2 else ""
        draw_text(surf, self.v['name'] + cur, (nr.x + 5, nr.y + 3))
        for k, minus, plus in self.ctrls:
            for b, sym in ((minus, "-"), (plus, "+")):
                wbutton(surf, b, sym, 'gold', hover=b.collidepoint(mp), radius=5)
            box = wfield(surf, (minus.right + 4, minus.y, plus.x - minus.right - 8, 22))
            draw_text(surf, self._label(k), box.center, W_INK, FONT, True)
        draw_text(surf, "Shift+click = x5", (r.x + 14, r.y + 304), W_DIM, FONT_SMALL)


# FILES=OFF: all graphics, sounds and dialogs are generated internally.
# Only explicitly requested level saves/loads touch disk; no asset files.


class WorkerFileDialog(Dialog):
    """Worker-style file picker rendered in pygame (no Tk dependency)."""
    ROWS = 11

    def __init__(self, mode, initial_dir, initial_file):
        super().__init__("Save Level As" if mode == "save" else "Open Level", 530, 372)
        self.mode = mode
        self.folder = os.path.abspath(os.path.expanduser(initial_dir))
        self.filename = initial_file if mode == "save" else ""
        self.focus_name = mode == "save"
        self.select_filename = mode == "save"
        self.offset = 0
        self.selected = -1
        self.entries = []
        self.error = ""
        self.list_rect = pygame.Rect(self.rect.x + 14, self.rect.y + 62, 502, 210)
        self.name_rect = pygame.Rect(self.rect.x + 92, self.rect.y + 284, 424, 24)
        self.add_button("Save" if mode == "save" else "Open", "accept", 356, 336, 76)
        self.add_button("Cancel", "cancel", 440, 336, 76)
        self.refresh()

    def refresh(self):
        try:
            names = os.listdir(self.folder)
            dirs = sorted((n for n in names if os.path.isdir(os.path.join(self.folder, n))), key=str.lower)
            files = sorted((n for n in names if os.path.isfile(os.path.join(self.folder, n)) and
                            n.lower().endswith((".kenigne", ".json"))), key=str.lower)
            self.entries = [("..", True)] + [(n, True) for n in dirs] + [(n, False) for n in files]
            self.offset = self.selected = 0
            self.error = ""
        except OSError as exc:
            self.entries = [("..", True)]
            self.error = str(exc)[:72]

    def navigate(self, name):
        target = os.path.abspath(os.path.join(self.folder, name))
        if os.path.isdir(target):
            self.folder = target
            self.refresh()

    def accept(self):
        name = self.filename.strip().strip('"')
        if not name:
            self.error = "Enter a file name."
            return
        path = os.path.abspath(os.path.expanduser(name if os.path.isabs(name) else os.path.join(self.folder, name)))
        if os.path.isdir(path):
            self.folder = path
            self.refresh()
            return
        if self.mode == "save" and not path.lower().endswith((LEVEL_EXT, ".json")):
            path += LEVEL_EXT
        if self.mode == "open" and not os.path.isfile(path):
            self.error = "File does not exist."
            return
        if self.mode == "save" and os.path.exists(path):
            # Explicit confirmation prevents accidental overwrites.
            self.result = ("overwrite", path)
            self.done = True
        else:
            self.finish(path)

    def event(self, ev):
        if ev.type == pygame.MOUSEWHEEL:
            self.offset = max(0, min(max(0, len(self.entries) - self.ROWS), self.offset - ev.y))
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.name_rect.collidepoint(ev.pos):
                self.focus_name = True
                return
            if self.list_rect.collidepoint(ev.pos):
                idx = self.offset + (ev.pos[1] - self.list_rect.y - 4) // 18
                if 0 <= idx < len(self.entries):
                    name, is_dir = self.entries[idx]
                    double = idx == self.selected and pygame.time.get_ticks() - getattr(self, 'last_click', -9999) < 380
                    self.last_click = pygame.time.get_ticks()
                    self.selected = idx
                    self.focus_name = False
                    if double and is_dir:
                        self.navigate(name)
                    elif double:
                        self.filename = name
                        self.accept()
                    elif not is_dir:
                        self.filename = name
                return
            for rect, _label, value in self.buttons:
                if rect.collidepoint(ev.pos):
                    if value == "accept":
                        self.accept()
                    else:
                        self.finish(None)
                    return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.finish(None)
            elif ev.key == pygame.K_RETURN:
                if not self.focus_name and 0 <= self.selected < len(self.entries):
                    name, is_dir = self.entries[self.selected]
                    if is_dir:
                        self.navigate(name)
                        return
                    self.filename = name
                self.accept()
            elif self.focus_name:
                if ev.key == pygame.K_a and pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_META):
                    self.select_filename = True
                elif ev.key == pygame.K_BACKSPACE:
                    self.filename = "" if self.select_filename else self.filename[:-1]
                    self.select_filename = False
                elif ev.unicode and ev.unicode.isprintable() and len(self.filename) < 240:
                    self.filename = ev.unicode if self.select_filename else self.filename + ev.unicode
                    self.select_filename = False
            elif ev.key in (pygame.K_UP, pygame.K_DOWN):
                delta = -1 if ev.key == pygame.K_UP else 1
                self.selected = max(0, min(len(self.entries) - 1, self.selected + delta))
                self.offset = max(0, min(self.offset, self.selected))
                self.offset = max(self.offset, self.selected - (self.ROWS - 1))
            elif ev.key == pygame.K_BACKSPACE:
                self.navigate('..')

    def draw(self, surf):
        self.frame(surf)
        r = self.rect
        mp = pygame.mouse.get_pos()
        draw_text(surf, "Look in:", (r.x + 15, r.y + 36), W_INK, FONT_BOLD)
        path_rect = wfield(surf, (r.x + 76, r.y + 30, 440, 26))
        path = self.folder
        while FONT.size(path)[0] > 424 and len(path) > 4:
            path = '...' + path[4:]
        surf.blit(mini_icon('dir'), (path_rect.x + 6, path_rect.y + 6))
        draw_text(surf, path, (path_rect.x + 26, path_rect.y + 5))
        lr = wfield(surf, self.list_rect)
        for j, (name, is_dir) in enumerate(self.entries[self.offset:self.offset + self.ROWS]):
            idx = self.offset + j
            yy = lr.y + 4 + j * 18
            row = pygame.Rect(lr.x + 3, yy, lr.w - 6, 18)
            if idx == self.selected:
                wbox(surf, row, BTN_STYLES['blue'][:2], 4, border=BTN_STYLES['blue'][2])
            elif row.collidepoint(mp):
                pygame.draw.rect(surf, (226, 238, 255), row, border_radius=4)
            surf.blit(mini_icon('dir' if is_dir else 'level'), (row.x + 5, yy + 2))
            if idx == self.selected:
                otext(surf, name[:60], (row.x + 26, yy + 1), W_WHITE, FONT, outline=BTN_STYLES['blue'][2])
            else:
                draw_text(surf, name[:60], (row.x + 27, yy + 2), W_INK)
        if len(self.entries) > self.ROWS:
            track = pygame.Rect(lr.right - 8, lr.y + 4, 4, lr.h - 8)
            pygame.draw.rect(surf, (210, 222, 242), track, border_radius=2)
            th = max(16, track.h * self.ROWS // len(self.entries))
            ty = track.y + (track.h - th) * self.offset // max(1, len(self.entries) - self.ROWS)
            pygame.draw.rect(surf, BTN_STYLES['blue'][1], (track.x, ty, 4, th), border_radius=2)
        draw_text(surf, "File name:", (r.x + 15, r.y + 289), W_INK, FONT_BOLD)
        nr = wfield(surf, self.name_rect, self.focus_name)
        visible = self.filename
        while FONT.size(visible)[0] > nr.w - 12 and visible:
            visible = visible[1:]
        cursor = '|' if self.focus_name and pygame.time.get_ticks() // 450 % 2 == 0 else ''
        draw_text(surf, visible + cursor, (nr.x + 5, nr.y + 4))
        draw_text(surf, self.error or "Type a name, or double-click a folder to browse.",
                  (r.x + 15, r.y + 316), W_RED if self.error else W_DIM, FONT_SMALL)


def file_dialog(screen, clock, mode, initial_dir=None, initial_file="level.kenigne"):
    """Worker-style Save/Open file browser."""
    dlg = WorkerFileDialog(mode, initial_dir or os.getcwd(), initial_file)
    while True:
        result = dlg.run(screen, clock)
        if isinstance(result, tuple) and result[0] == 'overwrite':
            if MessageBox("Confirm Save As", "This level already exists. Replace it?",
                          ("Yes", "No")).run(screen, clock) == "Yes":
                return result[1]
            dlg.done, dlg.result = False, None
            continue
        return result


# ----- editor --------------------------------------------------------------
HELP_TEXT = """Left click: place      Right click: erase      Ctrl+click: pick object
Middle drag / arrows / WASD / wheel: scroll      Shift+wheel: scroll vertically
Wheel over the element tray: browse elements      PgUp/PgDn: category
1 Pencil   2 Eraser   3 Rectangle fill   G grid   Z zoom
F4 level settings   F5 test level   F6 test from mouse   F7 cycle game style
Ctrl+N/O/S new/open/save   Ctrl+Z/Y undo/redo   Esc title screen

In game: arrows move, Z/Space/Up jump, X/Shift run + fireball,
Down = duck / enter warp pipe, P/Enter pause, Esc back to editor."""


class Editor:
    # bottom element panel geometry (Super Mario Worker layout)
    SLOT, COLS, ROWS = 36, 12, 2
    TAB_W = 56
    TRAY = pygame.Rect(20, PANEL.y + 27, 12 * 36, 2 * 36)
    TRAY_BOX = TRAY.inflate(6, 6)
    LARR = pygame.Rect(3, TRAY_BOX.y, 13, TRAY_BOX.h)
    RARR = pygame.Rect(TRAY_BOX.right + 2, TRAY_BOX.y, 13, TRAY_BOX.h)
    INFO = pygame.Rect(4, PANEL.y + 108, WIN_W - 8, 20)
    DECK_X = 474

    def __init__(self, screen, clock, level=None, path=None):
        self.screen, self.clock = screen, clock
        self.level = level or new_level()
        activate_style(self.level.style)
        self.path = path
        self.dirty = False
        self.cam_x = 0.0
        self.cam_y = max(0, self.level.height * TS - CANVAS.h)
        self.zoom = 1.0
        self.tool = 'pencil'
        self.cat = 0
        self.item = 'ground'
        self.params = dict(PARAM_DEFAULT)
        self.scroll = {c: 0 for c in CATEGORIES}
        self.grid = True
        self.undo_stack, self.redo_stack = [], []
        self.drag = None             # 'place' | 'erase' | 'pan' | 'rect' | 'rect_erase'
        self.last_cell = None
        self.rect_start = None
        self.pan_origin = None
        self.status, self.status_t = "", 0
        self.frame = 0
        self.mouse = (0, 0)
        self.quit_to = None
        self._build_menu()
        self._build_toolbar()
        self.set_status(f"{APP_TITLE} — press F1 for help")

    # -- UI construction --------------------------------------------------
    def _build_menu(self):
        self.menubar = MenuBar([
            ("File", [("New level", self.cmd_new, "Ctrl+N"), ("Open...", self.cmd_open, "Ctrl+O"),
                      ("Save", self.cmd_save, "Ctrl+S"), ("Save as...", self.cmd_save_as, "Ctrl+Shift+S"),
                      None, ("Export JSON...", self.cmd_export_json, ""), None,
                      ("Title screen", self.cmd_menu, "Esc"), ("Quit", self.cmd_quit, "")]),
            ("Edit", [("Undo", self.undo, "Ctrl+Z"), ("Redo", self.redo, "Ctrl+Y"), None,
                      ("Pencil", lambda: self.set_tool('pencil'), "1"),
                      ("Eraser", lambda: self.set_tool('eraser'), "2"),
                      ("Rectangle fill", lambda: self.set_tool('rect'), "3"), None,
                      ("Clear level", self.cmd_clear, "")]),
            ("Level", [("Settings...", self.cmd_props, "F4"), None,
                       ] + [(f"Game style: {style}", (lambda style=style: self.cmd_style(style)), "F7")
                            for style in GAME_STYLES] + [None,
                       ("Test level", self.cmd_play, "F5"),
                       ("Test from mouse", self.cmd_play_here, "F6"), None]
                      + [(f"Scene: {THEME_LABELS[t]}", (lambda t=t: self.cmd_theme(t)), "") for t in THEMES]),
            ("View", [("Toggle grid", self.cmd_grid, "G"), ("Toggle zoom", self.cmd_zoom, "Z"),
                      ("Go to start", lambda: self.goto(0), "Home"),
                      ("Go to end", lambda: self.goto(1), "End")]),
            ("Help", [("Controls...", self.cmd_help, "F1"), ("About...", self.cmd_about, "")]),
        ])

    def _build_toolbar(self):
        x0, y0 = self.DECK_X, PANEL.y
        rows = [
            [('pencil', lambda: self.set_tool('pencil'), "Pencil (1)"),
             ('eraser', lambda: self.set_tool('eraser'), "Eraser (2)"),
             ('rect', lambda: self.set_tool('rect'), "Rectangle fill (3)"),
             ('undo', self.undo, "Undo (Ctrl+Z)"), ('redo', self.redo, "Redo (Ctrl+Y)"),
             ('grid', self.cmd_grid, "Grid (G)")],
            [('new', self.cmd_new, "New level (Ctrl+N)"), ('open', self.cmd_open, "Open level (Ctrl+O)"),
             ('save', self.cmd_save, "Save level (Ctrl+S)"), ('zoom', self.cmd_zoom, "Zoom (Z)"),
             ('props', self.cmd_props, "Level settings (F4)"), ('help', self.cmd_help, "Controls (F1)")],
        ]
        self.tools = []
        for row, spec in enumerate(rows):
            for i, (name, cb, tip) in enumerate(spec):
                self.tools.append(dict(rect=pygame.Rect(x0 + i * 27, y0 + 4 + row * 27, 24, 24),
                                       name=name, cb=cb, tip=tip, label=None, style='light'))
        for label, style, cb, tip, r in (
                ("TEST", 'green', self.cmd_play, "Test level (F5)  -  F6 tests from the mouse",
                 (x0, y0 + 59, 79, 22)),
                ("SAVE", 'gold', self.cmd_save, "Save level (Ctrl+S)", (x0 + 83, y0 + 59, 79, 22)),
                ("MENU", 'red', self.cmd_menu, "Back to the title screen (Esc)", (x0, y0 + 84, 79, 20)),
                ("STYLE", 'blue', self.cycle_style, "Cycle game style SMB1 / SMB3 / SMW (F7)",
                 (x0 + 83, y0 + 84, 79, 20))):
            self.tools.append(dict(rect=pygame.Rect(r), name=label.lower(), cb=cb, tip=tip,
                                   label=label, style=style))

    # -- helpers ------------------------------------------------------------
    def set_status(self, msg):
        self.status, self.status_t = msg, 240

    def set_tool(self, t):
        self.tool = t

    def view_size(self):
        return CANVAS.w / self.zoom, CANVAS.h / self.zoom

    def clamp_cam(self):
        vw, vh = self.view_size()
        W, H = self.level.width * TS, self.level.height * TS
        self.cam_x = max(-TS, min(max(0, W - vw) + TS, self.cam_x))
        if H <= vh:
            self.cam_y = H - vh          # short level: keep the floor at the canvas bottom
        else:
            self.cam_y = max(-TS * 2, min(H - vh + TS, self.cam_y))

    def goto(self, end):
        vw, _vh = self.view_size()
        self.cam_x = 0 if not end else self.level.width * TS - vw
        self.clamp_cam()

    def cell_at(self, pos):
        if not CANVAS.collidepoint(pos):
            return None
        wx = self.cam_x + (pos[0] - CANVAS.x) / self.zoom
        wy = self.cam_y + (pos[1] - CANVAS.y) / self.zoom
        return (_fl(wx / TS), _fl(wy / TS))

    def snapshot(self):
        return json.dumps(self.level.to_dict(), separators=(',', ':'))

    def push_undo(self):
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            self.set_status("Nothing to undo")
            return
        self.redo_stack.append(self.snapshot())
        self.level = Level.from_dict(json.loads(self.undo_stack.pop()))
        activate_style(self.level.style)
        self.dirty = True
        self.clamp_cam()

    def redo(self):
        if not self.redo_stack:
            self.set_status("Nothing to redo")
            return
        self.undo_stack.append(self.snapshot())
        self.level = Level.from_dict(json.loads(self.redo_stack.pop()))
        activate_style(self.level.style)
        self.dirty = True
        self.clamp_cam()

    # -- editing ------------------------------------------------------------
    def place(self, cell, oid=None):
        oid = oid or self.item
        x, y = cell
        lv = self.level
        if not lv.in_bounds(x, y):
            return False
        c = CATALOG[oid]
        if c['kind'] == 'tile':
            changed = False
            for dx, dy, t in (c['foot'] or [(0, 0, oid)]):
                if lv.in_bounds(x + dx, y + dy) and lv.tiles.get((x + dx, y + dy)) != t:
                    lv.tiles[(x + dx, y + dy)] = t
                    changed = True
            return changed
        if c['kind'] == 'scenery':
            if lv.scenery.get(cell) == oid:
                return False
            lv.scenery[cell] = oid
            return True
        prm = self.params.get(oid, 0)
        if lv.sprites.get(cell) == [oid, prm]:
            return False
        if oid in UNIQUE_SPRITES:
            old = lv.find_sprite(oid)
            if old:
                del lv.sprites[old]
        lv.sprites[cell] = [oid, prm]
        return True

    def erase(self, cell, all_layers=False):
        lv = self.level
        changed = False
        for layer in (lv.sprites, lv.tiles, lv.scenery):
            if cell in layer:
                del layer[cell]
                changed = True
                if not all_layers:
                    break
        return changed

    def pick(self, cell):
        lv = self.level
        oid = None
        if cell in lv.sprites:
            oid, prm = lv.sprites[cell]
            if oid in PARAM_SPRITES:
                self.params[oid] = prm
        elif cell in lv.tiles:
            oid = lv.tiles[cell]
            oid = {'pipe_tl': 'pipe_top', 'pipe_tr': 'pipe_top', 'pipe_l': 'pipe_body',
                   'pipe_r': 'pipe_body'}.get(oid, oid)
        elif cell in lv.scenery:
            oid = lv.scenery[cell]
        if oid in CATALOG:
            self.item = oid
            self.cat = CATEGORIES.index(CATALOG[oid]['cat'])
            self.reveal_item()
            self.set_status(f"Picked: {CATALOG[oid]['label']}")

    def rect_cells(self, a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]

    # -- commands -----------------------------------------------------------
    def confirm_discard(self):
        if not self.dirty:
            return True
        r = MessageBox("Unsaved changes", "Save changes to this level first?",
                       ("Save", "Discard", "Cancel")).run(self.screen, self.clock)
        if r == "Save":
            return self.cmd_save()
        return r == "Discard"

    def cmd_new(self):
        if not self.confirm_discard():
            return
        self.level, self.path, self.dirty = new_level(), None, False
        activate_style(self.level.style)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.cam_x, self.cam_y = 0, max(0, self.level.height * TS - CANVAS.h)
        self.clamp_cam()
        self.set_status("New level")

    def cmd_open(self):
        if not self.confirm_discard():
            return
        p = file_dialog(self.screen, self.clock, "open",
                        os.path.dirname(self.path) if self.path else None)
        if not p:
            return
        try:
            lv = load_level(p)
        except (OSError, ValueError, KeyError, TypeError, zlib.error, struct.error) as e:
            MessageBox("Open failed", f"Could not open level:\n{e}").run(self.screen, self.clock)
            return
        self.level, self.path, self.dirty = lv, p, False
        activate_style(lv.style)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.cam_x, self.cam_y = 0, max(0, lv.height * TS - CANVAS.h)
        self.clamp_cam()
        self.set_status(f"Opened {os.path.basename(p)}")

    def _write(self, p):
        try:
            save_level(p, self.level)
        except OSError as e:
            MessageBox("Save failed", f"Could not save:\n{e}").run(self.screen, self.clock)
            return False
        self.set_status(f"Saved {os.path.basename(p)}")
        return True

    def cmd_save(self):
        if not self.path or self.path.lower().endswith('.json'):
            return self.cmd_save_as()
        if self._write(self.path):
            self.dirty = False
            return True
        return False

    def cmd_save_as(self):
        name = (os.path.basename(self.path) if self.path and self.path.lower().endswith(LEVEL_EXT)
                else (self.level.name or "level").replace(" ", "_") + LEVEL_EXT)
        p = file_dialog(self.screen, self.clock, "save",
                        os.path.dirname(self.path) if self.path else None, name)
        if not p:
            return False
        if self._write(p):
            self.path, self.dirty = p, False
            return True
        return False

    def cmd_export_json(self):
        name = (self.level.name or "level").replace(" ", "_") + ".json"
        p = file_dialog(self.screen, self.clock, "save", None, name)
        if p:
            if not p.lower().endswith('.json'):
                p = os.path.splitext(p)[0] + '.json'
            self._write(p)

    def cmd_menu(self):
        if self.confirm_discard():
            self.quit_to = 'menu'

    def cmd_quit(self):
        if self.confirm_discard():
            self.quit_to = 'quit'

    def cmd_clear(self):
        if MessageBox("Clear level", "Remove every object from this level?",
                      ("Yes", "No")).run(self.screen, self.clock) == "Yes":
            self.push_undo()
            self.level.tiles.clear()
            self.level.sprites.clear()
            self.level.scenery.clear()
            self.dirty = True

    def cmd_props(self):
        before = self.snapshot()
        if PropertiesDialog(self.level).run(self.screen, self.clock):
            if self.snapshot() != before:
                self.undo_stack.append(before)
                self.redo_stack.clear()
                self.dirty = True
                self.clamp_cam()

    def cmd_style(self, style):
        if self.level.style != style:
            self.push_undo()
            self.level.style = style
            activate_style(style)
            self.dirty = True
            self.set_status(f"Game style: {style}")

    def cycle_style(self):
        i = GAME_STYLES.index(self.level.style) if self.level.style in GAME_STYLES else 0
        self.cmd_style(GAME_STYLES[(i + 1) % len(GAME_STYLES)])

    def cmd_theme(self, t):
        if self.level.theme != t:
            self.push_undo()
            self.level.theme = t
            self.dirty = True

    def cmd_grid(self):
        self.grid = not self.grid

    def cmd_zoom(self):
        cx = self.cam_x + CANVAS.w / self.zoom / 2
        cy = self.cam_y + CANVAS.h / self.zoom / 2
        self.zoom = 0.5 if self.zoom == 1.0 else 1.0
        self.cam_x = cx - CANVAS.w / self.zoom / 2
        self.cam_y = cy - CANVAS.h / self.zoom / 2
        self.clamp_cam()

    def cmd_help(self):
        MessageBox("Controls", HELP_TEXT).run(self.screen, self.clock)

    def cmd_about(self):
        MessageBox("About", f"{APP_TITLE}\nLevel editor in the style of Super Mario Worker\n"
                   "Mario Forever physics • 640x480 • 60 fps • FILES=OFF\n"
                   "A.C Holdings / Team Flames • AC Kondo 1999-2026\n"
                   "Fan project — Mario characters belong to Nintendo"
                   ).run(self.screen, self.clock)

    def cmd_play(self, start=None):
        lv = self.level.copy()
        if not lv.find_sprite('start') and start is None:
            self.set_status("No player start mark — using default position")
        game = Game(lv, Session(), start_cell=start, test=True)
        res = game.run(self.screen, self.clock)
        pygame.event.clear()
        activate_style(self.level.style)
        if res == 'quit':
            if self.confirm_discard():
                self.quit_to = 'quit'
            return
        self.set_status({'cleared': "Course clear!", 'gameover': "Game over",
                         'exit': "Test stopped"}.get(res, ""))

    def cmd_play_here(self):
        cell = self.cell_at(self.mouse)
        if cell is None or not self.level.in_bounds(*cell):
            self.set_status("Put the mouse over the level, then press F6")
            return
        self.cmd_play(start=cell)

    # -- element panel -------------------------------------------------------
    def tab_rects(self):
        return [pygame.Rect(4 + i * self.TAB_W, PANEL.y + 4, self.TAB_W - 2, 20)
                for i in range(len(CATEGORIES))]

    def _max_scroll(self, c=None):
        c = c or CATEGORIES[self.cat]
        cols = (len(CAT_ITEMS[c]) + self.ROWS - 1) // self.ROWS
        return max(0, cols - self.COLS)

    def item_rects(self):
        c = CATEGORIES[self.cat]
        items = CAT_ITEMS[c]
        off = self.scroll[c]
        out = []
        for i, oid in enumerate(items[off * self.ROWS:(off + self.COLS) * self.ROWS]):
            col, row = divmod(i, self.ROWS)
            out.append((pygame.Rect(self.TRAY.x + col * self.SLOT, self.TRAY.y + row * self.SLOT,
                                    self.SLOT, self.SLOT), oid))
        return out

    def reveal_item(self):
        c = CATEGORIES[self.cat]
        if self.item not in CAT_ITEMS[c]:
            return
        col = CAT_ITEMS[c].index(self.item) // self.ROWS
        off = self.scroll[c]
        if not off <= col < off + self.COLS:
            self.scroll[c] = max(0, min(self._max_scroll(c), col - self.COLS // 2))

    def param_rects(self):
        y = self.INFO.y + 2
        return pygame.Rect(222, y, 18, 16), pygame.Rect(282, y, 18, 16)

    def sidebar_scroll(self, d):
        c = CATEGORIES[self.cat]
        self.scroll[c] = max(0, min(self._max_scroll(c), self.scroll[c] + d))

    def panel_click(self, pos):
        for i, r in enumerate(self.tab_rects()):
            if r.collidepoint(pos):
                self.cat = i
                return
        for r, oid in self.item_rects():
            if r.collidepoint(pos):
                self.item = oid
                if CATALOG[oid]['kind'] != 'tile' and self.tool == 'rect':
                    self.tool = 'pencil'
                return
        if self.LARR.collidepoint(pos):
            self.sidebar_scroll(-self.COLS // 2)
            return
        if self.RARR.collidepoint(pos):
            self.sidebar_scroll(self.COLS // 2)
            return
        for b in self.tools:
            if b['rect'].collidepoint(pos):
                b['cb']()
                return
        if self.item in PARAM_SPRITES:
            m, p = self.param_rects()
            lo, hi = PARAM_RANGE[self.item]
            if m.collidepoint(pos):
                self.params[self.item] = max(lo, self.params.get(self.item, lo) - 1)
            elif p.collidepoint(pos):
                self.params[self.item] = min(hi, self.params.get(self.item, lo) + 1)

    def _tool_active(self, name):
        return (name == self.tool) or (name == 'grid' and self.grid) or (name == 'zoom' and self.zoom != 1)

    def draw_panel(self, s):
        activate_style(self.level.style)
        mp = self.mouse
        tip = ""
        wbox(s, PANEL, W_PANEL, 0, border=None, gloss=False)
        pygame.draw.line(s, W_NAVY, (0, PANEL.y), (WIN_W, PANEL.y))
        pygame.draw.line(s, W_WHITE, (0, PANEL.y + 1), (WIN_W, PANEL.y + 1))
        pygame.draw.line(s, (96, 140, 210), (self.DECK_X - 5, PANEL.y + 6), (self.DECK_X - 5, self.INFO.y - 4))
        # category tabs
        for i, r in enumerate(self.tab_rects()):
            sel = i == self.cat
            hov = r.collidepoint(mp)
            wbutton(s, r, CATEGORIES[i], 'gold' if sel else 'blue', hover=hov and not sel,
                    font=FONT_SMALL, radius=5)
            if hov:
                tip = f"{CATEGORIES[i]} elements  (PgUp / PgDn)"
        # element tray — drawn over the level's sky like Mario Worker's palette
        bg = (92, 148, 252) if self.level.theme != 'snow' else (164, 200, 252)
        pygame.draw.rect(s, bg, self.TRAY_BOX, border_radius=5)
        slot_line = _lerp_c(bg, W_WHITE, .22)
        for col in range(self.COLS):
            for row in range(self.ROWS):
                sr = pygame.Rect(self.TRAY.x + col * self.SLOT, self.TRAY.y + row * self.SLOT,
                                 self.SLOT, self.SLOT)
                pygame.draw.rect(s, slot_line, sr.inflate(-2, -2), 1, border_radius=4)
        for r, oid in self.item_rects():
            if oid == self.item:
                wbox(s, r.inflate(-1, -1), BTN_STYLES['gold'][:2], 5, border=W_RED)
                pygame.draw.rect(s, W_RED, r.inflate(-1, -1), 2, border_radius=5)
            elif r.collidepoint(mp):
                pygame.draw.rect(s, W_WHITE, r.inflate(-2, -2), 2, border_radius=4)
            s.blit(item_icon(oid, self.level.theme), (r.x + 2, r.y + 2))
            if r.collidepoint(mp):
                tip = CATALOG[oid]['label']
        pygame.draw.rect(s, W_NAVY, self.TRAY_BOX, 2, border_radius=5)
        mx = self._max_scroll()
        off = self.scroll[CATEGORIES[self.cat]]
        wbutton(s, self.LARR, "<", 'light', hover=self.LARR.collidepoint(mp), disabled=off <= 0, radius=4)
        wbutton(s, self.RARR, ">", 'light', hover=self.RARR.collidepoint(mp), disabled=off >= mx, radius=4)
        if mx:
            bar = pygame.Rect(self.TRAY.x, self.TRAY_BOX.bottom + 1, self.TRAY.w, 3)
            pygame.draw.rect(s, (150, 184, 236), bar, border_radius=1)
            vis = self.COLS / (self.COLS + mx)
            bw = max(14, int(bar.w * vis))
            bx = bar.x + int((bar.w - bw) * off / mx)
            pygame.draw.rect(s, W_NAVY, (bx, bar.y, bw, 3), border_radius=1)
        # tool deck
        for b in self.tools:
            r = b['rect']
            hov = r.collidepoint(mp)
            if b['label'] is None:
                act = self._tool_active(b['name'])
                wbutton(s, r, None, 'gold' if act else 'light', hover=hov, down=act, radius=5)
                ICONS[b['name']](s, r, W_INK)
            else:
                lab = self.level.style if b['name'] == 'style' else b['label']
                wbutton(s, r, lab, b['style'], hover=hov, radius=6)
            if hov:
                tip = b['tip']
        # info strip
        info = wbox(s, self.INFO, W_SHEET, 5, gloss=False)
        div = 306
        pygame.draw.line(s, (150, 176, 220), (div, info.y + 3), (div, info.bottom - 4))
        lab = CATALOG[self.item]['label']
        while FONT_BOLD.size(lab)[0] > (140 if self.item in PARAM_SPRITES else 280) and len(lab) > 3:
            lab = lab[:-2] + "~"
        mini = pygame.transform.smoothscale(item_icon(self.item, self.level.theme), (16, 16))
        s.blit(mini, (info.x + 4, info.y + 2))
        draw_text(s, lab, (info.x + 24, info.y + 3), W_INK, FONT_BOLD)
        if self.item in PARAM_SPRITES:
            m, p = self.param_rects()
            draw_text(s, PARAM_SPRITES[self.item], (m.x - 4 - FONT_SMALL.size(PARAM_SPRITES[self.item])[0],
                                                    m.y + 2), W_DIM, FONT_SMALL)
            val = self.params.get(self.item, 0)
            if self.item.startswith('firebar'):
                val = "CW" if val else "CCW"
            for b, sym in ((m, "-"), (p, "+")):
                wbutton(s, b, sym, 'gold', hover=b.collidepoint(mp), font=FONT_SMALL, radius=4)
            draw_text(s, str(val), ((m.right + p.x) // 2, m.centery), W_INK, FONT_BOLD, True)
        cell = self.cell_at(mp)
        coord = f"X:{cell[0]}  Y:{cell[1]}" if cell else f"{self.level.width}x{self.level.height}"
        cw = FONT_SMALL.size(coord)[0]
        draw_text(s, coord, (info.right - cw - 8, info.y + 4), W_DIM, FONT_SMALL)
        mid = tip or (self.status if self.status_t > 0 else
                      f"{THEME_LABELS[self.level.theme]}  •  {self.level.style}  •  "
                      f"World {self.level.world}-{self.level.stage}  •  tool: {self.tool}")
        room = info.right - cw - 16 - (div + 8)
        while FONT_SMALL.size(mid)[0] > room and len(mid) > 3:
            mid = mid[:-2] + "~"
        draw_text(s, mid, (div + 8, info.y + 4), W_RED if (not tip and self.status_t > 0) else W_INK, FONT_SMALL)

    # -- drawing ------------------------------------------------------------
    def draw_canvas(self, s):
        activate_style(self.level.style)
        lv = self.level
        vw, vh = self.view_size()
        vw, vh = int(math.ceil(vw)), int(math.ceil(vh))
        world = pygame.Surface((vw, vh))
        cx, cy = int(self.cam_x), int(self.cam_y)
        draw_background(world, lv.theme, cx, cy, self.frame)
        draw_scenery_layer(world, lv.scenery, lv.theme, cx, cy, vw, vh)
        draw_sprite_marks(world, lv, cx, cy, vw, vh, behind=True)
        draw_tile_layer(world, lv.tiles, lv.theme, cx, cy, vw, vh, self.frame, editor=True)
        draw_sprite_marks(world, lv, cx, cy, vw, vh, behind=False)
        draw_water_layer(world, lv.tiles, cx, cy, vw, vh)
        W, H = lv.width * TS, lv.height * TS
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 0))
        out = (14, 34, 92, 170)
        if cx < 0:
            shade.fill(out, (0, 0, -cx, vh))
        if W - cx < vw:
            shade.fill(out, (W - cx, 0, vw - (W - cx), vh))
        if cy < 0:
            shade.fill(out, (0, 0, vw, -cy))
        if H - cy < vh:
            shade.fill(out, (0, H - cy, vw, vh - (H - cy)))
        world.blit(shade, (0, 0))
        if self.grid:
            gc = (255, 255, 255, 40)
            g = pygame.Surface((vw, vh), pygame.SRCALPHA)
            for x in range(-(cx % TS), vw, TS):
                pygame.draw.line(g, gc, (x, 0), (x, vh))
            for y in range(-(cy % TS), vh, TS):
                pygame.draw.line(g, gc, (0, y), (vw, y))
            world.blit(g, (0, 0))
        # cursor / rectangle preview
        cell = self.cell_at(self.mouse)
        if self.drag in ('rect', 'rect_erase') and self.rect_start and cell:
            cs = self.rect_cells(self.rect_start, cell)
            xs = [c[0] for c in cs]
            ys = [c[1] for c in cs]
            r = pygame.Rect(min(xs) * TS - cx, min(ys) * TS - cy,
                            (max(xs) - min(xs) + 1) * TS, (max(ys) - min(ys) + 1) * TS)
            pygame.draw.rect(world, (255, 0, 0) if self.drag == 'rect_erase' else (255, 255, 0), r, 2)
        elif cell and self.drag != 'pan':
            r = pygame.Rect(cell[0] * TS - cx, cell[1] * TS - cy, TS, TS)
            if self.tool == 'eraser':
                pygame.draw.rect(world, (255, 60, 60), r, 2)
            else:
                ghost = self._ghost(cell)
                if ghost:
                    surf, pos = ghost
                    ghost_surface = surf.copy()
                    ghost_surface.set_alpha(150)
                    world.blit(ghost_surface, (pos[0] - cx, pos[1] - cy))
                pygame.draw.rect(world, (255, 255, 0), r, 1)
        if self.zoom != 1.0:
            world = pygame.transform.scale(world, (int(vw * self.zoom), int(vh * self.zoom)))
        s.set_clip(CANVAS)
        s.blit(world, CANVAS.topleft)
        s.set_clip(None)

    def _ghost(self, cell):
        oid = self.item
        c = CATALOG[oid]
        x, y = cell
        if c['kind'] == 'tile':
            if c['foot']:
                src = pygame.Surface((64, 32), pygame.SRCALPHA)
                for dx, dy, t in c['foot']:
                    src.blit(ART.tile(t, self.level.theme), (dx * TS, dy * TS))
                return src, (x * TS, y * TS)
            return item_icon(oid, self.level.theme).copy(), (x * TS, y * TS)
        if c['kind'] == 'scenery':
            s = ART.scenery(oid, self.level.theme).copy()
            return s, (x * TS, (y + 1) * TS - s.get_height())
        parts = sprite_preview(oid, self.params.get(oid, 0), self.level.theme)
        rx, ry, rw, rh = spawn_rect(oid, x, y)
        s0, (dx, dy) = parts[0]
        return s0.copy(), (rx + dx, ry + dy)

    def draw(self):
        s = self.screen
        s.fill(W_NAVY)
        self.draw_canvas(s)
        self.draw_panel(s)
        name = self.level.name or "Untitled"
        self.menubar.caption = f"{APP_TITLE}  -  {name}{' *' if self.dirty else ''}"
        self.menubar.draw(s)

    # -- input --------------------------------------------------------------
    def on_event(self, ev):
        if ev.type == pygame.QUIT:
            self.cmd_quit()
            return
        if self.menubar.handle(ev):
            return
        mods = pygame.key.get_mods()
        ctrl = mods & (pygame.KMOD_CTRL | pygame.KMOD_META)
        if ev.type == pygame.MOUSEMOTION:
            self.mouse = ev.pos
            if self.drag == 'pan' and self.pan_origin:
                (mx, my), (cx0, cy0) = self.pan_origin
                self.cam_x = cx0 - (ev.pos[0] - mx) / self.zoom
                self.cam_y = cy0 - (ev.pos[1] - my) / self.zoom
                self.clamp_cam()
            elif self.drag in ('place', 'erase'):
                self._stroke(self.cell_at(ev.pos))
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = ev.pos
            if ev.button in (4, 5):
                d = -1 if ev.button == 4 else 1
                if PANEL.collidepoint(ev.pos):
                    self.sidebar_scroll(d)
                elif mods & pygame.KMOD_SHIFT:
                    self.cam_y += d * 64
                else:
                    self.cam_x += d * 64
                self.clamp_cam()
                return
            if PANEL.collidepoint(ev.pos):
                if ev.button == 1:
                    self.panel_click(ev.pos)
                return
            if ev.pos[1] < CANVAS.y:
                return
            cell = self.cell_at(ev.pos)
            if cell is None:
                return
            if ev.button == 2:
                self.drag = 'pan'
                self.pan_origin = (ev.pos, (self.cam_x, self.cam_y))
                return
            if ev.button == 1 and ctrl:
                self.pick(cell)
                return
            if ev.button in (1, 3):
                self.push_undo()
                self._stroke_changed = False
                self.last_cell = None
                erase = ev.button == 3 or self.tool == 'eraser'
                if self.tool == 'rect' and CATALOG[self.item]['kind'] == 'tile' or \
                        (self.tool == 'rect' and ev.button == 3):
                    self.drag = 'rect_erase' if ev.button == 3 else 'rect'
                    self.rect_start = cell
                else:
                    self.drag = 'erase' if erase else 'place'
                    self._stroke(cell)
        elif ev.type == pygame.MOUSEBUTTONUP:
            if self.drag in ('rect', 'rect_erase') and self.rect_start:
                end = self.cell_at(ev.pos) or self.rect_start
                x0, x1 = sorted((self.rect_start[0], end[0]))
                y0, y1 = sorted((self.rect_start[1], end[1]))
                for yy in range(max(0, y0), min(self.level.height - 1, y1) + 1):
                    for xx in range(max(0, x0), min(self.level.width - 1, x1) + 1):
                        if self.drag == 'rect':
                            self._stroke_changed |= self.place((xx, yy))
                        else:
                            self._stroke_changed |= self.erase((xx, yy), all_layers=True)
            if self.drag in ('place', 'erase', 'rect', 'rect_erase'):
                if not self._stroke_changed and self.undo_stack:
                    self.undo_stack.pop()          # nothing happened: drop the snapshot
                else:
                    self.dirty = True
            self.drag = None
            self.rect_start = None
            self.pan_origin = None
        elif ev.type == pygame.KEYDOWN:
            k = ev.key
            shift = mods & pygame.KMOD_SHIFT
            if ctrl:
                if k == pygame.K_z:
                    self.undo()
                elif k == pygame.K_y:
                    self.redo()
                elif k == pygame.K_s:
                    self.cmd_save_as() if shift else self.cmd_save()
                elif k == pygame.K_o:
                    self.cmd_open()
                elif k == pygame.K_n:
                    self.cmd_new()
                return
            if k == pygame.K_ESCAPE:
                self.cmd_menu()
            elif k == pygame.K_F1:
                self.cmd_help()
            elif k == pygame.K_F4:
                self.cmd_props()
            elif k == pygame.K_F5:
                self.cmd_play()
            elif k == pygame.K_F6:
                self.cmd_play_here()
            elif k == pygame.K_F7:
                self.cycle_style()
            elif k == pygame.K_g:
                self.cmd_grid()
            elif k == pygame.K_z:
                self.cmd_zoom()
            elif k == pygame.K_1:
                self.set_tool('pencil')
            elif k == pygame.K_2:
                self.set_tool('eraser')
            elif k == pygame.K_3:
                self.set_tool('rect')
            elif k == pygame.K_HOME:
                self.goto(0)
            elif k == pygame.K_END:
                self.goto(1)
            elif k == pygame.K_PAGEUP:
                self.cat = (self.cat - 1) % len(CATEGORIES)
            elif k == pygame.K_PAGEDOWN:
                self.cat = (self.cat + 1) % len(CATEGORIES)

    def _stroke(self, cell):
        if cell is None or cell == self.last_cell:
            return
        self.last_cell = cell
        if self.drag == 'erase':
            self._stroke_changed |= self.erase(cell)
        else:
            self._stroke_changed |= self.place(cell)

    def run(self):
        while self.quit_to is None:
            for ev in pygame.event.get():
                self.on_event(ev)
                if self.quit_to:
                    break
            keys = pygame.key.get_pressed()
            mods = pygame.key.get_mods()
            if not (mods & (pygame.KMOD_CTRL | pygame.KMOD_META)) and self.menubar.open < 0:
                sp = 24 if mods & pygame.KMOD_SHIFT else 10
                dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
                dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
                if dx or dy:
                    self.cam_x += dx * sp / self.zoom
                    self.cam_y += dy * sp / self.zoom
                    self.clamp_cam()
            self.frame += 1
            if self.status_t > 0:
                self.status_t -= 1
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        return self.quit_to


# ---------------------------------------------------------------------------
# TITLE SCREEN — cat's mario forever worker 0.1
# ---------------------------------------------------------------------------
LOGO_COLS = [(232, 48, 16), (252, 200, 24), (40, 184, 40), (32, 112, 248)]


def logo_text(surf, text, cx, y, scale, colors, outline=(0, 0, 0), shadow=True):
    """Chunky multi-colour outlined logo built from the HUD pixel font."""
    text = str(text).upper()
    adv = 6 * scale
    w = len(text) * adv - scale
    x0 = cx - w // 2
    o = max(2, scale // 2)
    ci = 0
    for i, ch in enumerate(text):
        if ch == ' ':
            continue
        x = x0 + i * adv
        col = colors[ci % len(colors)]
        ci += 1
        if shadow:
            surf.blit(_glyph(ch, scale, (0, 0, 0)), (x + o + 2, y + o + 2))
        g = _glyph(ch, scale, outline)
        for dx in (-o, 0, o):
            for dy in (-o, 0, o):
                if dx or dy:
                    surf.blit(g, (x + dx, y + dy))
        surf.blit(_glyph(ch, scale, col), (x, y))
        surf.blit(_glyph(ch, scale, _lerp_c(col, (255, 255, 255), .45)), (x, y), (0, 0, 5 * scale, 2 * scale))
    return w


def draw_title_bg(s, frame):
    s.fill((92, 148, 252))
    for x, y, sid in ((40, 3, 'cloud2'), (360, 2, 'cloud1'), (500, 4, 'cloud3')):
        cs = ART.scenery(sid, 'overworld')
        s.blit(cs, ((x - frame * 0.3) % (WIN_W + 200) - 100, y * TS))
    s.blit(ART.scenery('hill_big', 'overworld'), (20, 13 * TS - 76))
    s.blit(ART.scenery('hill_small', 'overworld'), (420, 13 * TS - 44))
    s.blit(ART.scenery('bush3', 'overworld'), (230, 13 * TS - 32))
    for x in range(0, WIN_W, TS):
        s.blit(ART.tile('ground', 'overworld'), (x, 13 * TS))
        s.blit(ART.tile('ground', 'overworld'), (x, 14 * TS))
    for i, t in enumerate(('brick', 'qcoin', 'brick')):
        s.blit(ART.tile(t, 'overworld', [0, 0, 0, 1, 2, 1][(frame // 10) % 6]), (500 + i * TS, 8 * TS))
    s.blit(ART.spr('mario_s_stand_0'), (96, 12 * TS))
    s.blit(ART.spr('goomba', (frame // 8) % 2), (540, 12 * TS))


def main_menu(screen, clock):
    items = ["LEVEL EDITOR", "PLAY LEVEL", "SMB1 DEMO", "SMB3 DEMO", "SMW DEMO", "SOUND", "EXIT"]
    sel = 0
    frame = 0
    audio = Audio.get()
    audio.music(5)
    bw, bh, gap, top = 236, 26, 30, 148
    rects = [pygame.Rect(WIN_W // 2 - bw // 2, top + i * gap, bw, bh) for i in range(len(items))]
    back = pygame.Rect(rects[0].x - 12, top - 10, bw + 24, gap * len(items) + 16)
    plate = pygame.Surface(back.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, (14, 34, 92, 140), (0, 0, back.w, back.h), border_radius=12)
    pygame.draw.rect(plate, (255, 255, 255, 120), (0, 0, back.w, back.h), 2, border_radius=12)

    def toggle_sound():
        audio.music_on = audio.sfx_on = not audio.sfx_on
        audio.music(5) if audio.music_on else audio.stop_music()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'quit'
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(items)
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(items)
                elif ev.key in (pygame.K_RETURN, pygame.K_z, pygame.K_SPACE):
                    if items[sel] == "SOUND":
                        toggle_sound()
                        continue
                    return items[sel]
                elif ev.key == pygame.K_ESCAPE:
                    return 'quit'
            if ev.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(ev.pos):
                        sel = i
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(ev.pos):
                        if items[i] == "SOUND":
                            toggle_sound()
                        else:
                            return items[i]
        frame += 1
        activate_style("SMB1")
        draw_title_bg(screen, frame)
        # logo
        bob = int(math.sin(frame / 24) * 2)
        logo_text(screen, "KOOPA ENGINE", WIN_W // 2, 22 + bob, 5, LOGO_COLS)
        ww = logo_text(screen, "MARIO WORKER", WIN_W // 2 - 22, 62 + bob, 5, [(252, 176, 24)])
        badge = pygame.Rect(WIN_W // 2 - 22 + ww // 2 + 14, 78 + bob, 48, 26)
        wbutton(screen, badge, "0.1", 'red', font=FONT_BIG, radius=7)
        btext(screen, "A.C HOLDINGS / TEAM FLAMES  -  AC KONDO 1999-2026", WIN_W // 2, 124, 1,
              (252, 236, 120), center=True)
        # menu plate + glossy buttons
        screen.blit(plate, back.topleft)
        for i, (r, label) in enumerate(zip(rects, items)):
            if label == "SOUND":
                label = f"SOUND: {'ON' if audio.sfx_on else 'OFF'}"
            on = i == sel
            wbutton(screen, r, label, 'gold' if on else 'blue', font=FONT_BIG, radius=8)
            if on:
                m = pygame.transform.scale(ART.spr('mushroom'), (20, 20))
                screen.blit(m, (r.x + 6, r.y + 3))
                screen.blit(m, (r.right - 26, r.y + 3))
        btext(screen, "ARROWS + ENTER  OR  MOUSE", WIN_W // 2, 454, 1, (252, 252, 252), center=True)
        pygame.display.flip()
        clock.tick(FPS)


def play_file(screen, clock, path):
    try:
        lv = load_level(path)
    except (OSError, ValueError, KeyError, TypeError, zlib.error, struct.error) as e:
        MessageBox("Open failed", f"Could not open level:\n{e}").run(screen, clock)
        return 'menu'
    return play_level(screen, clock, lv)


def play_level(screen, clock, lv):
    res = Game(lv, Session(), test=False).run(screen, clock)
    pygame.event.clear()
    return 'quit' if res == 'quit' else 'menu'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pygame.mixer.pre_init(SR, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption(APP_TITLE)
    clock = pygame.time.Clock()
    init_ui_fonts()
    Audio.get()
    state = 'menu'
    if argv:
        if argv[0] == '--demo':
            lv = demo_level()
            lv.style = next((v for v in GAME_STYLES if v.lower() in argv), "SMB1")
            state = play_level(screen, clock, lv)
        elif argv[0] == '--play' and len(argv) > 1:
            state = play_file(screen, clock, argv[1])
        else:
            try:
                lv = load_level(argv[0])
                state = Editor(screen, clock, lv, argv[0]).run()
            except (OSError, ValueError, KeyError, TypeError, zlib.error, struct.error) as e:
                MessageBox("Open failed", f"Could not open {argv[0]}:\n{e}").run(screen, clock)
    while state != 'quit':
        choice = main_menu(screen, clock)
        Audio.get().stop_music()
        if choice == 'quit' or choice == "EXIT":
            break
        if choice == "LEVEL EDITOR":
            state = Editor(screen, clock).run()
        elif choice == "PLAY LEVEL":
            p = file_dialog(screen, clock, "open")
            state = play_file(screen, clock, p) if p else 'menu'
        elif choice in ("SMB1 DEMO", "SMB3 DEMO", "SMW DEMO"):
            lv = demo_level()
            lv.style = choice.split()[0]
            state = play_level(screen, clock, lv)
    Audio.get().stop_all()
    pygame.quit()


if __name__ == "__main__":
    main()
