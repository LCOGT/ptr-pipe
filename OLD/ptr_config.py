# -*- coding: utf-8 -*-
"""
Created on Fri Aug  2 11:57:41 2019
Updated 20220904 22:42WER

@authors: wrosing, mfitz
"""

import os
import pathlib
import sys
import socket

import glob

# This routine here removes all mention of previous configs from the path...
# for safety and local computer got clogged with all manner of configs in the path

path_removals = []
for q in range(len(sys.path)):
    if "ptr-pipe" in sys.path[q] and "configs" in sys.path[q]:
        print("Removing old config path: " + str(sys.path[q]))
        path_removals.append(sys.path[q])

for remover in path_removals:
    sys.path.remove(remover)

pathdone = 0

# First try to get the pipename from a file in the directory above (..) ptr-observatory
cwd = str(pathlib.Path().resolve())
hwd = cwd.replace("ptr-pipe", "")
pipename_file = glob.glob(hwd + "pipename*")


try:
    #breakpoint()
    site_name = pipename_file[0].split("pipename")[1].split('.')[0]
    # print(
    #     "Adding new config path: "
    #     + str(os.path.join(pathlib.Path().resolve(), "configs", site_name))
    # )
    sys.path.append(os.path.join(pathlib.Path().resolve(), "configs", site_name))
    pathdone = 1
except OSError:
    print(
        "Could not find a pipename* file in the directory above ptr-observatory \
        (e.g. pipenamesro).\n Trying another method..."
    )

if pathdone == 0:
    print("Attempting pipename approach to config file...")

    # NB May be better to split on '-' and use first part of pipename.
    host_site = socket.gethostname()[:3].lower()

    #if host_site == "saf":
     #   host_site == "aro"  # NB NB THIS is a blatant hack. TODO Remove this

    # print(
    #     "Adding new config path: "
    #     + str(os.path.join(pathlib.Path().resolve(), "configs", host_site))
    # )
    sys.path.append(os.path.join(pathlib.Path().resolve(), "configs", host_site))



try:
    from pipe_config import *

except ImportError:
    print(
        "Failed the pipename approach to config file.\n"
        + str(host_site)
        + " isn't a real place, or there isn't a config file \
                        that I can find!"
    )

    try:
        site_name = input("What site am I running at?\n")
        sys.path.append(os.path.join(pathlib.Path().resolve(), "configs", site_name))
        from site_config import *

    except ImportError:
        print(
            str(site_name)
            + " isn't a real place, or there isn't a config file \
                        that I can find! Make sure you supplied \
                        a correct site name. Exiting."
        )
        sys.exit()
