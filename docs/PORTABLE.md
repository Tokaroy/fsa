# Portable bodies for MWCC-only code

The PC port compiles these sources with clang. Anything inside
`#ifdef __MWERKS__` is invisible there, so a block that holds asm and has no
`#else` compiles to nothing, with no error. That is how a paired-single TVec3
copy (`JGeometry::setTVec3f`) became a no-op on the port and gave a black
screen.

## The rule

Every `#ifdef __MWERKS__` (or `#if defined(__MWERKS__)`, not negated) block
that holds asm (`asm`/`__asm`, `psq_*`, `ps_*`, `frsqrte`) has an `#else`
branch with a portable C body that does everything the asm block does:

- all of it: in `negateInternal`/`mulInternal` only `z` was C, `x`/`y` were
  in the asm;
- a function whose asm is split over several blocks that share registers
  (`J3DMtxBuffer::calcWeightEnvelopeMtx`) may do all its work in one `#else`
  and leave a comment in the others;
- the MWCC branch is never touched, so `main.dol` and every object stay
  byte-identical;
- where no correct C can be written yet: `#else` + `#error "needs portable
  body"` (THP's IDCT and Huffman decoders, MetroTRK), so the port fails
  loudly instead of silently.

Bodies may come from TwilitRealm/dusklight (TP PC port, CC0) only where our
asm is the same instruction sequence as Dusklight's (FSA's JSystem is older
than TP's); otherwise write the C from our asm. Say which in a comment.

Conversions:

| asm | C |
|---|---|
| `frsqrte` | `1.0f / sqrtf(x)` |
| `ps_madd a, b, c, d` | `a = b * c + d` (also `fmadds`) |
| `ps_msub` / `fmsubs a, b, c, d` | `a = b * c - d` |
| `ps_nmsub` / `fnmsubs a, b, c, d` | `a = d - b * c` |
| `psq_l`/`psq_st` type 0 | plain `f32` loads and stores |
| `psq_l`/`psq_st` type 2-5 | GQR table below |

## GQRs

`OSInitFastCast` (and JASAudioThread, JASTaskThread, J3DSys, which do the
same) sets:

| GQR | type | scale |
|---|---|---|
| 2 | u8 | 0 |
| 3 | u16 | 0 |
| 4 | s8 | 0 |
| 5 | s16 | 0 |

A quantised load is a plain integer-to-float conversion. A quantised store
truncates toward zero and clamps to the type's range (`__OSf32tou8` of 300.0f
is 255, of -3.0f is 0); write the clamp out.

The only other GQR writes in the game: `__OSPSInit` (all zero), OSContext
save/restore, MetroTRK, and THPDec's `__THPGQRSetup`, which saves GQR5/GQR6
and sets GQR5 = s16 and GQR6 = u8 with scale -3 (stores divide by 8, loads
multiply by 8) around the IDCT, then restores them. No game unit writes a GQR
itself.

## Big-endian data

Game data read through casts (`*(const s32*)data`) is big-endian and may be
unaligned. Use `include/portable/BigEndian.h`: `be_read_s32/u32/s16/u16` are
the same plain loads under `__MWERKS__` (macros, so MWCC's code is unchanged)
and byte-order-safe reads otherwise. `tu_803944C8.cpp`'s message-tag readers
use it.

## The check

`python3 tools/asm_else_check.py` lists flagged blocks and exits 1 if there
are any; `gate.py` runs it (`check_asm_else`). It checks the files the build
compiles, read from `ninja -t deps` for the `.o` targets (`--skipped` lists
hits in files outside that set, `--all` checks everything). Files it skips
today: `include/JSystem/JMath/JMath.h` and `libs/sdk/dolphin/mtx/quat.c`,
which no unit includes or builds.

Not covered: asm with no `__MWERKS__` guard at all (whole `asm` functions in
the SDK's OS/PPCArch/OSCache/OSContext code). Clang rejects those, so they
fail loudly; the port replaces that layer anyway. MWCC intrinsics
(`__fres`, `__frsqrte`, `__fabsf`, `__cntlzw`, `__rlwimi`) need shims in the
port.
