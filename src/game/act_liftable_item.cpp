#include "game/Effect.h"
#include "game/GameAudio.h"
#include "game/Message.h"
#include "game/act/act_liftable_item.h"
#include "game/act/act_stop_npc.h"
#include "game/ActorManager.h"
#include "game/GameGlobals.h"
#include "game/Map.h"
#include "game/Player.h"

// By item kind (field_0x234): what the item gives (passed to fn_8038BD08; 0x27F is
// special-cased) and the message shown for it.
static const s32 lbl_80465E38[80] = {
    0x72F, 0x730, 0x731, 0x732, 0xD7, 0xD8, 0xD9, 0xDA,
    0xE6, 0x10F, 0x110, 0x111, 0xD6, 0xD6, 0xD6, 0xD6,
    0xD1, 0xD2, 0x733, 0x266, 0xC8, 0x734, 0x112, 0x735,
    0x736, 0x735, 0xC8, 0xC8, 0xC8, 0xC8, 0xC8, 0xC8,
    0xD3, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6,
    0xE6, 0xE6, 0xC8, 0xC8, 0xC8, 0xC8, 0x10E, 0xDB,
    0xC7, 0xDC, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE,
    0xCF, 0xD0, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6,
    0x26A, 0xDC, 0x263, 0x264, 0x262, 0x261, 0x269, 0x268,
    0x27F, 0x260, 0x265, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6,
};
static const s32 lbl_80465F78[80] = {
    0x1BC, 0x1BD, 0x1BE, 0x1BF, 0x194, 0x193, 0x192, 0x191,
    0x1B7, 0x1B8, 0x1B9, 0x1BA, 0xD6, 0xD6, 0xD6, 0xD6,
    0x1A6, 0x1A7, 0x411, 0x412, 0x19C, 0x413, 0x1BB, 0x414,
    0x415, 0x415, 0x19C, 0x19C, 0x19C, 0x19C, 0x19C, 0x19C,
    0x1A1, 0x416, 0x417, 0x418, 0x419, 0x115, 0xE6, 0xE6,
    0xE6, 0xE6, 0x19C, 0x19C, 0x19C, 0x19C, 0x431, 0x432,
    0x19E, 0x1AB, 0x1A5, 0x19D, 0x19F, 0x1A9, 0x1A2, 0x1A3,
    0x1A4, 0x1A0, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6,
    0x19E, 0x1AB, 0x1A5, 0x19D, 0x19F, 0x1A9, 0x1A2, 0x1A3,
    0x1A4, 0x1A0, 0x149, 0xE6, 0xE6, 0xE6, 0xE6, 0xE6,
};

s32 lbl_804A0170[12] = {
    1, 5, 20, 50, 100, 150, 200, 300, 1000, 1500, 2000, 3000,
};
s32 lbl_804A01A0[12] = {
    1, 5, 9, 13, 17, 21, 25, 29, 0x45A, 0x456, 0x462, 0x45E,
};

