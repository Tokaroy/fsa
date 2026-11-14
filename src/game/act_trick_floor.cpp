#include "game/GameAudio.h"
#include "game/GameGlobals.h"
#include "game/GameView.h"
#include "game/Map.h"
#include "game/SpriteParams.h"
#include "JSystem/JMath/JMath.h"
#include <math.h>
#include "game/act/act_trick_floor.h"

// Tile rows / columns the kind lays down at init (rodata, in this unit).
static const s32 lbl_8046C8B0[7] = {4, 4, 6, 4, 6, 6, 4};
static const s32 lbl_8046C8CC[7] = {4, 4, 5, 5, 6, 6, 4};
static const u16 lbl_8046C8E8[4][4] = {
    {0x1B0, 0x1B0, 0x1B0, 0x1B0},
    {0x1B0, 0x1D8, 0x1DA, 0x1B0},
    {0x1B0, 0x1D9, 0x1DB, 0x1B0},
    {0x1B0, 0x1B0, 0x1B0, 0x1B0},
};
static const f32 lbl_8046C908[7] = {32.0f, 32.0f, 48.0f, 32.0f, 64.0f, 64.0f, 32.0f};
static const f32 lbl_8046C924[7] = {32.0f, 32.0f, 40.0f, 40.0f, 64.0f, 64.0f, 32.0f};
static const f32 lbl_8046C940[7] = {1.0f, 1.0f, 1.5f, 1.0f, 1.0f, 1.0f, 1.0f};
static const f32 lbl_8046C95C[7] = {1.0f, 1.0f, 1.3f, 1.3f, 1.0f, 1.0f, 1.0f};

// FIXME(shotgun): 98.13 %, operands + reloc-name; behaviour clean.
void TrickFloor_804A83A0::init() {
    field_0x234 = field_0x90 & 0x7F;
    field_0x238 = (field_0x90 >> 7) & 0x1F;
    field_0x240 = (field_0x90 >> 12) & 0xFFF;
    field_0x23c = (field_0x90 >> 24) & 3;
    field_0x248 = 0.0f;
    switch (field_0x234) {
    case 6:
    default:
        if (field_0x23c == 1) {
            mBox.set(-20.0f, -20.0f, 20.0f, 20.0f);
        } else {
            mBox.set(-32.0f, -32.0f, 32.0f, 32.0f);
        }
        break;
    case 2:
        mBox.i.x = -40.0f;
        mBox.i.y = -32.0f;
        mBox.f.x = 40.0f;
        mBox.f.y = 32.0f;
        break;
    case 3:
        mBox.i.x = -24.0f;
        mBox.i.y = -32.0f;
        mBox.f.x = 24.0f;
        mBox.f.y = 32.0f;
        break;
    case 4:
    case 5:
        mBox.i.x = -16.0f;
        mBox.i.y = -50.0f;
        mBox.f.x = 24.0f;
        mBox.f.y = 50.0f;
        field_0x248 = -0.06f;
        break;
    }
    field_0x244 = 20;
    if (gGameRoot_8053AAF8->field_0x7f == 1) {
        field_0x252 = 12;
    } else {
        field_0x252 = 13;
    }
    if (field_0x234 >= 2) {
        f32 px = mPos.x;
        s32 layer = field_0x4;
        GameView_804A9950* gameView = getGameView_802D6A9C();
        const JGeometry::TBox2f* src = (layer < 8) ? &gameView->mVisibleBox : &gameView->field_0xdc;
        JGeometry::TBox2f view;
        view = *src;
        for (s32 i = 0; i < lbl_8046C8B0[field_0x234]; i++) {
            f32 py = mPos.y;
            s32 tx = (s32)(px - view.i.x);
            for (s32 j = 0; j < lbl_8046C8CC[field_0x234]; j++) {
                s32 x = tx;
                s32 y = (s32)(py - view.i.y);
                if (x < 0) {
                    x = 0;
                } else if (x >= 0x200) {
                    x = 0x1FF;
                }
                if (y < 0) {
                    y = 0;
                } else if (y >= 0x200) {
                    y = 0x1FF;
                }
                s32 idx =(x & 0x100) | ((y << 1) & 0x200) | (y & 0xF0) | ((x >> 4) & 0xF);
                gGameRoot2_8053AB10->field_0x20->fn_802F9974(field_0x4, idx, 6);
                py += 16.0f;
            }
            px += 16.0f;
        }
    }
    field_0x230 = 0;
}

