#ifndef GAME_ACT_ACT_TALKING_SIGN_H
#define GAME_ACT_ACT_TALKING_SIGN_H

// Code: game/act_talking_sign.cpp.

#include "game/ActorBase.h"
#include "game/Message.h"

// The KNBN actor ("Talking sign", docs/names/actors.tsv, med confidence): the
// spawner constructs it with fn_80203610, which stores this vtable
// (config/G4SE01/game_units.tsv). Named after its vtable, 0x804AF428.
class TalkingSign_804AF428 : public ActorBase_804A5770 {
public:
    TalkingSign_804AF428() {}
    /* 0x08 */ virtual ~TalkingSign_804AF428();
    /* 0x0C */ virtual void init();
    /* 0x14 */ virtual void update();
    /* 0x20 */ virtual void draw();

    // Opens the sign's message for mPlayer; the position is passed on by value; serial and
    // layer are loaded before that copy (parameters), mPlayer and the message id after it.
    bool talk(s32 serial, s32 layer, const JGeometry::TVec3f& pos, u16 flags) {
        return openMessageById_8038C678(mPlayer, (mSpawnParam_0x90 & 0xFFFF) + 0x12B, serial, layer, pos, flags);
    }

    /* 0x230 */ s32 mState; // 0 watching the sign's area, 1 message open
    /* 0x234 */ s32 mPlayer; // fn_8022FD8C(mSerial); -1 when none
}; // Size: 0x238

#endif
