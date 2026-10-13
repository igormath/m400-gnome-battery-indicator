/**
 * delux_battery.c - Delux M400 Mouse Battery Query Utility for Linux
 *
 * Designed for high-speed, low-overhead execution (e.g., from GNOME Shell extensions).
 * Pure C / POSIX (Zero external dependencies).
 *
 * Compiles with:
 *   gcc -O2 -Wall -Wextra -o delux-battery delux_battery.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/select.h>
#include <sys/types.h>
#include <sys/stat.h>

#define SYSFS_HIDRAW_DIR "/sys/class/hidraw"
#define TIMEOUT_MS 500

typedef struct {
    char path[320];
    bool is_wireless;
} DeviceInfo;

/*
 * Checks if a hidraw sysfs entry belongs to Delux M400 Interface 0.
 */
static bool inspect_hidraw_node(const char *node_name, DeviceInfo *out_info) {
    char filepath[512];
    char buffer[1024];
    int fd;
    ssize_t bytes_read;

    // 1. Check uevent
    snprintf(filepath, sizeof(filepath), "%s/%s/device/uevent", SYSFS_HIDRAW_DIR, node_name);
    fd = open(filepath, O_RDONLY);
    if (fd < 0) return false;

    bytes_read = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (bytes_read <= 0) return false;
    buffer[bytes_read] = '\0';

    bool is_wireless = (strstr(buffer, "1A2C:00008FFF") != NULL || strstr(buffer, "1A2C:8FFF") != NULL ||
                        strstr(buffer, "1a2c:00008fff") != NULL || strstr(buffer, "1a2c:8fff") != NULL);
    bool is_wired    = (strstr(buffer, "1A2C:00009046") != NULL || strstr(buffer, "1A2C:9046") != NULL ||
                        strstr(buffer, "1a2c:00009046") != NULL || strstr(buffer, "1a2c:9046") != NULL);

    if (!is_wireless && !is_wired) {
        return false;
    }

    // 2. Identify Interface 0
    // Check report_descriptor: Interface 0 is a vendor collection of 34 bytes starting with 0x06, 0x02, 0xFF
    snprintf(filepath, sizeof(filepath), "%s/%s/device/report_descriptor", SYSFS_HIDRAW_DIR, node_name);
    fd = open(filepath, O_RDONLY);
    if (fd >= 0) {
        unsigned char desc[64];
        ssize_t desc_len = read(fd, desc, sizeof(desc));
        close(fd);

        if (desc_len == 34 && desc[0] == 0x06 && desc[1] == 0x02 && desc[2] == 0xFF) {
            snprintf(out_info->path, sizeof(out_info->path), "/dev/%s", node_name);
            out_info->is_wireless = is_wireless;
            return true;
        }
    }

    // Secondary fallback: check HID_PHYS or link for input0 / :1.0
    if (strstr(buffer, ":1.0") != NULL || strstr(buffer, "input0") != NULL) {
        snprintf(out_info->path, sizeof(out_info->path), "/dev/%s", node_name);
        out_info->is_wireless = is_wireless;
        return true;
    }

    return false;
}

static bool find_device(DeviceInfo *info) {
    DIR *dir = opendir(SYSFS_HIDRAW_DIR);
    if (!dir) return false;

    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (strncmp(entry->d_name, "hidraw", 6) == 0) {
            if (inspect_hidraw_node(entry->d_name, info)) {
                closedir(dir);
                return true;
            }
        }
    }

    closedir(dir);
    return false;
}

int main(int argc, char *argv[]) {
    bool output_text = false;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--text") == 0 || strcmp(argv[i], "-t") == 0) {
            output_text = true;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            printf("Usage: %s [options]\n", argv[0]);
            printf("  --json       (default) Compact JSON output\n");
            printf("  --text, -t   Human-readable text output\n");
            printf("  --help, -h   Show this help\n");
            return 0;
        }
    }

    DeviceInfo dev;
    if (!find_device(&dev)) {
        if (output_text) {
            fprintf(stderr, "Error: Delux M400 mouse not found.\n");
        } else {
            printf("{\"error\":\"not_found\"}\n");
        }
        return 1;
    }

    int fd = open(dev.path, O_RDWR | O_NONBLOCK);
    if (fd < 0) {
        if (output_text) {
            perror("Error opening hidraw device (check permissions)");
        } else {
            printf("{\"error\":\"permission_denied\",\"device\":\"%s\"}\n", dev.path);
        }
        return 2;
    }

    // Construct 64-byte query report
    unsigned char cmd[64] = {0};
    if (dev.is_wireless) {
        // BB AA 99 88 09 FD ...
        cmd[0] = 0xBB;
        cmd[1] = 0xAA;
        cmd[2] = 0x99;
        cmd[3] = 0x88;
        cmd[4] = 0x09;
        cmd[5] = 0xFD;
    } else {
        // Wired: 08 FD ...
        cmd[0] = 0x08;
        cmd[1] = 0xFD;
    }

    ssize_t written = write(fd, cmd, sizeof(cmd));
    if (written < 0) {
        close(fd);
        if (output_text) {
            perror("Error sending command");
        } else {
            printf("{\"error\":\"write_failed\"}\n");
        }
        return 3;
    }

    // Wait for response via select()
    fd_set rfds;
    FD_ZERO(&rfds);
    FD_SET(fd, &rfds);

    struct timeval tv;
    tv.tv_sec = 0;
    tv.tv_usec = TIMEOUT_MS * 1000;

    int sel_ret = select(fd + 1, &rfds, NULL, NULL, &tv);
    if (sel_ret <= 0) {
        close(fd);
        if (output_text) {
            fprintf(stderr, "Error: Timeout waiting for mouse response.\n");
        } else {
            printf("{\"error\":\"timeout\"}\n");
        }
        return 4;
    }

    unsigned char resp[64] = {0};
    ssize_t read_bytes = read(fd, resp, sizeof(resp));
    close(fd);

    if (read_bytes < 7) {
        if (output_text) {
            fprintf(stderr, "Error: Incomplete response from mouse.\n");
        } else {
            printf("{\"error\":\"short_read\"}\n");
        }
        return 5;
    }

    unsigned char *payload = resp;
    // Check if 1-byte report ID was prepended
    if (payload[0] != 0xAA && read_bytes >= 8 && payload[1] == 0xAA) {
        payload++;
    }

    // Validate magic header: AA 55 CC 33
    if (payload[0] != 0xAA || payload[1] != 0x55 || payload[2] != 0xCC || payload[3] != 0x33) {
        if (output_text) {
            fprintf(stderr, "Error: Invalid header in response.\n");
        } else {
            printf("{\"error\":\"invalid_header\"}\n");
        }
        return 6;
    }

    int battery = payload[5];
    int status_code = payload[6];
    bool charging = (status_code == 3);

    if (output_text) {
        printf("Delux M400 (%s) | Battery: %d%% [%s] (%s)\n",
               dev.is_wireless ? "wireless" : "wired",
               battery,
               charging ? "Charging" : "Discharging",
               dev.path);
    } else {
        printf("{\"battery\":%d,\"charging\":%s,\"mode\":\"%s\",\"device\":\"%s\"}\n",
               battery,
               charging ? "true" : "false",
               dev.is_wireless ? "wireless" : "wired",
               dev.path);
    }

    return 0;
}