// The rotation part of m from Euler angles (R = Rz Ry Rx), as setRotScaleMtx (game/RotMatrix.h)
// without the scale and with the cosines first (z, y, x, then the sines).
static inline void setRotMtx(Mtx m, const JGeometry::TVec3f& rot) {
    f32 cz = cos(rot.z);
    f32 cy = cos(rot.y);
    f32 cx = cos(rot.x);
    f32 sz = sin(rot.z);
    f32 sy = sin(rot.y);
    f32 sx = sin(rot.x);
    m[0][0] = cy * cz;
    m[1][0] = cy * sz;
    m[2][0] = -sy;
    m[0][1] = sx * sy * cz - cx * sz;
    m[1][1] = sx * sy * sz + cx * cz;
    m[2][1] = sx * cy;
    m[0][2] = cx * cz * sy + sx * sz;
    m[1][2] = cx * sz * sy - sx * cz;
    m[2][2] = cx * cy;
}

// Draws the 'SMP ' sprite `name` at pos with the floor's params, below layer 8.
static inline void drawSmp(TrickFloor_804A83A0* self, const JGeometry::TVec3f* pos, const char* name,
                           SpriteParams_801F5AE0* params) {
    if (self->field_0x4 < 8) {
        void* res = gGameRoot_8053AAF8->field_0xa4->getResource('SMP ', name);
        gGameRoot2_8053AB10->field_0x20->fn_802F6CF4(pos, res, params);
    }
}

// The tile index of a view-relative position (as init computes it).
static inline s32 tileIndex(s32 tx, s32 ty) {
    s32 cx = tx;
    if (cx < 0) {
        cx = 0;
    } else if (cx >= 0x200) {
        cx = 0x1FF;
    }
    s32 cy = ty;
    if (cy < 0) {
        cy = 0;
    } else if (cy >= 0x200) {
        cy = 0x1FF;
    }
    return (cx & 0x100) | ((cy & 0x100) << 1) | (cy & 0xF0) | ((cx >> 4) & 0xF);
}

// Sets every tile of the floor's block (counts by kind) from x to `tile`.
static inline void fillTiles(TrickFloor_804A83A0* self, f32 x, u16 tile) {
    s32 layer = self->field_0x4;
    GameView_804A9950* view = getGameView_802D6A9C();
    const JGeometry::TBox2f* src = layer < 8 ? &view->mVisibleBox : &view->field_0xdc;
    JGeometry::TBox2f box;
    box = *src;
    for (s32 i = 0; i < lbl_8046C8B0[self->field_0x234]; i++) {
        s32 tx = (s32)(x - box.i.x);
        f32 y = self->mPos.y;
        for (s32 j = 0; j < lbl_8046C8CC[self->field_0x234]; j++) {
            s32 ty = (s32)(y - box.i.y);
            gGameRoot2_8053AB10->field_0x20->fn_802F9974(self->field_0x4, tileIndex(tx, ty), tile);
            y += 16.0f;
        }
        x += 16.0f;
    }
}

// The four dust emitters 0x381-0x384 at the floor's corner.
static inline void spawnDust(TrickFloor_804A83A0* self, s32 a) {
    {
        JGeometry::TVec3f pos(32.0f + self->mPos.x, 32.0f + self->mPos.y, 0.0f);
        spawnEmitter_8013CC50(self->field_0x4, &pos, 0x381, a, 0, NULL, NULL, true, 1.0f);
    }
    {
        JGeometry::TVec3f pos(32.0f + self->mPos.x, 32.0f + self->mPos.y, 0.0f);
        spawnEmitter_8013CC50(self->field_0x4, &pos, 0x382, a, 0, NULL, NULL, true, 1.0f);
    }
    {
        JGeometry::TVec3f pos(32.0f + self->mPos.x, 32.0f + self->mPos.y, 0.0f);
        spawnEmitter_8013CC50(self->field_0x4, &pos, 0x383, a, 0, NULL, NULL, true, 1.0f);
    }
    {
        JGeometry::TVec3f pos(32.0f + self->mPos.x, 32.0f + self->mPos.y, 0.0f);
        spawnEmitter_8013CC50(self->field_0x4, &pos, 0x384, a, 0, NULL, NULL, true, 1.0f);
    }
}

