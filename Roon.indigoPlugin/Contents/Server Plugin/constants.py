#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# TRV Controller - Constants © Autolog 2018
#

# plugin Constants

try:
    # noinspection PyUnresolvedReferences
    import indigo
except ImportError, e:
    pass

ZONE_MAP_ALPHAS = list()
for minor_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
	for major_letter in [' ', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
		ZONE_MAP_ALPHAS.append('{}{}'.format(major_letter, minor_letter))

ZONE_MAP_ALPHAS.sort()

OUTPUT_MAP_NUMBERS = list()
for major_number in [' ', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
	for minor_number in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
		OUTPUT_MAP_NUMBERS.append('{}{}'.format(major_number, minor_number))

OUTPUT_MAP_NUMBERS.sort()

OUTPUT_MAP_NUMBERS.pop(0)  # Remove firts entry = '0'

# Image Types
ARTIST = 0
ALBUM = 1

# QUEUE Priorities
QUEUE_PRIORITY_STOP_THREAD    = 0
QUEUE_PRIORITY_INIT_DISCOVERY = 50
QUEUE_PRIORITY_WAVEFORM       = 100
QUEUE_PRIORITY_COMMAND_HIGH   = 200
QUEUE_PRIORITY_COMMAND_MEDIUM = 300
QUEUE_PRIORITY_STATUS_HIGH    = 400
QUEUE_PRIORITY_STATUS_MEDIUM  = 500
QUEUE_PRIORITY_DISCOVERY      = 600
QUEUE_PRIORITY_POLLING        = 700
QUEUE_PRIORITY_LOW            = 800