void LiftableItem_804A01D0::init() {
    field_0x234 = mSpawnParam_0x90 & 0xFFF;
    field_0x250 = (mSpawnParam_0x90 >> 24) & 3;
    field_0x24c = (mSpawnParam_0x90 >> 26) & 3;
    field_0x254 = (mSpawnParam_0x90 >> 28) & 1;
    field_0x268 = (mSpawnParam_0x90 >> 23) & 1;
    field_0x26c = (mSpawnParam_0x90 >> 22) & 1;
    field_0x270 = (mSpawnParam_0x90 >> 21) & 1;
    field_0x258 = (mSpawnParam_0x90 >> 31) & 1;
    field_0x25c = (mSpawnParam_0x90 >> 30) & 1;
    field_0x264 = (mSpawnParam_0x90 >> 29) & 1;
    mEmitter2a8 = NULL;
    mEmitter2ac = NULL;
    mEmitter2b0 = NULL;
    field_0x290 = -1;
    field_0x244 = 0;
    field_0x238 = 0;
    field_0x23c = 0;
    field_0x240 = 26;
    field_0x29c.set(0.0f, 0.0f, 0.0f);
    mVel_0x3c.set(0.0f, 0.0f, 0.0f);
    if (gGameRoot_8053AAF8->field_0x7f == 1) {
        field_0x238 = 90;
    } else {
        field_0x238 = 45;
    }
    field_0x288 = 0;
    field_0x27c = *getPlayerPos_8023E724(field_0x250);
    field_0x274 = field_0x250;
    if (hasPlayerLeader_8022F514(field_0x250)) {
        field_0x274 = getPlayerLeader_8022F3DC(field_0x250);
    }
    field_0x28c = 10;
    switch (field_0x234) {
    case 0:
    case 1:
    case 2:
    case 3:
        if (field_0x25c == 0) {
            fn_802362C4(field_0x274, lbl_804A0170[field_0x234]);
        }
        break;
    case 4:
    case 5:
    case 6:
    case 7:
    case 8:
    case 9:
    case 10:
    case 11:
        if (field_0x25c == 0) {
            lbl_8053AED0->fn_8043D874(field_0x274, lbl_804A0170[field_0x234], 0);
        }
        if (field_0x270 != 0) {
            field_0x28c = 2;
        }
        break;
    case 0x2E:
        mPos.z = field_0x27c.z + 22.0f;
        field_0x290 = getActorManager_801F856C()->spawnActor_801F9484('BBMB', mLayer_0x4, &mPos, 0x20000, -1, -1);
        break;
    }
    field_0x230 = 0;
    if (field_0x258 == 0) {
        if (field_0x28c != 2) {
            field_0x260 = getActorManager_801F856C()->spawnActor_801F9484('STPN', mLayer_0x4, &mPos, 0, -1, -1);
            if (gGameRoot_8053AAF8->field_0x96 == 0) {
                field_0x260 = 0;
            }
        } else {
            if (gGameRoot_8053AAF8->field_0x7e == 0) {
                field_0x238 = 45;
            } else {
                field_0x28c = 10;
            }
            field_0x260 = 0;
        }
    } else {
        field_0x260 = 0;
    }
    field_0x278 = -1;
    field_0x294 = -1;
}

LiftableItem_804A01D0::~LiftableItem_804A01D0() {
    releaseEmitter_801EE434(mEmitter2a8);
    releaseEmitter_801EE434(mEmitter2ac);
    releaseEmitter_801EE434(mEmitter2b0);
}

static inline u32 checkInputs_8015A374() {
    for (s32 i = 0; i < 4; i++) {
        u32 input = lbl_8053AD30->fn_80309D6C(getPlayerInputSlot_8030AAF4(i), 0x100);
        if (input != 0) {
            return input;
        }
    }
    return 0;
}

