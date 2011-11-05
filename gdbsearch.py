#!/usr/bin/env python

# Author: antti.kervinen@intel.com

"""
Usage: gdbsearch gdb_command [options] [measure [paths_to_subroutines]]

    gdb_command starts debugger with debugged program

    measure (optional) specifies the function to be used
        for evaluating the debugged program state after every step
        taken by the debugger. Available measuring functions:
        - %s

    paths_to_subroutines is a list of paths where paths are
        lists of indexes of "step" commands in gdb. If an index
        is i, gdb will be given i "next" commands before "step".
        Lists are given in Python format. Examples: 
        "[[]]" debugging is started on only one function: main()
        "[[2], [0, 1]]" will debug the two functions reached by
        1) next - next - step, and
        2) step - next - step in the start of main in gdb.

    Options:
        -e <expression>
            track change deeper in the code if the expression
            evaluates to True. Two variables defined for expression:
            n: new measurement, p: previous measurement.
            Default expression: "n > p"

Examples:

    gdbsearch "gdb ./myapp" private_mem
        searches myapp program lines where memory consumption
        (in terms of private memory) increases

    gdbsearch -e "n > p + 100000" "gdb --args ./myapp myarg" io_rchar
        runs "./myapp myarg" and searches program lines which cause
        reading more than 100,000 bytes from any io source.

"""

import subprocess
import select
import getopt
import cgi
import sys
import os

def print_usage():
    l = [s[8:] for s in globals().keys() if s.startswith("measure_")]
    l.sort()
    s = '\n        - '.join(l)
    print __doc__ % (s,)

def error(msg):
    sys.stderr.write('ERROR: ' + msg + '\n')
    sys.exit(1)

def flush():
    sys.stdout.flush()

def read_answer(pipe, maxlines = -1, timeout = 1):
    """maxlines -1 means read until nothing to read until timeout"""
    lines = []
    while 1:
        readable, _, _ = select.select([pipe], [], [], timeout)
        if not readable:
            break
        else:
            if not lines: lines.append("")
            lines[-1] += pipe.read(1)
            if lines[-1][-1] == '\n':
                if len(lines) == maxlines: break
                else: lines.append("")
            if lines[-1] == '(gdb) ': 
                break # got prompt, nothing more is coming
    return lines

def expect_prompt(answer):
    if len(answer) == 0 or not answer[-1].startswith('(gdb)'):
        error('Did not receive the gdb prompt. Got:\n' + ''.join(answer))

def start_gdb(gdb_command):
    """returns gdb_pipes"""
    gdb = subprocess.Popen(gdb_command, shell=True,
                           stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE)
    answer = read_answer(gdb.stdout)
    expect_prompt(answer)
    return gdb

def run_to_start_of_main(gdb):
    gdb.stdin.write('break main\n')
    bp_row, gdb_prompt = read_answer(gdb.stdout, 5)
    if not bp_row.startswith('Breakpoint 1 at'):
        error("Could not set breakpoint to main. Got error:\n" + bp_row)
    gdb.stdin.write('run\n')
    rows = read_answer(gdb.stdout, 6, 8)
    expect_prompt(rows)

def get_pid_of_debugged_process(gdb):
    gdb.stdin.write('info proc\n')
    rows = read_answer(gdb.stdout, 5)
    if not len(rows) == 5 or not rows[0].startswith('process'):
        error("Could not read process id. Answer started with:\n" + "".join(rows))
    expect_prompt(rows)
    return rows[0].split()[1]

def get_backtrace(gdb):
    gdb.stdin.write('bt\n')
    rows = read_answer(gdb.stdout)
    expect_prompt(rows)
    return rows[:-1]

def next_row(gdb):
    gdb.stdin.write('next\n')
    rows = read_answer(gdb.stdout)
    if len(rows) > 1:
        codeline = rows[-2]
    else:
        codeline = ""
    expect_prompt(rows)
    return codeline

def step_into_subroutine(gdb):
    gdb.stdin.write('step\n')
    rows = read_answer(gdb.stdout)
    expect_prompt(rows)

def quit_gdb(gdb):
    gdb.stdin.write('quit\n')
    try:
        gdb.stdin.write('y\n')
    except: pass

# Measuring functions take gdb and pid as parameters and return a
# number describing the current state of the process. Measuring
# function is called after every step of the measured function. If the
# returned valude is greater than it was before the previous step, the
# previous step will be examined in more detail by later debugger
# runs. Prefix the function names with 'measure_'

