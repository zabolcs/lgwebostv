#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define BROKER_NAME "LG Remote Broker"
#define BROKER_VERSION "4-evdev-relay"
#define LOCK_FILE "/tmp/hu.szabi.remote-broker.lock"
#define ACTION_ROOT "/var/lib/webosbrew/remote-broker/actions"
#define RELOAD_ACK "/tmp/hu.szabi.remote-broker.reload"
#define KEY_STATE_PREFIX "/tmp/hu.szabi.remote-broker.key-"
#define MAX_SOURCES 16
#define MAX_PREFIXES 8
#define PREFIX_LENGTH 96
#define PATH_LENGTH 256
#define BROKER_KEY_MAX 2047U
#define BITS_PER_LONG (sizeof(unsigned long) * 8U)
#define LONGS_FOR(x) (((x) + BITS_PER_LONG) / BITS_PER_LONG)

enum binding_kind { BIND_ORIGINAL = 0, BIND_IGNORE, BIND_REPLACE, BIND_ACTION, BIND_LONG_ACTION };

struct binding {
    enum binding_kind kind;
    unsigned short target;
};

struct config {
    bool grab;
    char output[PREFIX_LENGTH];
    char prefixes[MAX_PREFIXES][PREFIX_LENGTH];
    size_t prefix_count;
    struct binding bindings[BROKER_KEY_MAX + 1];
};

struct source {
    int fd;
    int ufd;
    bool grabbed;
    char path[PATH_LENGTH];
    char name[256];
};

static volatile sig_atomic_t stopping = 0;
static volatile sig_atomic_t reload_requested = 0;
/* Freeze the routing decision from down until up, including across reloads. */
static bool held[BROKER_KEY_MAX + 1];
static int routed[BROKER_KEY_MAX + 1]; /* -1 = consumed, otherwise output code */
static unsigned short output_refs[BROKER_KEY_MAX + 1];
static uint64_t last_action_ms[BROKER_KEY_MAX + 1];
static bool long_action_armed[BROKER_KEY_MAX + 1];
static bool long_action_fired[BROKER_KEY_MAX + 1];
static struct input_event long_action_down[BROKER_KEY_MAX + 1];

static void on_signal(int sig) {
    (void)sig;
    stopping = 1;
}

static void on_reload(int sig) {
    (void)sig;
    reload_requested = 1;
}

static uint64_t monotonic_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)ts.tv_nsec / 1000000ULL;
}

static int write_number_file(const char *path, long value) {
    char text[64];
    char temporary[PATH_LENGTH + 32];
    if (snprintf(temporary, sizeof(temporary), "%s.%ld.new", path, (long)getpid()) >= (int)sizeof(temporary)) return -1;
    int length = snprintf(text, sizeof(text), "%ld\n", value);
    int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return -1;
    ssize_t written = write(fd, text, (size_t)length);
    int saved = errno;
    close(fd);
    errno = saved;
    if (written == length && rename(temporary, path) == 0) return 0;
    unlink(temporary);
    return -1;
}

static int write_key_state(unsigned int code, int value) {
    char path[PATH_LENGTH];
    char temporary[PATH_LENGTH + 32];
    char text[64];
    if (snprintf(path, sizeof(path), KEY_STATE_PREFIX "%u.state", code) >= (int)sizeof(path)) return -1;
    if (snprintf(temporary, sizeof(temporary), "%s.%ld.new", path, (long)getpid()) >= (int)sizeof(temporary)) return -1;
    int length = snprintf(text, sizeof(text), "%u => %d\n", code, value);
    int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return -1;
    ssize_t written = write(fd, text, (size_t)length);
    int saved = errno;
    close(fd);
    errno = saved;
    if (written == length && rename(temporary, path) == 0) return 0;
    unlink(temporary);
    return -1;
}

static char *trim(char *text) {
    while (*text == ' ' || *text == '\t') text++;
    size_t n = strlen(text);
    while (n && (text[n - 1] == ' ' || text[n - 1] == '\t' || text[n - 1] == '\r' || text[n - 1] == '\n')) {
        text[--n] = '\0';
    }
    return text;
}

