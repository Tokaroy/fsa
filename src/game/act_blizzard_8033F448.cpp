#include "game/GameAudio.h"
#include "game/Effect.h"
#include "game/GameGlobals.h"
#include "game/GameState.h"
#include "game/GameView.h"
#include "game/Player.h"
#include "game/act/act_blizzard_8033F448.h"

// The visible box is passed by value: that is what makes the original copy it to
// the stack (lwz/stw) before reading it with lfs.
static inline void getCenter(f32& x, f32& y, JGeometry::TBox2f box) {
    x = box.f.x + 0.5f * (box.i.x - box.f.x);
    y = box.f.y + 0.5f * (box.i.y - box.f.y);
}

void Blizzard_804AC388::init() {
    field_0x230 = 300;
    field_0x234 = (mSpawnParam_0x90 >> 4) & 0xF;
    field_0x238 = (mSpawnParam_0x90 >> 8) & 0xF;
    mParamAtcp_0x114 = 1;
    field_0x23c = false;
}

// FIXME: 99.13 %, regalloc-only; behaviour clean.
// FIXME: regalloc-only. The spawned flag is r28 and the second and third loop
// counter r29 in the original, the reverse here.
void Blizzard_804AC388::update() {
    bool spawned = false;
    if (field_0x23c == true) {
        getGameView_802D6A9C()->fn_802D9FF4(field_0x234, field_0x238);
        gGameRoot_8053AAF8->fn_80136798(16, 1);
        for (s32 i = 0; i < 4; i++) {
            fn_8023764C(i, getPlayerMaxLife_80237810(i) - 4);
            fn_8022CA6C(i, 0, true);
        }
        mAlive = false;
    } else {
        if (field_0x230 <= 0) {
            for (s32 i = 0; i < 4; i++) {
                if (isPlayerActive_8023F264(i) && getPlayerLayer_8023DE58(i) < 8 && !fn_80230188(i) &&
                    !fn_8022F478(i) && !fn_80236D14(i)) {
                    JGeometry::TVec3f* player = getPlayerPos_8023E724(i);
                    JGeometry::TVec2f pos;
                    pos.x = player->x;
                    pos.y = player->y;
                    pos.x += 0.1f;
                    pos.y -= 0.1f;
                    hitPlayerGroup_80238548(i, 1, &pos, 1);
                    lbl_80529DEC.field_0x239 |= (u8)(1 << i);
                    spawned = true;
                }
            }
            field_0x230 = 300;
        }
        if (spawned) {
            f32 x;
            f32 y;
            getCenter(x, y, getGameView_802D6A9C()->mVisibleBox);
            startSound_801F0E34(0x30036, 0);
            spawnEmitter_8013CC50(mLayer_0x4, &JGeometry::TVec3f(x, y, 0.0f), 0x1bc, 2, 2, NULL, NULL, true, 1.0f);
        }
        for (s32 i = 0; i < 4; i++) {
            if (!hasPlayerLeader_8022F514(i) && fn_80236A18(i) && isPlayerActive_8023F264(i)) {
                field_0x23c = true;
            }
        }
        field_0x230--;
    }
}

void Blizzard_804AC388::draw() {}

Blizzard_804AC388::~Blizzard_804AC388() {}