// Stack slots only: the original keeps the TVec3f copied into the found actor (case 0x2E) below the by-value
// message positions (0x38), ours above them.
void LiftableItem_804A01D0::update() {
    // The `== true` tests below are deliberate: the compiled code has more instructions without them.


    addCalc2_801F71A4(&mVel_0x3c.x, field_0x29c.x, 0.3f, 1.0f);
    addCalc2_801F71A4(&mVel_0x3c.y, field_0x29c.y, 0.3f, 1.0f);
    mPos += mVel_0x3c;

    switch (field_0x230) {
    case 0:
        if (field_0x238 <= 0) {
            if (field_0x26c != 0) {
                field_0x230 = 1;
                break;
            }
            if (field_0x258 == 0) {
                if (mLayer_0x4 >= 8 && gGameRoot_8053AAF8->field_0x7e == 1) {
                    lbl_8053AED0->requestMessage_8043D67C(lbl_80465F78[field_0x234], field_0x274, 0);
                }
                if ((u32)lbl_80465E38[field_0x234] == 0x27F) {
                    if ((u32)((gGameRoot_8053AAF8->field_0x83 >> (field_0x274 * 2)) & 3) == 2) {
                        if (field_0x250 == field_0x24c) {
                            field_0x278 = getActorManager_801F856C()->spawnActor_801F9484('PEFF', mLayer_0x4, &mPos, (field_0x250 & 3) | 0x24, -1, -1);
                            fn_8038BD08(field_0x24c, lbl_80465E38[field_0x234], getField_0x4(), mPos, 0x21);
                        }
                    } else {
                        if (field_0x250 == field_0x24c) {
                            field_0x278 = getActorManager_801F856C()->spawnActor_801F9484('PEFF', mLayer_0x4, &mPos, (field_0x250 & 3) | 0x24, -1, -1);
                            fn_8038BD08(field_0x24c, 0x284, getField_0x4(), mPos, 0x21);
                        }
                    }
                } else if (field_0x234 < 0x10) {
                    if (field_0x250 == field_0x24c) {
                        field_0x278 = getActorManager_801F856C()->spawnActor_801F9484('PEFF', mLayer_0x4, &mPos, (field_0x250 & 3) | 0x24, -1, -1);
                        fn_8038BD08(field_0x24c, lbl_80465E38[field_0x234], getField_0x4(), mPos, 1);
                    }
                } else {
                    if (field_0x250 == field_0x24c) {
                        field_0x278 = getActorManager_801F856C()->spawnActor_801F9484('PEFF', mLayer_0x4, &mPos, (field_0x250 & 3) | 0x24, -1, -1);
                        fn_8038BD08(field_0x24c, lbl_80465E38[field_0x234], getField_0x4(), mPos, 0x21);
                    }
                }
                if (field_0x250 == field_0x24c) {
                    fn_801597EC();
                }
            } else {
                fn_801597EC();
            }
            field_0x230 = 1;
        } else {
            if (field_0x240 == 1 && field_0x234 == 0x2E) {
                fn_80230EB8(field_0x250, 0x3E);
            }
            field_0x28c--;
            if (field_0x28c == 0) {
                field_0x28c = 1;
                if (field_0x26c != 0) {
                    s32 serial = field_0x260;
                    if (serial != 0) {
                        StopNPC_804AA2D8* actor = static_cast<StopNPC_804AA2D8*>(getActorManager_801F856C()->findActorBySerial_801F666C(serial));
                        if (actor != NULL) {
                            actor->fn_802ED140();
                        }
                    }
                }
                if (field_0x234 != 0x2F) {
                    if (field_0x234 == 0x14) {
                        if (field_0x288 == 0) {
                            mPos.x = field_0x27c.x + 4.0f;
                            mPos.y = field_0x27c.y - 16.0f;
                            mPos.z = field_0x27c.z;
                            field_0x28c = 4;
                            fn_80236804(fn_8022F340(field_0x274), 4);
                            fn_80230F44(field_0x24c, 0x01000002);
                        } else if (field_0x288 == 1) {
                            mPos.x = field_0x27c.x + 6.0f;
                            mPos.y = field_0x27c.y - 19.0f;
                            mPos.z = field_0x27c.z;
                            mEmitter2b0 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x562, 0, 1, NULL, NULL, true, 0.8f);
                            mEmitter2a8 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x563, 0, 1, NULL, NULL, true, 0.6f);
                        }
                        if (field_0x234 != 0x2F && field_0x288 < 4) {
                            field_0x288++;
                        }
                        if (field_0x288 < 4) {
                            field_0x288++;
                        }
                        s32 frame = field_0x288;
                        if (frame >= 4) {
                            frame = 3;
                        }
                        fn_80230498(field_0x250, &field_0x27c, frame + 0xE9, 0xFF, -0x80, -0x80, true);
                    } else if (field_0x234 == 0x2E) {
                        if (field_0x288 == 0) {
                            mPos.z = field_0x27c.z + 22.0f;
                            field_0x28c = 4;
                        } else if (field_0x288 == 1) {
                            mPos.z = field_0x27c.z + 39.0f;
                            field_0x28c = 4;
                        } else if (field_0x288 == 2) {
                            mPos.z = field_0x27c.z + 28.0f;
                        }
                        ActorBase_804A5770* actor = getActorManager_801F856C()->findActorBySerial_801F666C(field_0x290);
                        if (actor != NULL) {
                            JGeometry::TVec3f pos = mPos;
                            actor->mPos = pos;
                        }
                        if (field_0x288 < 4) {
                            field_0x288++;
                        }
                        s32 frame = field_0x288;
                        if (frame >= 4) {
                            frame = 3;
                        }
                        if (fn_80233E40(field_0x250)) {
                            fn_80230498(field_0x250, &field_0x27c, frame + 0x336, 0xFF, -0x80, -0x80, true);
                        } else {
                            fn_80230498(field_0x250, &field_0x27c, frame + 0xED, 0xFF, -0x80, -0x80, true);
                        }
                    } else if (field_0x234 <= 0x0B) {
                        if (field_0x288 == 0) {
                            mPos.y = field_0x27c.y - 18.0f;
                            if (field_0x270 != 0 && gGameRoot_8053AAF8->field_0x7e == 1) {
                                field_0x28c = 4;
                            }
                        } else if (field_0x288 == 1) {
                            mPos.y = field_0x27c.y - 35.0f;
                            if (field_0x270 != 0 && gGameRoot_8053AAF8->field_0x7e == 1) {
                                field_0x28c = 4;
                            }
                            if (field_0x25c == 0) {
                                fn_80230FD0(field_0x250, 0x10008);
                            }
                        } else if (field_0x288 == 2) {
                            if (field_0x270 != 0 && gGameRoot_8053AAF8->field_0x7e == 1) {
                                field_0x28c = 50;
                            }
                            mPos.y = field_0x27c.y - 24.0f;
                            if (field_0x234 >= 8) {
                                mEmitter2b0 = spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(mPos.x, mPos.y - 12.0f, mPos.z), 0x562, 0, 1, NULL, NULL, true, 1.6f);
                                mEmitter2a8 = spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(mPos.x, mPos.y - 6.0f, mPos.z), 0x563, 0, 1, NULL, NULL, true, 1.2f);
                                if (field_0x25c == 0) {
                                    JGeometry::TVec3f pos = mPos;
                                    pos.y -= 32.0f;
                                    getActorManager_801F856C()->fn_801F6718(field_0x274, mLayer_0x4, &pos, field_0x234, 2);
                                }
                            } else {
                                mEmitter2b0 = spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(mPos.x, mPos.y - 6.0f, mPos.z), 0x562, 0, 1, NULL, NULL, true, 0.8f);
                                mEmitter2a8 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x563, 0, 1, NULL, NULL, true, 0.6f);
                                if (field_0x25c == 0) {
                                    JGeometry::TVec3f pos = mPos;
                                    pos.y -= 16.0f;
                                    getActorManager_801F856C()->fn_801F6718(field_0x274, mLayer_0x4, &pos, field_0x234, 2);
                                }
                            }
                        }
                        if (field_0x288 < 3) {
                            field_0x288++;
                        }
                        if (field_0x25c == 0) {
                            s32 frame = field_0x288;
                            if (frame >= 4) {
                                frame = 3;
                            }
                            if (fn_80233E40(field_0x250)) {
                                fn_80230498(field_0x250, &field_0x27c, frame + 0x336, 0xFF, -0x80, -0x80, true);
                            } else {
                                fn_80230498(field_0x250, &field_0x27c, frame + 0xED, 0xFF, -0x80, -0x80, true);
                            }
                        }
                    } else if ((u32)(field_0x234 - 0x10) <= 2 || (u32)(field_0x234 - 0x16) <= 3 || field_0x234 == 0x25) {
                        if (field_0x288 == 0) {
                            mPos.y = field_0x27c.y - 16.0f;
                            mPos.z = field_0x27c.z;
                            field_0x28c = 4;
                            fn_80230F44(field_0x24c, 0x01000002);
                        } else if (field_0x288 == 1) {
                            mPos.y = field_0x27c.y - 19.0f;
                            mPos.z = field_0x27c.z;
                            mEmitter2b0 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x562, 0, 1, NULL, NULL, true, 0.7f);
                            mEmitter2a8 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x563, 0, 1, NULL, NULL, true, 0.6f);
                        }
                        if (field_0x288 < 4) {
                            field_0x288++;
                        }
                        s32 frame = field_0x288;
                        if (frame >= 4) {
                            frame = 3;
                        }
                        if (fn_80233E40(field_0x250)) {
                            fn_80230498(field_0x250, &field_0x27c, frame + 0x336, 0xFF, -0x80, -0x80, true);
                        } else {
                            fn_80230498(field_0x250, &field_0x27c, frame + 0xED, 0xFF, -0x80, -0x80, true);
                        }
                    } else {
                        if (field_0x288 == 0) {
                            mPos.x = field_0x27c.x + 4.0f;
                            mPos.y = field_0x27c.y - 16.0f;
                            mPos.z = field_0x27c.z;
                            fn_80230F44(field_0x24c, 0x01000002);
                            field_0x28c = 4;
                        } else if (field_0x288 == 1) {
                            mPos.x = field_0x27c.x + 6.0f;
                            mPos.y = field_0x27c.y - 19.0f;
                            mPos.z = field_0x27c.z;
                            mEmitter2b0 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x562, 0, 1, NULL, NULL, true, 0.7f);
                            mEmitter2a8 = spawnEmitter_8013CC50(mLayer_0x4, &mPos, 0x563, 0, 1, NULL, NULL, true, 0.6f);
                        }
                        if (field_0x288 < 4) {
                            field_0x288++;
                        }
                        s32 frame = field_0x288;
                        if (frame >= 4) {
                            frame = 3;
                        }
                        fn_80230498(field_0x250, &field_0x27c, frame + 0xE9, 0xFF, -0x80, -0x80, true);
                    }
                }
            }
        }
        if (field_0x288 >= 4) {
            if (checkInputs_8015A374() != 0) {
                field_0x288 = 3;
                field_0x238 = 0;
            }
        }
        break;

    case 1:
        if (field_0x238 <= 0) {
            if (field_0x26c != 0) {
                if (field_0x25c != 0 || stepMessageWindow_803865B8(field_0x250)) {
                    die_0x24();
                }
                break;
            }
            if (field_0x234 == 0x2E) {
                if (mLayer_0x4 < 8 && fn_80388EEC(field_0x250)) {
                    field_0x230 = 2;
                    field_0x238 = 20;
                    LiftableItem_804A01D0* actor = static_cast<LiftableItem_804A01D0*>(getActorManager_801F856C()->findActorBySerial_801F666C(field_0x290));
                    if (actor != NULL) {
                        actor->field_0x250 = gAudioMgr_8053AF80->field_0x58;
                        actor->field_0x230 = 4;
                        actor->mVel_0x3c = JGeometry::TVec3f(0.0f, 3.0f, 0.0f);
                    }
                }
                break;
            }
            if (field_0x258 == 0) {
                if (gGameRoot_8053AAF8->field_0x7e == 1) {
                    if (fn_80388EEC(field_0x24c)) {
                        if (field_0x268 != 0) {
                            if (fn_8023061C(field_0x274, 0) == true) {
                                die_0x24();
                            }
                        } else {
                            if (fn_80230224(field_0x250, 0) == true) {
                                die_0x24();
                            }
                        }
                    }
                } else {
                    if (fn_80388EEC(field_0x24c)) {
                        if (field_0x268 != 0) {
                            if (fn_80230534(false) == true) {
                                die_0x24();
                            }
                        } else {
                            if (fn_80230224(field_0x250, 0) == true) {
                                die_0x24();
                            }
                        }
                    }
                }
            } else {
                field_0x230 = 3;
            }
        }
        if (checkInputs_8015A374() != 0) {
            field_0x238 = 0;
            fn_8037E8D4(field_0x250);
        }
        break;

    case 2:
        if (field_0x238 > 17) {
            field_0x288 = 14;
        } else if (field_0x238 > 9) {
            field_0x288 = 13;
        } else if (field_0x238 > 8) {
            field_0x288 = 12;
        } else {
            field_0x288 = 11;
            if (gGameRoot_8053AAF8->field_0x7e == 1) {
                if (fn_80388EEC(field_0x24c)) {
                    if (field_0x268 != 0) {
                        if (fn_8023061C(field_0x274, 0) == true) {
                            die_0x24();
                            break;
                        }
                    } else {
                        if (fn_80230224(field_0x250, 0) == true) {
                            die_0x24();
                            break;
                        }
                    }
                }
            } else {
                if (fn_80388EEC(field_0x24c)) {
                    if (field_0x268 != 0) {
                        if (fn_80230534(false) == true) {
                            die_0x24();
                            break;
                        }
                    } else {
                        if (fn_80230224(field_0x250, 0) == true) {
                            die_0x24();
                            break;
                        }
                    }
                }
            }
        }
        fn_80230498(field_0x250, &field_0x27c, field_0x288 + 0x322, 0xFF, -0x80, -0x80, true);
        break;

    case 3:
        break;
    }

    if (field_0x234 == 0x20) {
        if (field_0x23c <= 0) {
            field_0x244 ^= 1;
            field_0x23c = 10;
        }
    } else if (field_0x234 <= 0x0B) {
        if (field_0x23c <= 0) {
            field_0x244++;
            field_0x244 &= 3;
            if (field_0x244 == 0) {
                field_0x23c = 20;
            } else {
                field_0x23c = 2;
            }
        }
    } else {
        if (field_0x23c <= 0) {
            field_0x244 ^= 1;
            field_0x23c = 10;
        }
    }

    if (field_0x238 > 0) {
        field_0x238--;
    }
    if (field_0x23c > 0) {
        field_0x23c--;
    }
    if (field_0x240 > 0) {
        field_0x240--;
    }
}

