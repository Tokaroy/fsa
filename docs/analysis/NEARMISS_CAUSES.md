# Near-miss causes: shared instruction-count drift in the big near-miss functions

2026-11-23, branch `shared-causes`. Input: `g2-logs/shared_causes_fns.tsv`, 82 functions
>= 2 KB, >= 95 % fuzzy, with no structural credit (379 KB, mostly actor/boss `update`).
Question: which missing/extra instructions come from one cause that one fix removes in
many functions (like `getActorEnd` or `Player_804A6F38::heldActor()`, INLINE_LEADS.md)?

## Method

`python3 tools/nearmiss_hunks.py --tsv ../g2-logs/shared_causes_fns.tsv [--top N] [--show N] [--json F]`
(~4 s). Diffs each unit with objdiff-cli (report setting), cuts every function into
hunks (runs of rows objdiff could not pair), normalises them (registers -> r/f, r1 offsets
-> SP, `lbl_`/`@N`/`...data.N`/`jumptable_` -> DATA, callee names kept) and anchors each
hunk to the last call before it in the target. It prints two clusterings ranked by the
bytes of the functions they touch: **net** (one normalised instruction whose count differs
over the whole function; moves cancel) and **hunks** (identical hunk shapes).

## Cluster 1 (fixed): out-of-line JGeometry ctors written as free-function calls

**Shape.** `+ bl __ct__Q29JGeometry8TVec2<f>Fv` (5 fns, +11), `+ bl __ct__...TBox2<f>Fv`
(4 fns, +8), `+ bl __ct__...TVec3<f>Fv` (3 fns, +7), each with an `addi r3, r1, X` before
it, right before a call to a provisional helper on the same stack slot:

```
target:  addi r3, r1, 0xd8 ; addi r4, r31, 0x80 ; bl copyBox_801546F4
ours:    addi r3, r1, 0xc8 ; bl __ct__Q29JGeometry8TBox2<f>Fv ; addi r3, r1, 0xc8 ; addi r4, r31, 0x80 ; bl copyBox_801546F4
```

**Evidence.** Our source wrote `JGeometry::TBox2f b; copyBox_801546F4(&b, &mBox);`. In the
original no default ctor ever runs on the object before `copyBox_801546F4`, `fn_801546D0`,
`fn_8015457C` or `fn_801546E8` (0 of 40 call sites in `build/G4SE01/asm/game`), the return
value (r3 = this) is used (`bl fn_801546E8; mr r4, r3`), and MWCC's own out-of-line copies
of the TBox2/TVec3/TVec2 copy ctors and of the `TVec2(U x, U y)` template ctor have exactly
their sizes and bodies (0x24, 0x14, 0x14, 0xC). They sit in act_sword_soldier's .text among
the other weak copies its 13 KB update() could not inline (inline budget, see below). The
template ctor's copy is local (MWCC emits member-template instantiations local), so each
unit has its own: fn_80196D24 / fn_80196D60 in act_ganon, etc.

**Fix recipe.**
1. In `symbols.txt` rename the helper to the real mangled name:
   - `copyBox_801546F4` -> `__ct__Q29JGeometry8TBox2<f>FRCQ29JGeometry8TBox2<f>`
   - `fn_801546D0` -> `__ct__Q29JGeometry8TVec3<f>FRCQ29JGeometry8TVec3<f>`
   - `fn_8015457C` -> `__ct__Q29JGeometry8TVec2<f>FRCQ29JGeometry8TVec2<f>`
   - **not** the `TVec2(x, y)` / `TVec3(x, y, z)` helpers (`fn_X__FPQ29JGeometry8TVec2<f>ff`, 0xC;
     `...TVec3<f>fff`, 0x10): see "Template ctors: reverted" below.
2. Delete the hand-written helper definition; write the construction:
   `TBox2f b(mBox);`, `TVec3f old(mPos);`,
   `TVec2f t(*fn_801546E8(&tmp, x, y));` for `fn_8015457C(&t, fn_801546E8(&tmp, x, y))`, and
   pass by value where the callee takes a `TVec3f` (openMessage_8038AD24).
