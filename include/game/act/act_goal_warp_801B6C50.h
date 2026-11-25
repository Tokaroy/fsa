#ifndef GAME_ACT_ACT_GOAL_WARP_801B6C50_H
#define GAME_ACT_ACT_GOAL_WARP_801B6C50_H

// Code: game/act_goal_warp_801B6C50.cpp.

#include "game/ActorBase.h"
#include "game/Player.h"
#include "game/Message.h"

// Spawned for 'GLWP'; moved here from game/act/tu_801F9484.h.
class GoalWarp_804A39DC : public ActorBase_804A5770 {
public:
    GoalWarp_804A39DC() {}
    /* 0x08 */ virtual ~GoalWarp_804A39DC();
    /* 0x0C */ virtual void init();
    /* 0x14 */ virtual void update();
    /* 0x20 */ virtual void draw();
    // Not in the binary (update inlines it): the message call with the position by reference.
    bool talk(u32 msg, s32 serial, s32 layer, const JGeometry::TVec3f& pos, u32 flags) {
        return openMessage_8038AD24(getRepresentativePlayer_8022EA0C(0), msg, serial, layer, pos, flags);
    }
    /* 0x230 */ s32 field_0x230; // state (0-8)
    /* 0x234 */ s32 field_0x234[3]; // counted down every update ([1]: state countdown)
    /* 0x240 */ s32 field_0x240;
    /* 0x244 */ s32 field_0x244;
    /* 0x248 */ s32 field_0x248;
    /* 0x24C */ s32 field_0x24c; // bits 8-11 of mSpawnParam_0x90
    /* 0x250 */ s32 field_0x250; // bits 0-3
    /* 0x254 */ s32 field_0x254; // bits 4-7
    /* 0x258 */ s32 field_0x258; // bits 12-15 (0 when above 10)
    /* 0x25C */ f32 field_0x25c; // the screen fade amount
    /* 0x260 */ f32 field_0x260;
    /* 0x264 */ JGeometry::TVec3f field_0x264[4];
    /* 0x294 */ JPABaseEmitter* mEmitters[4]; // released by the destructor
}; // Size: 0x2A4

#endif
