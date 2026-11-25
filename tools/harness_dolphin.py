#!/usr/bin/env python3
"""Behaviour harness, Dolphin side (docs/HARNESS_DOLPHIN.md).

Runs a DOL in headless Dolphin (the fsa-harness branch of the Dolphin fork),
replays a per-pad-read inputs file and collects the sync and state streams in
the port's format (fsaport docs/HARNESS.md), so runs of the original DOL (A),
of a DOL built from the decomp (B) and of the port can be diffed with the
port's tools/harness_compare.py.

    python3 tools/harness_dolphin.py inputs --script 'start@300,a@420:10' --reads 1800 -o in.jsonl
    python3 tools/harness_dolphin.py run --dol A --inputs in.jsonl --reads 1800 -o runs/a1
    python3 tools/harness_dolphin.py build-b           # links build/G4SE01/fsa_game_code.dol (B)
    python3 tools/harness_dolphin.py run --dol B --inputs in.jsonl --reads 1800 -o runs/b1
    python3 tools/harness_dolphin.py compare runs/a1 runs/b1

`run` writes OUT/sync.jsonl, OUT/state.jsonl (and OUT/inputs.jsonl when run
without --inputs: record mode), OUT/spec.txt (what Dolphin was told) and
OUT/dolphin.log. A is orig/sys/main.dol with config/G4SE01/symbols.txt; B is
build/G4SE01/fsa_game_code.dol with its linker map. Both boot the same way: as
an extracted disc tree (harness-disc/, outside the repo) whose sys/main.dol is
the DOL under test.

The state tables below mirror fsaport game/src/port/harness_state.cpp:
same names, same order; the offsets are the decomp headers' (include/game).
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.dirname(os.path.dirname(ROOT)) if os.path.basename(os.path.dirname(ROOT)) == 'fsa-wt' else os.path.dirname(ROOT)
DOLPHIN = os.environ.get('FSA_DOLPHIN', os.path.join(PROJ, 'dolphin', 'build', 'Binaries', 'dolphin-emu-nogui'))
DISC = os.environ.get('FSA_DISC', os.path.join(PROJ, 'LoZ- FSA.rvz'))
# Extracted disc trees (never inside a repo): A/ is the disc as dtk extracts it; each other DOL
# gets a tree whose sys/main.dol is that DOL and whose files/ links to A's.
DISC_DIR = os.environ.get('FSA_DISC_DIR', os.path.join(PROJ, 'harness-disc'))
DTK = os.environ.get('FSA_DTK', os.path.join(ROOT, 'build', 'tools', 'dtk'))
PORT = os.environ.get('FSA_PORT', os.path.join(os.path.dirname(PROJ), 'fsaport'))

A_DOL = os.path.join(ROOT, 'orig', 'sys', 'main.dol')
A_SYMS = os.path.join(ROOT, 'config', 'G4SE01', 'symbols.txt')
B_DOL = os.path.join(ROOT, 'build', 'G4SE01', 'fsa_game_code.dol')
B_MAP = os.path.join(ROOT, 'build', 'G4SE01', 'fsa_game_code.elf.MAP')

# PAD_BUTTON_* bits
BUTTONS = {'left': 0x1, 'right': 0x2, 'down': 0x4, 'up': 0x8, 'z': 0x10, 'r': 0x20, 'l': 0x40,
           'a': 0x100, 'b': 0x200, 'x': 0x400, 'y': 0x800, 'start': 0x1000}
STICK = {'sl': (0, -127, 0), 'sr': (0, 127, 0), 'su': (0, 0, 127), 'sd': (0, 0, -127)}

# --- state tables (fsaport game/src/port/harness_state.cpp) -------------------------------------
# Paths: a symbol, then '*' (load a pointer) or '+off'. ROOT_ = gGameRoot_8053AAF8's object.
ROOT_ = ['gGameRoot_8053AAF8', '*']
STAGE_SUB = ROOT_ + ['+4', '*']                     # GameRoot_8049EF20::field_0x4 (GameRootSub04_801F856C)
VIEW = STAGE_SUB + ['+c', '*']                       # getGameView_802D6A9C(): field_0x4->mView
FADE = ['fn_80119DD0()']                             # its function-local static (lbl_804BC504)
DEMO = ['fn_8011921C()']                             # its function-local static (lbl_804BC540)
GLOBALS = [  # name, type, guard (None or path), path
    ('gGameRoot_8053AAF8->field_0x4c', 's32', None, ROOT_ + ['+4c']),
    ('gGameRoot_8053AAF8->field_0x50', 's32', None, ROOT_ + ['+50']),
    ('gGameRoot_8053AAF8->field_0x58', 's32', None, ROOT_ + ['+58']),
    ('gGameRoot_8053AAF8->field_0x60', 's32', None, ROOT_ + ['+60']),
    ('gGameRoot_8053AAF8->field_0x7f', 'u8', None, ROOT_ + ['+7f']),
    ('gGameRoot_8053AAF8->field_0xfd', 'u8', None, ROOT_ + ['+fd']),
    ('gGameRoot_8053AAF8->mPlayerMask', 'u8', None, ROOT_ + ['+82']),
    ('gGameRoot_8053AAF8->mRandom.seed', 'u32', None, ROOT_ + ['+b4']),
    ('lbl_80529DEC.mStage_0x118', 's32', None, ['lbl_80529DEC', '+118']),
    ('lbl_80529DEC.mLevel_0x11c', 's32', None, ['lbl_80529DEC', '+11c']),
    # The file select screen (FileSelect_804AFF60, include/game/file_select_803BC6F0.h).
    # field_0x7c is a u32 the port prints with j.i (signed), hence s32 here.
    ('lbl_8053ADB0->mState', 'u8', None, ['lbl_8053ADB0', '*', '+110']),
    ('lbl_8053ADB0->field_0x7c', 's32', None, ['lbl_8053ADB0', '*', '+7c']),
    ('lbl_8053ADB0->field_0x114', 'u8', None, ['lbl_8053ADB0', '*', '+114']),
    ('lbl_8053ADB0->field_0x116', 'u8', None, ['lbl_8053ADB0', '*', '+116']),
    ('getGameView_802D6A9C()->mStage_0x4', 's32', STAGE_SUB, VIEW + ['+4']),
    ('getGameView_802D6A9C()->mLevel_0x8', 's32', STAGE_SUB, VIEW + ['+8']),
    ('getGameView_802D6A9C()->mScreenX_0x14', 's32', STAGE_SUB, VIEW + ['+14']),
    ('getGameView_802D6A9C()->mScreenY_0x18', 's32', STAGE_SUB, VIEW + ['+18']),
    ('fn_80119DD0()->field_0x0', 'u8', STAGE_SUB, FADE + ['+0']),
    ('fn_80119DD0()->field_0x4', 's32', STAGE_SUB, FADE + ['+4']),
    ('fn_80119DD0()->field_0x14', 'f32', STAGE_SUB, FADE + ['+14']),
    ('fn_8011921C()->field_0x8', 's32', STAGE_SUB, DEMO + ['+8']),
    ('gGameRoot2_8053AB10->field_0x24->mViewBox_0x164', 'box2', STAGE_SUB,
     ['gGameRoot2_8053AB10', '*', '+24', '*', '+164']),
]
# Fields a script's `set` step may write besides GLOBALS (Dolphin-side extension, docs/HARNESS_DOLPHIN.md):
# GameState's saved stage/level, which fsaport's ?stage= sets together with mStage/mLevel.
SETTABLES = [
    ('lbl_80529DEC.field_0x128', 's32', ['lbl_80529DEC', '+128']),
    ('lbl_80529DEC.field_0x12c', 's32', ['lbl_80529DEC', '+12c']),
]
# Extra fields for localising a divergence (`run --watch GROUP`), written under "watch" in the
# state records; not in the port's records, so leave them off for port comparisons.
GAMEOVER = STAGE_SUB + ['+18', '*']  # GameRootSub04_801F856C::field_0x18 (GameOverScreen_804B17A0)
WATCH = {
    # GameRoot_8049EF20's mode-switch state: the archive loads applyRequestedMode_80135494 waits on.
    'root': [
        ('gGameRoot_8053AAF8->field_0x7c', 's16', None, ROOT_ + ['+7c']),
        ('gGameRoot_8053AAF8->field_0x84', 'u8', None, ROOT_ + ['+84']),
        ('gGameRoot_8053AAF8->field_0xac', 'u32', None, ROOT_ + ['+ac']),
        ('gGameRoot_8053AAF8->field_0xac->field_0x4', 's32', None, ROOT_ + ['+ac', '*', '+4']),
        ('gGameRoot_8053AAF8->field_0xb0', 'u32', None, ROOT_ + ['+b0']),
        ('gGameRoot_8053AAF8->field_0xb0->field_0x4', 's32', None, ROOT_ + ['+b0', '*', '+4']),
    ],
    'gameover': [(f'GameOverScreen_804B17A0.{n}', t, STAGE_SUB, GAMEOVER + [f'+{o:x}']) for n, t, o in [
        ('field_0x38', 's32', 0x38), ('field_0x3c', 's32', 0x3C), ('field_0x40', 'u8', 0x40),
        ('field_0x41', 'u8', 0x41), ('field_0x42', 'u8', 0x42), ('field_0x43', 'u8', 0x43),
        ('field_0x44', 's32', 0x44), ('field_0x48', 's32', 0x48), ('field_0x4c', 'f32', 0x4C),
        ('field_0x50', 'f32', 0x50), ('field_0x54', 's16', 0x54), ('field_0x56', 's16', 0x56),
        ('field_0x58', 'u8', 0x58), ('field_0x59', 'u8', 0x59), ('field_0x5a', 'u8', 0x5A),
        ('field_0x5b', 'u8', 0x5B), ('field_0x5c', 'u8', 0x5C), ('field_0x5d', 'u8', 0x5D),
        ('field_0x5e', 'u8', 0x5E), ('field_0x5f', 'u8', 0x5F)]],
}
SCENE = [ROOT_ + ['+4c'], ['lbl_80529DEC', '+118'], ['lbl_80529DEC', '+11c']]
ACTORS = (STAGE_SUB + ['+8', '*'], 0x8, 0x1008)    # ActorManager_804A5800: mActors[], mActorEnd
ACTOR_FIELDS = [  # ActorBase_804A5770
    ('mSlot', 's32', 0x19C), ('mActorId', 'id4', 0x1A0), ('mSerial', 's32', 0x198),
    ('mAlive', 'bool', 0x11C), ('mLayer_0x4', 's32', 0x4), ('mPos', 'vec3', 0xC),
    ('mDir_0x98', 's32', 0x98), ('mLife', 's32', 0x108),
]
PLAYERS = (['gPlayerManager_8053AC90', '*'], 0x4, 4)  # PlayerManager_804A6F28::mPlayers[4]
PLAYER_FIELDS = [  # Player_804A6F38
    ('mPlayerNo_0x4', 's32', 0x4), ('mActive', 'bool', 0xCAC), ('mPos', 'vec3', 0x8),
    ('mLayer_0x3b4', 's32', 0x3B4), ('mFacing_0x3dc', 's32', 0x3DC), ('mState_0x1240', 's32', 0x1240),
    ('mLife_0xbfc', 's32', 0xBFC),
]
# Accessors whose object is a function-local static: the static's symbol, by name in symbols.txt
# (and in a map when the unit links from asm or keeps the name).
# In a map of a build where tu_80118384 links from C they are locals, `<file>:<name>$<n>`.
ALIASES = {'fn_80119DD0()': ['lbl_804BC504', r'tu_80118384:instance\$\d+'],
           'fn_8011921C()': ['lbl_804BC540', r'tu_80118384:lbl_804BC540\$\d+']}


# --- symbols ---------------------------------------------------------------------------------------
def load_symbols(path):
    syms = {}
    if path.endswith('.txt'):
        rx = re.compile(r'^(\S+) = \.?\w+:0x([0-9A-Fa-f]{8});(?:\s*//.*?size:0x([0-9A-Fa-f]+))?')
        for line in open(path):
            m = rx.match(line)
            if m:
                syms.setdefault(m.group(1), (int(m.group(2), 16), int(m.group(3) or '0', 16)))
    else:
        rx = re.compile(r'^\s+[0-9a-f]{8} ([0-9a-f]{6}) ([0-9a-f]{8})\s+\d+ (\S+)\s+(\S+)\.o')
        for line in open(path, errors='replace'):
            m = rx.match(line)
            if m and int(m.group(2), 16):
                v = (int(m.group(2), 16), int(m.group(1), 16))
                syms.setdefault(m.group(3), v)
                syms.setdefault(m.group(4) + ':' + m.group(3), v)  # locals, by object
    return syms


def sym(syms, name):
    if name in syms:
        return syms[name][0]
    for pat in ALIASES.get(name, []):
        hits = [k for k in syms if re.fullmatch(pat, k)]
        if len(hits) == 1:
            return syms[hits[0]][0]
    raise SystemExit(f'harness_dolphin: symbol {name} not found')


def path_text(syms, path):
    out = [f'{sym(syms, path[0]):08X}']
    for p in path[1:]:
        out.append(p)
    return ','.join(out)


def read_dol(path):
    data = open(path, 'rb').read()
    secs = []
    for i in range(18):
        off, = struct.unpack_from('>I', data, 0x00 + 4 * i)
        addr, = struct.unpack_from('>I', data, 0x48 + 4 * i)
        size, = struct.unpack_from('>I', data, 0x90 + 4 * i)
        if size:
            secs.append((addr, size, off))
    return data, secs


def dol_word(dol, addr):
    data, secs = dol
    for a, size, off in secs:
        if a <= addr < a + size:
            return struct.unpack_from('>I', data, off + addr - a)[0]
    return None


def find_hook(dol_path, syms):
    """The instruction after JUTGamePad::read's `bl PADRead`."""
    dol = read_dol(dol_path)
    start, size = syms['read__10JUTGamePadFv']
    target = sym(syms, 'PADRead')
    for a in range(start, start + (size or 0x400), 4):
        w = dol_word(dol, a)
        if w is not None and (w & 0xFC000003) == 0x48000001:
            off = w & 0x03FFFFFC
            if off & 0x02000000:
                off -= 0x04000000
            if (a + off) & 0xFFFFFFFF == target:
                return a + 4
    raise SystemExit('harness_dolphin: no bl PADRead in JUTGamePad::read')


