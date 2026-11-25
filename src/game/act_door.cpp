#include "game/GameAudio.h"
#include "game/GameView.h"
#include "game/Map.h"
#include "game/act/act_door.h"
#include "game/ActorManager.h"
#include "game/BgRewrite.h"
#include "game/Camera.h"
#include "game/Effect.h"
#include "game/GameGlobals.h"
#include "game/Player.h"
#include "game/cls_804AE9B0.h"
#include "game/act/act_small_key.h"
#include "game/act/act_warp.h"

// FIXME(shotgun): 98.90 %, missing/extra; behaviour drift.
void Door_804A8D88::init() {
    field_0x258 = mPos;
    field_0x234 = mSpawnParam_0x90 & 0x7F;
    field_0x238 = (mSpawnParam_0x90 >> 7) & 0x1F;
    field_0x23c = (mSpawnParam_0x90 >> 12) & 0x1F;
    field_0x240 = (mSpawnParam_0x90 >> 17) & 1;
    field_0x24c = (mSpawnParam_0x90 >> 18) & 1;
    field_0x250 = 0;
    field_0x248 = -1;
    if (field_0x234 == 0) {
        field_0x230 = 0;
    } else {
        field_0x230 = 1;
    }
    mBox.i.x = -8.0f;
    mBox.i.y = -8.0f;
    mBox.f.x = 8.0f;
    mBox.f.y = 8.0f;
    switch (field_0x234) {
    case 0:
    case 1:
    case 2:
    case 3:
    case 4:
    case 8:
        switch (field_0x23c) {
        case 0:
            switch (field_0x238) {
            case 0:
                mPos.x += 12.0f;
                mPos.y += 4.0f;
                break;
            case 1:
                mPos.x += 12.0f;
                mPos.y += 12.0f;
                break;
            case 2:
                mPos.x += 12.0f;
                mPos.y += 12.0f;
                break;
            case 3:
                mPos.x += 4.0f;
                mPos.y += 12.0f;
                break;
            }
            break;
        case 1:
            switch (field_0x238) {
            case 0:
                mPos.x += 28.0f;
                mPos.y += 4.0f;
                break;
            case 1:
                mPos.x += 28.0f;
                mPos.y += 12.0f;
                break;
            case 2:
                mPos.x += 12.0f;
                mPos.y += 28.0f;
                break;
            case 3:
                mPos.x += 4.0f;
                mPos.y += 28.0f;
                break;
            }
            break;
        case 2:
            switch (field_0x238) {
            case 0:
                mPos.x += 44.0f;
                mPos.y += 4.0f;
                break;
            case 1:
                mPos.x += 44.0f;
                mPos.y += 12.0f;
                break;
            case 2:
                mPos.x += 12.0f;
                mPos.y += 44.0f;
                break;
            case 3:
                mPos.x += 4.0f;
                mPos.y += 44.0f;
                break;
            }
            break;
        }
        break;
    case 5:
        mBox.i.x = -9.0f;
        mBox.i.y = -9.0f;
        mBox.f.x = 9.0f;
        mBox.f.y = 9.0f;
        mPos.x += 8.0f;
        mPos.y += 8.0f;
        field_0x230 = 2;
        break;
    case 6:
        mBox.i.x = -12.0f;
        mBox.i.y = -12.0f;
        mBox.f.x = 12.0f;
        mBox.f.y = 12.0f;
        mPos.x += 16.0f;
        mPos.y += 16.0f;
        field_0x230 = 2;
        break;
    case 7:
        mBox.i.x = -9.0f;
        mBox.i.y = -9.0f;
        mBox.f.x = 9.0f;
        mBox.f.y = 9.0f;
        mPos.x += 16.0f;
        mPos.y += 8.0f;
        field_0x230 = 2;
        break;
    }
    field_0x264.x = mPos.x;
    field_0x264.y = mPos.y;
    field_0x26c.i.x = mBox.i.x;
    field_0x26c.i.y = mBox.i.y;
    field_0x26c.f.x = mBox.f.x;
    field_0x26c.f.y = mBox.f.y;
    field_0x26c.i.x += field_0x264.x;
    field_0x26c.i.y += field_0x264.y;
    field_0x26c.f.x += field_0x264.x;
    field_0x26c.f.y += field_0x264.y;
    if (field_0x23c == 0 || (field_0x23c == 2 && field_0x234 == 0)) {
        JGeometry::TVec2f v(field_0x258.x, field_0x258.y);
        field_0x244 = getCellIndex_80226BC4(&v, mLayer_0x4);
    } else if (field_0x238 < 2) {
        JGeometry::TVec2f v(field_0x258.x + 16.0f, field_0x258.y);
        field_0x244 = getCellIndex_80226BC4(&v, mLayer_0x4);
    } else {
        JGeometry::TVec2f v(field_0x258.x, field_0x258.y + 16.0f);
        field_0x244 = getCellIndex_80226BC4(&v, mLayer_0x4);
    }
    if ((field_0x234 >= 1 && field_0x234 <= 4) || field_0x234 == 8) {
        s32 layer = mLayer_0x4;
        if (layer < 8) {
            if (getGameView_802D6A9C()->fn_802D49A8(layer, (u16)field_0x244)) {
                field_0x230 = 3;
                update();
                field_0x230 = 5;
            }
        } else {
            if (getGameView_802D6A9C()->fn_802D4ADC(layer, (u16)field_0x244)) {
                field_0x230 = 3;
                update();
                field_0x230 = 5;
            }
        }
    } else if (field_0x234 >= 5) {
        if (getGameView_802D6A9C()->fn_802D4ADC(mLayer_0x4, (u16)field_0x244) == true) {
            field_0x230 = 5;
        }
    } else {
        update();
    }
}


