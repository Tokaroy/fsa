#include "game/GameAudio.h"
#include "game/act/tu_801D8400.h"

// The sprite name for each value.
const char* lbl_804A4DA8[48] = {
    "boss_koori_loop_01.bti",
    "boss_koori_loop_01.bti",
    "boss_koori_loop_02.bti",
    "boss_koori_loop_03.bti",
    "boss_koori_loop_04.bti",
    "boss_koori_bougyo_05.bti",
    "boss_koori_bougyo_06.bti",
    "boss_koori_bougyo_07.bti",
    "boss_koori_bougyo_08.bti",
    "boss_koori_bougyo_09.bti",
    "boss_koori_bougyo_10.bti",
    "boss_koori_kougeki_05.bti",
    "boss_koori_kougeki_06.bti",
    "boss_koori_rakka_01.bti",
    "boss_koori_rakka_02.bti",
    "boss_koori_rakka_03.bti",
    "boss_koori_rakka_04.bti",
    "boss_koori_rakkago_01.bti",
    "boss_koori_rakkago_02.bti",
    "boss_koori_rakkago_03.bti",
    "boss_koori_rakkago_04.bti",
    "boss_koori_tobumade_01.bti",
    "boss_koori_tobumade_02.bti",
    "boss_koori_tobumade_03.bti",
    "boss_koori_tobumade_04.bti",
    "boss_koori_tobumade_05.bti",
    "boss_koori_tobumade_06.bti",
    "boss_koori_tobumade_07.bti",
    "boss_koori_fly_01.bti",
    "boss_koori_fly_02.bti",
    "boss_koori_fly_03.bti",
    "boss_koori_tsuiraku_01.bti",
    "boss_koori_tsuiraku_02.bti",
    "boss_koori_tsuiraku_03.bti",
    "boss_koori_tsuiraku_04.bti",
    "boss_koori_tsuiraku_05.bti",
    "boss_koori_tsuiraku_06.bti",
    "boss_koori_tsuiraku_07.bti",
    "boss_koori_tsuiraku_08.bti",
    "boss_koori_tsuiraku_09.bti",
    "boss_koori_tsuiraku_10.bti",
    "boss_koori_tsuiraku_11.bti",
    "boss_koori_fly_tojiru_01.bti",
    "boss_koori_fly_tojiru_02.bti",
    "boss_koori_fly_tojiru_03.bti",
    "boss_koori_fly_hiraku_01.bti",
    "boss_koori_fly_hiraku_02.bti",
    "boss_koori_fly_hiraku_03.bti",
};
// Per animation (field_0x0): the value list (0xFF ends it) and, step by step, how many
// frames each value is held. The short lists land in .sdata2, the long ones in .rodata.
static const u8 lbl_804699F8[] = {1, 2, 1, 2, 1, 2, 1, 2, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 2, 0xFF};
static const u8 lbl_80469A14[] = {6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 0xFF};
static const u8 lbl_80469A30[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 9, 10, 9, 8, 0xFF};
static const u8 lbl_80469A40[] = {1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 30, 0xFF};
static const u8 lbl_8053F238[] = {8, 9, 10, 9, 10, 9, 8, 0xFF};
static const u8 lbl_8053F240[] = {3, 3, 3, 3, 3, 3, 30, 0xFF};
static const u8 lbl_80469A50[] = {1, 2, 3, 4, 5, 6, 7, 8, 0xFF};
static const u8 lbl_80469A5C[] = {3, 3, 3, 3, 4, 4, 4, 26, 0xFF};
static const u8 lbl_8053F248[] = {8, 7, 6, 4, 11, 12, 0xFF};
static const u8 lbl_8053F250[] = {4, 4, 4, 4, 4, 20, 0xFF};
static const u8 lbl_8053F258[] = {13, 14, 15, 16, 0xFF};
static const u8 lbl_8053F260[] = {4, 4, 4, 20, 0xFF};
static const u8 lbl_8053F268[] = {17, 18, 19, 20, 0xFF};
static const u8 lbl_8053F270[] = {4, 4, 4, 30, 0xFF};
static const u8 lbl_80469A68[] = {20, 21, 22, 23, 24, 25, 26, 27, 28, 0xFF};
static const u8 lbl_80469A74[] = {20, 6, 6, 6, 15, 6, 6, 6, 6, 0xFF};
static const u8 lbl_8053F278[] = {28, 29, 28, 30, 0xFF};
static const u8 lbl_8053F280[] = {6, 6, 6, 6, 0xFF};
static const u8 lbl_8053F288[] = {27, 0xFF};
static const u8 lbl_8053F28C[] = {6, 0xFF};
static const u8 lbl_8053F290[] = {31, 32, 33, 34, 35, 36, 0xFF};
static const u8 lbl_8053F298[] = {4, 4, 4, 4, 4, 30, 0xFF};
static const u8 lbl_8053F2A0[] = {37, 38, 39, 40, 0xFF};
static const u8 lbl_8053F2A8[] = {4, 4, 6, 20, 0xFF};
static const u8 lbl_8053F2B0[] = {39, 41, 40, 0xFF};
static const u8 lbl_8053F2B4[] = {4, 4, 40, 0xFF};
static const u8 lbl_80469A80[] = {40, 38, 37, 36, 35, 34, 33, 32, 31, 28, 0xFF};
static const u8 lbl_80469A8C[] = {4, 4, 15, 4, 4, 4, 4, 4, 4, 40, 0xFF};
static const u8 lbl_8053F2B8[] = {42, 43, 42, 44, 0xFF};
static const u8 lbl_8053F2C0[] = {6, 6, 6, 6, 0xFF};
static const u8 lbl_8053F2C8[] = {45, 46, 45, 47, 0xFF};
static const u8 lbl_8053F2D0[] = {6, 6, 6, 6, 0xFF};

