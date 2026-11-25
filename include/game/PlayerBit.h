#ifndef GAME_PLAYERBIT_H
#define GAME_PLAYERBIT_H

#include "game/GameGlobals.h"

// Whether bit `player` of the game root's mPlayerMask is set: the body of
// GameRoot_8049EF20::fn_8023F98C (tu_8022AD64), which the per-player code
// (tu_8022AD64, player_8023FBF0) inlines. It returns a byte (u8), not bool: tu_802684A4
// fn_8026C350 keeps the value (neg / or / srwi, then cmplwi 1) for `== true` where a bool
// return folds it into and.; every other user compiles the same either way.
inline u8 isPlayerBitSet(GameRoot_8049EF20* root, s32 player) {
    u8 bit = 1 << player;
    return (root->mPlayerMask & bit) != 0;
}

// The header inlines behind the test: the game-root getter, the member that tests one
// bit and the one-argument form. Their out-of-line copies are weak: fn_8023F9B0 and
// fn_8023F98C in game/tu_8022AD64.cpp, fn_8018A614 in game/act_phantom_ganon_2.cpp
// (fn_80235B68's inlined recursion calls all three).
inline GameRoot_8049EF20* fn_8023F9B0() {
    return gGameRoot_8053AAF8;
}

inline bool GameRoot_8049EF20::fn_8023F98C(s32 player) {
    u8 bit = 1 << player;
    return (mPlayerMask & bit) != 0;
}

inline bool fn_8018A614(s32 player) {
    return fn_8023F9B0()->fn_8023F98C(player);
}

#endif
