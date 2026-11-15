# How MWCC GC 2.6 assigns registers, and what in the source decides it

For functions whose instructions are right but sit in other registers (`regalloc-only`,
`scheduling+regalloc`). The rules below are read from the compiler itself: `../donors/doldecomp__mweppc`
is a decompilation of GC 2.6 build 107, the compiler of FSA's game code (`src/backend/CodeGen.c`
`allocate_local_vregs`, `src/backend/Coloring.c` `simplifygraph` / `colorgraph`,
`src/backend/Registers.c`, `src/frontend/CInline.c` `CInline_Expand` / `CInline_NewLocalObject`).
They were checked on `game/tu_8023FBF0.cpp`: they predict our build's registers value by value, and
applying them made 28 functions match at once (commit "the group loops read the leader through an
inline accessor").

## The rules

1. **Every value gets a number, in creation order.** Arguments first; then the function's own named
   locals; then compiler-named locals (`@...`: every local of every inlined function is one of
   these); then the temporaries the code generator makes while compiling expressions.
   Within the named and the `@` locals the most recently created has the LOWEST number.
2. **Colouring runs from the highest number down.** So: code-generator temporaries first; then `@`
   locals, the ones created first coming first; then the named locals in DECLARATION order (first
   declared, first coloured); arguments last.
3. **A value takes the lowest-numbered register free for it.** Free = not held by a value that is
   live at the same time. A value that lives across a call conflicts with every volatile register, so
   it chooses among the callee-saved registers already handed out; only when none of those is free
   does it get a new one, and new ones are handed out r31, r30, r29, ... (f31, f30, ...).
   - The first values that need callee-saved registers therefore get r31, r30, r29 in the order they
     are coloured: descending.
   - Later, once several are handed out, a value takes the LOWEST free one: a group coloured after
     another group gets its registers ascending (r28, r29, r30).
   - Two values that are never live together share a register only if that register is the lowest
     free choice of the one coloured second. `leader` in r27 next to `self` in r28 need not mean
     they conflict: r27 existed by then and was lower.
4. **Inlining goes level by level** (`CInline_Expand`): pass 0 expands the calls written in the
   function, pass 1 the calls inside the bodies just inserted, and so on (up to 8 levels). Within a
   pass, statement order; of two inline calls in one expression the right one came first in our
   test. Expanding a call creates the callee's used locals as new `@` locals of the caller, most
   recently declared first, then the parameters that need an object.
   - A helper with locals declared `a, b, c` colours them a, b, c when compiled on its own and
     **c, b, a in every inlined copy**. A declaration order that matches the standalone function can
     be wrong for its copies and the other way round; only one order satisfies both.
   - Everything created in an earlier pass is coloured before a copy's locals, everything from a
     later pass after them. Nesting depth is therefore visible in the registers.
   - A value that comes out of a NESTED inline which has a local of its own is created one pass
     later than the locals of the function that uses it, and coloured after them. An accessor that
     only returns the member (`return mX;`) creates no object and changes nothing.

## Reading a difference with them

`python3 tools/diag.py <unit> <function>` names the values and gives each one's register in the
original and in ours. Then:

- List, for one stretch of code, the values that live across a call and their registers in the
  original. Descending from the first new register = they were coloured in that order with nothing
  handed out before them. Ascending from the lowest = the same order, coloured after other values.
- A value sitting LOWER than its neighbours in the original was coloured after them: it was created
  later (declared earlier in an inlined copy, later in the function's own body, or it comes out of a
  nested inline), or other values were created earlier than in ours.
- When the function is a caller and the stretch is an inlined copy, change the HELPER, and check
  every user: `python3 tools/permute.py --callees --units <unit>` scores each rewrite of a helper on
  the whole unit; `--callees --chain --kinds nest,decl` tries the nested-read rewrite on the unit's
  helpers together (it finds the Player fix in seconds).
- A test costs half a second (`python3 tools/try.py <unit>`: line 1 is the number of matching
  functions). Predict first, then test: a prediction that fails says the creation order is not what
  you assumed.

## Worked example: the Player group loops

`fn_80248970` counts a player's group; it keeps the leader (`field_0xd60`) and its own number in
registers across calls. On its own it matched; its ~100 inlined copies did not: ours gave `leader`
the register of `self`, the original the caller's lowest callee-saved register. By rule 3 that needs
`leader` coloured after every loop counter of the caller, so by rules 1, 2 and 4 created after them:
not with the loop's locals but one inlining pass later. Reading the field through an inline with a
local of its own (`leaderOf(player)`), in `fn_80248970` and in `fn_80248778`, does exactly that.

Still open there (see docs/PLAYER.md): in `fn_8024BDBC` the copy of `fn_80248970` that is called
directly has its leader in r28 where the original has r27 (the original creates it after the
`partner` of a loop four levels deeper), and the third loop's count and index are exchanged.

## Not covered here

Volatile registers (r0, r3-r12, f0-f13) follow rule 3 with the volatile set, lowest free first;
copies the compiler merges (`fCoalesced`) and spilling are not described.