3. Only where the original has no `__ct...Fv` on that slot first (check the target rows).

**Done** (copy ctors only; SHA-1 OK, order_check clean, no function at 100 % dropped):

| Function | before | after | insns |
|---|---:|---:|---|
| SwordSoldier::update | 98.64 | 99.20 | +15 -> -1 |
| Ganon::update | 97.99 | 98.53 | +17 -> +7 |
| PhantomGanon2::update | 98.38 | 98.64 | +6 -> +2, **structural** |
| PrincessZeldaGanonBattle::fn_80198828 | 99.42 | 99.49 | +11 -> +9 |
| PhantomGanon::update (loss) | 94.13 | 93.70 | ours inlines the copy ctor (below) |

**Still to apply.** Other copy-ctor-shaped helpers: `fn_80182690` (TVec2, 0x24,
act_helmaroc_king_8017EF40) and the 0x1C TVec3 copies (`fn_801545A4`, `copyVec3_80196D70`, ...)
look like `set(const TVec3&)` (lfs/stfs, not MWCC's psq copy ctor): check the body before
renaming. `fn_8017EC38` (TBox2, 0x24, 5 units) and `fn_80233BA0` are assigned into existing
boxes: probably `set`/`operator=`, not ctors. Find candidates with
`grep -E '__FPQ29JGeometry8T(Vec2|Vec3|Box2)<f>PCQ29JGeometry8T\w+<f> =' config/G4SE01/symbols.txt`.

**Template ctors: reverted.** `fn_801546E8` (act_sword_soldier), `fn_80196D24` / `fn_80196D60`
(act_ganon) and the other 0xC / 0x10 `(x, y)` / `(x, y, z)` helpers behave like the
`TVec2(U x, U y)` / `TVec3(U, U, U)` template ctors (no default ctor first, this returned, one
local copy per unit). Written that way, MWCC emits the instance local, but right after its
first user (update), while the original has it among the unit's late helpers (0x801546E8,
0x80196D24): tools/order_check.py fails. A non-template `TVec2(T, T)` ctor next to the
template one isn't chosen by MWCC (it still emits `__ct<f>`). Whether the original's helper
was a template instance at all is open: "local, one per unit" also fits a file-static helper.
Ganon::update reached 1 instruction off with them, so the placement puzzle is worth one more
look (deferred-inlining emission order of template instances); until then keep the helpers.

**Template ctors: placement settled (2026-11-24, branch `lead-tctor`), no commit.** Scratch
builds with the game flags (`-O4,p -inline auto,deferred`, forced out of line) show where MWCC
puts an out-of-line value ctor, by how it is written:

| construct | binding | placed |
|---|---|---|
| in-class template ctor (implicit instance), or `inline` explicit specialization | local `t` | right after its first emitted referencer (update) |
| template ctor defined out of class, not `inline` | weak | at its source position |
| non-template ctor defined out of class, not `inline` | global | at its source position |
| **`template <> template <> TVec2<f32>::TVec2(f32, f32) {…}`, not `inline`** | **local `t`, same `__ct<f>__…Fff` name** | **at its source position** |
| file-local struct (`namespace { struct V : TVec3f { V(f32, f32, f32); }; }`, ctor out of class) | local | at its source position |

Only the non-inline explicit specialization has every property of the original (MWCC's
template-instance name, local, one per unit, sitting among the late helpers; act_door's
`__ct<f>__…TVec3<f>Ffff` at 0x802C7CB8, right after update, is the plain implicit instance,
so both forms occur in the game). mkdd, whose JSystem we import, found the same:
`libs/sdk/include/JSystem/JGeometry/Vec.h:445` specializes `TVec3f::TVec3(f32, f32, f32)`
"to emit them in the right order in RaceMgr", but `inline`.

