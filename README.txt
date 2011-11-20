gdbsearch - search code for preset measurable effects

gdbsearch generates HTML that highlights the code lines that have had
measurable effects. gdbsearch follows the lines down to libraries to
find out what exactly made the change.

gdbsearch makes measurements before and after executing each line of
code. First this is done for the main function. For each piece of code
that had an effect, gdbsearch automatically reruns the software and
makes deeper analysis recursively.

gdbsearch can measure, for instance, I/O and memory consumption of the
debugged program. However, gdbsearch can be easily modified to measure
any property in the system, such as bytes sent through a network
interface or a number of times the D-Bus daemon has been scheduled,
etc.