static int parse_code(const char *text, unsigned int *code) {
    char *end = NULL;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    if (errno || end == text || *end != '\0' || value > BROKER_KEY_MAX) return -1;
    *code = (unsigned int)value;
    return 0;
}

static int load_config(const char *path, struct config *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        perror("open config");
        return -1;
    }
    struct stat st;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != 0 || (st.st_mode & 0022) != 0) {
        fprintf(stderr, "config must be a root-owned regular file not writable by group/other\n");
        close(fd);
        return -1;
    }
    FILE *stream = fdopen(fd, "r");
    if (!stream) {
        perror("fdopen config");
        close(fd);
        return -1;
    }
    char line[512];
    unsigned int line_number = 0;
    bool version_seen = false;
    bool mode_seen = false;
    while (fgets(line, sizeof(line), stream)) {
        line_number++;
        if (!strchr(line, '\n') && !feof(stream)) {
            fprintf(stderr, "config line %u is too long\n", line_number);
            fclose(stream);
            return -1;
        }
        char *entry = trim(line);
        if (!*entry || *entry == '#') continue;
        char *equals = strchr(entry, '=');
        if (!equals) {
            fprintf(stderr, "config line %u has no '='\n", line_number);
            fclose(stream);
            return -1;
        }
        *equals = '\0';
        char *key = trim(entry);
        char *value = trim(equals + 1);
        if (!strcmp(key, "version")) {
            if (strcmp(value, "2") != 0 || version_seen) goto invalid;
            version_seen = true;
        } else if (!strcmp(key, "mode")) {
            if (mode_seen || (strcmp(value, "passive") && strcmp(value, "grab"))) goto invalid;
            cfg->grab = strcmp(value, "grab") == 0;
            mode_seen = true;
        } else if (!strcmp(key, "output")) {
            if (!*value || strlen(value) >= sizeof(cfg->output) || cfg->output[0]) goto invalid;
            strcpy(cfg->output, value);
        } else if (!strcmp(key, "device")) {
            size_t length = strlen(value);
            if (!length || length >= PREFIX_LENGTH || cfg->prefix_count >= MAX_PREFIXES) goto invalid;
            strcpy(cfg->prefixes[cfg->prefix_count++], value);
        } else {
            unsigned int code = 0;
            if (parse_code(key, &code) != 0 || cfg->bindings[code].kind != BIND_ORIGINAL) goto invalid;
            if (!strcmp(value, "ignore")) {
                cfg->bindings[code].kind = BIND_IGNORE;
            } else if (!strcmp(value, "action")) {
                cfg->bindings[code].kind = BIND_ACTION;
            } else if (!strncmp(value, "replace:", 8)) {
                unsigned int target = 0;
                if (parse_code(value + 8, &target) != 0) goto invalid;
                cfg->bindings[code].kind = BIND_REPLACE;
                cfg->bindings[code].target = (unsigned short)target;
            } else if (!strcmp(value, "long-action")) {
                cfg->bindings[code].kind = BIND_LONG_ACTION;
            } else {
                goto invalid;
            }
        }
        continue;
invalid:
        fprintf(stderr, "invalid config entry on line %u\n", line_number);
        fclose(stream);
        return -1;
    }
    if (ferror(stream)) {
        perror("read config");
        fclose(stream);
        return -1;
    }
    fclose(stream);
    if (!version_seen || !mode_seen || cfg->prefix_count != 1 ||
        strcmp(cfg->prefixes[0], "LGE M-RCU - Builtin [0]") ||
        strcmp(cfg->output, "LGE M-RCU - Builtin [2]")) {
        fprintf(stderr, "relay requires version=2 and distinct exact Builtin [0] source / Builtin [2] output\n");
        return -1;
    }
    return 0;
}

static bool name_matches(const struct config *cfg, const char *name) {
    if (!strcmp(name, BROKER_NAME)) return false;
    for (size_t i = 0; i < cfg->prefix_count; i++) {
        if (!strcmp(name, cfg->prefixes[i])) return true;
    }
    return false;
}

