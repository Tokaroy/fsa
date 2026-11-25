#include "game/GameAudio.h"
#include "game/cls_804A7BE8.h"
#include "game/ActorManager.h"
#include "game/GameGlobals.h"
#include "game/Player.h"
#include "game/ViewLayer.h"
#include "game/Camera.h"
#include "game/SpriteParams.h"
#include "JSystem/JUtility/JUTGamePad.h"

// FIXME: 99.44 %, regalloc-only; behaviour clean.
// Registers only: count/index/end sit in r28/r30/r29 in the original. The
// 30.0f literal is lbl_8054075C in the original (data split).
void UnknownFORM_804A7BE8::init() {
    if (hasPlayerLeader_8022F514(mSpawnParam_0x90 & 3)) {
        mAlive = false;
        return;
    }
    fn_8022CF08(mSpawnParam_0x90 & 3);
    mPos = *getPlayerPos_8023E724(mSpawnParam_0x90 & 3);
    mPos.z += 30.0f;
    mLife = 0;
    field_0x234 = 1;
    field_0x238 = 0;
    field_0x240 = field_0x23c = fn_8022CAF8(mSpawnParam_0x90 & 3);
    field_0x244 = true;
    mUpdateWhilePaused_0x11f = 1;
    playSe_801F0D20(0x45);
    field_0x248 = mSpawnParam_0x90 & 3;

    s32 i;
    s32 count = 3;
    for (i = 0; i < 4; i++) {
        if (hasPlayerLeader_8022F514(i)) {
            count--;
        }
    }
    if (count == 0) {
        field_0x24c = true;
        if (viewLayerFlag(mLayer_0x4)) {
            field_0x230 = 0x3F;
        } else {
            field_0x230 = 0x3D;
        }
        if (field_0x23c == 5) {
            field_0x23c = 3;
        }
    } else {
        field_0x24c = false;
        if (viewLayerFlag(mLayer_0x4)) {
            field_0x230 = 0x44;
        } else {
            field_0x230 = 0x43;
        }
        if (field_0x23c == 5) {
            field_0x23c = 0;
        }
    }

    field_0x250 = 0;
    field_0x254 = NULL;
    ActorBase_804A5770* actor;
    s32 actorEnd = getActorManager_801F856C()->mActorEnd;
    for (i = 0; i < actorEnd; i++) {
        actor = getActorManager_801F856C()->mActors[i];
        if (actor != NULL && actor->mActorId == 'FGAL' && actor->mAlive == true) {
            field_0x254 = static_cast<FourGirlsControl_804AE4B0*>(actor);
        }
    }
}

UnknownFORM_804A7BE8::~UnknownFORM_804A7BE8() {
    if (field_0x244 == 0 && field_0x240 != field_0x23c) {
        fn_8022CA6C(mSpawnParam_0x90 & 3, field_0x23c, true);
    }
    if (gGameRoot_8053AAF8->field_0x7e == 0) {
        gGameRoot_8053AAF8->fn_80134FE0(0);
    }
    fn_8022CDD4(mSpawnParam_0x90 & 3);
}

// Sprite-state remap tables (rodata, 6 states each): lbl_8046C400 + 0x00..0x48 remap field_0x23c
// on the two shoulder buttons, 0x60 / 0x78 map field_0x23c to the sprite id (field_0x230).
static const s32 lbl_8046C400[6] = {3, 0, 1, 2, 4, 5};
static const s32 lbl_8046C418[6] = {1, 0, 2, 3, 4, 5};
static const s32 lbl_8046C430[6] = {1, 2, 3, 0, 4, 5};
static const s32 lbl_8046C448[6] = {1, 0, 2, 3, 4, 5};
static const s32 lbl_8046C460[6] = {0x3A, 0x3B, 0x3C, 0x39, 0x3E, 0x3E};
static const s32 lbl_8046C478[6] = {0x41, 0x42, 0x39, 0x39, 0x39, 0x40};