void LiftableItem_804A01D0::draw() {
    if (!fn_8023188C(field_0x250)) {
        return;
    }
    s32 flag = 0;
    if (field_0x234 >= 8 && field_0x234 <= 11) {
        flag = 1;
    }
    SpriteParams_801F5AE0 params;
    params.field_0x1d = 1;
    params.field_0x1c = 1;
    params.field_0x2d = 1;

    s32 type = field_0x234;
    if (type == 0x2f) {
        return;
    }

    if (type <= 7) {
        drawSprite_801F06F0("enemy_both2_sob.bin", field_0x244 + lbl_804A01A0[type], &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + lbl_804A01A0[field_0x234], flag != 0, 2, -1, true, 0, 0);
    } else if (type <= 11) {
        drawSprite_801F06F0("enemy_gc_sob.bin", field_0x244 + lbl_804A01A0[type], &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + lbl_804A01A0[field_0x234 - 4], flag != 0, 2, -1, true, 0, 0);
    } else if (type >= 0x10 && type <= 0x19) {
        JGeometry::TVec3f pos(mPos.x, mPos.y, mPos.z);
        s32 id = type + 0x1d;
        if (mLayer_0x4 < 8) {
            void* res = gGameRoot_8053AAF8->field_0xa4->getResource('SOB ', "enemy_both2_sob.bin");
            gGameRoot2_8053AB10->field_0x20->drawSobSprite_802F86CC(&pos, res, id, &params, 1.0f, 1.0f);
        }
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x234 + 0x1d, false, 2, -1, true, 0, 0);
    } else if (type == 0x20) {
        drawSprite_801F06F0("enemy_both2_sob.bin", field_0x244 + 0x90, &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + 0x90, false, 2, -1, true, 0, 0);
    } else if (type == 0x21) {
        drawSprite_801F06F0("enemy_both2_sob.bin", field_0x244 + 0x2af, &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + 0x2af, false, 2, -1, true, 0, 0);
    } else if (type == 0x22) {
        drawSprite_801F06F0("enemy_both2_sob.bin", field_0x244 + 0x8c, &params, 7, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + 0x8c, false, 2, -1, false, 0, 0);
    } else if (type == 0x23) {
        params.field_0x2d = 1;
        drawSprite_801F06F0("enemy_both2_sob.bin", 0x2aa, &params, 7, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, 0x2aa, false, 2, -1, false, 0, 0);
    } else if (type == 0x24) {
        drawSprite_801F06F0("enemy_both2_sob.bin", field_0x244 + 0x2c7, &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x244 + 0x2c7, false, 2, -1, true, 0, 0);
    } else if (type == 0x25) {
        drawSprite_801F06F0("enemy_both2_sob.bin", 0x98, &params, -1, 1.0f, 1.0f);
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, 0x98, false, 2, -1, true, 0, 0);
    } else if (type >= 0x2a && type <= 0x2d) {
        drawSprite_801F06F0("enemy_gc_sob.bin", type + 0x255, &params, -1, 1.0f, 1.0f);
    } else if (type == 0x2e) {
        return;
    } else if (type < 0x40) {
        JGeometry::TVec3f pos(mPos.x, mPos.y, mPos.z);
        s32 id = type + 0x11;
        if (mLayer_0x4 < 8) {
            void* res = gGameRoot_8053AAF8->field_0xa4->getResource('SOB ', "enemy_both2_sob.bin");
            gGameRoot2_8053AB10->field_0x20->drawSobSprite_802F86CC(&pos, res, id, &params, 1.0f, 1.0f);
        }
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x234 + 0x11, false, 2, -1, true, 0, 0);
    } else {
        JGeometry::TVec3f pos(mPos.x, mPos.y, mPos.z);
        s32 id = type + 0x1cd;
        if (mLayer_0x4 < 8) {
            void* res = gGameRoot_8053AAF8->field_0xa4->getResource('SOB ', "enemy_both2_sob.bin");
            gGameRoot2_8053AB10->field_0x20->drawSobSprite_802F86CC(&pos, res, id, &params, 1.0f, 1.0f);
        }
        showGbaSprite_803075AC(mSerial, mLayer_0x4, &mPos, field_0x234 + 0x1cd, false, 2, -1, true, 0, 0);
    }
}

