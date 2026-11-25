#include "game/GameAudio.h"
#include "game/GameGlobals.h"
#include "game/GameState.h"
#include "game/act/act_vaati_boss.h"

// Auto-inlining is off for the whole file (docs/INLINING.md, pragma rule 2): the
// original inlines no same-unit plain function. Checked: built with inlining off,
// every written function's calls to this unit's functions equal the original's
// `bl`s. The callers that need it: draw calls fn_801EDC0C out of line.
#pragma auto_inline off

static const char* lbl_804A5760[] = {"e_gufu_1.bti", "e_gufu_2.bti", "e_gufu_3.bti",
                                     "e_gufu_4.bti"};

// The target picks max(1.0f + field_0x52c.field_0x28, 0.001f) with one fsel
// (0.001f - x >= 0), written with __fsel. Ours rounds the fsel result (one frsp)
// before storing it to mtx[2][2]; the target stores it unrounded. The rest
// differs in registers and order only.
// FIXME: 67.65 %, missing/extra; behaviour near.
void VaatiBoss_804A4958::fn_801EDD0C() {
    void* res = getBossArchiveResource_804032E8('TIMG', lbl_804A5760[mAnim.mCel]);
    SpriteParams_801F5AE0 params;
    Mtx mtx;
    params.field_0x1f = 0;
    params.field_0x1c = 1;
    params.field_0x1d = 1;
    s32 flags = 7;
    if (field_0x5d1 != 0) {
        flags = 0x407;
        params.field_0x10.a = 0;
    }
    f32 scale = 1.0f + field_0x52c.field_0x28.value;
    f32 minScale = 0.001f;
    mtx[0][3] = 0.0f;
    mtx[1][3] = 0.0f;
    mtx[2][3] = 0.0f;
    mtx[0][0] = 1.0f;
    mtx[0][1] = 0.0f;
    mtx[0][2] = 0.0f;
    mtx[1][0] = 0.0f;
    mtx[1][1] = 1.0f;
    mtx[1][2] = 0.0f;
    mtx[2][0] = 0.0f;
    mtx[2][1] = 0.0f;
    mtx[2][2] = __fsel(minScale - scale, minScale, scale);
    params.mMtx = mtx;
    if (mState == 5) {
        if (mSpriteParams.mMtx == NULL) {
            drawShadow_801EF830(mLayer_0x4, &mPos, &params, flags, NULL, 0, res);
        }
        f32 inv = 1.0f / fn_802F5FF4(lbl_8053F0B8);
        f32 k = fn_802F5FF4(mPos.z) * inv;
        for (int j = 0; j < 4; j++) {
            f32 x = mtx[0][j] * k;
            f32 y = mtx[1][j] * k;
            f32 z = mtx[2][j] * k;
            mtx[0][j] = x;
            mtx[1][j] = y;
            mtx[2][j] = z;
        }
        params.mMtx = mtx;
        drawSpriteRes_801EFD34(res, &params, -1, 0.0f, -12.0f * lbl_8053F0BC, 0.0f);
    } else {
        drawSpriteRes_801EFD34(res, &params, flags, 0.0f, -12.0f * lbl_8053F0BC, 0.0f);
    }
}

void VaatiBoss_804A4958::fn_801EDC0C(s32 frame) {
    JGeometry::TVec3f offset;
    field_0x52c.fn_801D6CEC(&offset);
    mPos += offset;
    if (mState == 0xb && mStateTimer >= 0x3c) {
        if (mStateTimer % 4 < 2) {
            mPos.x += 1.0f;
        } else {
            mPos.x -= 1.0f;
        }
    }
    if (isUpperLayer_801CD2F8(mLayer_0x4)) {
        drawSpriteScaled_801F02BC("enemy_both_sob.bin", frame, NULL, -1, 0, false, 1.0f, 1.0f);
    } else {
        fn_801EDD0C();
    }
}

void VaatiBoss_804A4958::draw() {
    if (mState != 0x17) {
        JGeometry::TVec3f savedPos = mPos;
        fn_801EDC0C(mAnim.mCel + 0x10c);
        mPos.set(savedPos.x, savedPos.y, savedPos.z);
    }
}