def write_spec(path, dol_path, syms, out, inputs, stop, shots=(), tick=60, script=None, watch=(), logreads=False):
    lines = ['# written by tools/harness_dolphin.py', f'out {out}']
    if inputs:
        lines.append(f'inputs {inputs}')
    if script:
        lines.append(f'script {script}')
    lines.append(f'stop {stop}')
    lines += [f'shot {n}' for n in shots]
    if logreads:
        lines.append('logreads')
    if tick != 60:
        lines.append(f'tick {tick}')
    lines.append(f'hook {find_hook(dol_path, syms):08X}')
    lines.append(f'pads {sym(syms, "mPadStatus__10JUTGamePad"):08X}')
    # The `set` key seed_on_stage is applied here (createModeScreen_80135020(7), before the stage's
    # actors spawn), as the port does.
    lines.append(f'stagehook {sym(syms, "createModeScreen_80135020__17GameRoot_8049EF20Fl"):08X}')
    for key, p in zip(('scene_mode', 'scene_stage', 'scene_level'), SCENE):
        lines.append(f'{key} {path_text(syms, p)}')
    for name, typ, guard, p in GLOBALS:
        lines.append(f'global {name} {typ} {path_text(syms, guard) if guard else "-"} {path_text(syms, p)}')
    for group in watch:
        for name, typ, guard, p in WATCH[group]:
            lines.append(f'watch {name} {typ} {path_text(syms, guard) if guard else "-"} {path_text(syms, p)}')
    for name, typ, p in SETTABLES:
        lines.append(f'settable {name} {typ} {path_text(syms, p)}')
    p, arr, end = ACTORS
    lines.append(f'actors {path_text(syms, p)} {arr:X} {end:X}')
    for name, typ, off in ACTOR_FIELDS:
        lines.append(f'afield {name} {typ} {off:X}')
    p, arr, count = PLAYERS
    lines.append(f'players {path_text(syms, p)} {arr:X} {count:X}')
    for name, typ, off in PLAYER_FIELDS:
        lines.append(f'pfield {name} {typ} {off:X}')
    open(path, 'w').write('\n'.join(lines) + '\n')


