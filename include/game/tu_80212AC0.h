#ifndef GAME_TU_80212AC0_H
#define GAME_TU_80212AC0_H

// Exports of game/tu_80212AC0.cpp. Called by the Pengator actors
// (act_pengator, act_leever_80182914, act_geldman_80183544: fn_80212AF0 on their mPos at 0xC),
// tu_801DE714 and game_view_802D39B8 (which clears the count).

#include "types.h"
#include "JSystem/JGeometry.h"
#include "game/ActorManager.h"
#include "game/act/act_quicksand.h"

// The guarded static at 0x804CCDB8 (function-local static of fn_80212AC0, flag
// lbl_8053AC70; .bss, 0x180 bytes in the symbol because it covers the unit's
// global-object records too). A list of up to 0x20 actor serials. No vtable,
// ctor or dtor symbol (the constructor is inlined into fn_80212AC0); named
// after its first function.
struct cls_80212AC0 {
    cls_80212AC0() : mCount(0) {}
    Quicksand_804A6270* find(const JGeometry::TVec3f* pos) const {
        Quicksand_804A6270* actor;
        Quicksand_804A6270* found = NULL;
        for (s32 i = 0; i < mCount; i++) {
            actor = static_cast<Quicksand_804A6270*>(getActorManager_801F856C()->findActorBySerial_801F666C(mSerials[i]));
            if (actor != NULL && actor->fn_80211000(pos)) {
                found = actor;
                break;
            }
        }
        return found;
    }
    // Looks the tracked actors up in order; for the first one whose area
    // contains *pos, pushes *pos out by the vector fn_80210E90 returns.
    void fn_80212AF0(JGeometry::TVec3f* pos) const;
    // Removes the first entry equal to serial, shifting the rest down.
    void fn_80212BA0(s32 serial);
    // Appends serial.
    void fn_80212BFC(s32 serial);

    /* 0x00 */ s32 mSerials[0x20];
    /* 0x80 */ s32 mCount;
}; // Size: 0x84

cls_80212AC0* fn_80212AC0();

#endif