// The unit's .rodata (0x8046D598, 0x270 bytes): BG tile pairs per door type, direction and width,
// and the cell offsets of the second layer.
// [type][dir], width 1
static const u16 lbl_8046D598[9][4][2] = {
    {{0x342, 0x343}, {0x350, 0x351}, {0x345, 0x355}, {0x346, 0x356}},
    {{0x342, 0x343}, {0x350, 0x351}, {0x345, 0x355}, {0x346, 0x356}},
    {{0x32A, 0x32B}, {0x338, 0x339}, {0x32D, 0x33D}, {0x32E, 0x33E}},
    {{0x3A2, 0x3A3}, {0x3B0, 0x3B1}, {0x3A5, 0x3B5}, {0x3A6, 0x3B6}},
    {{0x38A, 0x38B}, {0x398, 0x399}, {0x38D, 0x39D}, {0x38E, 0x39E}},
    {{0x38A, 0x38B}, {0x398, 0x399}, {0x38D, 0x39D}, {0x38E, 0x39E}},
    {{0x38A, 0x38B}, {0x398, 0x399}, {0x38D, 0x39D}, {0x38E, 0x39E}},
    {{0x38A, 0x38B}, {0x398, 0x399}, {0x38D, 0x39D}, {0x38E, 0x39E}},
    {{0x3A2, 0x3A3}, {0x3B0, 0x3B1}, {0x3A5, 0x3B5}, {0x3A6, 0x3B6}},
};
// [type][dir], width 2
static const u16 lbl_8046D628[3][4][4] = {
    {{0x2FA, 0x2FE, 0x2FE, 0x2FB}, {0x2EA, 0x2EE, 0x2EE, 0x2EB}, {0x2EC, 0x2EF, 0x2EF, 0x2FC}, {0x2ED, 0x2FF, 0x2FF, 0x2FD}},
    {{0x2FA, 0x2FE, 0x2FE, 0x2FB}, {0x2EA, 0x2EE, 0x2EE, 0x2EB}, {0x2EC, 0x2EF, 0x2EF, 0x2FC}, {0x2ED, 0x2FF, 0x2FF, 0x2FD}},
    {{0x2DA, 0x2DE, 0x2DE, 0x2DB}, {0x2CA, 0x2CE, 0x2CE, 0x2CB}, {0x2CC, 0x2CF, 0x2CF, 0x2DC}, {0x2CD, 0x2DF, 0x2DF, 0x2DD}},
};
// [type][dir], width 3
static const u16 lbl_8046D688[3][4][6] = {
    {{0x2FA, 0x2FE, 0x2FE, 0x2FE, 0x2FE, 0x2FB}, {0x2EA, 0x2EE, 0x2EE, 0x2EE, 0x2EE, 0x2EB}, {0x2EC, 0x2EF, 0x2EF, 0x2EF, 0x2EF, 0x2FC}, {0x2ED, 0x2FF, 0x2FF, 0x2FF, 0x2FF, 0x2FD}},
    {{0x2FA, 0x2FE, 0x2FE, 0x2FE, 0x2FE, 0x2FB}, {0x2EA, 0x2EE, 0x2EE, 0x2EE, 0x2EE, 0x2EB}, {0x2EC, 0x2EF, 0x2EF, 0x2EF, 0x2EF, 0x2FC}, {0x2ED, 0x2FF, 0x2FF, 0x2FF, 0x2FF, 0x2FD}},
    {{0x2DA, 0x2DE, 0x2DE, 0x2DE, 0x2DE, 0x2DB}, {0x2CA, 0x2CE, 0x2CE, 0x2CE, 0x2CE, 0x2CB}, {0x2CC, 0x2CF, 0x2CF, 0x2CF, 0x2CF, 0x2DC}, {0x2CD, 0x2DF, 0x2DF, 0x2DF, 0x2DF, 0x2DD}},
};
// second layer [dir], width 1, type 2
static const u16 lbl_8046D718[4][2] = {{0x33A, 0x33B}, {0x328, 0x329}, {0x32C, 0x33C}, {0x32F, 0x33F}};
// second layer [dir], width 1, type 4
static const u16 lbl_8046D728[4][2] = {{0x39A, 0x39B}, {0x388, 0x389}, {0x38C, 0x39C}, {0x38F, 0x39F}};
// second layer [dir], width 2
static const u16 lbl_8046D738[4][4] = {{0x2D4, 0x2D5, 0x2D5, 0x2D6}, {0x2C4, 0x2C5, 0x2C5, 0x2C6}, {0x2C7, 0x2C8, 0x2C8, 0x2C9}, {0x2D7, 0x2D8, 0x2D8, 0x2D9}};
// second layer [dir], width 3
static const u16 lbl_8046D758[4][6] = {{0x2D4, 0x2D5, 0x2D5, 0x2D5, 0x2D5, 0x2D6}, {0x2C4, 0x2C5, 0x2C5, 0x2C5, 0x2C5, 0x2C6}, {0x2C7, 0x2C8, 0x2C8, 0x2C8, 0x2C8, 0x2C9}, {0x2D7, 0x2D8, 0x2D8, 0x2D8, 0x2D8, 0x2D9}};
// open [dir], width 1
static const u16 lbl_8046D788[4][2] = {{0x2F0, 0x2F1}, {0x2E0, 0x2E1}, {0x2E2, 0x2F2}, {0x2E3, 0x2F3}};
// open [dir], width 2
static const u16 lbl_8046D798[4][4] = {{0x31A, 0x310, 0x311, 0x31B}, {0x30A, 0x300, 0x301, 0x30B}, {0x30C, 0x302, 0x312, 0x31C}, {0x30D, 0x303, 0x313, 0x31D}};
// open [dir], width 3
static const u16 lbl_8046D7B8[4][6] = {{0x31A, 0x318, 0x310, 0x311, 0x318, 0x31B}, {0x30A, 0x308, 0x300, 0x301, 0x308, 0x30B}, {0x30C, 0x309, 0x302, 0x312, 0x309, 0x31C}, {0x30D, 0x319, 0x303, 0x313, 0x319, 0x31D}};
// second layer cell offset x [dir]
static const s32 lbl_8046D7E8[4] = {0, 0, -16, 16};
// second layer cell offset y [dir]
static const s32 lbl_8046D7F8[4] = {16, -16, 0, 0};

