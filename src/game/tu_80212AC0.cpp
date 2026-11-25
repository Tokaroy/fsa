#include "game/GameAudio.h"
#include "game/ActorManager.h"
#include "game/GameGlobals.h"
#include "game/tu_80212AC0.h"
#include "game/act/act_quicksand.h"

void cls_80212AC0::fn_80212BFC(s32 serial) {
    mSerials[mCount] = serial;
    mCount++;
}

void cls_80212AC0::fn_80212BA0(s32 serial) {
    bool removed = false;
    for (s32 i = 0; i < mCount; i++) {
        if (!removed) {
            if (serial == mSerials[i]) {
                removed = true;
            }
        } else {
            mSerials[i - 1] = mSerials[i];
        }
    }
    if (removed) {
        mCount--;
    }
}

void cls_80212AC0::fn_80212AF0(JGeometry::TVec3f* pos) const {
    Quicksand_804A6270* found = find(pos);
    if (found != NULL) {
        JGeometry::TVec3f push;
        found->fn_80210E90(pos, &push);
        *pos += push;
    }
}

cls_80212AC0* fn_80212AC0() {
    static cls_80212AC0 lbl_804CCDB8;
    return &lbl_804CCDB8;
}