// Who stands on the floor, then: 0 reads the tile under it, 1 waits for the switch,
// 2 waits for a rider (kinds 4/5: all four players) and drops, 3 sinks, 4 holds while
// ridden, 5 rises back and restores the tiles, 6 / 7 fall away, 8 stays down.
void TrickFloor_804A83A0::update() {
    JGeometry::TVec3f savedPos = mPos;
    switch (field_0x234) {
    case 6:
    default:
        mPos.x += 32.0f;
        mPos.y += 32.0f;
        break;
    case 2:
        mPos.x += 48.0f;
        mPos.y += 40.0f;
        break;
    case 3:
        mPos.x += 32.0f;
        mPos.y += 40.0f;
        break;
    case 4:
    case 5: {
        field_0x80.set(-48.0f, -48.0f, 48.0f, 48.0f);
        JGeometry::TBox2f box;
        box = field_0x80;
        mPos.x += 48.0f;
        mPos.y += 48.0f;
        JGeometry::TVec2f p(mPos.x, mPos.y);
        box.addPos(p);
        fn_80239914(&box, field_0x4, mSerial);
        mPos = savedPos;
        mPos.y += 48.0f;
        mBox.set(-16.0f, -50.0f, 24.0f, 50.0f);
        break;
    }
    }

    JGeometry::TVec2f p(mPos.x, mPos.y);
    JGeometry::TBox2f box = mBox;
    box.addPos(p);
    s32 standing = -1;
    for (s32 i = 0; i < 4; i++) {
        JGeometry::TVec3f p = *getPlayerPos_8023E724(i);
        if (p.x >= box.i.x && p.y >= box.i.y && p.x < box.f.x && p.y < box.f.y) {
            standing = i;
            if (fn_8022F478(i)) {
                standing = -1;
            } else {
                break;
            }
        }
    }
    if (field_0x23c == 1 && standing >= 0 && !fn_80234F68(standing)) {
        standing = -1;
    }
    s32 ball = fn_801F2718('SBAL');
    fn_8023A89C(&box, field_0x4, &p);
    s32 pushers = 0;
    for (s32 i = 0; i < 4; i++) {
        if (fn_8023A97C(i, &box, field_0x4, &p)) {
            pushers++;
        }
    }
    mPos = savedPos;

    switch (field_0x230) {
    case 0: {
        s32 layer = field_0x4;
        GameView_804A9950* gameView = getGameView_802D6A9C();
        const JGeometry::TBox2f* src = layer < 8 ? &gameView->mVisibleBox : &gameView->field_0xdc;
        JGeometry::TBox2f vbox;
        vbox = *src;
        s32 tx = (s32)(mPos.x - vbox.i.x);
        s32 ty = (s32)(mPos.y - vbox.i.y);
        field_0x250 = gGameRoot2_8053AB10->field_0x20->fn_802F9908(field_0x4, tileIndex(tx, ty));
        field_0x230 = 1;
        break;
    }
    case 1:
        if (field_0x238 != 0) {
            if (getGameView_802D6A9C()->fn_802D800C(field_0x238)) {
                field_0x230 = 2;
            }
        } else {
            field_0x230 = 2;
        }
        if (field_0x234 == 4 || field_0x234 == 5) {
            field_0x230 = 2;
            break;
        }
        if (field_0x230 == 2 && field_0x234 >= 2) {
            field_0x230 = 3;
            startSound_801F0E34(0x3001B, 0);
        }
        break;
    case 2:
        switch (field_0x234) {
        case 0:
        case 1:
        case 2:
        case 3:
        case 6:
            if (!((field_0x23c == 0 || field_0x23c == 2) && (standing >= 0 || ball >= 0)) &&
                (field_0x23c == 0 || !vfunc_0x34())) {
                break;
            }
            spawnDust(this, 0);
            if (standing >= 0) {
                vfunc_0x30(0xFF, true);
                startSound_801F0E34(0x30009, 0);
            }
            fillTiles(this, mPos.x, 6);
            field_0x230 = 3;
            startSound_801F0E34(0x3001B, 0);
            break;
        case 4:
        case 5:
            if (pushers != 4) {
                break;
            }
            vfunc_0x30(0xFF, true);
            startSound_801F0E34(0x30009, 0);
            fillTiles(this, mPos.x, 0x7C);
            field_0x24c = 0.07f;
            field_0x230 = 6;
            startSound_801F0E34(0x3001B, 0);
            break;
        }
        break;
    case 3:
        field_0x248 += 0.2f;
        if (field_0x248 >= 1.6f) {
            field_0x248 = 1.6384f;
            fillTiles(this, mPos.x, field_0x252);
            field_0x244 = 0x28;
            if (field_0x23c == 2) {
                field_0x230 = 8;
            } else {
                field_0x230 = 4;
            }
        }
        break;
    case 4:
        if (field_0x244 == 0 && standing < 0 && ball < 0) {
            startSound_801F0E34(0x3001C, 0);
            field_0x230 = 5;
            break;
        }
        if (field_0x244 != 0) {
            field_0x244--;
            if (field_0x244 == 0 && field_0x23c != 0 && vfunc_0x34()) {
                field_0x244 = 1;
            }
        }
        break;
    case 5:
        field_0x248 -= 0.04f;
        if (field_0x248 < 0.0f) {
            field_0x248 = 0.0f;
            f32 x = mPos.x;
            s32 layer = field_0x4;
            GameView_804A9950* gameView = getGameView_802D6A9C();
            const JGeometry::TBox2f* src = layer < 8 ? &gameView->mVisibleBox : &gameView->field_0xdc;
            JGeometry::TBox2f vbox;
            vbox = *src;
            for (s32 i = 0; i < lbl_8046C8B0[field_0x234]; i++) {
                s32 tx = (s32)(x - vbox.i.x);
                f32 y = mPos.y;
                for (s32 j = 0; j < lbl_8046C8CC[field_0x234]; j++) {
                    s32 ty = (s32)(y - vbox.i.y);
                    s32 index = tileIndex(tx, ty);
                    if (field_0x234 == 1) {
                        gGameRoot2_8053AB10->field_0x20->fn_802F9974(field_0x4, index, lbl_8046C8E8[i][j]);
                    } else {
                        gGameRoot2_8053AB10->field_0x20->fn_802F9974(field_0x4, index, field_0x250);
                    }
                    y += 16.0f;
                }
                x += 16.0f;
            }
            field_0x230 = 2;
            spawnDust(this, 1);
        }
        break;
    case 6: {
        field_0x248 -= field_0x24c;
        field_0x24c = field_0x24c - 0.001;
        if (field_0x248 <= -1.6f) {
            field_0x248 = -1.6f;
            field_0x244 = 4;
            field_0x230 = 7;
        }
        Camera_804AA9E4* camera = gGameRoot2_8053AB10->field_0x24;
        if (camera->field_0x7f4 == 0) {
            camera->field_0x7f5 = 1;
        }
        break;
    }
    case 7: {
        if (field_0x244 != 0) {
            field_0x244--;
        } else {
            field_0x248 -= field_0x24c;
            field_0x24c = field_0x24c + 0.0012;
            if (field_0x248 <= -3.2f) {
                field_0x248 = -3.2f;
                field_0x230 = 8;
                getGameView_802D6A9C()->fn_802D79E8(field_0x4, 8.0f, 0.0f, true);
                JGeometry::TVec3f pos(48.0f + (96.0f + mPos.x), 48.0f + mPos.y, 0.0f);
                spawnEmitter_8013CC50(field_0x4, &pos, 0x263, 0, 0, NULL, NULL, true, 1.0f);
                if (field_0x234 == 4) {
                    const char* name = getGameView_802D6A9C()->fn_802D9C4C();
                    spawnEmitter_8013CC50(field_0x4, &pos, 0x82, 1, 0, NULL, NULL, true, 1.0f);
                    spawnEmitter_8013CC50(field_0x4, &pos, 0x83, 1, 0, NULL, NULL, true, 1.0f);
                    spawnEmitter_8013CC50(field_0x4, &pos, 0x84, 1, 0, NULL, NULL, true, 1.0f);
                    if (name[0] == 'r' || name[0] == 's' || name[0] == 'y') {
                        spawnEmitter_8013CC50(field_0x4, &pos, 0x80, 1, 0, NULL, NULL, true, 1.0f);
                    } else {
                        spawnEmitter_8013CC50(field_0x4, &pos, 0x81, 1, 0, NULL, NULL, true, 1.0f);
                    }
                    startSound_801F0E34(0x30001, 0);
                } else {
                    fillTiles(this, 96.0f + mPos.x, field_0x240);
                }
                mAlive = false;
            }
        }
        Camera_804AA9E4* camera = gGameRoot2_8053AB10->field_0x24;
        if (camera->field_0x7f4 == 0) {
            camera->field_0x7f5 = 1;
        }
        break;
    }
    case 8:
        break;
    default:
        mAlive = false;
        break;
    }
}

