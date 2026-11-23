#ifndef GAME_ACT_ACT_PHANTOM_GANON_8017C01C_H
#define GAME_ACT_ACT_PHANTOM_GANON_8017C01C_H

// Code: game/act_phantom_ganon_8017C01C.cpp. Its small out-of-line helpers,
// called from other units.

#include "JSystem/JGeometry.h"

class JPABaseEmitter;

u8 fn_8017EC70(const JGeometry::TVec3f* pos, f32 value);
u8 fn_8017EB44(const JGeometry::TVec3f* pos); // a scripted camera move to pos
bool fn_8017EB1C(f32 value);
JGeometry::TBox2f* fn_8017EC5C(JGeometry::TBox2f* box, f32 x0, f32 y0, f32 x1, f32 y1);
void fn_8017EC38(JGeometry::TBox2f* dst, const JGeometry::TBox2f* src);
void invalidateEmitter_8017EAB4(JPABaseEmitter* emitter);

#endif