void LiftableItem_804A01D0::die_0x24() {
    if (mEmitter2a8 != NULL) {
        mEmitter2a8->becomeInvalidEmitter();
        mEmitter2a8->stopCreateParticle();
        mEmitter2a8 = NULL;
    }
    if (mEmitter2ac != NULL) {
        mEmitter2ac->becomeInvalidEmitter();
        mEmitter2ac->stopCreateParticle();
        mEmitter2ac = NULL;
    }
    if (mEmitter2b0 != NULL) {
        mEmitter2b0->becomeInvalidEmitter();
        mEmitter2b0->stopCreateParticle();
        mEmitter2b0 = NULL;
    }
    s32 serial = field_0x260;
    if (serial != 0) {
        StopNPC_804AA2D8* actor = static_cast<StopNPC_804AA2D8*>(getActorManager_801F856C()->findActorBySerial_801F666C(serial));
        if (actor != NULL) {
            actor->fn_802ED140();
        }
    }
    mAlive = false;
    serial = field_0x278;
    if (serial >= 0) {
        ActorBase_804A5770* actor = getActorManager_801F856C()->findActorBySerial_801F666C(serial);
        if (actor != NULL) {
            actor->mAlive = false;
        }
        field_0x278 = -1;
    }
    if (field_0x294 >= 0) {
        field_0x27c = *getPlayerPos_8023E724(field_0x250);
        getActorManager_801F856C()->spawnActor_801F9484('LSTI', mLayer_0x4, &field_0x27c, (field_0x298 << 22) | field_0x294, -1, -1);
    }
}