// FIXME(shotgun): 97.80 %, missing/extra; behaviour drift.
void Door_804A8D88::update() {
    JGeometry::TVec2f pos(field_0x258.x, field_0x258.y);
    s32 cell = getCellIndex_80226BC4(&pos, mLayer_0x4);
    switch (field_0x230) {
    case 0:
    case 3: {
        if (!(field_0x234 == 5 || field_0x234 == 6 || field_0x234 == 7)) {
            if (field_0x230 == 3) {
                s32 bit = getGameView_802D6A9C()->fn_802D4C10(mLayer_0x4, field_0x244);
                if (bit != -1) {
                    getGameView_802D6A9C()->setScreenMaskBit_802D7D00(mLayer_0x4, bit, true);
                }
            }
            u8 upper = 8;
            if (mLayer_0x4 < 8) {
                upper = 1;
            }
            switch (field_0x23c) {
            case 0: {
                gBgRewrite_8053AC98->writeTilePair_8029DEBC(mLayer_0x4, cell, (field_0x238 >> 1) & 1, lbl_8046D598[field_0x234][field_0x238][0], lbl_8046D598[field_0x234][field_0x238][1]);
                if (field_0x234 == 0 && field_0x230 == 3) {
                    if (field_0x238 == 0) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x443, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 1) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y, 0.0f), 0x446, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 2) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x444, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 3) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x445, 0, 0, NULL, NULL, true, 1.0f);
                    }
                }
                if (field_0x234 == 2 || field_0x234 == 4) {
                    JGeometry::TVec2f pos2(field_0x258.x + lbl_8046D7E8[field_0x238], field_0x258.y + lbl_8046D7F8[field_0x238]);
                    s32 cell2 = getCellIndex_80226BC4(&pos2, mLayer_0x4);
                    if (field_0x234 == 2) {
                        gBgRewrite_8053AC98->writeTilePair_8029DEBC(mLayer_0x4 + upper, cell2, (field_0x238 >> 1) & 1, lbl_8046D718[field_0x238][0], lbl_8046D718[field_0x238][1]);
                    } else {
                        gBgRewrite_8053AC98->writeTilePair_8029DEBC(mLayer_0x4 + upper, cell2, (field_0x238 >> 1) & 1, lbl_8046D728[field_0x238][0], lbl_8046D728[field_0x238][1]);
                    }
                }
                break;
            }
            case 1: {
                gBgRewrite_8053AC98->writeFourTiles_8029DD50(
                    mLayer_0x4, cell, (field_0x238 >> 1) & 1,
                    lbl_8046D628[field_0x234][field_0x238][0],
                    lbl_8046D628[field_0x234][field_0x238][1],
                    lbl_8046D628[field_0x234][field_0x238][2],
                    lbl_8046D628[field_0x234][field_0x238][3]);
                if (field_0x234 == 0 && field_0x230 == 3) {
                    if (field_0x238 == 0) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(32.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x43F, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 1) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(32.0f + field_0x258.x, field_0x258.y, 0.0f), 0x442, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 2) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 32.0f + field_0x258.y, 0.0f), 0x440, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 3) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 32.0f + field_0x258.y, 0.0f), 0x441, 0, 0, NULL, NULL, true, 1.0f);
                    }
                }
                if (field_0x234 == 2) {
                    JGeometry::TVec2f pos2(field_0x258.x + lbl_8046D7E8[field_0x238], field_0x258.y + lbl_8046D7F8[field_0x238]);
                    s32 cell2 = getCellIndex_80226BC4(&pos2, mLayer_0x4);
                    gBgRewrite_8053AC98->writeFourTiles_8029DD50(
                        mLayer_0x4 + upper, cell2, (field_0x238 >> 1) & 1,
                        lbl_8046D738[field_0x238][0],
                        lbl_8046D738[field_0x238][1],
                        lbl_8046D738[field_0x238][2],
                        lbl_8046D738[field_0x238][3]);
                }
                break;
            }
            case 2: {
                gBgRewrite_8053AC98->writeTileRun_8029DB2C(mLayer_0x4, cell, (field_0x238 >> 1) & 1, lbl_8046D688[field_0x234][field_0x238][0], lbl_8046D688[field_0x234][field_0x238][1], lbl_8046D688[field_0x234][field_0x238][2], lbl_8046D688[field_0x234][field_0x238][3], lbl_8046D688[field_0x234][field_0x238][4], lbl_8046D688[field_0x234][field_0x238][5]);
                if (field_0x234 == 0 && field_0x230 == 3) {
                    if (field_0x238 == 0) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(48.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x43B, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 1) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(48.0f + field_0x258.x, field_0x258.y, 0.0f), 0x43E, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 2) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 48.0f + field_0x258.y, 0.0f), 0x43C, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x238 == 3) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 48.0f + field_0x258.y, 0.0f), 0x43D, 0, 0, NULL, NULL, true, 1.0f);
                    }
                }
                if (field_0x234 == 2) {
                    JGeometry::TVec2f pos2(field_0x258.x + lbl_8046D7E8[field_0x238], field_0x258.y + lbl_8046D7F8[field_0x238]);
                    cell = getCellIndex_80226BC4(&pos2, mLayer_0x4);
                    gBgRewrite_8053AC98->writeTileRun_8029DB2C(mLayer_0x4, cell, (field_0x238 >> 1) & 1, lbl_8046D758[field_0x238][0], lbl_8046D758[field_0x238][1], lbl_8046D758[field_0x238][2], lbl_8046D758[field_0x238][3], lbl_8046D758[field_0x238][4], lbl_8046D758[field_0x238][5]);
                    gBgRewrite_8053AC98->writeTileRun_8029DB2C(mLayer_0x4 + upper, cell, (field_0x238 >> 1) & 1, lbl_8046D758[field_0x238][0], lbl_8046D758[field_0x238][1], lbl_8046D758[field_0x238][2], lbl_8046D758[field_0x238][3], lbl_8046D758[field_0x238][4], lbl_8046D758[field_0x238][5]);
                }
                break;
            }
            }
            if (field_0x234 == 8) {
                startSound_801F0E34(0x30006, 0);
            } else {
                startSound_801F0E34(0x30007, 0);
            }
            if ((field_0x230 == 3 && field_0x234 == 2) || field_0x234 == 4) {
                if (mLayer_0x4 >= 8) {
                    JGeometry::TVec3f p = field_0x258;
                    JGeometry::TVec3f spawnPos(8.0f + p.x, 10.0f + p.y, 0.0f);
                    getActorManager_801F856C()->spawnActor_801F9484('KMRI', mLayer_0x4, &spawnPos, 0, -1, -1);
                }
            } else if (field_0x234 == 8) {
                playSe_801F0D20(3);
            }
            if (field_0x230 == 3 && field_0x234 == 0 && field_0x240 == 0) {
                getActorManager_801F856C()->spawnActor_801F9484('SEN2', mLayer_0x4, &mPos, 0x2800, -1, -1);
            }
            if (field_0x230 == 0) {
                field_0x230 = 1;
            } else if (field_0x234 == 0 && field_0x240 != 0) {
                field_0x230 = 6;
            } else if (field_0x234 == 0 && mLayer_0x4 < 8 && field_0x24c != 0) {
                field_0x230 = 9;
                field_0x250 = 120;
            } else {
                field_0x230 = 5;
            }
        } else if (field_0x230 == 3) {
            if (field_0x234 == 5) {
                gBgRewrite_8053AC98->fn_802A3948(&field_0x258, 0, mLayer_0x4, 0x9E);
                if (mLayer_0x4 >= 8) {
                    JGeometry::TVec3f p = field_0x258;
                    p.z = 0.0f;
                    getActorManager_801F856C()->spawnActor_801F9484('KMRI', mLayer_0x4, &p, 0, -1, -1);
                } else {
                    spawnEmitter_8013CC50(mLayer_0x4, &field_0x258, 0x564, 0, 0, NULL, NULL, true, 0.5f);
                    spawnEmitter_8013CC50(mLayer_0x4, &field_0x258, 0x503, 1, 0, NULL, NULL, true, 1.0f);
                }
                startSound_801F0E34(0x30075, 0);
                field_0x230 = 5;
            } else if (field_0x234 == 6) {
                gBgRewrite_8053AC98->fn_8029DF80(cell, mLayer_0x4, 999, 1000, 1001, 1002);
                if (mLayer_0x4 >= 8) {
                    JGeometry::TVec3f p = field_0x258;
                    p.z = 0.0f;
                    getActorManager_801F856C()->spawnActor_801F9484('KMRI', mLayer_0x4, &p, 0, -1, -1);
                } else {
                    spawnEmitter_8013CC50(mLayer_0x4, &field_0x258, 0x564, 0, 0, NULL, NULL, true, 0.5f);
                    spawnEmitter_8013CC50(mLayer_0x4, &field_0x258, 0x503, 1, 0, NULL, NULL, true, 1.0f);
                }
                startSound_801F0E34(0x30075, 0);
                field_0x230 = 5;
            }
        }
        break;
    }
    case 1:
        if (!getGameView_802D6A9C()->isInTransition_802DCD0C() && field_0x234 == 0) {
            field_0x230 = 4;
        } else {
            field_0x230 = 2;
        }
        break;
    case 2:
        switch (field_0x234) {
        case 0:
            if (!isScreenFlagSet_0x34()) {
                break;
            }
            if (mLayer_0x4 < 8 && field_0x24c != 0 && field_0x240 == 0) {
                field_0x230 = 8;
            } else {
                field_0x230 = 3;
            }
            break;
        case 1:
        case 3:
        case 5:
        case 6:
            field_0x248 = fn_8023AF14(&field_0x26c, mLayer_0x4, false, 0.0f);
            if (field_0x248 < 0) {
                break;
            }
            if (fn_8022CAF8(field_0x248) == 4) {
                if (fn_8022F478(field_0x248) || getPlayerHeldActorId_8023EEB4(field_0x248) != 'KEY0') {
                    break;
                }
                SmallKey_804A8CD8* key = static_cast<SmallKey_804A8CD8*>(getActorManager_801F856C()->findActorBySerial_801F666C(fn_8023EF50(field_0x248)));
                if (key == NULL || (key->mSpawnParam_0x90 & 0x1F)) {
                    break;
                }
                fn_8023EE28(field_0x248);
                key->fn_802C1D90();
                field_0x230 = 0xA;
                break;
            }
            for (s32 i = 0; i < 4; i++) {
                if (i == field_0x248 || (hasPlayerLeader_8022F514(i) == true && field_0x248 == getPlayerLeader_8022F3DC(i))) {
                    if (getPlayerHeldActorId_8023EEB4(i) != 'KEY0') {
                        continue;
                    }
                    SmallKey_804A8CD8* key = static_cast<SmallKey_804A8CD8*>(getActorManager_801F856C()->findActorBySerial_801F666C(fn_8023EF50(i)));
                    if (key == NULL || (key->mSpawnParam_0x90 & 0x1F)) {
                        continue;
                    }
                    fn_8023EE28(i);
                    key->fn_802C1D90();
                    field_0x230 = 0xA;
                    break;
                }
            }
            break;
        case 2:
        case 4:
            if (field_0x240 == 0) {
                s32 serial = findOverlappingActor_801F2718('HBMB');
                if (serial < 0) {
                    break;
                }
                ActorBase_804A5770* bomb = getActorManager_801F856C()->findActorBySerial_801F666C(serial);
                if (bomb->field_0x94 == 0) {
                    break;
                }
                field_0x230 = 3;
                getActorManager_801F856C()->spawnActor_801F9484('SEN2', mLayer_0x4, &mPos, 0x3C00, -1, -1);
                if (field_0x238 == 0) {
                    spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y, 0.0f), 0x5D, 0, 0, NULL, NULL, true, 1.0f);
                } else if (field_0x238 == 1) {
                    if (field_0x23c == 0) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x60, 0, 0, NULL, NULL, true, 1.0f);
                    } else if (field_0x23c == 2) {
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(20.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x60, 0, 0, NULL, NULL, true, 1.0f);
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(36.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x60, 0, 0, NULL, NULL, true, 1.0f);
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(52.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x60, 0, 0, NULL, NULL, true, 1.0f);
                        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(68.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x60, 0, 0, NULL, NULL, true, 1.0f);
                    }
                } else if (field_0x238 == 2) {
                    spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x5E, 0, 0, NULL, NULL, true, 1.0f);
                } else if (field_0x238 == 3) {
                    spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x5F, 0, 0, NULL, NULL, true, 1.0f);
                }
                if (bomb->mSpawnParam_0x90 == 12) {
                    break;
                }
                s32 warpSerial = findOverlappingActor_801F2718('WARP');
                if (warpSerial < 0) {
                    break;
                }
                Warp_804A6DC8* warp = static_cast<Warp_804A6DC8*>(getActorManager_801F856C()->findActorBySerial_801F666C(warpSerial));
                if (warp == NULL) {
                    break;
                }
                const JGeometry::TVec3f* spawnPos = &warp->field_0x238;
                s32 raw = (warp->mSpawnParam_0x90 >> 24) & 7;
                s32 layer = raw + 7;
                if (raw == 0) {
                    layer = raw;
                }
                getActorManager_801F856C()->spawnActor_801F9484('HBMB', layer, spawnPos, 0xC, -1, -1);
            } else if (isScreenFlagSet_0x34()) {
                field_0x230 = 3;
            }
            break;
        case 7: {
            field_0x248 = fn_8023AF14(&field_0x26c, mLayer_0x4, false, 0.0f);
            if (field_0x248 < 0 || getPlayerHeldActorId_8023EEB4(field_0x248) != 'KEY0') {
                break;
            }
            SmallKey_804A8CD8* key = static_cast<SmallKey_804A8CD8*>(getActorManager_801F856C()->findActorBySerial_801F666C(fn_8023EF50(field_0x248)));
            if (key == NULL || (key->mSpawnParam_0x90 & 0xF) != 1) {
                break;
            }
            fn_8023EE28(field_0x248);
            key->fn_802C1DFC();
            bool talk = false;
            if (gGameRoot_8053AAF8->field_0x7e == 1) {
                if (fn_802308E0(field_0x248) == true) {
                    talk = true;
                }
            } else if (fn_8023077C() == true) {
                lbl_8053AD70->fn_8037AE30();
                talk = true;
            }
            if (talk == true) {
                field_0x230 = 0xC;
            }
            break;
        }
        case 8: {
            JGeometry::TVec2f p(field_0x258.x, field_0x258.y);
            field_0x248 = fn_8023B8E4(&field_0x26c, mLayer_0x4, &p, true);
            if (field_0x248 >= 0) {
                field_0x230 = 3;
            }
            break;
        }
        }
        break;
    case 4: {
        if (field_0x234 == 0 && isScreenFlagSet_0x34()) {
            field_0x230 = 6;
            break;
        }
        s32 bit = getGameView_802D6A9C()->fn_802D4C10(mLayer_0x4, field_0x244);
        if (bit != -1) {
            getGameView_802D6A9C()->setScreenMaskBit_802D7D00(mLayer_0x4, bit, false);
        }
        switch (field_0x23c) {
        case 0: {
            gBgRewrite_8053AC98->writeTilePair_8029DEBC(mLayer_0x4, cell, (field_0x238 >> 1) & 1, lbl_8046D788[field_0x238][0], lbl_8046D788[field_0x238][1]);
            if (field_0x234 != 0) {
                break;
            }
            if (field_0x238 == 0) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x437, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 1) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y, 0.0f), 0x43A, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 2) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x438, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 3) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x439, 0, 0, NULL, NULL, true, 1.0f);
            }
            break;
        }
        case 1: {
            gBgRewrite_8053AC98->writeFourTiles_8029DD50(
                mLayer_0x4, cell, (field_0x238 >> 1) & 1,
                lbl_8046D798[field_0x238][0],
                lbl_8046D798[field_0x238][1],
                lbl_8046D798[field_0x238][2],
                lbl_8046D798[field_0x238][3]);
            if (field_0x234 != 0) {
                break;
            }
            if (field_0x238 == 0) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(32.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x433, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 1) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(32.0f + field_0x258.x, field_0x258.y, 0.0f), 0x436, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 2) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 32.0f + field_0x258.y, 0.0f), 0x434, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 3) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 32.0f + field_0x258.y, 0.0f), 0x435, 0, 0, NULL, NULL, true, 1.0f);
            }
            break;
        }
        case 2: {
            gBgRewrite_8053AC98->writeTileRun_8029DB2C(mLayer_0x4, cell, (field_0x238 >> 1) & 1, lbl_8046D7B8[field_0x238][0], lbl_8046D7B8[field_0x238][1], lbl_8046D7B8[field_0x238][2], lbl_8046D7B8[field_0x238][3], lbl_8046D7B8[field_0x238][4], lbl_8046D7B8[field_0x238][5]);
            if (field_0x234 != 0) {
                break;
            }
            if (field_0x238 == 0) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(48.0f + field_0x258.x, 16.0f + field_0x258.y, 0.0f), 0x42F, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 1) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(48.0f + field_0x258.x, field_0x258.y, 0.0f), 0x432, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 2) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, 48.0f + field_0x258.y, 0.0f), 0x430, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 3) {
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 48.0f + field_0x258.y, 0.0f), 0x431, 0, 0, NULL, NULL, true, 1.0f);
            }
            break;
        }
        }
        startSound_801F0E34(0x30008, 0);
        field_0x230 = 2;
        break;
    }
    case 5:
        mAlive = false;
        break;
    case 6:
        switch (field_0x234) {
        case 0:
            if (!isScreenFlagSet_0x34()) {
                field_0x230 = 4;
            }
            break;
        }
        break;
    case 7: {
        if (field_0x248 < 0) {
            field_0x230 = 3;
            break;
        }
        if (fn_802308E0(field_0x248) != true) {
            break;
        }
        s32 leader = field_0x248;
        if (hasPlayerLeader_8022F514(field_0x248)) {
            leader = getPlayerLeader_8022F3DC(field_0x248);
        }
        for (s32 i = 0; i < 4; i++) {
            JGeometry::TVec3f player = *getPlayerPos_8023E724(i);
            JGeometry::TVec3f p = player;
            p.x = 1.0f + player.x;
            p.y = player.y - 12.0f;
            p.z = player.z;
            if (hasPlayerLeader_8022F514(i) == true && leader == getPlayerLeader_8022F3DC(i)) {
                if (i == field_0x248) {
                    getActorManager_801F856C()->spawnActor_801F9484('IMUP', mLayer_0x4, &p, 0x800004 + (i << 24) + (field_0x248 << 26), -1, -1);
                }
            } else if (i == leader && i == field_0x248) {
                getActorManager_801F856C()->spawnActor_801F9484('IMUP', mLayer_0x4, &p, 0x800004 + (i << 24) + (field_0x248 << 26), -1, -1);
            }
        }
        field_0x230 = 3;
        break;
    }
    case 8:
        gGameRoot2_8053AB10->field_0x24->addFocusPoint_8030C210(&mPos);
        if (gGameRoot2_8053AB10->field_0x24->isOnScreen_8030C2A8(&mPos) == true) {
            field_0x230 = 3;
        }
        break;
    case 9:
        gGameRoot2_8053AB10->field_0x24->addFocusPoint_8030C210(&mPos);
        if (field_0x250 == 0) {
            field_0x230 = 5;
        } else {
            field_0x250--;
        }
        break;
    case 0xA:
        if (field_0x234 == 5) {
            spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(8.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B3, 0, 0, NULL, NULL, true, 1.0f);
            spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(8.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B4, 0, 0, NULL, NULL, true, 1.0f);
            spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(8.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B5, 0, 0, NULL, NULL, true, 1.0f);
        } else {
            f32 offset = 0.0f;
            if (field_0x238 == 0) {
                if (field_0x23c == 0) {
                    offset = 16.0f;
                } else if (field_0x23c == 1) {
                    offset = 32.0f;
                } else if (field_0x23c == 2) {
                    offset = 48.0f;
                }
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, 16.0f + field_0x258.y, 0.0f), 0x4AA, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, 16.0f + field_0x258.y, 0.0f), 0x4AB, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, 16.0f + field_0x258.y, 0.0f), 0x4AC, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 1) {
                if (field_0x23c == 0) {
                    offset = 16.0f;
                } else if (field_0x23c == 1) {
                    offset = 32.0f;
                } else if (field_0x23c == 2) {
                    offset = 48.0f;
                }
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, field_0x258.y, 0.0f), 0x4B3, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, field_0x258.y, 0.0f), 0x4B4, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x + offset, field_0x258.y, 0.0f), 0x4B5, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 2) {
                if (field_0x23c == 0) {
                    offset = 16.0f;
                } else if (field_0x23c == 1) {
                    offset = 32.0f;
                } else if (field_0x23c == 2) {
                    offset = 48.0f;
                }
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, field_0x258.y + offset, 0.0f), 0x4AD, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, field_0x258.y + offset, 0.0f), 0x4AE, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(field_0x258.x, field_0x258.y + offset, 0.0f), 0x4AF, 0, 0, NULL, NULL, true, 1.0f);
            } else if (field_0x238 == 3) {
                if (field_0x23c == 0) {
                    offset = 16.0f;
                } else if (field_0x23c == 1) {
                    offset = 32.0f;
                } else if (field_0x23c == 2) {
                    offset = 48.0f;
                }
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y + offset, 0.0f), 0x4B0, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y + offset, 0.0f), 0x4B1, 0, 0, NULL, NULL, true, 1.0f);
                spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y + offset, 0.0f), 0x4B2, 0, 0, NULL, NULL, true, 1.0f);
            }
        }
        field_0x254 = 17;
        field_0x230 = 0xB;
        break;
    case 0xB:
        field_0x254--;
        if (field_0x254 != 0) {
            break;
        }
        field_0x230 = 3;
        startSound_801F0E34(0x30009, 0);
        if (gGameRoot_8053AAF8->field_0x7e == 1) {
            field_0x230 = 7;
        }
        break;
    case 0xC:
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B3, 0, 0, NULL, NULL, true, 1.0f);
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B4, 0, 0, NULL, NULL, true, 1.0f);
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 4.0f + field_0x258.y, 0.0f), 0x4B5, 0, 0, NULL, NULL, true, 1.0f);
        field_0x254 = 17;
        field_0x230 = 0xD;
        break;
    case 0xD:
        field_0x254--;
        if (field_0x254 != 0) {
            break;
        }
        gBgRewrite_8053AC98->fn_802A3948(&field_0x258, 0, mLayer_0x4, 0xBC);
        gBgRewrite_8053AC98->fn_802A3948(&JGeometry::TVec3f(16.0f + field_0x258.x, field_0x258.y, field_0x258.z), 0, mLayer_0x4, 0xBD);
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 8.0f + field_0x258.y, 0.0f), 0xCD, 0, 0, NULL, NULL, true, 1.0f);
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 8.0f + field_0x258.y, 0.0f), 0xCE, 0, 1, NULL, NULL, true, 1.0f);
        spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(16.0f + field_0x258.x, 8.0f + field_0x258.y, 0.0f), 0xCF, 0, 1, NULL, NULL, true, 1.0f);
        startSound_801F0E34(0x30076, 0);
        field_0x254 = 15;
        field_0x230 = 0xE;
        break;
    case 0xE:
        if (field_0x254 == 0) {
            bool done = false;
            if (gGameRoot_8053AAF8->field_0x7e == 1) {
                if (fn_8023061C(field_0x248, false) == true) {
                    done = true;
                }
            } else if (fn_80230534(false) == true) {
                done = true;
            }
            if (done == true) {
                getActorManager_801F856C()->spawnActor_801F9484('TKRA', mLayer_0x4, &mPos, (field_0x248 << 12) + 0x208, -1, -1);
                field_0x230 = 5;
            }
        } else {
            field_0x254--;
        }
        break;
    }
}

void Door_804A8D88::draw() {}

void Door_804A8D88::fn_802C59B0(const JGeometry::TVec3f* delta) {
    field_0x258.x += delta->x;
    field_0x258.y += delta->y;
}

Door_804A8D88::~Door_804A8D88() {}
