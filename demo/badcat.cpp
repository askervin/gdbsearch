#include <QFile>
#include <iostream>

void printFile(QFile &f)
{
    std::cout << f.readAll().data();
}

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++)
    {
        QFile f(argv[i]);
        f.open(QIODevice::ReadOnly);
        printFile(f);
    }
}
