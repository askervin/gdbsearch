#include <QFile>
#include <iostream>

#include "baddog.h"

void printFile(QFile &f)
{
    std::cout << f.readAll().data() << std::flush;
}

void printFileTwice(QFile &f)
{
    f.open(QIODevice::ReadOnly);
    std::cout << f.readAll().data();
    f.close();
    f.open(QIODevice::ReadOnly);
    std::cout << f.readAll().data();
    std::cout << std::flush;
    f.close();
}

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++)
    {
        QFile f(argv[i]);
        f.open(QIODevice::ReadOnly);
        printFile(f);
        f.close();
        printFileTwice(f);
    }
    eatmemory();
}
