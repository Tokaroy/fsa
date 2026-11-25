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
// Per animation (field_0x0) the value list (0xFF ends it) and the frame counts (.rodata /
// .sdata2 u8 arrays, 260 values: over gate.py's per-file literal limit, not written here yet).
extern const u8* const lbl_804A4E68[];
extern const u8* const lbl_804A4EA8[];

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

// FIXME(shotgun): 88.50 %, missing/extra. The original copies the value to the result register before the clamp tests.
s32 Sequencer_801DAA24::fn_801DA96C() {
    s32 value = field_0x4;
    if (value > 0x2F) {
        value = 0x2F;
    } else if (value < 0) {
        value = 0;
    }
    return value;
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
