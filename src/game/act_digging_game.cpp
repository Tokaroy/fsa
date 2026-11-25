#include "game/GameAudio.h"
#include "game/Camera.h"
#include "game/GameGlobals.h"
#include "game/Message.h"
#include "game/Player.h"
#include "game/act/act_digging_game.h"
#include "JSystem/JMath/JMath.h"

static u8 lbl_80539EB8[8] = {20, 15, 0, 0, 0, 0, 0, 0};

static inline void setCameraScript(const JGeometry::TVec3f& pos) {
    Camera_804AA9E4* camera = gGameRoot2_8053AB10->field_0x24;
    if (camera->mShowWholeArea_0x7f5 == 0) {
        camera->mFocusOverride_0x7f4 = 1;
        camera->mFocusMode_0x7f8 = 4;
        camera->mFocusPos_0x7fc.x = pos.x;
        camera->mFocusPos_0x7fc.y = pos.y;
        camera->mFocusPos_0x7fc.z = pos.z;
        camera->mOverrideBlend_0x7f6 = 0;
    }
}

// Turns the keeper towards the player that started the talk (field_0x23c)
// when that player is within 100 units.
static inline void faceTalker(DiggingGameKeeper_8049C970* self) {
    JGeometry::TVec3f diff;
    f32 dist;
    self->getNearestPlayerDir_801EE8F4(&diff, &dist, self->field_0x23c + 1);
    if (dist < 100.0f) {
        u32 angle = (u16)(s32)(JMath::atanTable_.atan2_(-diff.x, -diff.y) *
                          (32768.0f / JMath::TAngleConstant_<f32>::RADIAN_DEG180()));
        if (angle < 0x2000 || angle >= 0xe000) {
            self->field_0x235 = 3;
        } else if (angle >= 0x2000 && angle < 0x6000) {
            self->field_0x235 = 1;
        } else if (angle >= 0x6000 && angle <= 0xa000) {
            self->field_0x235 = 2;
        } else {
            self->field_0x235 = 0;
        }
    }
}

// No address (update inlines it in case 6): the players' digging results.
// Everyone but the best digger gets the item back that they held before the
// game. A function of its own in the original: its score[] sits below the
// by-value position copies of update's openMessage_8038AD24 calls and between
// the two faceTalker copies' locals on update's stack, where a block local of
// update would sit above them.
inline void DiggingGameKeeper_8049C970::restoreItems() {
    s32 i;
    s32 score[4];
    s32 maxDiff = -10000;
    for (i = 0; i < 4; i++) {
        score[i] = 0;
        if (!hasPlayerLeader_8022F514(i)) {
            score[i] = fn_80236100(i) - field_0x274[i];
            if (score[i] > maxDiff) {
                maxDiff = score[i];
            }
        }
    }
    for (i = 0; i < 4; i++) {
        if (!hasPlayerLeader_8022F514(i)) {
            if (maxDiff != score[i]) {
                fn_802372F8(i, field_0x254[i], field_0x264[i]);
            }
        }
    }
}

void DiggingGameKeeper_8049C970::init() {
    mBox.set(-10.0f, -10.0f, 10.0f, 10.0f);
    field_0x235 = 1;
    field_0x238 = 0;
    field_0x234 = 0;
    field_0x23c = -1;
    field_0x236 = gGameRoot_8053AAF8->getPlayerCount_80138A30();
    field_0x24c = (s32)(4.0f * gGameRoot_8053AAF8->mRandom.get_ufloat_1()) + 0x10;
    if (field_0x24c == 0x14) {
        field_0x24c = 0x13;
    }
    field_0x274[0] = 0;
    field_0x274[1] = 0;
    field_0x274[2] = 0;
    field_0x274[3] = 0;
    if (isScreenFlagSet_0x34()) {
        field_0x230 = 7;
        field_0x244 = 0;
    } else {
        field_0x230 = 0;
        field_0x244 = 0;
    }
}

