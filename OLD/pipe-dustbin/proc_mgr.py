# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 17:32:00 2020

@author: obs
Purloined from:
https://medium.com/@elijahlopezz/get-all-running-processes-with-python-windows-5c1b2e016b2c
"""

import re
from subprocess import Popen, PIPE, DEVNULL


def get_running_processes(look_for='Music Caster.exe'):
    # edited from https://stackoverflow.com/a/22914414/7732434
    cmd = f'tasklist /NH /FI "IMAGENAME eq {look_for}"'
    p = Popen(cmd, shell=True, stdout=PIPE, stdin=DEVNULL, stderr=DEVNULL, text=True)
    task = p.stdout.readline()
    while task != '':
        task = p.stdout.readline().strip()
        m = re.match(r'(.+?) +(\d+) (.+?) +(\d+) +(\d+.* K).*', task)
        if m is not None:
            process = {'name': m.group(1), 'pid': m.group(2), 'session_name': m.group(3),
                       'session_num': m.group(4), 'mem_usage': m.group(5)}
            yield process
            

def is_already_running(program_name, threshold=1):
    for process in get_running_processes(program_name):
        process_name = process['name']
        if process_name == program_name:
            threshold -= 1
            if threshold < 0: return True
    return False