def _sum_integers(filename, line_prefix, field_index):
    total = 0
    for line in file(filename):
        if line.startswith(line_prefix):
            total += int(line.split()[field_index])
    return total
 
def measure_private_dirty(gdb, pid):
    return _sum_integers("/proc/%s/smaps" % (pid,),
                         "Private_Dirty:", 1)

def measure_private_mem(gdb, pid):
    return _sum_integers("/proc/%s/smaps" % (pid,),
                         "Private_", 1)

def measure_io_rchar(gdb, pid):
    return _sum_integers("/proc/%s/io" % (pid,),
                         "rchar:", 1)

def measure_io_wchar(gdb, pid):
    return _sum_integers("/proc/%s/io" % (pid,),
                         "wchar:", 1)

def measure_fd_count(gdb, pid):
    return len(os.walk("/proc/%s/fd" % (pid,)).next()[2])

def step_and_measure_current_func(gdb, pid, measuring_func):
    bt = get_backtrace(gdb)
    orig_bt_length = len(bt) # if this changes, we are out of the func
    orig_func = bt[0].rsplit(':',1)[0] # everything before line number
    print "debug: inspecting:", orig_func
    flush()
    data = measuring_func(gdb, pid)
    rows_and_data = [(bt[0].strip(), data, "")]
    while 1:
        codeline = next_row(gdb)
        bt = get_backtrace(gdb)
        if (len(bt) < 1 or
            len(bt) != orig_bt_length or
            not bt[0].startswith(orig_func)):
            # we are out of the func!
            break
        data = measuring_func(gdb, pid)
        rows_and_data.append((bt[0].strip(), data, codeline))
    return rows_and_data

def find_need_for_deeper_checks(rows_and_data, track_if_true_function):
    steps = []
    step = 0
    if len(rows_and_data) == 0: return steps
    previous_value = rows_and_data[0][1]
    for row_and_data in rows_and_data[1:]:
        current_value = row_and_data[1]
        if track_if_true_function(current_value, previous_value):
            steps.append((step, current_value, previous_value))
        previous_value = current_value
        step += 1
    return steps

def walk_to_func(gdb, deeper_steps):
    step_index_in_current_func = 0
    my_deeper_steps = [s for s in deeper_steps] # copy
    while my_deeper_steps:
        next_deep_step = my_deeper_steps.pop(0)
        while step_index_in_current_func < next_deep_step:
            next_row(gdb)
            step_index_in_current_func += 1
        # now we are ready to take step into subroutine make sure that
        # we enter one by checking backtrace
        bt_in_current_func = get_backtrace(gdb)
        step_into_subroutine(gdb)
        bt_in_new_func = get_backtrace(gdb)
        if bt_in_new_func[0].startswith(bt_in_current_func[0].split(':')[0]):
            # function didn't really change. we have traced this
            # deeper_steps path to the bottom.
            return False
        step_index_in_current_func = 0
    return True

_all_findings = {}
_depth_fullpath_file_row_values = []
_file_not_found = {}
def add_to_all_findings(filename, rownumber, previous_value, current_value, current_path, step):
    if not filename in _all_findings:
        if filename in _file_not_found: return
        try: file(filename,"r")
        except IOError: 
            _file_not_found[filename]=1
            return
        _all_findings[filename] = []
    _all_findings[filename].append((rownumber, previous_value, current_value, current_path))
    _depth_fullpath_file_row_values.append((len(current_path), current_path + [step], filename, rownumber, previous_value, current_value))

def report_findings(results, current_path, deeper_checks):
    for dc in deeper_checks:
        step, current_value, previous_value = dc
        codeline = results[step][2]
        file_and_row = results[step][0]

        try:
            print "split", file_and_row
            file_and_row = file_and_row.rsplit(" at ", 1)[1]
            filename,rownumber = file_and_row.split(":")
            print "got", filename, rownumber
            add_to_all_findings(filename, int(rownumber), previous_value, current_value, current_path, step)
        except ValueError: pass

        print "%s -> %s %s %s" % (previous_value, current_value,
                               file_and_row, codeline)
    flush()

