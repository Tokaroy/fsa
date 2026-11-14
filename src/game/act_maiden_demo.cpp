#include "game/GameAudio.h"
#include "game/cls_8049D740.h"

#include "game/ActorId.h"
#include "game/ActorManager.h"
#include "game/GameGlobals.h"

// The Maiden's animation keys: (cel, frames) s16 pairs, ended by a cel of -1.
static const s16 lbl_8053C600[4] = {6, 20, -1, -1};
static const s16 lbl_8053C608[4] = {7, 20, -1, -1};
static const s16 lbl_8053C610[4] = {8, 20, -1, -1};
static const s16 lbl_8053C618[4] = {9, 20, -1, -1};
static const s16 lbl_8053C620[4] = {8, 9, -1, -1};
static const s16 lbl_80464678[14] = {0, 9, 1, 9, 2, 9, 3, 9, 4, 9, 5, 9, -1, -1};
static const s16 lbl_80464694[10] = {8, 5, 0x15, 6, 0x16, 6, 0x17, 60, -1, -1};
static const s16 lbl_804646A8[8] = {8, 9, 0xC, 9, 0xD, 40, -1, -1};
static const s16 lbl_804646B8[14] = {0xE, 9, 0xF, 9, 0x10, 9, 0x11, 9, 0x12, 9, 0x13, 9, -1, -1};
static const s16 lbl_804646D4[8] = {8, 6, 0x14, 9, 0xE, 9, -1, -1};
static const s16 lbl_804646E4[8] = {8, 1, 0xA, 30, 0xB, 10, -1, -1};
static const s16 lbl_804646F4[8] = {0x13, 9, 0x14, 9, 8, 40, -1, -1};

// The key tables of mAnim, in address order.
static const s16* lbl_8049D710[12] = {
    lbl_80464678, lbl_8053C600, lbl_8053C608, lbl_8053C610, lbl_8053C618, lbl_8053C620,
    lbl_80464694, lbl_804646A8, lbl_804646B8, lbl_804646D4, lbl_804646E4, lbl_804646F4,
};

// The Maiden's compare words (0x80464704), then one per-mode offset table
// (modes 0..5) for each of three checks.
static const s32 lbl_80464704[22] = {
    0x199, 0x1E7, 0x17F, 0x201, 0x1CD, 0x1B3, 0, 0, 0, 0x276, 0x2B2, 0x47E, 0x76C, 0x83E, 0x848, 0xA3C,
    0xAF0, 0xC9E, 0xD5C, 0xD66, 0xE24, 0,
};
static const s32 lbl_8046475C[6] = {0xA, 0x1E, 0x32, 0, 0x14, 0x28};
static const s32 lbl_80464774[6] = {0x14, 0x37, 0x4B, 0, 0x28, 0x41};
static const s32 lbl_8046478C[6] = {5, 0xA, 0, 0, 0xF, 0x14};
static const s32 lbl_804647A4[3] = {0x0235023D, 0x02340236, 0x02370238};

cls_8049D740::cls_8049D740()
    : field_0x230(0),
      mMode(0),
      field_0x238(0),
      field_0x23c(0),
      field_0x240(-1),
      field_0x244(0),
      field_0x248(0.0f),
      field_0x24c(0.0f),
      field_0x250(0.37f),
      mEmitter298(NULL),
      mEmitter29c(NULL),
      mEmitter2a0(NULL) {
}

cls_8049D740::~cls_8049D740() {
    releaseEmitter_801EE434(mEmitter298);
    mEmitter298 = NULL;
    releaseEmitter_801EE434(mEmitter29c);
    mEmitter29c = NULL;
    releaseEmitter_801EE434(mEmitter2a0);
    mEmitter2a0 = NULL;
}

void cls_8049D740::init() {
    cls_8049D140::init();
    mMode = field_0x90 & 0x1F;
    mAnim.fn_801D2608(lbl_8049D710, 12);
    mAnim.startAnim_801D22DC(5, 2, false);
    mAnim.fn_801D1F14(0.0f);
}

