#define _GNU_SOURCE
#ifndef __linux__
#error "This launcher requires Linux memfd_create and /proc"
#endif

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "embedded_pyz.h"

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "Usage: %s PYTHON_ENV_OR_EXECUTABLE [--] [APP_ARGS...]\n", argv[0]);
        return 2;
    }

    struct stat st;
    if (stat(argv[1], &st) == -1) {
        perror("Cannot access Python environment or executable");
        return 1;
    }
    char *python = argv[1];
    char *allocated_python = NULL;
    if (S_ISDIR(st.st_mode)) {
        size_t length = strlen(argv[1]) + sizeof("/bin/python");
        allocated_python = malloc(length);
        if (allocated_python == NULL) {
            perror("malloc");
            return 1;
        }
        snprintf(allocated_python, length, "%s/bin/python", argv[1]);
        python = allocated_python;
    }

    /* No MFD_CLOEXEC: Python and its zip importer need this descriptor after exec. */
    int fd = memfd_create("embedded-python.pyz", 0);
    if (fd == -1) {
        perror("memfd_create");
        free(allocated_python);
        return 1;
    }
    size_t offset = 0;
    while (offset < (size_t)embedded_pyz_len) {
        ssize_t written = write(fd, embedded_pyz + offset,
                                (size_t)embedded_pyz_len - offset);
        if (written < 0 && errno == EINTR)
            continue;
        if (written <= 0) {
            if (written == 0)
                errno = EIO;
            perror("Cannot populate in-memory archive");
            close(fd);
            free(allocated_python);
            return 1;
        }
        offset += (size_t)written;
    }
    if (lseek(fd, 0, SEEK_SET) == -1) {
        perror("lseek");
        close(fd);
        free(allocated_python);
        return 1;
    }

    char archive_path[64];
    snprintf(archive_path, sizeof(archive_path), "/proc/self/fd/%d", fd);
    int first_arg = (argc > 2 && strcmp(argv[2], "--") == 0) ? 3 : 2;
    char **python_argv = calloc((size_t)(argc - first_arg) + 3, sizeof(char *));
    if (python_argv == NULL) {
        perror("calloc");
        close(fd);
        free(allocated_python);
        return 1;
    }
    python_argv[0] = python;
    python_argv[1] = archive_path;
    for (int i = first_arg; i < argc; ++i)
        python_argv[i - first_arg + 2] = argv[i];

    /* Replace the launcher so signals and the Python exit status pass through. */
    execv(python, python_argv);
    perror("Cannot execute Python");
    free(python_argv);
    free(allocated_python);
    close(fd);
    return 1;
}