// Same instructions as the original up to order and registers: case 1's first
// loop keeps its counter in r25 where the original has r30, and case 4
// schedules the state store and the 0x3b argument in another order.
void DiggingGameKeeper_8049C970::update() {
    JGeometry::TVec3f pos = mPos;
    pos.y -= 50.0f;
    JGeometry::TVec3f camPos = mPos;
    JGeometry::TBox2f box(mBox);
    s32 i;
    box.i.x += mPos.x;
    box.i.y += mPos.y;
    box.f.x += mPos.x;
    box.f.y += mPos.y;

    fn_80239914(&box, mLayer_0x4, mSerial);

    field_0x234++;
    if (field_0x234 == lbl_80539EB8[field_0x238]) {
        field_0x238++;
        if (field_0x238 == 2) {
            field_0x238 = 0;
        }
        field_0x234 = 0;
    }

    switch (field_0x230) {
    case 0: {
        fn_8022FEB8(&box, mLayer_0x4, mSerial, true, false);
        field_0x23c = fn_8022FD8C(mSerial);
        if (field_0x23c < 0) {
            break;
        }
        if (!fn_802300EC(field_0x23c)) {
            break;
        }
        // Both branches are the same message here; the original still tests field_0x236 == 1.
        u32 msg = (field_0x236 == 1) ? 0x32e : 0x32e;
        if (!openMessage_8038AD24(field_0x23c, msg, getSerial(), getField_0x4(), pos, 0)) {
            break;
        }
        for (i = 0; i < 4; i++) {
            fn_802308E0(i);
        }
        field_0x230 = 1;
        field_0x244 = 0;

        faceTalker(this);
        break;
    }
    case 1: {
        setCameraScript(camPos);
        fn_8022FEB8(&box, mLayer_0x4, mSerial, true, false);
        if (!stepMessageWindow_803865B8(field_0x23c)) {
            break;
        }
        switch (fn_8037EFB4(field_0x23c)) {
        case 0:
            if (field_0x236 == 1) {
                if (fn_80236228(field_0x23c) < 0) {
                    fn_8038470C(field_0x23c, 0x333);
                    field_0x230 = 2;
                    field_0x244 = 0;
                    break;
                }
            }
            // As above: same message either way, the original still tests field_0x236 == 1.
            u32 msg = (field_0x236 == 1) ? 0x32f : 0x32f;
            fn_8038470C(field_0x23c, msg);
            field_0x230 = 3;
            field_0x244 = 0;
            for (i = 0; i < 4; i++) {
                field_0x254[i] = fn_802373EC(i);
                field_0x264[i] = fn_8023725C(i);
                fn_802372F8(i, 9, 2);
            }
            for (i = 0; i < 4; i++) {
                if (!hasPlayerLeader_8022F514(i)) {
                    fn_8023619C(i, -100);
                    field_0x274[i] = fn_80236100(i);
                }
            }
            break;
        case 1:
            fn_8038470C(field_0x23c, 0x330);
            field_0x230 = 2;
            field_0x244 = 0;
            break;
        }
        break;
    }
    case 2:
        setCameraScript(camPos);
        fn_8022FEB8(&box, mLayer_0x4, mSerial, true, false);
        if (fn_80388CAC(field_0x23c, mSerial)) {
            field_0x230 = 0;
            field_0x244 = 0;
            fn_80230534(false);
        }
        break;
    case 3:
        setCameraScript(camPos);
        fn_8022FE80(field_0x23c, getPlayerLayer_8023DE58(0), mSerial, false, false);
        if (fn_80388CAC(field_0x23c, mSerial)) {
            field_0x230 = 4;
            field_0x244 = 0;
            field_0x240 = 3600;
            fn_80230534(false);
            fn_8022B148();
            playSe_801F0D20(0x3a);
            field_0x248 = gAudioMgr_8053AF80->field_0x58;
            gAudioMgr_8053AF80->startBgm_80458FF0(0x1000007, true, 0);
            getGameView_802D6A9C()->setSwitchBit_802D8050(field_0x24c, true, 0xff);
        }
        break;
    case 4: {
        field_0x240--;
        if (field_0x240 / 60 <= 10 && (field_0x240 % 60) == 59) {
            playSe_801F0D20(0x3f);
            gAudioMgr_8053AF80->fn_80458508(1);
        }
        if (field_0x240 == 0) {
            field_0x250 = fn_8023077C();
            field_0x230 = 5;
            field_0x244 = 0;
            playSe_801F0D20(0x3b);
            field_0x235 = 2;
            getGameView_802D6A9C()->setSwitchBit_802D8050(field_0x24c, false, 0xff);
            gAudioMgr_8053AF80->fn_80458508(0);
        }
        break;
    }
    case 5:
        gGameRoot2_8053AB10->field_0x24->addFocusPoint_8030C210(&mPos);
        field_0x244++;
        if (field_0x250 == 0) {
            field_0x250 = fn_8023077C();
        }
        if (field_0x244 > 50 && field_0x250 == 1) {
            fn_8022FE80(0, getPlayerLayer_8023DE58(0), mSerial, false, false);
            if (fn_8022FD8C(mSerial) == 0) {
                openMessage_8038AD24(0, 0x331, getSerial(), getField_0x4(), pos, 2);
                field_0x230 = 6;
                field_0x244 = 0;
                fn_8022B130();
            }
        }
        break;
    case 6: {
        gGameRoot2_8053AB10->field_0x24->addFocusPoint_8030C210(&mPos);
        fn_8022FE80(0, getPlayerLayer_8023DE58(0), mSerial, false, false);
        if (!stepMessageWindow_803865B8(0) || !fn_80384C58(0, mSerial)) {
            break;
        }
        setScreenFlag_0x30(0xff, true);
        field_0x230 = 7;
        field_0x244 = 0;
        fn_80230534(false);

        restoreItems();
        gAudioMgr_8053AF80->startBgm_80458FF0(field_0x248, true, 0);
        break;
    }
    case 7: {
        fn_8022FEB8(&box, mLayer_0x4, mSerial, true, false);
        field_0x23c = fn_8022FD8C(mSerial);
        if (field_0x23c < 0) {
            break;
        }
        if (!openMessage_8038AD24(field_0x23c, 0x332, getSerial(), getField_0x4(), pos, 0)) {
            break;
        }
        field_0x230 = 8;
        field_0x244 = 0;

        faceTalker(this);
        break;
    }
    case 8:
        fn_8022FEB8(&box, mLayer_0x4, mSerial, true, false);
        if (fn_80388CAC(field_0x23c, mSerial)) {
            field_0x230 = 7;
            field_0x244 = 0;
        }
        break;
    }
}

// FIXME: 99.79 %, regalloc-only; behaviour clean.
// (the add that sums the frame uses r0/r5 swapped).
void DiggingGameKeeper_8049C970::draw() {
    s32 frame = field_0x238;
    frame += field_0x235 * 2;
    drawSpriteScaled_801F02BC("enemy_gc_sob.bin", frame + 0x311, NULL, 0, 0, false, 1.0f, 1.0f);
    if (field_0x230 == 4 || field_0x230 == 5 || field_0x230 == 6) {
        lbl_8053AED0->fn_8043CB24(field_0x240 / 60, 0xFF, 0, 2, true, 316.0f, 60.0f, 2.0f);
    }
}

DiggingGameKeeper_8049C970::~DiggingGameKeeper_8049C970() {}