It can't be written in our units: a unit may only specialize before the first use, and our
imported headers already use both. `Vec.h:447` defines the `TVec3f` specialization `inline`
("redefined"), and `Box.h:32` (`addPos(TVec2<f32>(x, y))`) instantiates the TVec2 one ("illegal
explicit template specialization"). Making the header's specialization non-inline doesn't
help: header code sits at the very end of `.text`, while 0x80196D24 / 0x80196D60 sit between
the unit's own helpers (D18 < D24 < D30 < D60 < D70).

The file-local struct is the only form that builds: Ganon::update +7 -> +1 (98.69 -> 98.74,
before renaming symbols), order_check clean, saved as
`/tmp/claude-1005/-bigdata-agent-tom-projects-fsadecomp/95b86131-5188-44d8-833d-1059682321d6/scratchpad/tctor/e_anon_struct.cpp`.
But it invents a type no programmer would write, which CLAUDE.md rule 5 forbids outside
the crack pass. It is left out. Options for the owner: (a) allow it as `FAKEMATCH(crack-pass)`
in the ten units; (b) reshape the imported `Vec.h` / `Box.h` so that the units can specialize
(drop the `inline` specialization and Box.h's temporary). Option (b) touches every unit that
inlines these, so it needs a whole-game build.

**The inline budget caveat.** These ctors are out of line in the original only because
the caller is huge (MWCC stops inlining past its per-function budget). Our source writes
many of the other inlines (zeroVec, getLayer, set...) as explicit calls, so our function is
smaller to the compiler and may still inline the ctor: that happened in
PhantomGanon::update (8.7 KB), which lost 0.4 % and is listed as a known loss. Apply the
recipe per unit and keep it only where the function gains.

## Lead (unproven): map tile queries take a TVec2f

SwordSoldier::update's remaining -9 is `getTileAt_80226998(TVec2f(mPos.x, mPos.y), layer)`:
the target builds a TVec2 with the template ctor and passes its address. Our Map.h declares
`getTileAt_80226998(const TVec3f*, s32)`, and 27 call sites in other units build a
`TVec3f p; p.x = ...; p.y = ...;` with z unset just to call it. Changing the parameter to
`const TVec2f&` (and the same check for getRawTile_80226850 / getTileCollisionCodeAlt_802265FC)
is a header fix that would touch every caller; test it unit by unit.

## Clusters without a single cause

From the hunk clustering, ranked by function bytes (after the fixes):

| Shape | fns | What it is |
|---|---:|---|
| `- mr r, r` (target copies a value, 32 sites) | 16 | Values kept in a second register (often a call result like getLayer's). Regalloc/creation order; per-site. Possibly also the inline budget (out-of-line getters in the original vs our field reads). |
| `+ li r, 0x0` / `+ li r, 0x1` | 13 / 9 | Constants or bools materialised again; per-site (bool vs BOOL, locals). |
| `lwz r, 0x4(r)` moved (+30 / -25 sites), `lwz 0x4 ; addi 0xc` moved | 12 / 6 | `mLayer_0x4` and `&mPos` argument loads in a different order: getLayer_8015461C() (out of line in the original) vs the field read, or argument order. Not one fix: both directions occur. |
| `stfs f, SP` / `stw r, SP` extra or missing | 10 / 5 | Spills: follow from register pressure, not a cause. |
| `lfs DATA@sda21` swapped with `lfs 0x3c(r)` / `lfs SP` | 5 / 3 | Operand order of float expressions (`a - K` vs `K - a`, which side is read first); per-site. |
| `cmpwi` <-> `cmplwi` 0xb / 6 / 7 | 2 | A switch on an unsigned state field; per-unit type fix. |
| `+ extsh` (9 sites) | 3 | s16 vs s32 locals; per-unit. |

The 30 KB screen functions (collect_screen, connect_screen, adv_entry_screen) share no
hunk shape with the actors beyond these generic ones.