# --- Dolphin ----------------------------------------------------------------------------------------
DOLPHIN_INI = """[Core]
SIDevice0 = 6
SIDevice1 = 0
SIDevice2 = 0
SIDevice3 = 0
GFXBackend = OGL
CPUThread = False
DSPHLE = True
SkipIPL = True
EnableCheats = False
FastDiscSpeed = False
EnableCustomRTC = True
CustomRTCValue = 0x69559280
EmulationSpeed = 0.0
[DSP]
Backend = No Audio Output
DSPThread = False
[Interface]
ConfirmStop = False
[Analytics]
PermissionAsked = True
Enabled = False
"""


# Port 0 is an emulated controller with no input device: without "Always Connected" Dolphin
# reports it unplugged (err -1) and the game never leaves the title screen, whatever is injected.
GCPAD_INI = """[GCPad1]
Device =
Options/Always Connected = True
"""


def symbolizer(syms):
    import bisect
    funcs = sorted((a, size, n) for n, (a, size) in syms.items() if ':' not in n and size)
    starts = [f[0] for f in funcs]

    def name(addr):
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0 and addr < funcs[i][0] + funcs[i][1]:
            return f'{funcs[i][2]}+0x{addr - funcs[i][0]:x}'
        return f'{addr:08x}'
    return name


