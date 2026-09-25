/* Hardware-free ARM regression tests. Never call run_broker or open /dev. */
#define main broker_program_main
#include "remote-broker.c"
#undef main
#undef NDEBUG
#include <assert.h>
#include <sys/wait.h>

static int pipe_fds[2];
static struct config cfg;
static unsigned int checks;
static void reset_test(void) {
    memset(&cfg, 0, sizeof(cfg));
    memset(held, 0, sizeof(held));
    memset(output_refs, 0, sizeof(output_refs));
    assert(pipe2(pipe_fds, O_NONBLOCK | O_CLOEXEC) == 0);
}
static void finish_test(void) { close(pipe_fds[0]); close(pipe_fds[1]); checks++; }
static int send_event(unsigned int type, unsigned int code, int value) {
    struct input_event event;
    memset(&event, 0, sizeof(event));
    event.type = type; event.code = code; event.value = value;
    return process_event(&cfg, pipe_fds[1], event);
}
static void expect(unsigned int type, unsigned int code, int value) {
    struct input_event event;
    assert(read(pipe_fds[0], &event, sizeof(event)) == sizeof(event));
    assert(event.type == type && event.code == code && event.value == value);
}
static void empty(void) {
    struct input_event event;
    assert(read(pipe_fds[0], &event, sizeof(event)) == -1 && errno == EAGAIN);
}
int main(void) {
    char key_state_path[] = "/tmp/hu.szabi.remote-broker.key-773.state";
    assert(write_key_state(773, 2) == 0);
    FILE *key_state = fopen(key_state_path, "r");
    char key_state_line[64] = {0};
    assert(key_state && fgets(key_state_line, sizeof(key_state_line), key_state));
    fclose(key_state);
    assert(!strcmp(key_state_line, "773 => 2\n"));
    unlink(key_state_path);
    checks++;

    reset_test();
    for (int value = 1; value <= 2; value++) {
        assert(send_event(EV_KEY, 1198, value) == 0); expect(EV_KEY, 1198, value);
    }
    assert(send_event(EV_KEY, 1198, 0) == 0); expect(EV_KEY, 1198, 0); empty();
    finish_test();

    reset_test();
    cfg.bindings[398].kind = BIND_IGNORE;
    assert(send_event(EV_KEY, 398, 1) == 0);
    cfg.bindings[398].kind = BIND_ORIGINAL; /* reload while held */
    assert(send_event(EV_KEY, 398, 2) == 0);
    assert(send_event(EV_KEY, 398, 0) == 0); empty();
    assert(send_event(EV_KEY, 398, 1) == 0); expect(EV_KEY, 398, 1);
    finish_test();

    reset_test();
    cfg.bindings[398] = (struct binding){BIND_REPLACE, 399};
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 399, 1);
    cfg.bindings[398] = (struct binding){BIND_REPLACE, 400};
    send_event(EV_KEY, 398, 2); expect(EV_KEY, 399, 2);
    send_event(EV_KEY, 398, 0); expect(EV_KEY, 399, 0);
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 400, 1);
    finish_test();

    reset_test();
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 398, 1);
    cfg.bindings[398].kind = BIND_IGNORE;
    send_event(EV_KEY, 398, 0); expect(EV_KEY, 398, 0);
    finish_test();

    reset_test();
    cfg.bindings[398] = (struct binding){BIND_REPLACE, 400};
    cfg.bindings[399] = (struct binding){BIND_REPLACE, 400};
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 400, 1);
    send_event(EV_KEY, 399, 1); empty();
    send_event(EV_KEY, 398, 0); empty();
    send_event(EV_KEY, 399, 0); expect(EV_KEY, 400, 0);
    finish_test();

    reset_test();
    send_event(EV_KEY, 398, 0); send_event(EV_KEY, 398, 2); empty();
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 398, 1);
    send_event(EV_KEY, 398, 1); empty();
    finish_test();

    reset_test();
    cfg.bindings[198].kind = BIND_ACTION; /* no generated script => passthrough */
    send_event(EV_KEY, 198, 1); expect(EV_KEY, 198, 1);
    send_event(EV_KEY, 198, 0); expect(EV_KEY, 198, 0);
    finish_test();

    reset_test();
    send_event(EV_REL, REL_WHEEL, -1); expect(EV_REL, REL_WHEEL, -1);
    send_event(EV_ABS, ABS_X, 123); expect(EV_ABS, ABS_X, 123);
    send_event(EV_SYN, SYN_REPORT, 0); expect(EV_SYN, SYN_REPORT, 0);
    finish_test();

    reset_test();
    assert(send_event(EV_SYN, SYN_DROPPED, 0) == -1); empty();
    assert(send_event(EV_KEY, 398, 99) == -1);
    close(pipe_fds[0]); pipe_fds[0] = -1;
    signal(SIGPIPE, SIG_IGN);
    assert(send_event(EV_KEY, 398, 1) == -1);
    finish_test();

    reset_test();
    send_event(EV_KEY, 398, 1); expect(EV_KEY, 398, 1);
    release_forwarded_keys(pipe_fds[1]);
    expect(EV_KEY, 398, 0); expect(EV_SYN, SYN_REPORT, 0); empty();
    assert(!held[398] && output_refs[398] == 0);
    finish_test();

    char folder[] = "/tmp/codex-relay-unit-XXXXXX";
    assert(mkdtemp(folder));
    char path[256]; snprintf(path, sizeof(path), "%s/heartbeat", folder);
    assert(write_number_file(path, 12345) == 0);
    pid_t reader = fork(); assert(reader >= 0);
    if (!reader) {
        for (unsigned int i = 0; i < 2000; i++) {
            FILE *file = fopen(path, "r"); long value = 0;
            if (!file || fscanf(file, "%ld", &value) != 1 || value != 12345) _exit(1);
            fclose(file);
        }
        _exit(0);
    }
    for (unsigned int i = 0; i < 1000; i++) assert(write_number_file(path, 12345) == 0);
    int status; assert(waitpid(reader, &status, 0) == reader && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    unlink(path); rmdir(folder); checks++;
    printf("PASS: %u native relay regression groups; no input devices opened\n", checks);
    return 0;
}
