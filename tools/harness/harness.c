// Headless mGBA runner: plays an input script and dumps screenshots / save states.
// Script lines:  run <frames> [keys]   shot <file.ppm>   save <file>   load <file>
// keys: any of A B s(select) S(start) R L U D r(right) l(left), or '-' for none.
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/core/log.h>
#include <stdarg.h>
#include <mgba/debugger/debugger.h>
#include <mgba/internal/arm/arm.h>

static struct mDebugger* dbg;
static int hits;
static void on_enter(struct mDebugger* d, enum mDebuggerEntryReason r, struct mDebuggerEntryInfo* info) {
    struct ARMCore* cpu = d->core->cpu;
    if (r == DEBUGGER_ENTER_BREAKPOINT) {
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
    FILE* sf = fopen(argv[2], "r");
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
        } else if (!strcmp(cmd, "save")) {
            size_t sz = core->stateSize(core); void* st = malloc(sz);
            core->saveState(core, st); FILE* o = fopen(a, "wb"); fwrite(st, 1, sz, o); fclose(o); free(st);
        } else if (!strcmp(cmd, "load")) {
            size_t sz = core->stateSize(core); void* st = malloc(sz);
            FILE* i = fopen(a, "rb"); fread(st, 1, sz, i); fclose(i); core->loadState(core, st); free(st);
        }
    }
    core->deinit(core);
    return 0;
}