static bool same_sources(const struct config *left, const struct config *right) {
    if (left->grab != right->grab || left->prefix_count != right->prefix_count || strcmp(left->output, right->output)) return false;
    for (size_t i = 0; i < left->prefix_count; i++) {
        if (strcmp(left->prefixes[i], right->prefixes[i]) != 0) return false;
    }
    return true;
}

static int open_sources(const struct config *cfg, struct source *sources, size_t *count) {
    *count = 0;
    for (unsigned int index = 0; index < 64 && *count < MAX_SOURCES; index++) {
        char path[PATH_LENGTH];
        snprintf(path, sizeof(path), "/dev/input/event%u", index);
        int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        char name[256] = {0};
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0 || !name_matches(cfg, name)) {
            close(fd);
            continue;
        }
        sources[*count].fd = fd;
        sources[*count].ufd = -1;
        sources[*count].grabbed = false;
        snprintf(sources[*count].path, sizeof(sources[*count].path), "%s", path);
        snprintf(sources[*count].name, sizeof(sources[*count].name), "%s", name);
        fprintf(stderr, "source %s: %s\n", path, name);
        (*count)++;
    }
    if (*count != 1) {
        fprintf(stderr, "need exactly one matching source; refusing missing/ambiguous device\n");
        for (size_t i = 0; i < *count; i++) close(sources[i].fd);
        *count = 0;
        return -1;
    }
    return 0;
}

static bool bit_is_set(const unsigned long *bits, unsigned int bit) {
    return (bits[bit / BITS_PER_LONG] & (1UL << (bit % BITS_PER_LONG))) != 0;
}

static bool bindings_fit_output(const struct config *cfg, int output) {
    unsigned long bits[LONGS_FOR(BROKER_KEY_MAX + 1)] = {0};
    if (ioctl(output, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) < 0) return false;
    for (unsigned int code = 0; code <= BROKER_KEY_MAX; code++) {
        if (cfg->bindings[code].kind == BIND_REPLACE && !bit_is_set(bits, cfg->bindings[code].target)) return false;
    }
    return true;
}

/* Reuse a factory evdev sink already read by surface-manager. No uinput
 * creation/destruction, and never write back into the grabbed source. */
static int open_output(const struct config *cfg, const struct source *source, bool require_idle) {
    int output = -1;
    for (unsigned int index = 0; index < 64; index++) {
        char path[PATH_LENGTH], name[256] = {0};
        snprintf(path, sizeof(path), "/dev/input/event%u", index);
        int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0 || strcmp(name, cfg->output)) {
            close(fd);
            continue;
        }
        struct stat a, b;
        if (output >= 0 || fstat(fd, &a) || fstat(source->fd, &b) || a.st_rdev == b.st_rdev) {
            close(fd);
            if (output >= 0) close(output);
            fprintf(stderr, "ambiguous or same-device output; refusing grab\n");
            return -1;
        }
        output = fd;
        fprintf(stderr, "factory relay output %s: %s\n", path, name);
    }
    if (output < 0) return -1;
    const unsigned int types[] = {EV_KEY, EV_REL, EV_ABS, EV_MSC};
    for (size_t t = 0; t < sizeof(types) / sizeof(types[0]); t++) {
        unsigned long src[LONGS_FOR(BROKER_KEY_MAX + 1)] = {0};
        unsigned long dst[LONGS_FOR(BROKER_KEY_MAX + 1)] = {0};
        if (ioctl(source->fd, EVIOCGBIT(types[t], sizeof(src)), src) < 0 ||
            ioctl(output, EVIOCGBIT(types[t], sizeof(dst)), dst) < 0) goto fail;
        for (size_t i = 0; i < sizeof(src) / sizeof(src[0]); i++) {
            if (src[i] & ~dst[i]) goto fail;
        }
        if (types[t] == EV_KEY) {
            for (unsigned int code = 0; code <= BROKER_KEY_MAX; code++) {
                if (cfg->bindings[code].kind == BIND_REPLACE &&
                    !bit_is_set(dst, cfg->bindings[code].target)) goto fail;
            }
        }
    }
    /* Do not intercept a half-press or share an already-held output key. */
    unsigned long state[LONGS_FOR(BROKER_KEY_MAX + 1)] = {0};
    for (int i = 0; require_idle && i < 2; i++) {
        memset(state, 0, sizeof(state));
        if (ioctl(i ? output : source->fd, EVIOCGKEY(sizeof(state)), state) < 0) goto fail;
        for (size_t b = 0; b < sizeof(state) / sizeof(state[0]); b++) if (state[b]) goto fail;
    }
    return output;
