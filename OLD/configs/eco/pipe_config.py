

# NB NB NB json is not bi-directional with tuples (), instead, use lists [], nested if tuples are needed.
degree_symbol = "°"
pipe_name = 'ecopipe'
instance_type = 'pipe'

pipe_config = {

    #'wema': 'eco',
    'pipe_name': 'ecopipe',
    'instance_type': 'pipe',

    'obsp_ids': ['eco1', 'eco2'],  # a list of the obsp's to deal with

    
    'owner':  ['google-oauth2|112401903840371673242'],  # Wayne

    'owner_alias': ['WER', 'TELOPS'],
    'admin_aliases': ["ANS", "WER", "TELOPS", "TB", "DH", "KVH", "KC"],

    'client_hostname':  'MRC-0m35',  # This is also the long-name  Client is confusing!
    # NB NB disk D at mrc may be faster for temp storage
    'client_path':  'C:/ptr/',  # Generic place for client host to stash misc stuff
    'alt_path':  'C:/ptr/',  # Generic place for this host to stash misc stuff
    'plog_path':  'C:/ptr/eco/',  # place where night logs can be found.
    'save_to_alt_path': 'no',
    'archive_path':  'C:/ptr/',

    'archive_age': -99.9,  # Number of days to keep files in the local archive before deletion. Negative means never delete



    'name': 'Eltham College Observatory',
    'airport_code':  'MEL: Melbourne Airport',
    'location': 'Eltham, Victoria, Australia',
    'telescope_description': 'n.a.',
    'observatory_url': 'https://elthamcollege.vic.edu.au/',   #  This is meant to be optional
    'observatory_logo': None,   # I expect these will ususally end up as .png format icons
    'description':  '''Eltham College is an independent, non-denominational, co-educational day school situated in Research, an outer suburb north east of Melbourne.
                    ''',    #  i.e, a multi-line text block supplied and eventually mark-up formatted by the owner.
    

    



    # 'defaults': {
    #     #'observing_conditions': 'observing_conditions1',
    #     #'enclosure': 'enclosure1',
    #     #'mount': 'mount1',
    #     #'telescope': 'telescope1',
    #     #'focuser': 'focuser1',
    #     #'rotator': 'rotator1',
    #     #'selector':  None,
    #     #'screen': 'screen1',
    #     #'filter_wheel': 'filter_wheel1',
    #     #'camera': 'camera_1_1',
    #     'sequencer': 'sequencer1'
    # },
    # 'device_types': [
    #     #'observing_conditions',
    #     #'enclosure',
    #     #'mount',
    #     #'telescope',
    #     # 'screen',
    #     #'rotator',
    #     #'focuser',
    #     #'selector',
    #     #'filter_wheel',
    #     #'camera',

    #     'sequencer',
    # ],
    # 'wema_types': [
    #     'observing_conditions',
    #     'enclosure',
    # ],
    # 'enc_types': [
    #     'enclosure'
    # ],
    # 'short_status_devices':  [
    #     # 'observing_conditions',
    #     # 'enclosure',
    #     #'mount',
    #     #'telescope',
    #     # 'screen',
    #     #'rotator',
    #     #'focuser',
    #     #'selector',
    #     #'filter_wheel',
    #     #'camera',

    #     'sequencer',
    # ],
    
#     'observing_conditions' : {
#         'observing_conditions1': {
#             'parent': 'site',
#             'ocn_is_custom':  False, 
#             # Intention it is found in this file.
#             'name': 'SRO File',
#             'driver': None,  # Could be redis, ASCOM, ...
#             'share_path_name': 'F:/ptr/',
#             'driver_2':  None,   #' ASCOM.Boltwood.OkToOpen.SafetyMonitor',
#             'driver_3':  None,    # 'ASCOM.Boltwood.OkToImage.SafetyMonitor'
#             'ocn_has_unihedron':  False,
#             'have_local_unihedron': False,     #  Need to add these to setups.
#             'uni_driver': 'ASCOM.SQM.serial.ObservingConditions',
#             'unihedron_port':  10    #  False, None or numeric of COM port.
#         },
#     },
    
#     'enclosure': {
#         'enclosure1': {
#             'parent': 'site',
#             'encl_is_custom':  False,   #SRO needs sorting, presuambly with this flag.
#             'directly_connected': True, # For ECO and EC2, they connect directly to the enclosure, whereas WEMA are different.
#             'name': 'Dragonfly Roof',
#             'hostIP':  None,
#             'driver': 'Dragonfly.Dome',  #'ASCOM.DigitalDomeWorks.Dome',  #  ASCOMDome.Dome',  #  ASCOM.DeviceHub.Dome',  #  ASCOM.DigitalDomeWorks.Dome',  #"  ASCOMDome.Dome',
#             'has_lights':  False,
#             'controlled_by': 'mount1',
# 			'encl_is_dome': False,
#             'encl_is_rolloff': False,
#             'rolloff_has_endwall': False,
#             'mode': 'Automatic',
#             #'cool_down': -90.0,    #  Minutes prior to sunset.
#             'settings': {
#                 'lights':  ['Auto', 'White', 'Red', 'IR', 'Off'],       #A way to encode possible states or options???
#                                                                         #First Entry is always default condition.
#                 'roof_shutter':  ['Auto', 'Open', 'Close', 'Lock Closed', 'Unlock'],
#             },
#             #'eve_bias_dark_dur':  2.0,   #  hours Duration, prior to next.
#             #'eve_screen_flat_dur': 1.0,   #  hours Duration, prior to next.
#             #'operations_begin':  -1.0,   #  - hours from Sunset
#             #'eve_cooldown_offset': -.99,   #  - hours beforeSunset
#             #'eve_sky_flat_offset':  0.5,   #  - hours beforeSunset
#             #'morn_sky_flat_offset':  0.4,   #  + hours after Sunrise
#             #'morning_close_offset':  0.41,   #  + hours after Sunrise
#             #'operations_end':  0.42,
#         },
#     },
}