def invalid_accesses(log, syms):
    """Dolphin's invalid-access reports (the fork prints LR and the stack's back chain), by read
    when the run used --log-reads, with symbol names."""
    name = symbolizer(syms)
    out, read = [], None
    try:
        lines = open(log, errors='replace').read().splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        m = re.match(r'\[fsa-harness\] read (\d+)', line)
        if m:
            read = int(m.group(1))
            continue
        m = re.match(r'\[fsa-harness\] invalid (\w+) ([0-9A-F]+) pc ([0-9A-F]+) lr ([0-9A-F]+) stack(.*)', line)
        if m:
            chain = [name(int(x, 16)) for x in m.group(5).split()]
            where = f'read {read}: ' if read is not None else ''
            out.append(f'{where}{m.group(1)} {m.group(2)} at {name(int(m.group(3), 16))} '
                       f'(lr {name(int(m.group(4), 16))}; callers {" < ".join(chain)})')
    return out


def disc_tree(dol, tag):
    """A Dolphin DirectoryBlob tree (sys/ + files/) whose main.dol is `dol`. Booting a bare DOL
    with the disc as Core.DefaultISO hangs before the first pad read; a tree boots like the disc."""
    a = os.path.join(DISC_DIR, 'A')
    if not os.path.exists(os.path.join(a, 'sys', 'main.dol')):
        os.makedirs(a, exist_ok=True)
        dtk = DTK if os.path.exists(DTK) else shutil.which('dtk')
        subprocess.run([dtk, 'vfs', 'cp', '-q', DISC + ':', a + '/'], check=True)
    if tag == 'A':
        return os.path.join(a, 'sys', 'main.dol')
    t = os.path.join(DISC_DIR, tag)
    os.makedirs(os.path.join(t, 'sys'), exist_ok=True)
    for f in os.listdir(os.path.join(a, 'sys')):
        if f != 'main.dol':
            shutil.copyfile(os.path.join(a, 'sys', f), os.path.join(t, 'sys', f))
    shutil.copyfile(dol, os.path.join(t, 'sys', 'main.dol'))
    if not os.path.exists(os.path.join(t, 'files')):
        os.symlink(os.path.join(a, 'files'), os.path.join(t, 'files'))
    return os.path.join(t, 'sys', 'main.dol')