fail:
    fprintf(stderr, "incompatible/busy factory output; refusing grab\n");
    close(output);
    return -1;
}

static bool safe_action_file(unsigned int code, char *path, size_t path_size) {
    snprintf(path, path_size, ACTION_ROOT "/%u", code);
    struct stat st;
    if (lstat(path, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != 0 || (st.st_mode & 0022) != 0 || (st.st_mode & S_IXUSR) == 0) {
        fprintf(stderr, "unsafe or missing action script for key %u; passing original key\n", code);
        return false;
    }
    return true;
}

static bool spawn_action(unsigned int code, const char *path) {
    uint64_t now = monotonic_ms();
    if (now && last_action_ms[code] && now - last_action_ms[code] < 250) return true;
    last_action_ms[code] = now;
    pid_t child = fork();
    if (child == 0) {
        clearenv();
        setenv("PATH", "/usr/bin:/bin", 1);
        execl(path, path, (char *)NULL);
        _exit(127);
    }
    if (child < 0) {
        perror("fork action");
        return false;
    }
    fprintf(stderr, "action key=%u pid=%ld\n", code, (long)child);
    return true;
}

static int forward_event(int ufd, const struct input_event *event) {
    ssize_t written;
    do {
        written = write(ufd, event, sizeof(*event));
    } while (written < 0 && errno == EINTR);
    if (written != (ssize_t)sizeof(*event)) {
        perror("write factory evdev output");
        return -1;
    }
    return 0;
}

static int forward_syn_report(int ufd, const struct input_event *basis) {
    struct input_event sync = *basis;
    sync.type = EV_SYN;
    sync.code = SYN_REPORT;
    sync.value = 0;
    return forward_event(ufd, &sync);
}

static int process_event(const struct config *cfg, int ufd, struct input_event event) {
    if (event.type == EV_SYN && event.code == SYN_DROPPED) {
        fprintf(stderr, "input queue overflow; releasing grab instead of using incomplete key state\n");
        return -1;
    }
    if (event.type != EV_KEY || event.code > BROKER_KEY_MAX) return forward_event(ufd, &event);
    unsigned int code = event.code;
    if (event.value < 0 || event.value > 2) return -1;
    /* Publish each physical key phase before starting its action.  The Home
     * action uses this root-owned per-key state to distinguish release from
     * the kernel's long-press repeat without delaying the broker itself. */
    if (write_key_state(code, event.value) != 0) {
        fprintf(stderr, "cannot publish key state for %u\n", code);
    }
    if (!held[code]) {
        if (event.value != 1) return 0; /* orphan up/repeat after startup */
        struct binding binding = cfg->bindings[code];
        int target = (int)code;
        if (binding.kind == BIND_IGNORE) target = -1;
        else if (binding.kind == BIND_REPLACE) target = binding.target;
        else if (binding.kind == BIND_ACTION) {
            char path[PATH_LENGTH];
            if (safe_action_file(code, path, sizeof(path)) && spawn_action(code, path)) target = -1;
        } else if (binding.kind == BIND_LONG_ACTION) {
            /* Buffer the initial down until release/repeat decides the gesture.
             * Short press is replayed as a normal down/up pair.  Long press is
             * consumed entirely, so the factory shell never sees a held Back. */
            long_action_armed[code] = true;
            long_action_fired[code] = false;
            long_action_down[code] = event;
        }
        held[code] = true;
        routed[code] = target;
        if (binding.kind == BIND_LONG_ACTION) return 0;
        if (target < 0) return 0;
        if (output_refs[target]++ != 0) return 0; /* two keys mapped to same output */
        event.code = (unsigned short)target;
        return forward_event(ufd, &event);
    }
    int target = routed[code];
    if (long_action_armed[code]) {
        if (event.value == 2) {
            if (!long_action_fired[code]) {
                char path[PATH_LENGTH];
                if (safe_action_file(code, path, sizeof(path)) && spawn_action(code, path)) {
                    long_action_fired[code] = true;
                } else {
                    /* Fail open from the first repeat: replay the delayed down
                     * and then resume the original repeat/up stream. */
                    long_action_armed[code] = false;
                    struct input_event down = long_action_down[code];
                    down.code = (unsigned short)target;
                    if (output_refs[target]++ == 0) {
                        if (forward_event(ufd, &down) != 0 || forward_syn_report(ufd, &down) != 0) return -1;
                    }
                }
            }
            if (long_action_fired[code]) return 0;
        } else if (event.value == 0) {
            held[code] = false;
            long_action_armed[code] = false;
            if (long_action_fired[code]) {
                long_action_fired[code] = false;
                return 0;
            }
            /* No repeat arrived: this was a short Back.  Emit a compact normal
             * press now, with a SYN boundary between down and up. */
            struct input_event down = long_action_down[code];
            down.code = (unsigned short)target;
            if (output_refs[target]++ == 0) {
                if (forward_event(ufd, &down) != 0 || forward_syn_report(ufd, &down) != 0) return -1;
            }
            if (--output_refs[target] != 0) return 0;
            event.code = (unsigned short)target;
            return forward_event(ufd, &event);
        } else {
            return 0;
        }
    }
    if (event.value == 0) {
        held[code] = false;
        long_action_armed[code] = false;
        long_action_fired[code] = false;
        if (target < 0 || --output_refs[target] != 0) return 0;
    } else if (target < 0 || event.value == 1) {
        return 0;
    }
    event.code = (unsigned short)target;
    return forward_event(ufd, &event);
}

static int release_forwarded_keys(int output) {
    int result = 0;
    struct input_event event;
    memset(&event, 0, sizeof(event));
    event.type = EV_KEY;
    for (unsigned int code = 0; code <= BROKER_KEY_MAX; code++) {
        if (!output_refs[code]) continue;
        event.code = (unsigned short)code;
        if (forward_event(output, &event) != 0) result = -1;
        output_refs[code] = 0;
    }
    event.type = EV_SYN;
    event.code = SYN_REPORT;
    if (forward_event(output, &event) != 0) result = -1;
    memset(held, 0, sizeof(held));
    memset(long_action_armed, 0, sizeof(long_action_armed));
    memset(long_action_fired, 0, sizeof(long_action_fired));
    memset(long_action_down, 0, sizeof(long_action_down));
    return result;
}

static void close_sources(struct source *sources, size_t count) {
    for (size_t i = 0; i < count; i++) {
        if (sources[i].ufd >= 0) release_forwarded_keys(sources[i].ufd);
        if (sources[i].grabbed) ioctl(sources[i].fd, EVIOCGRAB, 0);
        if (sources[i].fd >= 0) close(sources[i].fd);
        if (sources[i].ufd >= 0) close(sources[i].ufd);
        sources[i].fd = sources[i].ufd = -1;
        sources[i].grabbed = false;
    }
}

static int recover_output(const struct config *cfg) {
    struct source sources[MAX_SOURCES];
    size_t count = 0;
    if (open_sources(cfg, sources, &count) != 0) return 2;
    int output = open_output(cfg, &sources[0], false);
    close(sources[0].fd);
    if (output < 0) return 2;
    unsigned long state[LONGS_FOR(BROKER_KEY_MAX + 1)] = {0};
    if (ioctl(output, EVIOCGKEY(sizeof(state)), state) < 0) { close(output); return 2; }
    for (unsigned int code = 0; code <= BROKER_KEY_MAX; code++) output_refs[code] = bit_is_set(state, code) ? 1 : 0;
    int result = release_forwarded_keys(output);
    close(output);
    return result == 0 ? 0 : 2;
}

static int check_devices(const struct config *cfg) {
    struct source sources[MAX_SOURCES];
    size_t count = 0;
    if (open_sources(cfg, sources, &count) != 0) return 2;
    int output = open_output(cfg, &sources[0], true);
    close(sources[0].fd);
    if (output < 0) return 2;
    close(output); /* No grabs, event writes, or virtual devices. */
    puts("factory relay devices compatible and idle; no input intercepted");
    return 0;
}

static int run_broker(struct config *cfg, const char *config_path, const char *heartbeat, const char *pid_file, unsigned int run_seconds) {
    struct source sources[MAX_SOURCES];
    struct pollfd polls[MAX_SOURCES];
    size_t count = 0;
    memset(sources, 0, sizeof(sources));
    if (open_sources(cfg, sources, &count) != 0) return 2;
    if (cfg->grab) {
        for (size_t i = 0; i < count; i++) {
            sources[i].ufd = open_output(cfg, &sources[i], true);
            if (sources[i].ufd < 0) goto fail;
        }
        for (size_t i = 0; i < count; i++) {
            if (ioctl(sources[i].fd, EVIOCGRAB, 1) < 0) {
                perror("EVIOCGRAB");
                goto fail;
            }
            sources[i].grabbed = true;
        }
        fprintf(stderr, "grab mode active; forwarding to existing factory evdev output (no clones)\n");
    } else {
        fprintf(stderr, "passive mode active; no device is grabbed\n");
    }
    for (size_t i = 0; i < count; i++) {
        polls[i].fd = sources[i].fd;
        polls[i].events = POLLIN;
        polls[i].revents = 0;
    }
    if (write_number_file(pid_file, (long)getpid()) != 0) goto fail;
    uint64_t last_heartbeat = 0;
    uint64_t deadline = run_seconds ? monotonic_ms() + (uint64_t)run_seconds * 1000 : 0;
    int result = 0;
    while (!stopping) {
        if (deadline && monotonic_ms() >= deadline) break;
        if (reload_requested) {
            struct config replacement;
            reload_requested = 0;
            if (load_config(config_path, &replacement) != 0) {
                fprintf(stderr, "configuration reload rejected; keeping previous bindings\n");
            } else if (!same_sources(cfg, &replacement)) {
                fprintf(stderr, "configuration reload rejected; mode and input sources cannot change live\n");
            } else if (cfg->grab && !bindings_fit_output(&replacement, sources[0].ufd)) {
                fprintf(stderr, "configuration reload rejected; output does not support a replacement key\n");
            } else {
                *cfg = replacement;
                if (write_number_file(RELOAD_ACK, (long)getpid()) != 0) {
                    perror("write reload acknowledgement");
                }
                fprintf(stderr, "configuration reloaded; held-key routes preserved\n");
            }
        }
        uint64_t now = monotonic_ms() / 1000;
        if (now != last_heartbeat) {
            if (write_number_file(heartbeat, (long)now) != 0) {
                perror("write heartbeat");
                result = 3;
                break;
            }
            last_heartbeat = now;
        }
        int ready = poll(polls, count, 500);
        if (ready < 0) {
            if (errno == EINTR) continue;
            perror("poll");
            result = 3;
            break;
        }
        if (ready == 0) continue;
        for (size_t i = 0; i < count; i++) {
            if (polls[i].revents & (POLLERR | POLLHUP | POLLNVAL)) {
                fprintf(stderr, "input source disappeared: %s\n", sources[i].path);
                result = 3;
                stopping = 1;
                break;
            }
            if (!(polls[i].revents & POLLIN)) continue;
            struct input_event events[32];
            ssize_t bytes = read(sources[i].fd, events, sizeof(events));
            if (bytes < 0 && (errno == EAGAIN || errno == EINTR)) continue;
            if (bytes <= 0 || bytes % (ssize_t)sizeof(events[0]) != 0) {
                fprintf(stderr, "invalid read from %s\n", sources[i].path);
                result = 3;
                stopping = 1;
                break;
            }
            size_t event_count = (size_t)bytes / sizeof(events[0]);
            for (size_t e = 0; e < event_count; e++) {
                if (!cfg->grab) {
                    if (events[e].type == EV_KEY) fprintf(stderr, "key code=%u value=%d source=%s\n", events[e].code, events[e].value, sources[i].name);
                } else if (process_event(cfg, sources[i].ufd, events[e]) != 0) {
                    result = 3;
                    stopping = 1;
                    break;
                }
            }
        }
    }
    close_sources(sources, count);
    unlink(pid_file);
    unlink(heartbeat);
    unlink(RELOAD_ACK);
    return result;
fail:
    close_sources(sources, count);
    unlink(pid_file);
    unlink(heartbeat);
    unlink(RELOAD_ACK);
    return 2;
}

static void usage(const char *program) {
    fprintf(stderr, "usage: %s --config PATH [--heartbeat PATH --pid-file PATH] [--check-config | --recover-output] [--run-seconds N]\n", program);
}

int main(int argc, char **argv) {
    const char *config_path = NULL;
    const char *heartbeat = NULL;
    const char *pid_file = NULL;
    bool check_only = false;
    bool recovery_only = false;
    bool devices_only = false;
    unsigned int run_seconds = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--config") && i + 1 < argc) config_path = argv[++i];
        else if (!strcmp(argv[i], "--heartbeat") && i + 1 < argc) heartbeat = argv[++i];
        else if (!strcmp(argv[i], "--pid-file") && i + 1 < argc) pid_file = argv[++i];
        else if (!strcmp(argv[i], "--check-config")) check_only = true;
        else if (!strcmp(argv[i], "--recover-output")) recovery_only = true;
        else if (!strcmp(argv[i], "--check-devices")) devices_only = true;
        else if (!strcmp(argv[i], "--run-seconds") && i + 1 < argc) {
            if (parse_code(argv[++i], &run_seconds) != 0 || run_seconds < 1 || run_seconds > 300) return 64;
        }
        else if (!strcmp(argv[i], "--version")) { puts(BROKER_VERSION); return 0; }
        else {
            usage(argv[0]);
            return 64;
        }
    }
    if (!config_path || (!check_only && !recovery_only && !devices_only && (!heartbeat || !pid_file))) {
        usage(argv[0]);
        return 64;
    }
    struct config cfg;
    if (load_config(config_path, &cfg) != 0) return 65;
    if (check_only) {
        printf("configuration valid: mode=%s devices=%zu\n", cfg.grab ? "grab" : "passive", cfg.prefix_count);
        return 0;
    }
    pid_t parent = getppid();
    if (prctl(PR_SET_PDEATHSIG, SIGTERM) != 0 || getppid() != parent) {
        fprintf(stderr, "cannot arm parent-death fail-open protection\n");
        return 70;
    }
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    struct sigaction reload_action;
    memset(&reload_action, 0, sizeof(reload_action));
    reload_action.sa_handler = on_reload;
    sigemptyset(&reload_action.sa_mask);
    sigaction(SIGHUP, &reload_action, NULL);
    signal(SIGPIPE, SIG_IGN);
    signal(SIGCHLD, SIG_IGN);
    umask(077);
    int lock_fd = open(LOCK_FILE, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (lock_fd < 0 || flock(lock_fd, LOCK_EX | LOCK_NB) != 0) {
        fprintf(stderr, "another broker owns the singleton lock\n");
        if (lock_fd >= 0) close(lock_fd);
        return 73;
    }
    int result = devices_only ? check_devices(&cfg) : (recovery_only ? recover_output(&cfg) : run_broker(&cfg, config_path, heartbeat, pid_file, run_seconds));
    close(lock_fd);
    return result;
}