// FIXME: 72.89 %, different; behaviour clean.
void UnknownFORM_804A7BE8::update() {
    if (field_0x254 != NULL && field_0x254->mState >= 1 && field_0x254->mState <= 10) {
        field_0x254->fn_803703C8();
    }
    if (field_0x250 != 0) {
        field_0x250--;
        if (field_0x250 == 0) {
            mAlive = false;
            return;
        }
        field_0x238 = 0;
    } else {
        mPos = *getPlayerPos_8023E724(mSpawnParam_0x90 & 3);
        mPos.z += 30.0f;
        if (field_0x234 > 0) {
            field_0x234--;
            if (viewLayerFlag(mLayer_0x4)) {
                if (field_0x24c) {
                    field_0x230 = 0x3F;
                } else {
                    field_0x230 = 0x44;
                }
            } else {
                if (field_0x24c) {
                    field_0x230 = 0x3D;
                } else {
                    field_0x230 = 0x43;
                }
            }
        } else {
            bool changed = false;
            s32 dir = -1;
            JUTGamePad* pad = JUTGamePad::getGamePad(getPlayerInputSlot_8030AAF4(mSpawnParam_0x90 & 3));
            if (fn_8022C5EC(mSpawnParam_0x90 & 3, 0x100)) {
                field_0x244 = false;
                mAlive = false;
                if (field_0x240 == field_0x23c) {
                    fn_80230EB8(mSpawnParam_0x90 & 3, 0x58);
                }
            } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 0x200) || fn_8022C5EC(mSpawnParam_0x90 & 3, 0x40)) {
                field_0x244 = true;
                mAlive = false;
                fn_80230EB8(mSpawnParam_0x90 & 3, 0x58);
            } else if (viewLayerFlag(mLayer_0x4)) {
                field_0x23c = 5;
            } else {
                if (fn_8022C52C(mSpawnParam_0x90 & 3, 0x40)) {
                    if (fn_8022C9AC(mSpawnParam_0x90 & 3)) {
                        if (fn_8022C5EC(mSpawnParam_0x90 & 3, 8)) {
                            dir = 0;
                        } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 4)) {
                            dir = 1;
                        } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 1)) {
                            dir = 2;
                        } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 2)) {
                            dir = 3;
                        }
                    }
                } else if (pad != NULL && field_0x244 == true && fn_8022C9AC(mSpawnParam_0x90 & 3) &&
                           pad->mSubStick.mValue > 0.0f) {
                    s32 angle = pad->mSubStick.mAngle;
                    if (angle < -0x7000 || angle >= 0x7000) {
                        dir = 0;
                    } else if (angle >= -0x5000 && angle < -0x3000) {
                        dir = 2;
                    } else if (angle >= -0x1000 && angle < 0x1000) {
                        dir = 1;
                    } else if (angle >= 0x3000 && angle < 0x5000) {
                        dir = 3;
                    }
                } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 1)) {
                    playSe_801F0D20(0x46);
                    if (field_0x24c) {
                        field_0x23c = lbl_8046C400[field_0x23c];
                    } else {
                        field_0x23c = lbl_8046C418[field_0x23c];
                    }
                } else if (fn_8022C5EC(mSpawnParam_0x90 & 3, 2)) {
                    playSe_801F0D20(0x46);
                    if (field_0x24c) {
                        field_0x23c = lbl_8046C430[field_0x23c];
                    } else {
                        field_0x23c = lbl_8046C448[field_0x23c];
                    }
                }
                if (dir >= 0) {
                    if (dir == 0) {
                        if (field_0x24c) {
                            field_0x23c = 2;
                        } else {
                            field_0x23c = 1;
                        }
                    } else if (dir == 1) {
                        field_0x23c = 1;
                    } else if (dir == 2) {
                        if (field_0x24c) {
                            field_0x23c = 3;
                        } else {
                            field_0x23c = 0;
                        }
                    } else {
                        field_0x23c = 0;
                    }
                    changed = true;
                }
                if (changed == true) {
                    field_0x244 = false;
                    if (field_0x240 == field_0x23c) {
                        fn_80230EB8(mSpawnParam_0x90 & 3, 0x58);
                    }
                    field_0x250 = 6;
                    field_0x238 = 0;
                }
            }
            if (field_0x24c) {
                field_0x230 = lbl_8046C460[field_0x23c];
            } else {
                field_0x230 = lbl_8046C478[field_0x23c];
            }
        }
    }
    field_0x238++;
    if (field_0x238 >= 12) {
        field_0x238 = 0;
    }
    if (viewLayerFlag(mLayer_0x4)) {
        if (field_0x24c) {
            field_0x230 = 0x3F;
        } else {
            field_0x230 = 0x44;
        }
    } else if (field_0x238 >= 6) {
        if (field_0x24c) {
            field_0x230 = 0x3D;
        } else {
            field_0x230 = 0x43;
        }
    }
}