def sbg_running(name):
    out = subprocess.run(['sbg', 'ls'], capture_output=True, text=True).stdout
    return any(f' sbg {name} ' in l and 'running' in l for l in out.splitlines())


def run(args):
    if args.dol == 'A':
        dol, syms = A_DOL, load_symbols(A_SYMS)
    elif args.dol == 'B':
        dol, syms = B_DOL, load_symbols(B_MAP)
    else:
        dol, syms = args.dol, load_symbols(args.symbols)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    user = os.path.join(out, 'user')  # a fresh user dir each run: empty memory card, same SRAM
    os.makedirs(os.path.join(user, 'Config'))
    ini = DOLPHIN_INI
    if args.overclock:
        # A faster emulated CPU makes CPU-bound loads finish in the same number of frames in A
        # and B (B's C can be slower or faster than the original code; the RNG advances per frame).
        ini = ini.replace('[DSP]', f'OverclockEnable = True\nOverclock = {args.overclock}\n[DSP]')
    if not args.disc_timing:
        # The disc tree puts files after main.dol, so a DOL of another size moves every file and
        # Dolphin's seek-time model changes load lengths; fast disc speed takes that out.
        ini = ini.replace('FastDiscSpeed = False', 'FastDiscSpeed = True')
    open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(ini)
    open(os.path.join(user, 'Config', 'GCPadNew.ini'), 'w').write(GCPAD_INI)
    boot = disc_tree(dol, args.dol if args.dol in ('A', 'B') else 'X-' + os.path.basename(out))
    spec = os.path.join(out, 'spec.txt')
    inputs = os.path.abspath(args.inputs) if args.inputs else None
    shots = [int(x) for x in args.shots.split(',')] if args.shots else []
    script = os.path.abspath(args.script) if args.script else None
    if script and inputs:
        raise SystemExit('harness_dolphin: --script and --inputs exclude each other')
    write_spec(spec, dol, syms, out, inputs, args.reads, shots, args.tick, script,
               args.watch.split(',') if args.watch else (), args.log_reads)
    name = args.name or 'hd-' + os.path.basename(out)
    log = os.path.join(out, 'dolphin.log')
    env = ['env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY',
           '__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json',
           f'FSA_HARNESS={spec}']
    cmd = ['sh', '-c', 'exec "$@" > "$0" 2>&1', log] + env + [DOLPHIN, '-u', user, '-p', 'headless', '-v', 'OGL', '-e', boot]
    subprocess.run(['sbg', 'start', name, '--'] + cmd, check=True)
    t0 = time.time()
    try:
        time.sleep(2)
        while sbg_running(name):
            if time.time() - t0 > args.timeout:
                print(f'harness_dolphin: timeout after {args.timeout}s', file=sys.stderr)
                break
            time.sleep(1)
    finally:
        subprocess.run(['sbg', 'stop', name], capture_output=True)
    reads = 0
    try:
        with open(os.path.join(out, 'sync.jsonl')) as f:
            for line in f:
                o = json.loads(line)
                reads = max(reads, o.get('n', 0))
    except FileNotFoundError:
        pass
    shotdir = os.path.join(user, 'ScreenShots')
    for d, _, files in os.walk(shotdir):
        for f in files:
            os.makedirs(os.path.join(out, 'shots'), exist_ok=True)
            shutil.move(os.path.join(d, f), os.path.join(out, 'shots', f))
    if not args.keep_user:
        shutil.rmtree(user, ignore_errors=True)
    ends = []
    try:
        for line in open(os.path.join(out, 'sync.jsonl')):
            o = json.loads(line)
            if o.get('sync') in ('script_end', 'script_timeout'):
                ends.append(line.strip())
    except FileNotFoundError:
        pass
    bad = invalid_accesses(log, syms)
    if bad:
        with open(os.path.join(out, 'invalid.txt'), 'w') as f:
            f.write('\n'.join(bad) + '\n')
    print(f'{out}: last sync at read {reads}, {time.time() - t0:.0f}s {" ".join(ends)}'
          + (f'; {len(bad)} invalid accesses (OUT/invalid.txt), first: {bad[0]}' if bad else ''))


