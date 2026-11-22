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
   locals; then compiler-named locals (`@...`); then the temporaries the back end makes while
   generating code for expressions. `@` locals are, in the order they come into being: the locals
   of inlined functions (created when each call is expanded, rule 4), then what the optimiser makes
   after inlining (a strength-reduced table pointer, a load hoisted out of a loop).
   Within the named and the `@` locals the most recently created has the LOWEST number.
2. **Colouring runs from the highest number down.** So, first to last:
   back-end temporaries; the `@` locals of inlined functions, the ones created first coming first;
   the optimiser's `@` temporaries; the named locals in DECLARATION order (first declared, first
   coloured); arguments. (Measured exception, not settled: in a member function that inlines other
   member functions `this` gets r31 as if coloured first.)
   - A loop counter declared in the function is coloured AFTER the strength-reduced pointer of its
     loop; the counter of a loop that sits in an inlined helper is coloured BEFORE it.
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
   - A plain move between two compiler-made values merges them (`coalescenodes`,
     InterferenceGraph.c) into the lower-numbered one, the one created later: `leader =
     leaderOf(this)` is coloured where leaderOf's own local would be, not where `leader` was declared.
4. **Inlining goes level by level** (`CInline_Expand`): pass 0 expands the calls written in the
   function, pass 1 the calls inside the bodies just inserted, and so on (up to 8 levels). Within a
   pass, statement order; of two inline calls in one expression the right one came first in our
   test. Expanding a call creates, in this order: an object for its result if it is a non-void
   function with statements (`CInline_ExtractInlineFunction`), the callee's used locals as new `@`
   locals of the caller, most recently declared first, then the parameters that need an object.
   - A helper with locals declared `a, b, c` colours them a, b, c when compiled on its own and
     **c, b, a in every inlined copy**. A declaration order that matches the standalone function can
     be wrong for its copies and the other way round; only one order satisfies both.
   - Everything created in an earlier pass is coloured before a copy's locals, everything from a
     later pass after them. Nesting depth is therefore visible in the registers.
   - A value that comes out of a NESTED inline which has a local of its own is created one pass
     later than the locals of the function that uses it, and coloured after them. An accessor that
     only returns a member (`return mX;`) creates no object and changes nothing, but a wrapper
     around another inline (`return leaderOf(p);`) delays that inner call, and its local, by one
     more pass.
   - An inline call in the conditional part of `&&`, `||` or `?:` is split out into statements with
     a temporary of their own (`CInline_SerializeStatement`): one more object per split.
   - Deeper chains count against the inline size limit. One level too many can silently stop an
     OUTER call from being inlined (the function drops to a few percent and its extab entry
     changes): after every test look at the unit's sections and match count, not just the function.

## Reading a difference with them

`python3 tools/diag.py <unit> <function>` names the values and gives each one's register in the
original and in ours. Then:

- List, for one stretch of code, the values that live across a call and their registers in the
  original. Descending from the first new register = they were coloured in that order with nothing
  handed out before them. Ascending from the lowest = the same order, coloured after other values.
- A value sitting LOWER than its neighbours in the original was coloured after them: it was created
  later (declared earlier in an inlined copy, later in the function's own body, or it comes out of a
  nested inline), or other values were created earlier than in ours.
- A loop counter in the wrong register next to a compiler-made pointer: the loop belongs in an
  inline helper (`--kinds outline`).
- When the function is a caller and the stretch is an inlined copy, change the HELPER, and check
  every user: `python3 tools/permute.py --callees --units <unit>` scores each rewrite of a helper on
  the whole unit; `--callees --chain --kinds nest,decl` tries the nested-read rewrite on the unit's
  helpers together (it finds the Player fix in seconds).
- A test costs half a second (`python3 tools/try.py <unit>`: line 1 is the number of matching
  functions). Predict first, then test: a prediction that fails says the creation order is not what
  you assumed.

## Worked example: the Player group loops

`getGroupSize_80248970` counts a player's group; it keeps the leader (`field_0xd60`) and its own number in
registers across calls. On its own it matched; its ~100 inlined copies did not: ours gave `leader`
the register of `self`, the original the caller's lowest callee-saved register. By rule 3 that needs
`leader` coloured after every loop counter of the caller, so by rules 1, 2 and 4 created after them:
not with the loop's locals but one inlining pass later. Reading the field through an inline with a
local of its own (`leaderOf(player)`), in `getGroupSize_80248970` and in `getFollowerIndex_80248778`, does exactly that.

A second step by the same reasoning: `self` through an inline of its own (`selfOf`) and the leader
one level deeper (`groupLeader` wrapping `leaderOf`) matched six more. Still open (docs/PLAYER.md):
in `fn_8024BDBC` the directly called copy's leader is in r28 where the original has r27, and the
third loop's count and index are exchanged; the measurements say the original creates these values
about two levels deeper still, which only fits under the inline size limit with a differently
shaped chain.

## Worked example: the FileSelect pane loops

About a dozen functions of `game/tu_803BC6F0.cpp` loop over a table of pane tags
(`for (i < 9) ctrl->setAlpha(screen->search(table[i]), alphas[i])`). The original has the counter
in the first register and the table pointer the compiler makes in the next; ours had them the other
way round. By rule 2 the pointer (an optimiser temporary) is coloured before a named counter and
after an inlined one, so the original's loop sits in an inline function: with the loop moved into a
small inline helper `fn_803C05D8` matches. `python3 tools/permute.py <unit> <function> --kinds
outline,outblock,outrun` tries exactly that for every loop, every `if`, switch or block with locals
and every declaration together with the statements that use it (values of the function that the
statement only reads become the helper's parameters); `--shared --units <unit>` does it for a
statement the file writes out several times. The same rule explains the non-loop cases: a local
declared in a block of the function is one of the function's named locals, coloured in declaration
order after everything inlined; the same local in an inlined helper is coloured before them.

## An argument of another type is a copy

`int` and `s32` (`long`) are the same size but not the same type. A value of one handed to an inline
function's parameter of the other is converted, and MWCC makes the converted value a new temporary:
one more value to colour, in another place of the order. FileSelect's `restoreButtonAlphas(self,
s32 i)` matched in the five functions whose loop counter is `s32 i` and not in `fn_803C1734`, whose
counter was `int i`; with `s32 i` there too all six match. When one copy of a helper differs from
the others in registers only, compare the types of what the callers pass.

## Not covered here

Volatile registers (r0, r3-r12, f0-f13) follow rule 3 with the volatile set, lowest free first.
Not explained yet: the order of two float operands in `A - B` where the original gives the first
loaded value the lower register (FileSelect fn_803CE370 and three others); a value that reuses the
register of a finished loop instead of the lowest free one (ResultScreen fn_803A8F5C `frame`);
spilling.
