#include "game/GameAudio.h"
#include "game/ActorBase.h"
#include "game/GameGlobals.h"
#include "game/GameState.h"
#include "game/Map.h"
#include "game/Player.h"
#include "game/act/tu_80210630.h"
#include "JSystem/ResTIMG.h"

static const f32 lbl_8046A470[4] = {45.0f, 59.0f, 46.0f, 47.0f};
static const f32 lbl_8046A480[4] = {72.0f, 72.0f, 72.0f, 87.0f};

static const char* lbl_804A61A8[8] = {
    "bakudan_right.bti", "bakudan_left.bti", "bakudan_under.bti", "bakudan_top.bti",
    "atari_right.bti",   "atari_left.bti",   "atari_under.bti",   "atari_top.bti",
};

// Per direction (x, y) offsets in tiles, signed bytes.
static const s8 lbl_8053FAB8[4][2] = {
    {0x13, -4},
    {-0x14, -4},
    {0x04, 0x0A},
    {-4, -0x1C},
};

static inline void addBox(s32 serial, const JGeometry::TBox2f* box, s32 layer) {
    CollisionBoxes_8020D58C* boxes = fn_8020D58C();
    boxes->mLists[boxes->field_0x0].fn_8020D8C0(box, layer, serial);
}

static inline void setScaleMtx(Mtx m, f32 x, f32 y, f32 z) {
    m[0][0] = x;
    m[0][1] = 0.0f;
    m[0][2] = 0.0f;
    m[1][0] = 0.0f;
    m[1][1] = y;
    m[1][2] = 0.0f;
    m[2][0] = 0.0f;
    m[2][1] = 0.0f;
    m[2][2] = z;
}

static inline void setBox(JGeometry::TBox2f* out, const JGeometry::TVec3f& scale) {
    out->set(-16.0f * scale.x, -24.0f * scale.y, 16.0f * scale.x, 8.0f * scale.y);
}

f32 fn_80210B34(s32 dir) {
    return lbl_8053FAB8[dir][0];
}

f32 fn_80210AF8(s32 dir) {
    return lbl_8053FAB8[dir][1];
}

cls_804A61C8::cls_804A61C8() {
    field_0x2a8 = 0.0f;
}

bool cls_804A61C8::fn_80210A6C() {
    bool arrived = false;
    if (moveToward_801CD950(&field_0x2a8, 128.0f, 2.0f) == 0) {
        arrived = true;
    }
    return arrived;
}

void cls_804A61C8::fn_80210A30(JGeometry::TBox2f* out) {
    setBox(out, field_0x54);
}

// FIXME: 98.00 %, regalloc-only; behaviour clean.
void cls_804A61C8::fn_80210990(s32 dir, JGeometry::TBox2f* out) {
    f32 x = field_0x54.x;
    f32 y = field_0x54.y;
    setBox(out, field_0x54);
    switch (dir) {
    case 0:
        out->f.x -= 8.0f * x;
        break;
    case 1:
        out->i.x += 8.0f * x;
        break;
    case 2:
        out->f.y -= 8.0f * y;
        break;
    case 3:
        out->i.y += 8.0f * y;
        break;
    }
}

// FIXME: 95.25 %, scheduling+regalloc; behaviour clean.
// Same instructions; the original keeps this in r30 and the serial in r31 across
// the getter call, here this is in r31 and the serial in r30.
void cls_804A61C8::updateBehavior_0x9C(u8 mapHit) {
    EnemyBase_804A4808::updateBehavior_0x9C(mapHit);
    JGeometry::TBox2f box;
    setBox(&box, field_0x54);
    box.i.x += mPos.x;
    box.i.y += mPos.y;
    box.f.x += mPos.x;
    box.f.y += mPos.y;
    fn_80239914(&box, mLayer_0x4, mSerial);
    addBox(mSerial, &box, mLayer_0x4);
}

u8 cls_804A61C8::checkHitByPlayer_0x5C() {
    fn_801CEBD0();
    return 0;
}

// FIXME: 0.00 %, missing/extra + reloc-name; behaviour clean.
// Same operations; the original also keeps the shared constants -1 and 0 in r26/r27 (stmw,
// 0xB0 frame) and schedules the field loads ahead of the parameter stores.
void cls_804A61C8::fn_80210630(u8 arg0, u8 arg1, u8 arg2, s32 arg3) {
    ResTIMG* res = (ResTIMG*)getBossArchiveResource_804032E8('TIMG', lbl_804A61A8[mDir_0x98 + (arg0 ? 4 : 0)]);
    SpriteParams_801F5AE0 params;
    params.field_0x1c = arg1;
    params.field_0x1d = arg2;
    params.field_0x14.r = arg3;
    Mtx mtx;
    mtx[0][3] = 0.0f;
    mtx[1][3] = 0.0f;
    mtx[2][3] = 0.0f;
    setScaleMtx(mtx, 0.33333334f * field_0x54.x, 0.33333334f * field_0x54.y, 0.33333334f * field_0x54.z);
    params.mMtx = mtx;
    JGeometry::TVec3f pos(mPos);
    pos.x += mtx[0][0] * (0.5f * res->mSizeX - lbl_8046A470[mDir_0x98]);
    pos.y += mtx[1][1] * (0.5f * res->mSizeY - lbl_8046A480[mDir_0x98]);
    if (mLayer_0x4 < 8) {
        gGameRoot2_8053AB10->field_0x20->drawTimgImage_802F745C(&pos, res, &params);
    }
}