# --- inputs -----------------------------------------------------------------------------------------
# Title -> main menu -> Hyrulean Adventure -> "create a file?" Yes -> the opening narration
# (mode 7, stage 8 level 3 from read 1920), then A every 120 reads. Timed on A and B (2026-11-24).
OPENING = 'start@400,start@600,a@700,a@790,a@980,left@1100:10,a@1160,' + ','.join(
    f'a@{n}' for n in range(1300, 100000, 120))


def make_inputs(args):
    """--script 'start@300,a@420:10,sr@600:120': KEY@n[:frames] (default 6 reads held);
    --script opening: the preset above."""
    events = []
    script = OPENING if args.script == 'opening' else args.script
    for item in filter(None, script.split(',')):
        key, _, when = item.partition('@')
        at, _, dur = when.partition(':')
        events.append((key.lower(), int(at), int(dur or 6)))
    with open(args.out, 'w') as f:
        for n in range(args.reads):
            pad = [0, 0, 0, 0, 0, 0, 0]
            for key, at, dur in events:
                if at <= n < at + dur:
                    if key in BUTTONS:
                        pad[0] |= BUTTONS[key]
                    elif key in STICK:
                        pad[1] += STICK[key][1]
                        pad[2] += STICK[key][2]
                    else:
                        raise SystemExit(f'unknown key {key}')
            f.write(json.dumps({'n': n, 'pads': [pad, None, None, None]}, separators=(',', ':')) + '\n')


