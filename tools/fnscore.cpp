// fnscore: how far is a function of OURS.o from the same function of TARGET.o?
//
//   fnscore TARGET.o OURS.o SYMBOL...     one line per symbol: name<TAB>score<TAB>target insns<TAB>our insns
//   fnscore TARGET.o OURS.o --all         every function of TARGET.o
//   fnscore farm --target TARGET.o --dir DIR --src REL/PATH.cpp --jobs N [--keep] (--all | --sym NAME...) -- COMPILER ARGV...
//       the candidate farm: reads candidates from stdin (`C <id> <bytes>\n` then that many bytes of
//       source text), writes each to DIR/<id>/REL/PATH.cpp, runs COMPILER ARGV there ({SRC} and {OUT}
//       stand for the source path and the output directory) on N at a time, scores the object and
//       prints `N <name>...` once, then `R <id> <score>...` (one score per name, in order; with --hash
//       each is `<score>/<hash of our function's code>`) or
//       `E <id> <last line of the compiler's output>` per candidate. Nothing in the loop is Python.
//
// The inner loop of tools/permute.py: a search compiles thousands of candidates, and each needs one
// number that falls smoothly as the code gets closer to the original (objdiff's match % is flat
// across most register and ordering changes, and its JSON costs more than the compile). The
// instructions of both functions are aligned on their opcodes (Myers diff) and scored with
// decomp-permuter's weights: 100 per instruction only one side has, 5 per differing register,
// 1 per differing stack offset, 20 per other differing immediate, 5 per branch that goes to
// another place. Relocated fields are compared by relocation kind, and by target name when both
// sides name a real symbol (compiler literals `@123` and dtk's `lbl_` are anonymous).
// Score 0 = the same code up to anonymous relocation targets; -1 = the symbol is missing.
// The honest measure stays objdiff (tools/scratch.py checks every result with it).
//
// Build: g++ -O2 -std=c++17 -pthread -o build/tools/fnscore tools/fnscore.cpp   (tools/scratch.py does it on demand)

#include <algorithm>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <fcntl.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

namespace {

const int INSERT = 100, REG = 5, STACK = 1, IMM = 20, BRANCH = 5, RELOC = 20, NAME = 10;

struct Reloc {
    uint32_t type = 0;
    std::string sym;
    int32_t addend = 0;
    bool anon = true;
};

struct Insn {
    uint32_t w = 0;
    const Reloc *rel = nullptr;
};

struct Func {
    bool found = false;
    std::vector<Insn> code;
};

struct Obj {
    std::vector<uint8_t> d;
    struct Sec { uint32_t name, type, off, size, link, info, entsize; };
    struct Sym { std::string name; uint32_t value, size; uint8_t info; uint16_t shndx; };
    std::vector<Sec> secs;
    std::vector<Sym> syms;
    std::unordered_map<std::string, int> funcs;
    std::unordered_map<uint64_t, Reloc> rels;  // (section << 32 | instruction address) -> relocation

    uint16_t u16(size_t o) const { return o + 2 <= d.size() ? uint16_t(d[o] << 8 | d[o + 1]) : 0; }
    uint32_t u32(size_t o) const {
        return o + 4 <= d.size() ? uint32_t(d[o]) << 24 | uint32_t(d[o + 1]) << 16 | uint32_t(d[o + 2]) << 8 | d[o + 3] : 0;
    }
    std::string str(uint32_t tab, uint32_t off) const {
        if (tab >= secs.size()) return "";
        size_t o = size_t(secs[tab].off) + off;
        std::string s;
        while (o < d.size() && d[o]) s.push_back(char(d[o++]));
        return s;
    }