_html_print_bar_length=25
def print_html(all_findings):
    def steppath2filename(steppath):
        pstr = str(steppath).replace(", [",".").replace(",","-").replace("[","").replace("]","").replace(" ","")
        return "/tmp/gdbsearch%s.html" % (pstr,)
    def html_ascii(f, score, line, hyperref, datavalue):
        scorestr = (score * "#") + ( (_html_print_bar_length-score) * "-")
        linestr = cgi.escape(line).replace(" ", "&nbsp;")
        if hyperref != None: f.write('<a href="%s" title="measured value: %s">' % (hyperref, datavalue))
        f.write('<kbd>%s%s</kbd>' % (scorestr, linestr))
        if hyperref != None: f.write('</a>')
        f.write('<br>\n')
            
    def print_code_html(filename, data):
        try: totalvalue = sum([d[1] for d in data])
        except: import pdb; pdb.set_trace()
        nextline, nextvalue, nextpath = data.pop(0)
        f = file(steppath2filename(nextpath[:-1]), "w")
        f.write('<html><body><kbd>gdbsearch file:%s</kbd><br>\n' % (filename,))
        for lineindex, line in enumerate(file(filename).xreadlines()):
            lineno = lineindex + 1
            if lineno != nextline:
                html_ascii(f, 0, line.rstrip(), None, None)
            else:
                html_ascii(f, nextvalue*_html_print_bar_length/totalvalue, line.rstrip(), steppath2filename(nextpath), nextvalue)
                try: nextline, nextvalue, nextpath = data.pop(0)
                except: nextline = -1
        f.write('</body></html>\n')

    if not _depth_fullpath_file_row_values: return
    _depth_fullpath_file_row_values.sort()
    for d,fp,fn,ln,pv,cv in _depth_fullpath_file_row_values:
        print d,fp,fn,ln,pv,cv

    depth, fullpath, filename, lineno, previous_value, current_value = _depth_fullpath_file_row_values[0]
    current_depth = depth
    current_path = fullpath[:-1]
    current_filename = filename
    print_data = []
    while _depth_fullpath_file_row_values:
        depth, fullpath, filename, lineno, previous_value, current_value = _depth_fullpath_file_row_values.pop(0)
        if fullpath[:-1] != current_path: # current_file handled, moving to next. print gathered data
            if print_data:
                print_code_html(current_filename, print_data)
                print_data = []
            current_depth = depth
            current_path = fullpath[:-1]
            current_filename = filename
        print_data.append( (lineno, current_value - previous_value, fullpath) )
    if print_data: print_code_html(current_filename, print_data)

def main(argv):
    track_if_true = lambda curr, prev: curr > prev

    opts, remainder = getopt.getopt(argv[1:], 'e:', [])
    for opt, arg in opts:
        if opt == '-e':
            try:
                func_source = 'lambda n, p: ' + arg
                track_if_true = eval(func_source)
            except:
                error('Illegal check function "%s".\n"' +
                      'Example: "n > p + 100" is true if new measurement\n' +
                      'was greater than previous by 100')

    # 1st parameter: gdb command
    try:
        gdb_command = remainder[0]
        if gdb_command.startswith('-'): raise Exception()
    except:
        print_usage()
        error("Gdb command missing.")

    # 2nd parameter: measuring function (optional)
    if len(remainder) > 1:
        try:
            measuring_func = eval("measure_" + remainder[1])
            if type(measuring_func) != type(main): raise Exception()
        except:
            print_usage()
            error('Incorrect measure "%s"' % (remainder[1],))
    else:
        measuring_func = measure_private_mem

    # 3rd parameter: paths to measured subroutines
    if len(remainder) > 2:
        try:
            paths_to_interesting_subroutines = eval(remainder[2])
            if type(paths_to_interesting_subroutines) != type([]): raise Exception()
        except:
            error('Invalid paths to subroutines')
    else:    
        # path to main is []: no steps to subroutines
        paths_to_interesting_subroutines = [[]]

    print 'gdb command: %s' % (gdb_command,)
    print 'paths to inspected subroutines: %s' % (paths_to_interesting_subroutines,)
    print 'measuring function: %s' % (measuring_func.__name__,)

    while paths_to_interesting_subroutines:

        current_path = paths_to_interesting_subroutines.pop(0)

        gdb = start_gdb(gdb_command)
        run_to_start_of_main(gdb)
        pid = get_pid_of_debugged_process(gdb)
        
        if walk_to_func(gdb, current_path):
            results = step_and_measure_current_func(gdb, pid, measuring_func)
            deeper_checks = find_need_for_deeper_checks(results, track_if_true)
            report_findings(results, current_path, deeper_checks)

            paths_to_interesting_subroutines += [current_path + [dc[0]] for dc in deeper_checks]

        quit_gdb(gdb)
    
    print "all interesting paths examined"
    print_html(_all_findings)
        
if __name__ == '__main__':
    main(sys.argv)
