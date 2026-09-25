#include <stddef.h>
#include <stdio.h>
#include <linux/input.h>
#include <linux/uinput.h>
int main(void) {
    printf("input_event=%zu type-offset=%zu value-offset=%zu long=%zu time_t=%zu uinput_user_dev=%zu\n",
           sizeof(struct input_event), offsetof(struct input_event, type),
           offsetof(struct input_event, value), sizeof(long), sizeof(time_t), sizeof(struct uinput_user_dev));
    return 0;
}