    bool load(const char *path) {
        FILE *f = fopen(path, "rb");
        if (!f) return false;
        fseek(f, 0, SEEK_END);
        long n = ftell(f);
        fseek(f, 0, SEEK_SET);
        d.resize(n > 0 ? size_t(n) : 0);
        bool ok = n > 0 && fread(d.data(), 1, size_t(n), f) == size_t(n);
        fclose(f);
        if (!ok || d.size() < 52 || memcmp(d.data(), "\x7f" "ELF\x01\x02", 6) != 0) return false;
        uint32_t shoff = u32(32);
        uint16_t shentsize = u16(46), shnum = u16(48);
        for (uint16_t i = 0; i < shnum; i++) {
            size_t o = size_t(shoff) + size_t(i) * shentsize;
            secs.push_back({u32(o), u32(o + 4), u32(o + 16), u32(o + 20), u32(o + 24), u32(o + 28), u32(o + 36)});
        }
        for (size_t i = 0; i < secs.size(); i++) {
            if (secs[i].type != 2) continue;  // SHT_SYMTAB
            uint32_t cnt = secs[i].size / 16;
            for (uint32_t k = 0; k < cnt; k++) {
                size_t o = size_t(secs[i].off) + size_t(k) * 16;
                Sym s{str(secs[i].link, u32(o)), u32(o + 4), u32(o + 8), d[o + 12], u16(o + 14)};
                if ((s.info & 15) == 2 && s.size && s.shndx && s.shndx < secs.size()) funcs.emplace(s.name, int(syms.size()));
                syms.push_back(std::move(s));
            }
            break;
        }
        for (size_t i = 0; i < secs.size(); i++) {
            if (secs[i].type != 4) continue;  // SHT_RELA
            uint32_t cnt = secs[i].size / 12;
            for (uint32_t k = 0; k < cnt; k++) {
                size_t o = size_t(secs[i].off) + size_t(k) * 12;
                uint32_t off = u32(o), info = u32(o + 4);
                Reloc r;
                r.type = info & 0xff;
                r.addend = int32_t(u32(o + 8));
                uint32_t si = info >> 8;
                if (si < syms.size()) {
                    const Sym &s = syms[si];
                    r.sym = s.name;
                    r.anon = (s.info & 15) == 3 || s.name.empty() || s.name[0] == '@' || s.name[0] == '.' ||
                             s.name.compare(0, 4, "lbl_") == 0;
                }
                rels[uint64_t(secs[i].info) << 32 | (off & ~3u)] = std::move(r);
            }
        }
        return true;
    }