void LiftableItem_804A01D0::fn_801597EC() {
    s32 item = field_0x234;
    if (item == 0x10 || (u32)(item - 0x11) <= 1 || (u32)(item - 0x16) <= 2 || item == 0x19) {
        getActorManager_801F856C()->spawnActor_801F9484('KEY0', mLayer_0x4, &mPos, item + 0xF0 + (field_0x250 << 12), -1, -1);
    } else if (item == 0x13) {
        fn_80236DB0(field_0x274);
    } else if (item == 0x15) {
        fn_80236C88(field_0x274);
    } else if (item == 0x20) {
        getActorManager_801F856C()->spawnActor_801F9484('CRTL', mLayer_0x4, &mPos, (field_0x250 << 16) | 1, -1, -1);
    } else if (item == 0x21) {
        getActorManager_801F856C()->spawnActor_801F9484('NIWA', mLayer_0x4, &mPos, (field_0x250 << 8) | 5, -1, -1);
    } else if (item == 0x22) {
        getActorManager_801F856C()->spawnActor_801F9484('BMTY', mLayer_0x4, &mPos, (field_0x250 << 16) | 5, -1, -1);
    } else if (item == 0x23) {
        getActorManager_801F856C()->spawnActor_801F9484('NNJN', mLayer_0x4, &mPos, 0, -1, -1);
    } else if (item == 0x24) {
        getActorManager_801F856C()->spawnActor_801F9484('NIWA', mLayer_0x4, &mPos, (field_0x250 << 8) | 0x1005, -1, -1);
    } else if (item == 0x25) {
        getActorManager_801F856C()->spawnActor_801F9484('CRTL', mLayer_0x4, &mPos, (field_0x250 << 16) | 3, -1, -1);
    } else if (item >= 0x30) {
        if (item == 0x4a) {
            fn_80236ED8(field_0x274, 2);
        } else {
            s32 kind = 1;
            s32 index = item - 0x2f;
            if (item >= 0x40) {
                index = item - 0x3f;
                kind = 2;
            }
            if (field_0x264 == 0) {
                if (field_0x254 == 0 && fn_802373EC(field_0x250) != 0 && gGameRoot_8053AAF8->field_0x7f == 1 && field_0x258 == 0) {
                    field_0x294 = fn_802373EC(field_0x274);
                    field_0x298 = fn_8023725C(field_0x274);
                }
                fn_802372F8(field_0x250, index, kind);
            }
        }
    }
}

void LiftableItem_804A01D0::fn_801597C0() {
    die_0x24();
}

s32 LiftableItem_804A01D0::fn_801597B8() {
    return field_0x230;
}