# --- B build ---------------------------------------------------------------------------------------
def build_b(args):
    """Link every NonMatching unit's C object (configure.py --non-matching links only Equivalent
    ones); units whose objects break the link (undefined: the C does not define a symbol the unit
    owns; multiply-defined) are put back to asm, iteratively. Writes build/harness_b_excluded.txt."""
    g = os.path.realpath(args.tools) if args.tools else os.path.join(ROOT, 'build')
    owners = {}
    rx = re.compile(r'^\s+[0-9a-f]{8} [0-9a-f]{6} [0-9a-f]{8}\s+\d+ (\S+)\s+(\S+)\.o')
    for line in open(args.owner_map, errors='replace'):
        m = rx.match(line)
        if m:
            owners.setdefault(m.group(1), m.group(2))
    src = open(os.path.join(ROOT, 'configure.py')).read()
    units = set(re.findall(r'Object\(NonMatching, "game/([^"]+)\.cpp"', src))
    excluded = set(filter(None, (args.exclude or '').split(',')))
    for it in range(args.max_iter):
        s = src.replace('NonMatching = False ', 'NonMatching = config.non_matching ', 1)
        for u in excluded:
            s = s.replace(f'Object(NonMatching, "game/{u}.cpp"', f'Object(False, "game/{u}.cpp"')
        conf = os.path.join(ROOT, 'build', 'harness_configure.py')
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        open(conf, 'w').write(s)
        cargs = ['--non-matching', '--map']
        if args.tools:
            cargs += ['--binutils', f'{g}/binutils', '--compilers', f'{g}/compilers', '--dtk', f'{g}/tools/dtk',
                      '--wrapper', f'{g}/tools/wibo', '--sjiswrap', f'{g}/tools/sjiswrap.exe',
                      '--objdiff', f'{g}/tools/objdiff-cli']
        boot = ('import sys,os;sys.path.insert(0,os.getcwd());sys.argv=["configure.py"]+sys.argv[1:];'
                f'exec(compile(open({conf!r}).read(),"configure.py","exec"),'
                '{"__name__":"__main__","__file__":os.path.abspath("configure.py")})')
        # build.ninja regenerates itself with the plain configure.py whenever dtk's config.json
        # (or configure.py) is newer, which silently links the original objects again: bring
        # config.json up to date first, then write build.ninja, and check the link inputs after.
        for _ in range(3):
            subprocess.run(['ninja', 'build/G4SE01/config.json'], cwd=ROOT, capture_output=True)
            subprocess.run([sys.executable, '-c', boot] + cargs, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            r = subprocess.run(['ninja', '-j', str(args.jobs), 'build/G4SE01/fsa_game_code.dol'], cwd=ROOT,
                               capture_output=True, text=True)
            if 'RUN configure.py' not in r.stdout:
                break
        log = r.stdout + r.stderr
        ninja_text = open(os.path.join(ROOT, 'build.ninja')).read()
        link = ninja_text[ninja_text.index('build build/G4SE01/fsa_game_code.elf'):]
        link = link[:link.index('\n\n')]
        from_c = sum(1 for u in units - excluded if f'build/G4SE01/src/game/{u}.o' in link)
        if from_c != len(units - excluded):
            raise SystemExit(f'harness_dolphin: build.ninja links {from_c} of {len(units - excluded)} '
                             'units from C (regenerated by the plain configure.py?)')
        open(os.path.join(ROOT, 'build', 'harness_b.log'), 'w').write(log)
        if r.returncode == 0:
            break
        new = set()
        undef = set(re.findall(r"undefined: '([^']+)'", log))
        for name in undef:
            if owners.get(name) in units:
                new.add(owners[name])
        # Undefined with no C owner (e.g. a C++-mangled reference to an asm function): put the
        # referencing unit back instead.
        flat = re.sub(r'\n#\s*', ' ', log)
        for name, obj in re.findall(r"undefined: '([^']+)'\s+Referenced from '.*?' in\s+(\S+)\.o", flat):
            if owners.get(name) not in units and obj in units:
                new.add(obj)
        for name, obj in re.findall(r"multiply-defined: '([^']+)' in (\S+)\.o", log):
            if obj in units:
                new.add(obj)
        new -= excluded
        print(f'iteration {it}: {len(undef)} undefined; excluding {sorted(new)}')
        if not new:
            print('harness_dolphin: link fails and no unit to put back; see build/harness_b.log')
            return 1
        excluded |= new
    else:
        print('harness_dolphin: still not linking after --max-iter')
        return 1
    open(os.path.join(ROOT, 'build', 'harness_b_excluded.txt'), 'w').write('\n'.join(sorted(excluded)) + '\n')
    same = open(B_DOL, 'rb').read() == open(A_DOL, 'rb').read()
    if same:
        print('harness_dolphin: B is byte-identical to the original DOL')
        return 1
    print(f'B linked: {len(units) - len(excluded)} of {len(units)} NonMatching game units from C; '
          f'excluded {len(excluded)} (build/harness_b_excluded.txt)')
    return 0


def first_diff(args):
    """The first state record (by anchor order, then offset) where two runs differ, with each
    differing field and, for actors, the ActorId and slot. Run with --tick 1 for read precision."""
    sys.path.insert(0, os.path.join(PORT, 'tools'))
    from harness_compare import diff

    def load(run):
        anchors, states = [], {}
        for line in open(os.path.join(run, 'sync.jsonl')):
            o = json.loads(line)
            if o['sync'] == 'scene':
                anchors.append((('scene', o['mode'], o['stage'], o['level']), o['n']))
            elif o['sync'] == 'step':
                anchors.append((('step', o['step']), o['n']))
        for line in open(os.path.join(run, 'state.jsonl')):
            o = json.loads(line)
            states[o['n']] = o
        return anchors, states

    (aa, sa), (ab, sb) = load(args.a), load(args.b)
    for i, ((ida, na), (idb, nb)) in enumerate(zip(aa, ab)):
        if ida != idb:
            print(f'anchor {i}: {ida} at A {na} vs {idb} at B {nb}: sequences differ')
            return 1
        enda = aa[i + 1][1] if i + 1 < len(aa) else max(sa) + 1
        endb = ab[i + 1][1] if i + 1 < len(ab) else max(sb) + 1
        for off in range(0, min(enda - na, endb - nb)):
            x, y = sa.get(na + off), sb.get(nb + off)
            if x is None or y is None:
                continue
            x, y = dict(x), dict(y)
            for o in (x, y):
                o.pop('n'), o.pop('sync')
            d = list(diff(x, y))
            if not d:
                continue
            print(f'first difference: anchor {ida} +{off} (A read {na + off}, B read {nb + off}), {len(d)} fields')
            for path, u, v in d[:args.show]:
                who = ''
                m = re.match(r'actors\[(\d+)\]', path)
                if m and x.get('actors') and int(m.group(1)) < len(x['actors']):
                    act = x['actors'][int(m.group(1))]
                    who = f" ({act['mActorId']} slot {act['mSlot']})"
                print(f'  {path}{who}: {json.dumps(u)} vs {json.dumps(v)}')
            return 1
    print('no difference in the matched anchors')
    return 0


def compare(args):
    tool = os.path.join(PORT, 'tools', 'harness_compare.py')
    extra = ['--upto', str(args.upto)] if args.upto is not None else []
    if args.anchor:
        extra += ['--anchor', args.anchor]
    return subprocess.run([sys.executable, tool, args.a, args.b, '--show', str(args.show)] + extra).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='run a DOL in headless Dolphin and collect the streams')
    r.add_argument('--dol', required=True, help='A (original), B (build), or a DOL path (with --symbols)')
    r.add_argument('--symbols', help='symbols.txt or linker .MAP for a DOL path')
    r.add_argument('--inputs', help='inputs JSONL to replay (default: record)')
    r.add_argument('--script', help='input script (fsaport docs/HARNESS.md "Scripted input"), e.g. tools/harness_scripts/opening.json')
    r.add_argument('--reads', type=int, required=True, help='stop after this many pad reads')
    r.add_argument('-o', '--out', required=True)
    r.add_argument('--name', help='sbg process name')
    r.add_argument('--timeout', type=int, default=1800)
    r.add_argument('--overclock', type=float, help='emulated CPU clock factor (e.g. 4): CPU-bound loads take the same frames in A and B')
    r.add_argument('--disc-timing', action='store_true',
                   help="emulate disc timing (default: fast disc speed, so loads don't depend on the DOL's size)")
    r.add_argument('--watch', help='extra field groups under "watch": ' + ','.join(WATCH))
    r.add_argument('--log-reads', action='store_true', help='log every read to dolphin.log (places invalid accesses at a read)')
    r.add_argument('--tick', type=int, default=60, help='tick sync points every N reads (default 60, as the port; 1 for a full trace)')
    r.add_argument('--shots', help='comma-separated reads n to screenshot (OUT/shots/nNNNNNN.png)')
    r.add_argument('--keep-user', action='store_true', help='keep the Dolphin user dir (card, logs)')
    i = sub.add_parser('inputs', help='write a scripted inputs file')
    i.add_argument('--script', required=True)
    i.add_argument('--reads', type=int, required=True)
    i.add_argument('-o', '--out', required=True)
    b = sub.add_parser('build-b', help='link B: NonMatching units from C where they link')
    b.add_argument('--tools', help='a build dir with binutils/, compilers/, tools/ to reuse')
    b.add_argument('--owner-map', default=os.path.join(PROJ, 'fsa-decomp', 'build', 'G4SE01', 'fsa_game_code.elf.MAP'),
                   help="a matching build's .MAP (which unit owns each symbol)")
    b.add_argument('--exclude', help='units (game/<unit>.cpp names, no extension) to keep as asm')
    b.add_argument('--max-iter', type=int, default=20)
    b.add_argument('--jobs', type=int, default=16)
    c = sub.add_parser('compare', help="the port's tools/harness_compare.py")
    c.add_argument('a')
    c.add_argument('b')
    c.add_argument('--upto', type=int)
    c.add_argument('--show', type=int, default=3)
    c.add_argument('--anchor', choices=['scene'], help='scene/step-anchored comparison (script runs, port vs Dolphin)')
    f = sub.add_parser('first-diff', help='the first differing state record, anchor-aligned (use --tick 1 runs)')
    f.add_argument('a')
    f.add_argument('b')
    f.add_argument('--show', type=int, default=20)
    args = ap.parse_args()
    if args.cmd == 'run':
        run(args)
    elif args.cmd == 'inputs':
        make_inputs(args)
    elif args.cmd == 'build-b':
        sys.exit(build_b(args))
    elif args.cmd == 'first-diff':
        sys.exit(first_diff(args))
    elif args.cmd == 'compare':
        sys.exit(compare(args))


if __name__ == '__main__':
    main()