static const u8* lbl_804A4E68[16] = {
    lbl_804699F8,
    lbl_80469A30,
    lbl_8053F238,
    lbl_80469A50,
    lbl_8053F248,
    lbl_8053F258,
    lbl_8053F268,
    lbl_80469A68,
    lbl_8053F278,
    lbl_8053F288,
    lbl_8053F290,
    lbl_8053F2A0,
    lbl_8053F2B0,
    lbl_80469A80,
    lbl_8053F2B8,
    lbl_8053F2C8,
};
static const u8* lbl_804A4EA8[16] = {
    lbl_80469A14,
    lbl_80469A40,
    lbl_8053F240,
    lbl_80469A5C,
    lbl_8053F250,
    lbl_8053F260,
    lbl_8053F270,
    lbl_80469A74,
    lbl_8053F280,
    lbl_8053F28C,
    lbl_8053F298,
    lbl_8053F2A8,
    lbl_8053F2B4,
    lbl_80469A8C,
    lbl_8053F2C0,
    lbl_8053F2D0,
};

Sequencer_801DAA24::Sequencer_801DAA24() {
    field_0x0 = 0;
    field_0x4 = 0;
    field_0x8 = 0;
    field_0xc = 0;
    field_0x10 = 2;
    field_0x14 = 0;
}

void Sequencer_801DAA24::start_801DA9E8(s32 a, s32 b) {
    field_0x0 = a;
    field_0x8 = 0;
    field_0xc = 0;
    field_0x10 = b;
    field_0x14 = 0;
    field_0x4 = lbl_804A4E68[field_0x0][field_0xc];
}

bool Sequencer_801DAA24::fn_801DA994(s32 a, s32 b) {
    bool changed = false;
    if (field_0x0 != a) {
        field_0x0 = a;
        field_0x8 = 0;
        changed = true;
        field_0xc = 0;
        field_0x10 = b;
        field_0x14 = 0;
        field_0x4 = lbl_804A4E68[field_0x0][field_0xc];
    }
    return changed;
}

s32 Sequencer_801DAA24::fn_801DA96C() {
    s32 value = field_0x4;
    s32 result = value;
    if (value > 0x2F) {
        result = 0x2F;
    } else if (value < 0) {
        result = 0;
    }
    return result;
}

const char* Sequencer_801DAA24::fn_801DA938() {
    s32 value = field_0x4;
    if (value > 0x2F) {
        value = 0x2F;
    } else if (value < 0) {
        value = 0;
    }
    return lbl_804A4DA8[value];
}

bool Sequencer_801DAA24::fn_801DA904() {
    bool result = false;
    s32 value = field_0x4;
    if (value > 0x2F) {
        value = 0x2F;
    } else if (value < 0) {
        value = 0;
    }
    if (value >= 0x1C) {
        result = true;
    }
    return result;
}

bool Sequencer_801DAA24::fn_801DA894() {
    bool atEnd = false;
    if (field_0x10 == 2 && !(field_0x14 & 1)) {
        if (field_0x8 + 1 == lbl_804A4EA8[field_0x0][field_0xc] && lbl_804A4E68[field_0x0][field_0xc + 1] == 0xFF) {
            atEnd = true;
        }
    }
    return atEnd;
}

void Sequencer_801DAA24::fn_801DA7C0() {
    if (!(field_0x14 & 1)) {
        field_0x8++;
        if (field_0x8 >= lbl_804A4EA8[field_0x0][field_0xc]) {
            field_0x8 = 0;
            field_0xc++;
            if (lbl_804A4E68[field_0x0][field_0xc] == 0xFF) {
                if (field_0x10 == 0) {
                    field_0x14 |= 1;
                    field_0xc--;
                } else {
                    field_0x14 |= 2;
                    field_0xc = 0;
                }
            }
        }
    }
    field_0x4 = lbl_804A4E68[field_0x0][field_0xc];
}
