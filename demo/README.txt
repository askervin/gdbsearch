Build "badcat":

qmake
make

Measure and search where io writes take place:

gdbsearch -o results 'gdb --args ./badcat badcat.cpp' io_wchar

You can start viewing the results before this finishes:

firefox results/gdbsearch.html
