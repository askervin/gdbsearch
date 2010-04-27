#!/usr/bin/env python

# This script is public domain.
# Author: antti.kervinen@nokia.com

import subprocess
import select
import sys

def print_usage():
    print ''
    print 'Usage: ' + sys.argv[0] + ' gdb_command [measuring_func [paths_to_subroutines]]'
    print ''
    print '    gdb_command must start the debugger with the debugged program'
    print '        Example: "gdb /path/to/myapp"'
    print ''
    print '    measuring_func (optional) specifies the function to be used'
    print '        for evaluating the debugged program state after every step'
    print '        taken by the debugger. Available measuring functions:'
    print '        - ' + '\n        - '.join([f for f in globals().keys()
                                             if f.startswith('measure_')])
    print ''
    print '    paths_to_subroutines is a list of paths where paths are'
    print '        lists of indexes of "step" commands in gdb. If an index'
    print '        is i, gdb will be given i "next" commands before "step".'
    print '        Lists are given in Python format. Examples: '
    print '        "[[]]" debugging is started on only one function: main()'
    print '        "[[2], [0, 1]]" will debug the two functions reached by'
    print '        1) next - next - step, and'
    print '        2) step - next - step in the start of main in gdb.'
    print ''

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

def start_gdb(gdb_command):
    """returns gdb_pipes"""
    gdb = subprocess.Popen(gdb_command, shell=True,
                           stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE)
    answer = read_answer(gdb.stdout)
    if not answer[-1].startswith('(gdb)'):
        error('Did not receive the gdb prompt. Got:\n' + ''.join(answer))
    return gdb

def run_to_start_of_main(gdb):
    gdb.stdin.write('break main\n')
    bp_row, gdb_prompt = read_answer(gdb.stdout, 5)
    if not bp_row.startswith('Breakpoint 1 at'):
        error("Could not set breakpoint to main. Got error:\n" + bp_row)
    gdb.stdin.write('run\n')
    rows = read_answer(gdb.stdout, 6, 8)
    if not len(rows) == 6 or not rows[-1].startswith('(gdb)'):
        error("Could not stop at start of main. Error:\n" + ''.join(rows))

def get_pid_of_debugged_process(gdb):
    gdb.stdin.write('info proc\n')
    rows = read_answer(gdb.stdout, 5)
    if not len(rows) == 5 or not rows[0].startswith('process'):
        error("Could not read process id. Answer started with:\n" + "".join(rows))
    if not rows[-1].startswith('(gdb)'):
        error("gdb prompt not found by get_pid_of_debugged_process. Got:\n" + "".join(rows))
    return rows[0].split()[1]

def get_backtrace(gdb):
    gdb.stdin.write('bt\n')
    rows = read_answer(gdb.stdout)
    if not rows[-1].startswith('(gdb)'):
        error("gdb prompt not found by get_backtrace. Got:\n" + "".join(rows))
    return rows[:-1]

def next_row(gdb):
    gdb.stdin.write('next\n')
    rows = read_answer(gdb.stdout)
    if not rows[-1].startswith('(gdb)'):
        error("gdb prompt not found by next_row. Got:\n" + "".join(rows))

def step_into_subroutine(gdb):
    gdb.stdin.write('step\n')
    rows = read_answer(gdb.stdout)
    if not rows[-1].startswith('(gdb)'):
        error("gdb prompt not found by step_into_subroutine. Got:\n" + "".join(rows))

def quit_gdb(gdb):
    gdb.stdin.write('quit\n')
    gdb.stdin.write('y\n')

# Measuring functions take gdb and pid as parameters and return a
# number describing the current state of the process. Measuring
# function is called after every step of the measured function. If the
# returned valude is greater than it was before the previous step, the
# previous step will be examined in more detail by later debugger
# runs. Prefix the function names with 'measure_'
 
def measure_private_dirty(gdb, pid):
    private_dirty = 0
    for line in file("/proc/%s/smaps" % (pid,)):
        if line.startswith('Private_Dirty:'):
            private_dirty += int(line.split()[1])
    return private_dirty

def measure_private_mem(gdb, pid):
    private = 0
    for line in file("/proc/%s/smaps" % (pid,)):
        if line.startswith('Private_'):
            private += int(line.split()[1])
    return private

def step_and_measure_current_func(gdb, pid, measuring_func):
    bt = get_backtrace(gdb)
    orig_bt_length = len(bt) # if this changes, we are out of the func
    orig_func = bt[0].split(':')[0] # everything before line number
    print "inspecting:", orig_func
    flush()
    data = measuring_func(gdb, pid)
    rows_and_data = [(bt[0].strip(), data)]
    while 1:
        next_row(gdb)
        bt = get_backtrace(gdb)
        if (len(bt) < 1 or
            len(bt) != orig_bt_length or
            not bt[0].startswith(orig_func)):
            # we are out of the func!
            break
        data = measuring_func(gdb, pid)
        rows_and_data.append((bt[0].strip(), data))
    return rows_and_data

def find_need_for_deeper_checks(rows_and_data):
    steps = []
    step = 0
    if len(rows_and_data) == 0: return steps
    previous_value = rows_and_data[0][1]
    for row_and_data in rows_and_data[1:]:
        current_value = row_and_data[1]
        if current_value > previous_value:
            steps.append((step, current_value - previous_value))
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

def report_findings(results, current_path, deeper_steps):
    for dc in deeper_steps:
        print "growth %5s path %s %s" % (dc[1], current_path + [dc[0]], results[dc[0]])
    flush()

def main(argv):
    # 1st parameter: gdb command
    try:
        gdb_command = sys.argv[1]
        if gdb_command.startswith('-'): raise Exception()
    except:
        print_usage()
        error("Gdb command missing.")

    # 2nd parameter: measuring function (optional)
    if len(sys.argv) > 2:
        try:
            measuring_func = eval(sys.argv[2])
            if type(measuring_func) != type(main): raise Exception()
        except:
            print_usage()
            error('Incorrect measuring function')
    else:
        measuring_func = measure_private_mem

    # 3rd parameter: paths to measured subroutines
    if len(sys.argv) > 3:
        try:
            paths_to_interesting_subroutines = eval(sys.argv[3])
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
        
        if not walk_to_func(gdb, current_path):
            print "inspection cancelled: path", current_path, "was not a subroutine."
            flush()
        else:
            results = step_and_measure_current_func(gdb, pid, measure_private_mem)
            deeper_checks = find_need_for_deeper_checks(results)
            report_findings(results, current_path, deeper_checks)
    
            paths_to_interesting_subroutines += [current_path + [dc[0]] for dc in deeper_checks]

        quit_gdb(gdb)
    print "all interesting paths examined"
        
if __name__ == '__main__':
    main(sys.argv)