// The hole picture "otosiana_bg_s.bti" under the floor (scaled per type), then the floor's two
// halves tilted by field_0x248 (the left one about its edge, the right one mirrored); types 4 / 5
// draw the ground or the house instead while falling.
void TrickFloor_804A83A0::draw() {
    SpriteParams_801F5AE0 sp;
    sp.field_0x1c = -1;
    sp.field_0x1d = -2;
    Mtx m;
    m[0][3] = 0.0f;
    m[1][3] = 0.0f;
    m[2][3] = 0.0f;
    m[0][1] = 0.0f;
    m[0][0] = lbl_8046C940[field_0x234];
    m[0][2] = 0.0f;
    m[1][0] = 0.0f;
    m[1][1] = 1.0f;
    m[1][2] = 0.0f;
    m[2][0] = 0.0f;
    m[2][1] = 0.0f;
    m[2][2] = lbl_8046C95C[field_0x234];
    sp.mMtx = m;
    void* res = gGameRoot_8053AAF8->field_0xa4->getResource('TIMG', "otosiana_bg_s.bti");
    JGeometry::TVec3f hole(mPos.x + lbl_8046C908[field_0x234], mPos.y + lbl_8046C924[field_0x234], mPos.z);
    if (field_0x4 < 8) {
        gGameRoot2_8053AB10->field_0x20->fn_802F745C(&hole, res, &sp);
    }

    m[0][3] = 0.0f;
    m[1][3] = 0.0f;
    m[2][3] = 0.0f;
    setRotMtx(m, JGeometry::TVec3f(0.0f, field_0x248, 0.0f));
    sp.field_0x1c = -1;
    sp.field_0x1d = -1;
    sp.field_0x21 = 1;
    sp.mMtx = m;
    switch (field_0x234) {
    case 0:
        drawSmp(this, &mPos, "floor_smp.bin", &sp);
        break;
    case 1:
        drawSmp(this, &mPos, "mastersword_left_smp.bin", &sp);
        break;
    case 2:
        drawSmp(this, &mPos, "house_left_smp.bin", &sp);
        break;
    case 3:
        drawSmp(this, &mPos, "tree0_smp.bin", &sp);
        drawSmp(this, &mPos, "tree1_smp.bin", &sp);
        break;
    case 4:
    case 5:
        break;
    case 6:
        drawSmp(this, &mPos, "field_smp.bin", &sp);
        break;
    }

    m[0][3] = 0.0f;
    m[1][3] = 0.0f;
    m[2][3] = 0.0f;
    if (field_0x234 == 3 || field_0x234 == 4 || field_0x234 == 5) {
        setRotMtx(m, JGeometry::TVec3f(0.0f, 3.1415927f - field_0x248, 0.0f));
    } else {
        setRotMtx(m, JGeometry::TVec3f(0.0f, -field_0x248, 0.0f));
    }
    sp.mMtx = m;
    switch (field_0x234) {
    case 0: {
        JGeometry::TVec3f pos(64.0f + mPos.x - 32.0f * JMath::sincosTable_.cosRadian(-field_0x248),
                              32.0f * JMath::sincosTable_.sinRadian(field_0x248) + mPos.y, mPos.z);
        drawSmp(this, &pos, "floor_smp.bin", &sp);
        break;
    }
    case 1: {
        JGeometry::TVec3f pos(64.0f + mPos.x - 32.0f * JMath::sincosTable_.cosRadian(-field_0x248),
                              32.0f * JMath::sincosTable_.sinRadian(field_0x248) + mPos.y, mPos.z);
        drawSmp(this, &pos, "mastersword_right_smp.bin", &sp);
        break;
    }
    case 2: {
        JGeometry::TVec3f pos(96.0f + mPos.x - 48.0f * JMath::sincosTable_.cosRadian(-field_0x248),
                              48.0f * JMath::sincosTable_.sinRadian(field_0x248) + mPos.y, mPos.z);
        drawSmp(this, &pos, "house_right_smp.bin", &sp);
        break;
    }
    case 3: {
        JGeometry::TVec3f pos0(64.0f + mPos.x, mPos.y, mPos.z);
        drawSmp(this, &pos0, "tree0_smp.bin", &sp);
        JGeometry::TVec3f pos1(64.0f + mPos.x, mPos.y, mPos.z);
        drawSmp(this, &pos1, "tree1_smp.bin", &sp);
        break;
    }
    case 4:
    case 5:
        sp.field_0x1c = 1;
        sp.field_0x1d = -1;
        if (field_0x230 == 7) {
            JGeometry::TVec3f pos(96.0f + mPos.x, mPos.y, mPos.z);
            drawSmp(this, &pos, "jimen_smp.bin", &sp);
        } else if (field_0x230 != 8) {
            JGeometry::TVec3f pos(96.0f + mPos.x, mPos.y, mPos.z);
            drawSmp(this, &pos, "house_smp.bin", &sp);
        }
        break;
    case 6: {
        JGeometry::TVec3f pos(64.0f + mPos.x - 32.0f * JMath::sincosTable_.cosRadian(-field_0x248),
                              32.0f * JMath::sincosTable_.sinRadian(field_0x248) + mPos.y, mPos.z);
        drawSmp(this, &pos, "field_smp.bin", &sp);
        break;
    }
    }
}

TrickFloor_804A83A0::~TrickFloor_804A83A0() {}