void cls_8049D740::vfunc_0x10() {
    s32 serial = getActorManager_801F856C()->fn_801F7A08(ACTOR_DMGL);
    ActorBase_804A5770* goal = getActorManager_801F856C()->findActorBySerial_801F666C(serial);
    if (goal != NULL) {
        mGoalPos = goal->mPos;
    }
}

// FIXME: 97.37 %, missing/extra + reloc-name; behaviour drift.
void cls_8049D740::vfunc_0x54() {
    cls_801192AC* state = fn_8011921C();
    s32 id = state->field_0x8;
    if (field_0x23c != 0) {
        return;
    }
    if (id == lbl_80464704[8]) {
        fn_80112654(2);
        return;
    }
    if (id == lbl_80464704[9] + lbl_8046475C[mMode]) {
        fn_80112654(3);
        return;
    }
    if (id == lbl_80464704[10]) {
        fn_80112654(4);
        return;
    }
    if (id == lbl_80464704[11]) {
        fn_80112654(5);
        return;
    }
    if (id == lbl_80464704[12]) {
        fn_80112654(6);
        return;
    }
    if (id == lbl_80464704[13]) {
        fn_80112654(7);
        return;
    }
    if (id == lbl_80464704[14]) {
        fn_80112654(8);
        return;
    }
    if (id == lbl_80464704[15] + lbl_8046478C[mMode]) {
        fn_80112654(9);
        return;
    }
    if (id == lbl_80464704[16]) {
        fn_80112654(0xA);
        return;
    }
    if (id == lbl_80464704[17]) {
        fn_80112654(0xB);
        return;
    }
    if (id == lbl_80464704[18] + lbl_80464774[mMode]) {
        fn_80112654(0xC);
        return;
    }
    if (id == lbl_80464704[20]) {
        fn_80112654(0xF);
    }
}

s32 cls_8049D740::vfunc_0x58() {
    return field_0x238;
}

s32 cls_8049D740::vfunc_0x5C() {
    return 1;
}

// Maps (kind, mode) to a message id. Each kind has its own mode table.
s32 fn_801123C8(s32 kind, s32 mode) {
    switch (kind) {
    case 0:
        switch (mode) {
        case 0: return 0x2FD;
        case 1: return 0x307;
        case 2: return 0x301;
        case 3: return 0x2FF;
        case 4: return 0x305;
        case 5:
        default: return 0x303;
        }
    case 1:
        switch (mode) {
        case 0: return 0x2FE;
        case 1: return 0x308;
        case 2: return 0x302;
        case 3: return 0x300;
        case 4: return 0x306;
        case 5:
        default: return 0x304;
        }
    case 2:
        switch (mode) {
        case 0: return 0x2CF;
        case 1: return 0x2DE;
        case 2: return 0x2D5;
        case 3: return 0x2D2;
        case 4: return 0x2DB;
        case 5:
        default: return 0x2D8;
        }
    case 3:
        switch (mode) {
        case 0: return 0x2D0;
        case 1: return 0x2DF;
        case 2: return 0x2D6;
        case 3: return 0x2D3;
        case 4: return 0x2DC;
        case 5:
        default: return 0x2D9;
        }
    case 4:
        switch (mode) {
        case 0: return 0x2D1;
        case 1: return 0x2E0;
        case 2: return 0x2D7;
        case 3: return 0x2D4;
        case 4: return 0x2DD;
        case 5:
        default: return 0x2DA;
        }
    case 5:
    default:
        switch (mode) {
        case 0: return 0x2E4;
        case 1: return 0x2E9;
        case 2: return 0x2E6;
        case 3: return 0x2E5;
        case 4: return 0x2E8;
        case 5:
        default: return 0x2E7;
        }
    }
}
