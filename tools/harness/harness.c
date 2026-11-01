// Headless mGBA runner: plays an input script and dumps screenshots / save states.
// Script lines:  run <frames> [keys]   shot <file.ppm>   save <file>   load <file>
// keys: any of A B s(select) S(start) R L U D r(right) l(left), or '-' for none.
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/core/log.h>
#include <mgba/core/serialize.h>
#include <mgba-util/vfs.h>
#include <fcntl.h>
#include <stdarg.h>
#include <mgba/debugger/debugger.h>
#include <mgba/internal/arm/arm.h>

static struct mDebugger* dbg;
static int hits, quiet_brk;
static uint32_t until_addr; static int until_hit;
// breakpoint actions: when PC hits addr, set register reg = val (reg 0-15)
static struct { uint32_t addr; int reg; uint32_t val; int skip; } acts[64];
static int nacts;
static void on_enter(struct mDebugger* d, enum mDebuggerEntryReason r, struct mDebuggerEntryInfo* info) {
    struct ARMCore* cpu = d->core->cpu;
    if (r == DEBUGGER_ENTER_BREAKPOINT) {
        int acted = 0;
        if (until_addr && info->address == until_addr) { until_hit = 1; d->state = DEBUGGER_RUNNING; return; }
        for (int i = 0; i < nacts; i++) if (acts[i].addr == info->address) {
            acted = 1;
            if (acts[i].skip > 0) { acts[i].skip--; continue; }
            if (acts[i].skip == 0) { cpu->gprs[acts[i].reg] = acts[i].val; }
            if (acts[i].reg < 0 || acts[i].skip == 0) { }
        }
        for (int i = 0; i < nacts; i++) if (acts[i].addr == info->address && acts[i].skip == 0) acts[i].skip = -1;  // one-shot
        if (acted || quiet_brk) { d->state = DEBUGGER_RUNNING; return; }
        printf("break %08x r0=%08x r1=%08x r2=%08x r3=%08x lr=%08x [r0]=%08x\n", info->address, cpu->gprs[0], cpu->gprs[1], cpu->gprs[2], cpu->gprs[3], cpu->gprs[14],
               d->core->busRead32(d->core, cpu->gprs[0]));
    } else if (hits++ < 40)
        printf("watch %08x written=%08x pc=%08x lr=%08x r0=%08x r1=%08x r2=%08x\n", info->address, info->type.wp.newValue,
               cpu->gprs[15], cpu->gprs[14], cpu->gprs[0], cpu->gprs[1], cpu->gprs[2]);
    d->state = DEBUGGER_RUNNING;
}
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t parse_keys(const char* k) {
    uint32_t m = 0;
    for (; k && *k; k++) switch (*k) {
        case 'A': m |= 1 << 0; break; case 'B': m |= 1 << 1; break;
        case 's': m |= 1 << 2; break; case 'S': m |= 1 << 3; break;
        case 'r': m |= 1 << 4; break; case 'l': m |= 1 << 5; break;
        case 'U': m |= 1 << 6; break; case 'D': m |= 1 << 7; break;
        case 'R': m |= 1 << 8; break; case 'L': m |= 1 << 9; break;
    }
    return m;
}

static void quiet(struct mLogger* l, int c, enum mLogLevel lv, const char* f, va_list a) { (void) l; (void) c; (void) lv; (void) f; (void) a; }
static struct mLogger nolog = { .log = quiet };