void UnknownFORM_804A7BE8::draw() {
    JGeometry::TVec3f pos(mPos);
    JGeometry::TBox2f box;
    if (mLayer_0x4 == 0) {
        box = gGameRoot2_8053AB10->field_0x24->mViewBox_0x164;
        if (pos.y - pos.z < 28.0f + box.i.y) {
            pos.y += 52.0f;
        }
        if (field_0x24c) {
            if (pos.x < 68.0f + box.i.x) {
                pos.x = 68.0f + box.i.x;
            } else if (pos.x >= box.f.x - 60.0f) {
                pos.x = box.f.x - 60.0f;
            }
        } else {
            if (pos.x < 52.0f + box.i.x) {
                pos.x = 52.0f + box.i.x;
            } else if (pos.x >= box.f.x - 44.0f) {
                pos.x = box.f.x - 44.0f;
            }
        }
    } else {
        fn_8022B8EC(field_0x248, &box);
        if (pos.y - pos.z < 28.0f + box.i.y) {
            pos.y += 52.0f;
        }
        if (field_0x24c) {
            if (fn_8022C8EC(mSpawnParam_0x90 & 3)) {
                if (pos.x < 52.0f + box.i.x) {
                    pos.x = 52.0f + box.i.x;
                } else if (pos.x >= box.f.x - 52.0f) {
                    pos.x = box.f.x - 52.0f;
                }
            } else {
                if (pos.x < 80.0f + box.i.x) {
                    pos.x = 80.0f + box.i.x;
                } else if (pos.x >= box.f.x - 80.0f) {
                    pos.x = box.f.x - 80.0f;
                }
            }
        } else {
            if (fn_8022C8EC(mSpawnParam_0x90 & 3)) {
                if (pos.x < 36.0f + box.i.x) {
                    pos.x = 36.0f + box.i.x;
                } else if (pos.x >= box.f.x - 36.0f) {
                    pos.x = box.f.x - 36.0f;
                }
            } else {
                if (pos.x < 66.0f + box.i.x) {
                    pos.x = 66.0f + box.i.x;
                } else if (pos.x >= box.f.x - 66.0f) {
                    pos.x = box.f.x - 66.0f;
                }
            }
        }
    }
    SpriteParams_801F5AE0 params;
    params.field_0x1c = 2;
    params.field_0x2d = 1;
    s32 id = field_0x230;
    if (mLayer_0x4 < 8) {
        void* res = gGameRoot_8053AAF8->field_0xa4->getResource('SOB ', "enemy_both_sob.bin");
        gGameRoot2_8053AB10->field_0x20->drawSobSprite_802F86CC(&pos, res, id, &params, 1.0f, 1.0f);
    }
    if (fn_8022C8EC(mSpawnParam_0x90 & 3)) {
        fn_80307AC8(mSerial, mLayer_0x4, &pos, field_0x230, 0, 0, -1);
    } else {
        fn_80307AC8(mSerial, mLayer_0x4, &pos, field_0x230, 1, 0, -1);
    }
}
