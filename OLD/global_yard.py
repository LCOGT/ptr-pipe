# -*- coding: utf-8 -*-
"""
Created on Tue Jun 18 23:52:20 2019

@author: obs
"""

import ephem

#NBNB This whole idea breaks down if we have multiple devices of any given type.

g_dev = {
        'obs': None,
        'ocn': None,
        'enc': None,
        'mnt': None,
        'scr': None,
        'tel': None,
        'rot': None,
        'foc': None,
        'sel': None,
        'fil': None,
        'cam': None,
        'day': None,
        'events': None
        }


_sim_inc = 0.0     #  Unit is seconds
_sim_total = 0.0

def  ephem_sim_now(sim_delta=0.0):
    global _sim_total, _sim_inc
    _sim_total += (_sim_inc + sim_delta)/86400.
    if _sim_total >= 1:     #  Wrap a simulation around after one day.
        _sim_total = 0.0    
    sim_time = ephem.now() + _sim_total
    return sim_time
