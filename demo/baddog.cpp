#include <stdlib.h>

void eatmemory()
{
    const int bytes = 16 * 1024;
    void* p = malloc(bytes);
    memset(p, '\0', bytes);
}
