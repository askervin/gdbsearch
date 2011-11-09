#include <stdlib.h>

void eatmemory()
{
    const int bytes = 1024*1024;
    void* p = malloc(bytes);
    memset(p, '\0', bytes);
    memset(p, 'x', bytes);
}
