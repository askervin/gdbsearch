Build "badcat":

qmake
make

Measure and search where io writes take place:

gdbsearch -o results 'gdb --args ./badcat badcat.cpp' io_wchar

You can start viewing the results before this finishes:

firefox results/gdbsearch.html

If you want to trace writing into the QtCore library,

1. download Qt sources (apt-get source libqt4-core)
2. add path to src/corelib to ~/.gdbinit, for instance:
echo 'dir /home/whoami/src/qt4-x11-4.7.3/src/corelib' >> ~/.gdbinit