    Func func(const std::string &name) const {
        Func f;
        auto it = funcs.find(name);
        if (it == funcs.end()) return f;
        const Sym &s = syms[it->second];
        const Sec &sec = secs[s.shndx];
        if (sec.type != 1 || uint64_t(s.value) + s.size > sec.size) return f;
        f.found = true;
        for (uint32_t a = s.value; a + 4 <= s.value + s.size; a += 4) {
            Insn in;
            in.w = u32(size_t(sec.off) + a);
            auto r = rels.find(uint64_t(s.shndx) << 32 | a);
            if (r != rels.end()) in.rel = &r->second;
            f.code.push_back(in);
        }
        return f;
    }
};

uint32_t reloc_mask(const Reloc *r) {
    if (!r) return 0;
    switch (r->type) {
    case 10: return 0x03fffffc;                    // R_PPC_REL24
    case 11: return 0x0000fffc;                    // R_PPC_REL14
    case 4: case 5: case 6: return 0x0000ffff;     // R_PPC_ADDR16_LO / HI / HA
    case 109: return 0x001fffff;                   // R_PPC_EMB_SDA21 (base register and offset)
    default: return 0xffffffff;
    }
}

bool a_form(uint32_t w) { return ((w >> 1) & 0x1f) >= 18; }

// What makes two instructions "the same instruction" for the alignment: the mnemonic.
uint32_t key(uint32_t w) {
    uint32_t op = w >> 26;
    switch (op) {
    case 16: return op << 20 | ((w >> 21) & 0x1f) << 8 | ((w >> 16) & 3) << 2 | (w & 3);  // BO, condition bit, AA/LK
    case 18: return op << 20 | (w & 3);
    case 19: case 31: return op << 20 | ((w >> 1) & 0x3ff) << 1 | (w & 1);
    case 59: case 63: case 4:
        return a_form(w) ? op << 20 | 1u << 19 | ((w >> 1) & 0x1f) << 1 | (w & 1) : op << 20 | ((w >> 1) & 0x3ff) << 1 | (w & 1);
    case 20: case 21: case 23: return op << 20 | (w & 1);
    default: return op << 20;
    }
}

bool stack_form(uint32_t op) { return (op >= 32 && op <= 55) || op == 14; }

// Cost of two aligned instructions with the same key (branch displacements are scored by the caller).
int pair_cost(const Insn &a, const Insn &b) {
    int c = 0;
    uint32_t ma = reloc_mask(a.rel), mb = reloc_mask(b.rel);
    if ((a.rel != nullptr) != (b.rel != nullptr) || (a.rel && a.rel->type != b.rel->type)) c += RELOC;
    else if (a.rel && !a.rel->anon && !b.rel->anon && (a.rel->sym != b.rel->sym || a.rel->addend != b.rel->addend)) c += NAME;
    uint32_t m = ~(ma | mb);
    uint32_t x = a.w & m, y = b.w & m;
    if (x == y) return c;
    uint32_t op = a.w >> 26;
    auto fld = [&](int sh) { return int(((x >> sh) & 0x1f) != ((y >> sh) & 0x1f)); };
    switch (op) {
    case 16: return c + REG * fld(16);
    case 18: return c;
    case 20: case 21:
        return c + REG * (fld(21) + fld(16)) + (((x >> 1) & 0x7fff) != ((y >> 1) & 0x7fff) ? IMM : 0);
    case 23:
        return c + REG * (fld(21) + fld(16) + fld(11)) + (((x >> 1) & 0x3ff) != ((y >> 1) & 0x3ff) ? IMM : 0);
    case 19:
        return c + REG * (fld(21) + fld(16) + fld(11));
    case 31: {
        uint32_t xo = (x >> 1) & 0x3ff;
        bool imm3 = xo == 824 || xo == 339 || xo == 467 || xo == 19 || xo == 144;  // srawi, mfspr, mtspr, mfcr, mtcrf
        return c + REG * (fld(21) + fld(16)) + (imm3 ? IMM * fld(11) : REG * fld(11));
    }
    case 59: case 63: case 4:
        return c + REG * (fld(21) + fld(16) + fld(11) + (a_form(x) ? fld(6) : 0));
    default: {  // D-form
        int regs = fld(21) + fld(16);
        c += REG * regs;
        if ((x & 0xffff) != (y & 0xffff)) {
            bool stack = stack_form(op) && ((x >> 16) & 0x1f) == 1 && ((y >> 16) & 0x1f) == 1;
            c += stack ? STACK : IMM;
        }
        return c;
    }
    }
}

// Myers O(ND) alignment of the two key sequences: pairs (i, j) of matched instructions.
std::vector<std::pair<int, int>> align(const std::vector<uint32_t> &a, const std::vector<uint32_t> &b, int max_d) {
    int n = int(a.size()), m = int(b.size());
    int pre = 0;
    while (pre < n && pre < m && a[pre] == b[pre]) pre++;
    int suf = 0;
    while (suf < n - pre && suf < m - pre && a[n - 1 - suf] == b[m - 1 - suf]) suf++;
    std::vector<std::pair<int, int>> out;
    for (int i = 0; i < pre; i++) out.emplace_back(i, i);
    int N = n - pre - suf, M = m - pre - suf;
    if (N > 0 && M > 0) {
        int maxd = std::min(N + M, max_d);
        std::vector<std::vector<int>> trace;
        std::vector<int> v(2 * maxd + 3, 0);
        int off = maxd + 1, found = -1;
        for (int dd = 0; dd <= maxd && found < 0; dd++) {
            trace.push_back(v);
            for (int k = -dd; k <= dd; k += 2) {
                int x = (k == -dd || (k != dd && v[off + k - 1] < v[off + k + 1])) ? v[off + k + 1] : v[off + k - 1] + 1;
                int y = x - k;
                while (x < N && y < M && a[pre + x] == b[pre + y]) x++, y++;
                v[off + k] = x;
                if (x >= N && y >= M) { found = dd; break; }
            }
        }
        if (found >= 0) {
            std::vector<std::pair<int, int>> mid;
            int x = N, y = M;
            for (int dd = found; dd > 0; dd--) {
                const std::vector<int> &pv = trace[dd];
                int k = x - y;
                int pk = (k == -dd || (k != dd && pv[off + k - 1] < pv[off + k + 1])) ? k + 1 : k - 1;
                int px = pv[off + pk], py = px - pk;
                while (x > px && y > py && x > 0 && y > 0) { x--, y--; mid.emplace_back(pre + x, pre + y); }
                x = px, y = py;
            }
            while (x > 0 && y > 0) { x--, y--; mid.emplace_back(pre + x, pre + y); }
            std::reverse(mid.begin(), mid.end());
            out.insert(out.end(), mid.begin(), mid.end());
        }
        // else: too different to align within max_d; the middle counts as all inserted and deleted
    }
    for (int i = 0; i < suf; i++) out.emplace_back(n - suf + i, m - suf + i);
    return out;
}

int branch_target(const Insn &in, int idx) {  // instruction index a local branch goes to, or INT32_MIN
    if (in.rel) return INT32_MIN;
    uint32_t op = in.w >> 26;
    if (in.w & 2) return INT32_MIN;  // absolute
    if (op == 18) { int32_t d = int32_t(in.w << 6) >> 6; return idx + (d & ~3) / 4; }
    if (op == 16) { int32_t d = int32_t(int16_t(in.w & 0xfffc)); return idx + d / 4; }
    return INT32_MIN;
}

long score(const Func &t, const Func &o) {
    std::vector<uint32_t> ka, kb;
    for (auto &i : t.code) ka.push_back(key(i.w));
    for (auto &i : o.code) kb.push_back(key(i.w));
    auto pairs = align(ka, kb, 6000);
    std::vector<int> t2o(t.code.size() + 1, -1);
    for (auto &p : pairs) t2o[p.first] = p.second;
    long s = long(t.code.size() + o.code.size() - 2 * pairs.size()) * INSERT;
    for (auto &p : pairs) {
        const Insn &a = t.code[p.first], &b = o.code[p.second];
        s += pair_cost(a, b);
        int ta = branch_target(a, p.first), tb = branch_target(b, p.second);
        if (ta != INT32_MIN || tb != INT32_MIN) {
            bool same = ta != INT32_MIN && tb != INT32_MIN &&
                        ((ta >= 0 && ta < int(t.code.size()) && t2o[ta] == tb) ||
                         (ta == int(t.code.size()) && tb == int(o.code.size())) ||
                         ((ta < 0 || ta > int(t.code.size())) && ta - p.first == tb - p.second));
            if (!same) {
                // the target instruction may be one only one side has: accept the nearest aligned successor
                int na = ta;
                while (na >= 0 && na < int(t.code.size()) && t2o[na] < 0) na++;
                bool near = ta != INT32_MIN && tb != INT32_MIN && na >= 0 && na < int(t.code.size()) && t2o[na] >= tb &&
                            t2o[na] - tb <= na - ta + 8;
                if (!near) s += BRANCH;
            }
        }
    }
    return s;
}

// Our function's code with relocated fields masked: equal hashes = the same code.
uint32_t code_hash(const Func &f) {
    uint32_t h = 2166136261u;
    for (auto &i : f.code) {
        uint32_t w = i.w & ~reloc_mask(i.rel);
        for (int k = 0; k < 4; k++) { h ^= (w >> (8 * k)) & 0xff; h *= 16777619u; }
        h ^= i.rel ? i.rel->type + 1 : 0;
        h *= 16777619u;
    }
    return h;
}

// ---------------------------------------------------------------- the candidate farm

struct Job {
    std::string id, text;
};

std::string last_line(const std::string &path) {
    std::ifstream f(path);
    std::string line, keep;
    while (std::getline(f, line)) {
        size_t a = line.find_first_not_of(" \t\r");
        if (a == std::string::npos) continue;
        if (line.compare(0, 10, "User break") == 0) continue;
        keep = line.substr(a);
    }
    for (auto &c : keep)
        if (c == '\n' || c == '\r') c = ' ';
    return keep.substr(0, 200);
}

int farm(int argc, char **argv) {
    std::string target, dir, src;
    std::vector<std::string> names, cmd;
    int jobs = 8;
    bool keep = false, all = false, hashes = false;
    int i = 2;
    for (; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
        if (a == "--target") target = val();
        else if (a == "--dir") dir = val();
        else if (a == "--src") src = val();
        else if (a == "--jobs") jobs = std::max(1, atoi(val().c_str()));
        else if (a == "--sym") names.push_back(val());
        else if (a == "--all") all = true;
        else if (a == "--keep") keep = true;
        else if (a == "--hash") hashes = true;
        else if (a == "--") { i++; break; }
        else { fprintf(stderr, "fnscore farm: unknown option %s\n", a.c_str()); return 2; }
    }
    for (; i < argc; i++) cmd.push_back(argv[i]);
    if (target.empty() || dir.empty() || src.empty() || cmd.empty()) {
        fprintf(stderr, "fnscore farm: --target, --dir, --src and a compiler command are required\n");
        return 2;
    }
    Obj t;
    if (!t.load(target.c_str())) { fprintf(stderr, "fnscore: cannot read %s\n", target.c_str()); return 2; }
    if (all) {
        names.clear();
        for (auto &s : t.syms)
            if ((s.info & 15) == 2 && s.size && s.shndx) names.push_back(s.name);
    }
    std::vector<Func> tf;
    for (auto &n : names) tf.push_back(t.func(n));
    std::string objname = std::filesystem::path(src).stem().string() + ".o";

    std::mutex mu, out_mu;
    std::condition_variable cv;
    std::deque<Job> queue;
    bool done = false;
    {
        std::string head = "N";
        for (auto &n : names) head += " " + n;
        puts(head.c_str());
        fflush(stdout);
    }
    auto work = [&]() {
        for (;;) {
            Job job;
            {
                std::unique_lock<std::mutex> lk(mu);
                cv.wait(lk, [&] { return done || !queue.empty(); });
                if (queue.empty()) return;
                job = std::move(queue.front());
                queue.pop_front();
            }
            std::filesystem::path d = std::filesystem::path(dir) / job.id;
            std::error_code ec;
            std::filesystem::create_directories((d / src).parent_path(), ec);
            std::filesystem::create_directories(d / "out", ec);
            {
                std::ofstream f(d / src, std::ios::binary);
                f.write(job.text.data(), std::streamsize(job.text.size()));
            }
            std::vector<std::string> av;
            for (auto &c : cmd) av.push_back(c == "{SRC}" ? src : c == "{OUT}" ? std::string("out/") : c);
            std::vector<char *> cav;
            for (auto &c : av) cav.push_back(const_cast<char *>(c.c_str()));
            cav.push_back(nullptr);
            std::string log = (d / "log").string(), cwd = d.string();
            posix_spawn_file_actions_t fa;
            posix_spawn_file_actions_init(&fa);
            posix_spawn_file_actions_addchdir_np(&fa, cwd.c_str());
            posix_spawn_file_actions_addopen(&fa, 0, "/dev/null", O_RDONLY, 0);
            posix_spawn_file_actions_addopen(&fa, 1, log.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
            posix_spawn_file_actions_adddup2(&fa, 1, 2);
            pid_t pid = 0;
            int rc = posix_spawnp(&pid, cav[0], &fa, nullptr, cav.data(), environ);
            posix_spawn_file_actions_destroy(&fa);
            int status = -1;
            if (rc == 0) {
                while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
            }
            std::string line;
            Obj o;
            std::string objpath = (d / "out" / objname).string();
            if (rc == 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0 && o.load(objpath.c_str())) {
                line = "R " + job.id;
                for (size_t k = 0; k < names.size(); k++) {
                    Func b = o.func(names[k]);
                    line += " " + std::to_string(tf[k].found && b.found ? score(tf[k], b) : -1);
                    if (hashes) line += "/" + std::to_string(code_hash(b));
                }
            } else {
                line = "E " + job.id + " " + (rc ? std::string("cannot run ") + cav[0] : last_line(log));
            }
            if (!keep) std::filesystem::remove_all(d, ec);
            std::lock_guard<std::mutex> lk(out_mu);
            puts(line.c_str());
            fflush(stdout);
        }
    };
    std::vector<std::thread> pool;
    for (int k = 0; k < jobs; k++) pool.emplace_back(work);
    char head[256];
    while (fgets(head, sizeof head, stdin)) {
        char id[128];
        unsigned long n = 0;
        if (sscanf(head, "C %127s %lu", id, &n) != 2) continue;
        Job job;
        job.id = id;
        job.text.resize(n);
        if (n && fread(&job.text[0], 1, n, stdin) != n) break;
        {
            std::lock_guard<std::mutex> lk(mu);
            queue.push_back(std::move(job));
        }
        cv.notify_one();
    }
    {
        std::lock_guard<std::mutex> lk(mu);
        done = true;
    }
    cv.notify_all();
    for (auto &th : pool) th.join();
    return 0;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc >= 2 && std::string(argv[1]) == "farm") return farm(argc, argv);
    if (argc < 4) {
        fprintf(stderr, "usage: fnscore TARGET.o OURS.o (SYMBOL... | --all)\n");
        return 2;
    }
    Obj t, o;
    if (!t.load(argv[1])) { fprintf(stderr, "fnscore: cannot read %s\n", argv[1]); return 2; }
    if (!o.load(argv[2])) { fprintf(stderr, "fnscore: cannot read %s\n", argv[2]); return 2; }
    std::vector<std::string> names;
    if (std::string(argv[3]) == "--all") {
        for (auto &s : t.syms)
            if ((s.info & 15) == 2 && s.size && s.shndx) names.push_back(s.name);
    } else {
        for (int i = 3; i < argc; i++) names.push_back(argv[i]);
    }
    for (auto &n : names) {
        Func a = t.func(n), b = o.func(n);
        if (!a.found || !b.found) {
            printf("%s\t-1\t%zu\t%zu\n", n.c_str(), a.code.size(), b.code.size());
            continue;
        }
        printf("%s\t%ld\t%zu\t%zu\n", n.c_str(), score(a, b), a.code.size(), b.code.size());
    }
    return 0;
}