int main(int argc, char** argv) {
    if (!getenv("HARNESS_LOG")) mLogSetDefaultLogger(&nolog);
    if (argc < 3) { fprintf(stderr, "usage: %s rom script\n", argv[0]); return 1; }
    struct mCore* core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) { fprintf(stderr, "no core\n"); return 1; }
    mCoreInitConfig(core, NULL);
    unsigned w, h; core->desiredVideoDimensions(core, &w, &h);
    color_t* buf = calloc(w * h, sizeof(color_t));
    core->setVideoBuffer(core, buf, w);
    if (!mCoreLoadFile(core, argv[1])) { fprintf(stderr, "load failed\n"); return 1; }
    core->reset(core);
    FILE* sf = strcmp(argv[2], "-") ? fopen(argv[2], "r") : stdin;   // "-" = interactive (driven by tools/gba.py)
    int interactive = sf == stdin;
    char line[512];
    while (fgets(line, sizeof line, sf)) {
        char cmd[32] = {0}, a[256] = {0}, b[64] = {0};
        if (sscanf(line, "%31s %255s %63s", cmd, a, b) < 1 || cmd[0] == '#') continue;
        if (!strcmp(cmd, "run")) {
            int n = atoi(a); core->setKeys(core, parse_keys(b));
            for (int i = 0; i < n; i++) { if (dbg) mDebuggerRunFrame(dbg); else core->runFrame(core); }
            core->setKeys(core, 0);
        } else if (!strcmp(cmd, "shot")) {
            FILE* o = fopen(a, "wb"); fprintf(o, "P6\n%u %u\n255\n", w, h);
            for (unsigned i = 0; i < w * h; i++) {
                uint32_t c = buf[i];   // mGBA 32-bit color_t is 0xXXBBGGRR
                fputc(c & 0xff, o); fputc((c >> 8) & 0xff, o); fputc((c >> 16) & 0xff, o);
            }
            fclose(o);
        } else if (!strcmp(cmd, "dump")) {          // dump <file> <hexaddr:hexlen>
            unsigned long addr, len; sscanf(b, "%lx:%lx", &addr, &len);
            FILE* o = fopen(a, "wb");
            for (unsigned long i = 0; i < len; i++) fputc(core->busRead8(core, addr + i), o);
            fclose(o);
        } else if (!strcmp(cmd, "brk")) {           // brk <hexaddr>: log registers on execution
            if (!dbg) {
                dbg = calloc(1, sizeof(*dbg)); dbg->type = DEBUGGER_CUSTOM; dbg->entered = on_enter;
                mDebuggerAttach(dbg, core); dbg->state = DEBUGGER_RUNNING;
            }
            struct mBreakpoint bp = { .address = strtoul(a, NULL, 16), .segment = -1, .type = BREAKPOINT_HARDWARE };
            dbg->platform->setBreakpoint(dbg->platform, &bp);
        } else if (!strcmp(cmd, "watch")) {         // watch <hexaddr>: log writes (PC) to that address
            if (!dbg) {
                dbg = calloc(1, sizeof(*dbg)); dbg->type = DEBUGGER_CUSTOM; dbg->entered = on_enter;
                mDebuggerAttach(dbg, core); dbg->state = DEBUGGER_RUNNING;
            }
            struct mWatchpoint wp = { .address = strtoul(a, NULL, 16), .segment = -1, .type = WATCHPOINT_WRITE };
            dbg->platform->setWatchpoint(dbg->platform, &wp);
        } else if (!strcmp(cmd, "poke8") || !strcmp(cmd, "poke16") || !strcmp(cmd, "poke32")) {
            // poke32 <hexaddr> <hexval>: writes RAM/IO, or patches ROM (0x08xxxxxx) in memory
            uint32_t ad = strtoul(a, NULL, 16), v = strtoul(b, NULL, 16);
            if (cmd[4] == '8') core->rawWrite8(core, ad, -1, v);
            else if (cmd[4] == '1') core->rawWrite16(core, ad, -1, v);
            else core->rawWrite32(core, ad, -1, v);
        } else if (!strcmp(cmd, "peek")) {          // peek <hexaddr> <hexlen>: print bytes as hex
            uint32_t ad = strtoul(a, NULL, 16), n = strtoul(b, NULL, 16);
            printf("peek %08x ", ad);
            for (uint32_t i = 0; i < n; i++) printf("%02x", core->rawRead8(core, ad + i, -1));
            printf("\n"); fflush(stdout);
        } else if (!strcmp(cmd, "setreg")) {        // setreg <hexaddr> <reg>=<hexval>: on hitting addr, set register
            if (!dbg) {
                dbg = calloc(1, sizeof(*dbg)); dbg->type = DEBUGGER_CUSTOM; dbg->entered = on_enter;
                mDebuggerAttach(dbg, core); dbg->state = DEBUGGER_RUNNING;
            }
            uint32_t ad = strtoul(a, NULL, 16); int rg; unsigned long v; sscanf(b, "%d=%lx", &rg, &v);
            acts[nacts].addr = ad; acts[nacts].reg = rg; acts[nacts].val = v; nacts++;
            struct mBreakpoint bp = { .address = ad, .segment = -1, .type = BREAKPOINT_HARDWARE };
            dbg->platform->setBreakpoint(dbg->platform, &bp);
        } else if (!strcmp(cmd, "inject")) {        // inject <hexaddr> <skip> <r0hex> <r1hex>: on hit #skip+1 set r0,r1 (once)
            uint32_t ad = strtoul(a, NULL, 16); int sk = 0; unsigned long r0v = 0, r1v = 0;
            sscanf(line, "%*s %*s %d %lx %lx", &sk, &r0v, &r1v);
            if (!dbg) {
                dbg = calloc(1, sizeof(*dbg)); dbg->type = DEBUGGER_CUSTOM; dbg->entered = on_enter;
                mDebuggerAttach(dbg, core); dbg->state = DEBUGGER_RUNNING;
            }
            nacts = 0; quiet_brk = 1;
            acts[nacts].addr = ad; acts[nacts].reg = 0; acts[nacts].val = r0v; acts[nacts].skip = sk; nacts++;
            acts[nacts].addr = ad; acts[nacts].reg = 1; acts[nacts].val = r1v; acts[nacts].skip = sk; nacts++;
            struct mBreakpoint bp = { .address = ad, .segment = -1, .type = BREAKPOINT_HARDWARE };
            dbg->platform->setBreakpoint(dbg->platform, &bp);
        } else if (!strcmp(cmd, "until")) {         // until <hexaddr> <outstate> [maxframes]: tap A every 40 frames until
            // addr is executed, then save the state from the frame *before* the hit and leave the core there
            int mx = 20000; sscanf(line, "%*s %*s %*s %d", &mx);
            if (!dbg) {
                dbg = calloc(1, sizeof(*dbg)); dbg->type = DEBUGGER_CUSTOM; dbg->entered = on_enter;
                mDebuggerAttach(dbg, core); dbg->state = DEBUGGER_RUNNING;
            }
            until_addr = strtoul(a, NULL, 16); until_hit = 0;
            struct mBreakpoint bp = { .address = until_addr, .segment = -1, .type = BREAKPOINT_HARDWARE };
            dbg->platform->setBreakpoint(dbg->platform, &bp);
            size_t sz = core->stateSize(core); void* prev = malloc(sz);
            int f;
            for (f = 0; f < mx && !until_hit; f++) {
                core->saveState(core, prev);
                core->setKeys(core, (f % 40) < 3 ? 1 : 0);
                mDebuggerRunFrame(dbg);
            }
            core->setKeys(core, 0);
            if (until_hit) { core->loadState(core, prev); FILE* o = fopen(b, "wb"); fwrite(prev, 1, sz, o); fclose(o); }
            printf("until %08x %s after %d frames\n", until_addr, until_hit ? "hit" : "TIMEOUT", f); fflush(stdout);
            until_addr = 0; free(prev);
        } else if (!strcmp(cmd, "loadss")) {        // loadss <file>: load a state saved by the mGBA app (.ss0-.ss9 / .ss)
            struct VFile* vf = VFileOpen(a, O_RDONLY);
            int okk = vf && mCoreLoadStateNamed(core, vf, SAVESTATE_SAVEDATA | SAVESTATE_RTC);
            if (vf) vf->close(vf);
            printf("loadss %s\n", okk ? "ok" : "FAILED"); fflush(stdout);
        } else if (!strcmp(cmd, "savess")) {        // savess <file>: write an mGBA-app compatible state
            struct VFile* vf = VFileOpen(a, O_CREAT | O_TRUNC | O_RDWR);
            if (vf) { mCoreSaveStateNamed(core, vf, SAVESTATE_SAVEDATA | SAVESTATE_RTC | SAVESTATE_SCREENSHOT); vf->close(vf); }
        } else if (!strcmp(cmd, "loadsav")) {       // loadsav <file.sav>: battery save (Adventure Logs), then reset
            struct VFile* vf = VFileOpen(a, O_RDONLY);
            if (vf) { core->loadSave(core, vf); core->reset(core); }
            printf("loadsav %s\n", vf ? "ok" : "FAILED"); fflush(stdout);
        } else if (!strcmp(cmd, "echo")) {
            printf("%s %s\n", a, b); fflush(stdout);
        } else if (!strcmp(cmd, "quit")) { break;
        } else if (!strcmp(cmd, "save")) {
            size_t sz = core->stateSize(core); void* st = malloc(sz);
            core->saveState(core, st); FILE* o = fopen(a, "wb"); fwrite(st, 1, sz, o); fclose(o); free(st);
        } else if (!strcmp(cmd, "load")) {
            size_t sz = core->stateSize(core); void* st = malloc(sz);
            FILE* i = fopen(a, "rb"); fread(st, 1, sz, i); fclose(i); core->loadState(core, st); free(st);
        }
        if (interactive) { printf("ok\n"); fflush(stdout); }
    }
    core->deinit(core);
    return 0;
}
