"""
WER 20210624

First attempt at having a parallel dedicated agent for weather and enclosure.
This code should be as simple and reliable as possible, no hanging variables,
etc.

This would be a good place to log the weather data and any enclosure history,
once this code is stable enough to run as a service.

"""


import os
import signal
import json
import shelve
import time
import socket
from pathlib import Path
import math
import requests
import traceback
import ephem
import ptr_config
from api_calls import API_calls
import pipe_events
from devices.observing_conditions import ObservingConditions
from devices.enclosure import Enclosure
from global_yard import g_dev
from pipe_utility import plog


# FIXME: This needs attention once we figure out the restart_obs script.
def terminate_restart_observer(site_path, no_restart=False):
    """Terminates obs-platform code if running and restarts obs."""
    if no_restart is False:
        return

    camShelf = shelve.open(site_path + "ptr_night_shelf/" + "pid_obs")
    pid = camShelf["pid_obs"]  # a 9 character string
    camShelf.close()
    try:
        print("Terminating:  ", pid)
        os.kill(pid, signal.SIGTERM)
    except:
        print("No observer process was found, starting a new one.")
    # The above routine does not return but does start a process.
    parentPath = Path.cwd()
    os.system("cmd /c " + str(parentPath) + "\restart_obs.bat")

    return


def send_status(obsy, column, status_to_send):
    """Sends a status update to AWS."""
    
    uri_status = f"https://status.photonranch.org/status/{obsy}/status/"
    # NB None of the strings can be empty. Otherwise this put faults.
    payload = {"statusType": str(column), "status": status_to_send}\

    data = json.dumps(payload)
    try:
        response = requests.post(uri_status, data=data, timeout=20)

        if response.ok:
           # pass
           print("~")
    except:
        print(
            'self.api.authenticated_request("PUT", uri, status):  Failed! ',
            response.status_code,
        )

class PipeAgent:
    """A class for weather enclosure functionality."""

    def __init__(self, name, config):

        self.api = API_calls()
        self.command_interval = 30
        self.status_interval = 30
        self.config = config
        g_dev["pipe"] = self

        self.debug_flag = self.config['debug_mode']
        self.admin_only_flag = self.config['admin_owner_commands_only']
        if self.debug_flag:
            self.debug_lapse_time = time.time() + self.config['debug_duration_sec']
            g_dev['debug'] = True
        else:
            self.debug_lapse_time = 0.0
            g_dev['debug'] = False


        self.hostname = self.hostname = socket.gethostname()
        if self.hostname in self.config["pipe_hostname"]:
            self.is_pipe = True
            g_dev["pipe_write_share_path"] = config["pipe_path"]
            self.pipe_path = g_dev["pipe_write_share_path"]
            self.site_path = self.pipe_path
        else:
            # This host is a client
            self.is_pipe = False  # This is a client.
            self.site_path = config["pipe_path"]
            g_dev["site_path"] = self.site_path
            g_dev["pipe_write_share_path"] = self.site_path  # Just to be safe.
            self.pipe_path = g_dev["pipe_write_share_path"]


        self.last_request = None
        self.stopped = False
        self.site_message = "-"
        self.site_mode = config['site_enclosure_default_mode']
        self.device_types = config["pipe_types"]
        self.astro_events = pipe_events.Events(self.config)
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events()
        self.astro_events.display_events()

        

        self.pipe_pid = os.getpid()
        print("Fresh pipe_PID:  ", self.pipe_pid)
        
        self.update_config()
        self.create_devices(config)
        self.time_last_status = time.time() - 60  #forces early status on startup.
        self.loud_status = False
        self.blocks = None
        self.projects = None
        self.events_new = None
        immed_time = time.time()
        self.obs_time = immed_time
        self.pipe_start_time = immed_time
        self.cool_down_latch = False

        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        self.nightly_weather_report_complete = False
        self.weather_report_run_timer=time.time()-3600
        
        self.open_and_enabled_to_observe = False

        self.owm_active=config['OWM_active']
        self.local_weather_active=config['local_weather_active']
        
        self.enclosure_status_check_period=config['enclosure_status_check_period']
        self.weather_status_check_period = config['weather_status_check_period']
        self.safety_status_check_period = config['safety_status_check_period']
        self.scan_requests_check_period = 4
        self.pipe_settings_upload_period = 10

        # Timers rather than time.sleeps
        self.enclosure_status_check_timer=time.time() - 2*self.enclosure_status_check_period
        self.weather_status_check_timer = time.time() - 2*self.weather_status_check_period
        self.safety_check_timer=time.time() - 2*self.safety_status_check_period
        self.scan_requests_timer=time.time() -2 * self.scan_requests_check_period
        self.pipe_settings_upload_timer=time.time() -2 * self.pipe_settings_upload_period

        # This is a flag that enables or disables observing for all OBS in the pipe.
        self.observing_mode = 'active'
        self.rain_limit_quiet=False
        self.cloud_limit_quiet=False
        self.humidity_limit_quiet=False
        self.windspeed_limit_quiet=False
        self.lightning_limit_quiet=False
        self.temp_minus_dew_quiet=False
        self.skytemp_limit_quiet=False
        self.hightemp_limit_quiet=False
        self.lowtemp_limit_quiet=False

        if self.config['observing_conditions']['observing_conditions1']['driver'] == None:
            self.ocn_exists=False
        else:
            self.ocn_exists=True

        # This variable prevents the roof being called to open every loop...        
        self.enclosure_next_open_time = time.time()
        # This keeps a track of how many times the roof has been open this evening
        # Which is really a measure of how many times the enclosure has
        # attempted to observe but been shut on....
        # If it is too many, then it shuts down for the whole evening. 
        self.opens_this_evening = 0
        self.local_weather_ok = None
        self.weather_text_report = []
        
        #obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        
        self.times_to_open = []
        self.times_to_close = []
        self.hourly_report_holder=[]
        self.weather_report_open_at_start = False
        self.nightly_reset_complete = False
      
        self.keep_open_all_night = False
        self.keep_closed_all_night   = False          
        self.open_at_specific_utc = False
        self.specific_utc_when_to_open = -1.0  
        self.manual_weather_hold_set = False
        self.manual_weather_hold_duration = -1.0
    

        # This prevents commands from previous nights/runs suddenly running
        # when pipe.py is booted (has happened a bit!)
        url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
        body = {"site": self.config['pipe_name']}
        #cmd = {}
        # Get a list of new jobs to complete (this request
        # marks the commands as "RECEIVED")
        requests.request(
            "POST", url_job, data=json.dumps(body), timeout=30
        ).json()


    def create_devices(self, config: dict):
        self.all_devices = {}
        for (
            dev_type
        ) in self.device_types:  # This has been set up for pipe to be ocn and enc.
            self.all_devices[dev_type] = {}
            devices_of_type = config.get(dev_type, {})
            device_names = devices_of_type.keys()
            if dev_type == "camera":
                pass
            for name in device_names:
                driver = devices_of_type[name]["driver"]
 
                if dev_type == "observing_conditions" and not self.config['observing_conditions']['observing_conditions1']['ocn_is_custom']:

                    device = ObservingConditions(
                        driver, name, self.config, self.astro_events
                    )
                    self.ocn_status_custom=False
                elif dev_type == "observing_conditions" and self.config['observing_conditions']['observing_conditions1']['ocn_is_custom']:
                    
                    device=None
                    self.ocn_status_custom=True
                    
                    
                elif dev_type == "enclosure" and not self.config['enclosure']['enclosure1']['encl_is_custom']:
                    device = Enclosure(driver, name, self.config, self.astro_events)
                    self.enc_status_custom=False
                elif dev_type == "enclosure" and self.config['enclosure']['enclosure1']['encl_is_custom']:
                    
                    device=None
                    self.enc_status_custom=True
                   
                else:
                    print(f"Unknown device: {name}")
                self.all_devices[dev_type][name] = device
        print("Finished creating devices.")

    def update_config(self):
        """Sends the config to AWS."""

        uri = f"{self.config['pipe_name']}/config/"
        self.config["events"] = g_dev["events"]
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            print("\n\nConfig uploaded successfully.")

    def scan_requests(self):
        """
        
        This can pick up owner/admin Shutdown and Automatic request but it 
        would need to be a custom api endpoint.
        
        Not too many useful commands: Shutdown, Automatic, Immediate close,
        BadWxSimulate event (ie a 15 min shutdown)

        For a pipe this can be used to capture commands to the pipe once the
        AWS side knows how to redirect from any mount/telescope to the common
        pipe.
        This should be changed to look into the site command queue to pick up
        any commands directed at the Wx station, or if the agent is going to
        always exist lets develop a seperate command queue for it.
        
        NB NB NB should this be on some sort of timeout so that if AWS
        connection goes away the code can deal with that case?
        """


        url_job = "https://jobs.photonranch.org/jobs/getnewjobs"
        body = {"site": self.config['pipe_name']}
        cmd = {}
        # Get a list of new jobs to complete (this request
        # marks the commands as "RECEIVED")
        #plog ("scanning requests")
        try:
            unread_commands = requests.request(
                "POST", url_job, data=json.dumps(body), timeout=20
            ).json()
        except:
            plog(traceback.format_exc())
            plog("problem gathering scan requests. Likely just a connection glitch.")
            unread_commands = []
        # Make sure the list is sorted in the order the jobs were issued
        # Note: the ulid for a job is a unique lexicographically-sortable id.
        if len(unread_commands) > 0:
            try:
                unread_commands.sort(key=lambda x: x["timestamp_ms"])
                # Process each job one at a time
                for cmd in unread_commands:
                    if 'action' in cmd:
                        plog(cmd)
                        if cmd['action']=='open':
                            plog ("open enclosure command received")
                            self.open_enclosure(g_dev['enc'].get_status(), g_dev['ocn'].get_status())
                            self.enclosure_status_check_timer=time.time() - 2*self.enclosure_status_check_period
                            self.update_status()
                            
                        if cmd['action']=='close':
                            plog ("command enclosure command received")
                            self.park_enclosure_and_close()
                            self.enclosure_status_check_timer=time.time() - 2*self.enclosure_status_check_period
                            self.update_status()
                        
                        
                        if cmd['action']=='simulate_weather_hold':
                            plog("simulate weather hold button doesn't do anything yet")
                        
                        if cmd['action']=='open_no_earlier_than_owm_plan':
                            plog("open no earlier than owm button doesn't do anything yet")
                        
                        # Change in Enclosure mode
                        if cmd['action']=='set_enclosure_mode':
                            plog ("set enclosure mode command received")
                            g_dev['enc'].mode = cmd['required_params']['enclosure_mode']
                            self.enclosure_status_check_timer =time.time() - 2* self.enclosure_status_check_period
                            self.update_status()
                            
                        
                        if cmd['action']=='set_observing_mode':
                            plog ("set observing mode command received")
                            self.observing_mode=cmd['required_params']['observing_mode']
                            self.enclosure_status_check_timer =time.time() - 2* self.enclosure_status_check_period
                            self.update_status()
                            
                        if cmd['action']=='configure_active_weather_report':
                            plog ("configure weather settings command received")
                            if cmd['required_params']["weather_type"] == 'local':
                                if cmd['required_params']["weather_type_value"] == 'on':
                                    self.local_weather_active=True
                                if cmd['required_params']["weather_type_value"] == 'off':
                                    self.local_weather_active=False
                             
                            if cmd['required_params']["weather_type"] == 'owm':
                                if cmd['required_params']["weather_type_value"] == 'on':
                                    self.owm_active=True
                                if cmd['required_params']["weather_type_value"] == 'off':
                                    self.owm_active=False
                            
                            self.pipe_settings_upload_timer=time.time() -2 * self.pipe_settings_upload_period
                            self.update_status()
                            
                            
                        if cmd['action']=='force_roof_state':
                            if cmd['required_params']["force_roof_state"] == 'open':
                                plog ("keep roof open all night command received")
                                self.keep_open_all_night = True
                                self.keep_closed_all_night = False
                            
                            if cmd['required_params']["force_roof_state"] == 'closed':
                                
                                plog ("keep roof closed all night command received")
                                self.keep_closed_all_night= True
                                self.keep_open_all_night = False
                            
                            if cmd['required_params']["force_roof_state"] == 'auto':
                                
                                plog ("Remove roof force command received")
                                self.keep_closed_all_night= False
                                self.keep_open_all_night = False
                            
                            self.pipe_settings_upload_timer=time.time() -2 * self.pipe_settings_upload_period
                            self.update_status()
                            
                        if cmd['action']=='set_weather_values': 
                            tempval=cmd['required_params']['weather_values']
                            
                            g_dev['ocn'].rain_limit_on='on' in tempval['rain']['status']
                            g_dev['ocn'].warning_rain_limit_setting=tempval['rain']['warning_level']
                            g_dev['ocn'].rain_limit_setting=tempval['rain']['danger_level']
                            
                            g_dev['ocn'].cloud_cover_limit_on='on' in tempval['clouds']['status']
                            g_dev['ocn'].warning_cloud_cover_limit_setting=tempval['clouds']['warning_level']
                            g_dev['ocn'].cloud_cover_limit_setting=tempval['clouds']['danger_level']
                            
                            g_dev['ocn'].humidity_limit_on='on' in tempval['humidity']['status']
                            g_dev['ocn'].warning_humidity_limit_setting=tempval['humidity']['warning_level']
                            g_dev['ocn'].humidity_limit_setting=tempval['humidity']['danger_level']
                            
                            g_dev['ocn'].windspeed_limit_on='on' in tempval['windspeed']['status']
                            g_dev['ocn'].warning_windspeed_limit_setting=tempval['windspeed']['warning_level']
                            g_dev['ocn'].windspeed_limit_setting=tempval['windspeed']['danger_level']
                            
                            g_dev['ocn'].lightning_limit_on='on' in tempval['lightning']['status']
                            g_dev['ocn'].warning_lightning_limit_setting=tempval['lightning']['warning_level']
                            g_dev['ocn'].lightning_limit_setting=tempval['lightning']['danger_level']
                            
                            g_dev['ocn'].temp_minus_dew_on='on' in tempval['tempDew']['status']
                            g_dev['ocn'].warning_temp_minus_dew_setting=tempval['tempDew']['warning_level']
                            g_dev['ocn'].temp_minus_dew_setting=tempval['tempDew']['danger_level']
                            
                            g_dev['ocn'].sky_temperature_limit_on='on' in tempval['skyTempLimit']['status']
                            g_dev['ocn'].warning_sky_temp_limit_setting=tempval['skyTempLimit']['warning_level']
                            g_dev['ocn'].sky_temp_limit_setting=tempval['skyTempLimit']['danger_level']
                            
                            self.pipe_settings_upload_timer=time.time() -2 * self.pipe_settings_upload_period
                            self.update_status()
                            
                    else:
                        plog ("orphanned command?")
                        plog(cmd)

            except:
                if 'Internal server error' in str(unread_commands):
                    plog("AWS server glitch reading unread_commands")
                else:
                    plog(traceback.format_exc())
                    plog("unread commands")
                    plog(unread_commands)
                    plog("MF trying to find whats happening with this relatively rare bug!")

        return



    def update_status(self):
        """
        Collect status from weather and enclosure devices and sends an
        update to AWS. Each device class is responsible for implementing the
        method 'get_status()', which returns a dictionary.
        """

        loud = False
        while time.time() < self.time_last_status + self.status_interval:
            return
        
        enc_status = None
        ocn_status = None
        pipe = self.config['pipe_name']  
        
        # Hourly Weather Report
        if time.time() > (self.weather_report_run_timer + 3600):
            self.weather_report_run_timer=time.time()
            if self.enc_status_custom:
                enc_status={}
                enc_status['enclosure']={}

                enc_status['enclosure']['enclosure1']= get_enc_status_custom()
                self.run_nightly_weather_report(enc_status=enc_status['enclosure']['enclosure1'])
            else:
                self.run_nightly_weather_report(enc_status=g_dev['enc'].get_status())
        
        
        # Enclosure Status
        if time.time() > self.enclosure_status_check_timer + self.enclosure_status_check_period:
            self.enclosure_status_check_timer = time.time()
            status = {}
            status["timestamp"] = round(time.time(), 1)
            status['enclosure']={}
            if self.enc_status_custom==False:
                device=self.all_devices.get('enclosure', {})['enclosure1']
                status['enclosure']['enclosure1'] = device.get_status()
                enc_status = {"enclosure": status.pop("enclosure")}
            else:
                enc_status={}
                enc_status['enclosure']={}

                enc_status['enclosure']['enclosure1']= get_enc_status_custom()

            if enc_status is not None:
                # New Tim Entries
                if enc_status['enclosure']['enclosure1']['shutter_status'] == 'Open':
                    enc_status['enclosure']['enclosure1']['enclosure_is_open'] = True
                    enc_status['enclosure']['enclosure1']['shut_reason_bad_weather'] = False
                    enc_status['enclosure']['enclosure1']['shut_reason_daytime'] = False
                    enc_status['enclosure']['enclosure1']['shut_reason_manual_mode'] = False
                else:
                    enc_status['enclosure']['enclosure1']['enclosure_is_open'] = False
                    if not enc_status['enclosure']['enclosure1']['enclosure_mode'] == 'Automatic':
                        enc_status['enclosure']['enclosure1']['shut_reason_manual_mode'] = True
                    else:
                        enc_status['enclosure']['enclosure1']['shut_reason_manual_mode'] = False
                    if ocn_status is not None:  #NB NB ocn status has never been established first time this is envoked after startup -WER
                        if ocn_status['observing_conditions']['observing_conditions1']['wx_ok'] == 'Unknown':
                            enc_status['enclosure']['enclosure1']['shut_reason_bad_weather'] = False
                        elif ocn_status['observing_conditions']['observing_conditions1']['wx_ok'] == 'No' or not self.weather_report_open_at_start:
                            enc_status['enclosure']['enclosure1']['shut_reason_bad_weather'] = True
                    elif not self.weather_report_open_at_start:
                        enc_status['enclosure']['enclosure1']['shut_reason_bad_weather'] = True
                    else:
                        enc_status['enclosure']['enclosure1']['shut_reason_bad_weather'] = False

                        # NEED TO INCLUDE WEATHER REPORT AND FITZ NUMBER HERE

                    if g_dev['events']['Cool Down, Open'] < ephem.now() or ephem.now() < g_dev['events'][
                        'Close and Park'] > ephem.now():
                        enc_status['enclosure']['enclosure1']['shut_reason_daytime'] = True
                    else:
                        enc_status['enclosure']['enclosure1']['shut_reason_daytime'] = False

                # If the observing mode is set to off, append a noobs to prevent the obs from observing
                if self.observing_mode == 'inactive':
                    enc_status['enclosure']['enclosure1']['shutter_status'] = enc_status['enclosure']['enclosure1']['shutter_status'] + '/NoObs'

                if enc_status is not None:
                    lane = "enclosure"
                    try:                        
                        send_status(pipe, lane, enc_status)
                    except:
                        plog('could not send enclosure status')


        if time.time() > self.weather_status_check_timer + self.weather_status_check_period:
            self.weather_status_check_timer=time.time()
            status = {}
            status["timestamp"] = round(time.time(), 1)
            status['observing_conditions'] = {}
            if self.ocn_status_custom==False:
                device = self.all_devices.get('observing_conditions', {})['observing_conditions1']
                if device == None:
                    status['observing_conditions']['observing_conditions1'] = None
                else:
                    status['observing_conditions']['observing_conditions1'] = device.get_status()
                    ocn_status = {"observing_conditions": status.pop("observing_conditions")}
            else:
                ocn_status={}
                ocn_status['observing_conditions']={}
                ocn_status['observing_conditions']['observing_conditions1'] = get_ocn_status_custom()

            if ocn_status is None or ocn_status['observing_conditions']['observing_conditions1']  == None:   #20230709 Changed from not None
                ocn_status = {}
                ocn_status['observing_conditions'] = {}
                ocn_status['observing_conditions']['observing_conditions1'] = dict(wx_ok='Unknown',
                                                                                       wx_hold='no',
                                                                                       hold_duration=0)


            ocn_status['observing_conditions']['observing_conditions1']['weather_report_good'] = self.weather_report_open_at_start
            try:
                ocn_status['observing_conditions']['observing_conditions1']['fitzgerald_number'] = self.night_fitzgerald_number
            except:
                pass


            #breakpoint()
            if self.enclosure_next_open_time - time.time() > 0:
                ocn_status['observing_conditions']['observing_conditions1']['hold_duration'] = self.enclosure_next_open_time - time.time()
            else:
                ocn_status['observing_conditions']['observing_conditions1']['hold_duration'] = 0
            
            
            ocn_status['observing_conditions']['observing_conditions1']["wx_hold"] = not self.local_weather_ok
    
            if ocn_status is not None:
                lane = "weather"
                try:
                    send_status(pipe, lane, ocn_status)
                except:
                    plog('could not send weather status')                  

            loud = False
            if loud:
                print("\n\n > Status Sent:  \n", ocn_status)

        # pipe Settings
        if time.time() > self.pipe_settings_upload_timer + self.pipe_settings_upload_period:
            self.pipe_settings_upload_timer = time.time()

            status = {}
            status['pipe_settings']={}
            status['pipe_settings']['OWM_active']=self.owm_active
            status['pipe_settings']['local_weather_active']=self.local_weather_active
            status['pipe_settings']['keep_roof_open_all_night'] = self.keep_open_all_night
            status['pipe_settings']['keep_roof_closed_all_night']  = self.keep_closed_all_night
            
            status['pipe_settings']['open_at_specific_utc'] = self.open_at_specific_utc
            status['pipe_settings']['specific_utc_when_to_open'] = self.specific_utc_when_to_open
            
            status['pipe_settings']['manual_weather_hold_set'] = self.manual_weather_hold_set
            status['pipe_settings']['manual_weather_hold_duration'] = self.manual_weather_hold_duration
            status['pipe_settings']['observing_mode'] =self.observing_mode
                    
            if self.ocn_exists:
                # Local Weather Limits
                status['pipe_settings']['rain_limit_on'] = g_dev['ocn'].rain_limit_on
                status['pipe_settings']['rain_limit_quiet'] = self.rain_limit_quiet
                status['pipe_settings']['rain_limit_warning_level'] = g_dev['ocn'].warning_rain_limit_setting
                status['pipe_settings']['rain_limit_danger_level'] = g_dev['ocn'].rain_limit_setting
                
                status['pipe_settings']['cloud_limit_on'] = g_dev['ocn'].cloud_cover_limit_on
                status['pipe_settings']['cloud_limit_quiet'] = self.cloud_limit_quiet
                status['pipe_settings']['cloud_limit_warning_level'] = g_dev['ocn'].warning_cloud_cover_limit_setting
                status['pipe_settings']['cloud_limit_danger_level'] = g_dev['ocn'].cloud_cover_limit_setting
                
                status['pipe_settings']['humidity_limit_on']  = g_dev['ocn'].humidity_limit_on
                status['pipe_settings']['humidity_limit_quiet'] = self.humidity_limit_quiet
                status['pipe_settings']['humidity_limit_warning_level'] = g_dev['ocn'].warning_humidity_limit_setting
                status['pipe_settings']['humidity_limit_danger_level'] = g_dev['ocn'].humidity_limit_setting
                
                status['pipe_settings']['windspeed_limit_on']  = g_dev['ocn'].windspeed_limit_on
                status['pipe_settings']['windspeed_limit_quiet'] = self.windspeed_limit_quiet
                status['pipe_settings']['windspeed_limit_warning_level'] = g_dev['ocn'].warning_windspeed_limit_setting
                status['pipe_settings']['windspeed_limit_danger_level'] = g_dev['ocn'].windspeed_limit_setting
                
                status['pipe_settings']['lightning_limit_on']  = g_dev['ocn'].lightning_limit_on
                status['pipe_settings']['lightning_limit_quiet'] = self.lightning_limit_quiet
                status['pipe_settings']['lightning_limit_warning_level'] = g_dev['ocn'].warning_lightning_limit_setting
                status['pipe_settings']['lightning_limit_danger_level'] =  g_dev['ocn'].lightning_limit_setting
                
                status['pipe_settings']['tempminusdew_limit_on']  = g_dev['ocn'].temp_minus_dew_on
                status['pipe_settings']['tempminusdew_limit_quiet'] = self.temp_minus_dew_quiet
                status['pipe_settings']['tempminusdew_limit_warning_level'] = g_dev['ocn'].warning_temp_minus_dew_setting
                status['pipe_settings']['tempminusdew_limit_danger_level'] = g_dev['ocn'].temp_minus_dew_setting
                
                status['pipe_settings']['skytemp_limit_on']  = g_dev['ocn'].sky_temperature_limit_on
                status['pipe_settings']['skytemp_limit_quiet'] = self.skytemp_limit_quiet
                status['pipe_settings']['skytemp_limit_warning_level'] = g_dev['ocn'].warning_sky_temp_limit_setting
                status['pipe_settings']['skytemp_limit_danger_level'] = g_dev['ocn'].sky_temp_limit_setting
                
                status['pipe_settings']['hightemperature_limit_on']  = g_dev['ocn'].highest_temperature_on
                status['pipe_settings']['hightemperature_limit_quiet'] = self.hightemp_limit_quiet
                status['pipe_settings']['hightemperature_limit_warning_level'] = g_dev['ocn'].warning_highest_temperature_setting
                status['pipe_settings']['hightemperature_limit_danger_level'] = g_dev['ocn'].highest_temperature_setting
                
                status['pipe_settings']['lowtemperature_limit_on']  = g_dev['ocn'].lowest_temperature_on
                status['pipe_settings']['lowtemperature_limit_quiet'] = self.lowtemp_limit_quiet
                status['pipe_settings']['lowtemperature_limit_warning_level'] = g_dev['ocn'].warning_lowest_temperature_setting
                status['pipe_settings']['lowtemperature_limit_danger_level'] = g_dev['ocn'].lowest_temperature_setting

            lane = "pipe_settings"
            try:                
                send_status(pipe, lane, status)
            except:
                plog('could not send pipe_settings status') 
            
            

    def update(self):     ## NB NB NB This is essentially the sequencer for the pipe.
        self.update_status()

        if time.time() > self.scan_requests_timer + self.scan_requests_check_period:
            self.scan_requests_timer=time.time()
            self.scan_requests()


        if time.time() > self.safety_check_timer + self.safety_status_check_period:
            self.safety_check_timer=time.time()

            # Here it runs through the various checks and decides whether to open or close the roof or not.
            # Check for delayed opening of the enclosure and act accordingly.
            
            

            # If the enclosure is simply delayed until opening, then wait until then, then attempt to start up the enclosure
            obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
            if (g_dev['events']['Cool Down, Open'] <= ephem_now):
                self.nightly_reset_complete = False

            if (g_dev['events']['Close and Park'] <= ephem_now):
                self.nightly_reset_complete = False
            if self.ocn_status_custom==False:                            
                ocn_status = g_dev['ocn'].get_status()
            else:
                ocn_status = get_ocn_status_custom()
            if self.enc_status_custom==False:                
                enc_status = g_dev['enc'].get_status()
            else:
                enc_status = get_enc_status_custom()
           
            if ocn_status==None:
                self.local_weather_ok = None
            else:
                if 'wx_ok' in ocn_status:
                    if ocn_status['wx_ok'] == 'Yes':
                        self.local_weather_ok = True
                    elif ocn_status['wx_ok'] == 'No':
                        self.local_weather_ok = False
                    else:
                        self.local_weather_ok = None
                else:
                    self.local_weather_ok = None

            plog("***************************************************************")
            plog("Current time             : " + str(time.asctime()))
            plog("Shutter Status           : " + str(enc_status['shutter_status']))
            if ocn_status == None:
                plog("This pipe does not report observing conditions")
            else:
                plog("Observing Conditions      : " +str(ocn_status))
                
            if self.local_weather_ok == None:
                plog("No information on local weather available.")
            else:
                plog("Local Weather Ok to Observe  : " +str(self.local_weather_ok))
                if not self.local_weather_active:
                    plog ("However, Local Weather control is set off")
            
            if g_dev['enc'].mode == 'Manual':
                plog ("Weather Considerations overriden due to being in Manual or debug mode: ")
            
            plog("Weather Report Good to Observe: " + str(self.weather_report_open_at_start))
            plog("Time until Cool and Open      : " + str(round(( g_dev['events']['Cool Down, Open'] - ephem_now) * 24,2)) + " hours")
            plog("Time until Close and Park     : "+ str(round(( g_dev['events']['Close and Park'] - ephem_now) * 24,2)) + " hours")
            plog("Time until Nightly Reset      : " + str(round((g_dev['events']['Nightly Reset'] - ephem_now) * 24, 2)) + " hours")
            plog("Nightly Reset Complete        : " + str(self.nightly_reset_complete))
            plog("\n")

            if len(self.weather_text_report) >0:
                for line in self.weather_text_report:
                    plog (line)
        
            if not self.owm_active:
                plog("OWM is off. OWM information is advisory only, it is currently inactive.")

            if self.owm_active:
                plog("OWM is on. OWM predicts it will set to open/close the roof at these times.")

            if not self.local_weather_active:
                plog("Reacting to local weather is *OFF*. Not reacting to local weather signals.")

            if self.local_weather_active:
                plog("Reacting to local weather is *ON*. Reacting to local weather signals.")

            if self.keep_open_all_night:
                plog("Roof is being forced to stay OPEN ALL NIGHT")

            if self.keep_closed_all_night:                
                plog("Roof is being forced to stay CLOSED ALL NIGHT")


            plog("**************************************************************")

            if (g_dev['events']['Nightly Reset'] <= ephem.now() < g_dev['events']['End Nightly Reset']):
                if self.nightly_reset_complete == False:
                    self.nightly_reset_complete = True
                    self.nightly_reset_script(enc_status)
            
            # Safety checks here
            if not g_dev['debug'] and self.open_and_enabled_to_observe:
                if enc_status is not None:
                    if enc_status['shutter_status'] == 'Software Fault':
                        plog("Software Fault Detected. Will alert the authorities!")
                        self.open_and_enabled_to_observe = False
                        self.park_enclosure_and_close()
                        
                    if enc_status['shutter_status'] == 'Closing':
                        plog("Detected Roof Closing.")
                        self.open_and_enabled_to_observe = False
                        self.enclosure_next_open_time = time.time(
                         ) + self.config['roof_open_safety_base_time'] * self.opens_this_evening

                    if enc_status['shutter_status'] == 'Error':
                        plog("Detected an Error in the Roof Status. Packing up for safety.")
                        self.open_and_enabled_to_observe = False
                        self.park_enclosure_and_close()
                        self.enclosure_next_open_time = time.time(
                        ) + self.config['roof_open_safety_base_time'] * self.opens_this_evening
                            
                else:
                    plog("Enclosure roof status probably not reporting correctly. pipe down?")

            roof_should_be_shut = False

            if g_dev['enc'].mode in ['Shutdown']:
                roof_should_be_shut = True
                self.open_and_enabled_to_observe = False

            if not (g_dev['events']['Cool Down, Open'] < ephem_now < g_dev['events']['Close and Park']):
                roof_should_be_shut = True
                self.open_and_enabled_to_observe = False
                
            if self.keep_closed_all_night:
                roof_should_be_shut = True
                self.open_and_enabled_to_observe = False
                
            if enc_status['shutter_status'] == 'Open':
                if roof_should_be_shut == True and not g_dev['enc'].mode == 'Manual':
                    plog("Safety check notices that the roof was open outside of the normal observing period")
                    self.park_enclosure_and_close()
                
                if not (self.local_weather_ok == None) and g_dev['enc'].mode == 'Automatic':
                    if (not self.local_weather_ok and self.local_weather_active):
                        plog("Safety check notices that the local weather is not ok. Shutting the roof.")
                        self.park_enclosure_and_close()

            if enc_status['shutter_status'] == 'Closed' and self.keep_open_all_night and g_dev['enc'].mode in ['Automatic']:

                if time.time() > self.enclosure_next_open_time and self.opens_this_evening < self.config[
                    'maximum_roof_opens_per_evening']:
                    self.nightly_reset_complete = False
                    self.open_enclosure(enc_status, ocn_status)

            if (self.enclosure_next_open_time - time.time()) > 0:
                plog("opens this eve: " + str(self.opens_this_evening))

                plog("minutes until next open attempt ALLOWED: " +
                     str((self.enclosure_next_open_time - time.time()) / 60))

            
            if (not self.keep_closed_all_night) and ((g_dev['events']['Cool Down, Open'] <= ephem_now < g_dev['events']['Observing Ends']) and (self.keep_open_all_night or self.weather_report_open_at_start==True or not self.owm_active) and \
                g_dev['enc'].mode == 'Automatic') and not self.cool_down_latch and (self.keep_open_all_night or self.local_weather_ok == True or (not self.ocn_exists) or (not self.local_weather_active)) and not \
                enc_status['shutter_status'] in ['Software Fault', 'Opening', 'Closing', 'Error']:

                self.cool_down_latch = True

                if not self.open_and_enabled_to_observe and (self.weather_report_open_at_start or not self.owm_active): # and (self.weather_report_open_during_evening == False or self.local_weather_always_overrides_OWM):

                    if time.time() > self.enclosure_next_open_time and self.opens_this_evening < self.config['maximum_roof_opens_per_evening']:
                        self.nightly_reset_complete = False
                        self.open_enclosure(enc_status, ocn_status)

                self.cool_down_latch = False

            # If in post-close and park era of the night, check those two things have happened!
            if (g_dev['events']['Close and Park'] <= ephem_now < g_dev['events']['Nightly Reset']) \
                    and g_dev['enc'].mode == 'Automatic':

                if not ('closed' in enc_status['shutter_status'].lower()):
                    plog("Found shutter open after Close and Park, shutting up the shutter")
                    self.park_enclosure_and_close()


    def nightly_reset_script(self, enc_status):
        
        if g_dev['enc'].mode == 'Automatic':
            self.park_enclosure_and_close()
        
        # Set weather report to false because it is daytime anyways.
        self.weather_report_open_at_start=False
        
        #events = g_dev['events']
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

        # Reopening config and resetting all the things.
        self.astro_events.compute_day_directory()
        self.astro_events.calculate_events()
        self.astro_events.display_events()
        
        # sending this up to AWS
        '''
        Send the config to aws.
        '''
        uri = f"{self.config['pipe_name']}/config/"
        self.config['events'] = g_dev['events']
        response = self.api.authenticated_request("PUT", uri, self.config)
        if response:
            plog("Config uploaded successfully.")

        self.cool_down_latch = False
        self.nightly_reset_complete = True
        self.opens_this_evening=0
        
        self.keep_open_all_night = False
        self.keep_closed_all_night   = False          
        self.open_at_specific_utc = False
        self.specific_utc_when_to_open = -1.0  
        self.manual_weather_hold_set = False
        self.manual_weather_hold_duration = -1.0
        
        return



    def run(self):  # run is a poor name for this function.
        """Runs the continuous pipe process.

        Loop ends with keyboard interrupt."""
        try:
            while True:
                self.update()  # `Ctrl-C` will exit the program.
        except KeyboardInterrupt:
            print("Finishing loops and exiting...")
            self.stopped = True
            return

    # def send_to_user(self, p_log, p_level="INFO"):
    #     """ """
    #     url_log = "https://logs.photonranch.org/logs/newlog"
    #     body = json.dumps(
    #         {
    #             "site": self.config["site"],
    #             "log_message": str(p_log),
    #             "log_level": str(p_level),
    #             "timestamp": time.time(),
    #         }
    #     )
    #     try:
    #         response = requests.post(url_log, body, timeout=20)
    #     except Exception:
    #         print("Log did not send, usually not fatal.")

    def park_enclosure_and_close(self):

        self.open_and_enabled_to_observe = False
        g_dev['enc'].close_roof_directly({}, {})
        
        return

    def open_enclosure(self, enc_status, ocn_status, no_sky=False):

        
        flat_spot, flat_alt = g_dev['evnt'].flat_spot_now()
        obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

        if g_dev['enc'].mode in ['Shutdown']:
            plog ("Not OPENING the enclosure. Site in Shutdown mode.")
            return

        if self.keep_closed_all_night and not g_dev['enc'].mode in ['Manual']:
            plog ("Observatory set to be closed all night. Not opening enclosure.")
            return

        # Only send an enclosure open command if the weather
        if (self.weather_report_open_at_start or not self.owm_active or g_dev['enc'].mode == "Manual"):

            if not g_dev['debug'] and not g_dev['enc'].mode in ['Manual'] and (
                    ephem_now < g_dev['events']['Cool Down, Open']) or \
                    (g_dev['events']['Close and Park'] < ephem_now < g_dev['events']['Nightly Reset']):
                plog("NOT OPENING THE enclosure -- IT IS THE DAYTIME!!")
                return
            else:

                try:

                    plog("Attempting to open the roof.")

                    if ocn_status == None:
                        if not enc_status['shutter_status'] in ['Open', 'open','Opening','opening'] and \
                                g_dev['enc'].mode == 'Automatic' or g_dev['enc'].mode == 'Manual':
                            self.opens_this_evening = self.opens_this_evening + 1

                            g_dev['enc'].open_roof_directly({}, {})
                           

                    elif  not enc_status['shutter_status'] in ['Open', 'open','Opening','opening'] and \
                            g_dev['enc'].mode == 'Automatic' \
                            and time.time() > self.enclosure_next_open_time and self.weather_report_open_at_start:#  and self.weather_report_is_acceptable_to_observe:  # NB

                        self.opens_this_evening = self.opens_this_evening + 1

                        g_dev['enc'].open_roof_directly({}, {})

                    elif not enc_status['shutter_status'] in ['Open', 'open', 'Opening', 'opening'] and \
                            g_dev['enc'].mode == 'Manual':
                        self.opens_this_evening = self.opens_this_evening + 1

                        g_dev['enc'].open_roof_directly({}, {})

                        
                    plog("Attempting to Open Shutter. Waiting until shutter opens")
                    if not g_dev['enc'].enclosure.ShutterStatus == 0:
                        time.sleep(self.config['period_of_time_to_wait_for_roof_to_open'])

                    self.enclosure_next_open_time = time.time() + (self.config['roof_open_safety_base_time'] * 60) * self.opens_this_evening


                    if g_dev['enc'].enclosure.ShutterStatus == 0:
                        self.open_and_enabled_to_observe = True

                        try:
                            plog("Synchronising dome.")
                            g_dev['enc'].sync_mount_command({}, {})
                        except:
                            pass
                        # Prior to skyflats no dome following.
                        self.dome_homed = False

                        return

                    else:
                        plog("Failed to open roof. Sending the close command to the roof.")
                        plog("opens this eve: " + str(self.opens_this_evening))
                        plog("minutes until next open attempt ALLOWED: " + str(
                            (self.enclosure_next_open_time - time.time()) / 60))
                        g_dev['enc'].close_roof_directly({}, {})

                        return

                except Exception as e:
                    plog("Enclosure opening glitched out: ", e)
                    plog(traceback.format_exc())

        else:
            plog("An enclosure command was rejected because the weather report was not acceptable.")

        return

    def run_nightly_weather_report(self,enc_status=None):
       
        events = g_dev['events']

        obs_win_begin, sunset, sunrise, ephem_now = self.astro_events.getSunEvents()
        
        self.update_status()
        # First thing to do at the Cool Down, Open time is to calculate the quality of the evening
        # using the broad weather report.
        try: 
            plog("Applsing quality of evening from Open Weather Map.")
            owm = OWM('d5c3eae1b48bf7df3f240b8474af3ed0')
            mgr = owm.weather_manager()
            try:
                one_call = mgr.one_call(lat=self.config["latitude"], lon=self.config["longitude"])
            except:
                plog ("Connection glitch probably. Bailing out, will try again soon")
                plog(traceback.format_exc())
                time.sleep(10)
                return
            self.weather_report_run_timer = time.time()
            
            # Collect relevant info for fitzgerald weather number calculation
            hourcounter=0
            fitzgerald_weather_number_grid=[]
            hours_until_end_of_observing= math.ceil((events['Close and Park'] - ephem_now) * 24)
            hours_until_start_of_observing= math.ceil((events['Cool Down, Open'] - ephem_now) * 24)
            if hours_until_start_of_observing < 0:
                hours_until_start_of_observing = 0
            plog("Hours until end of observing: " + str(hours_until_end_of_observing))
            
            OWM_status_json={}
            OWM_status_json["timestamp"] = round(time.time(), 1)
            for hourly_report in one_call.forecast_hourly:
                
                
                clock_hour=int(hourly_report.reference_time('iso').split(' ')[1].split(':')[0])

                # Calculate Fitzgerald number for this hour
                tempFn=0
                # Add humidity score up
                if 80 < hourly_report.humidity <= 85:
                    tempFn=tempFn+4
                elif 85 < hourly_report.humidity <= 90:
                    tempFn=tempFn+20
                elif 90 < hourly_report.humidity <= 100:
                    tempFn=tempFn+101

                # Add cloud score up
                if 20 < hourly_report.clouds <= 40:
                    tempFn=tempFn+10
                elif 40 < hourly_report.clouds <= 60:
                    tempFn=tempFn+40
                elif 60 < hourly_report.clouds <= 80:
                    tempFn=tempFn+60
                elif 80 < hourly_report.clouds <= 100:
                    tempFn=tempFn+101

                # Add wind score up
                if 8 < hourly_report.wind()['speed'] <=12:
                    tempFn=tempFn+1
                elif 12 < hourly_report.wind()['speed'] <= 15:
                    tempFn=tempFn+4
                elif 15 < hourly_report.wind()['speed'] <= 20:
                    tempFn=tempFn+40
                elif 20 < hourly_report.wind()['speed'] :
                    tempFn=tempFn+101

                if 'rain'  in hourly_report.detailed_status or 'storm'  in hourly_report.detailed_status or hourly_report.rain != {}:
                    tempFn=tempFn+101

                weatherline=[hourly_report.humidity,hourly_report.clouds,hourly_report.wind()['speed'],hourly_report.status, hourly_report.detailed_status, clock_hour, tempFn, hourly_report.reference_time('iso'), hourly_report.temperature()['temp'] - 273.15, hourly_report.rain]
                fitzgerald_weather_number_grid.append(weatherline)

                hourcounter=hourcounter + 1


            forecast_status=[]
            for weatherline in fitzgerald_weather_number_grid:

                status_line={}
                status_line['humidity']=weatherline[0]
                status_line['cloud_cover'] = weatherline[1]
                status_line['wind_speed'] = weatherline[2]
                status_line['short_text'] = weatherline[3]
                status_line['long_text'] = weatherline[4]
                status_line['utc_clock_hour'] = weatherline[5]
                status_line['fitz_number'] = weatherline[6]
                status_line['utc_long_form'] = weatherline[7].replace(' ','T').split('+')[0]+'Z'
                status_line['temperature'] = weatherline[8]
                status_line['rain'] = weatherline[9]

                if float(weatherline[6]) < 11:
                    status_line['weather_quality_number'] = 1
                elif float (weatherline[6]) < 21:
                    status_line['weather_quality_number'] = 2
                elif float (weatherline[6]) < 41:
                    status_line['weather_quality_number'] = 3
                elif float (weatherline[6]) < 101:
                    status_line['weather_quality_number'] = 4
                else:
                    status_line['weather_quality_number'] = 5

                forecast_status.append(status_line)
                

            if forecast_status is not None:
                lane = "forecast"
                obsy = self.config['pipe_name']
                url = f"https://status.photonranch.org/status/{obsy}/status"

                payload = json.dumps({
                    "statusType": "forecast",
                    "status": { "forecast": forecast_status }
                })
                response = requests.request("POST", url, data=payload)

            
            # Fitzgerald weather number calculation.
            hourly_fitzgerald_number=[]
            hourly_fitzgerald_number_by_hour=[]
            hourcounter = 0
            self.hourly_report_holder=[]
            for entry in fitzgerald_weather_number_grid:
                if hourcounter >= hours_until_start_of_observing and hourcounter <= hours_until_end_of_observing:
                    
                    textdescription= entry[4]+ '   Cloud:   ' + str(entry[1]) + '%     Hum:    ' + str(entry[0]) +   '%    Wind:  ' +str(entry[2])+' m/s      rain: ' + str(entry[9])  # WER changed to make more readable.

                    hourly_fitzgerald_number.append(entry[6])
                    hourly_fitzgerald_number_by_hour.append([entry[5],entry[6],textdescription])
                hourcounter=hourcounter+1
            
            plog ("Hourly Fitzgerald number report")
            self.hourly_report_holder.append("Hourly Fitzgerald number report")
            
            plog ("For Evening of " +str(g_dev['dayhyphened']) )
            self.hourly_report_holder.append("For LOCAL Evening of " +str(g_dev['dayhyphened']) )
            
            plog("Time of Weather Report: " + str(time.asctime()))
            self.hourly_report_holder.append("Time of Weather Report (UTC): " + str(time.asctime()))
            
            plog ("*******************************")
            self.hourly_report_holder.append("*******************************")
            plog ("Hour(UTC) |  FNumber |  Text    ")
            self.hourly_report_holder.append("Hour(UTC) |  FNumber |  Text    ")
            for line in hourly_fitzgerald_number_by_hour:
                plog (str(line[0]) + '         | '+ str(line[1]) + '        | ' + str(line[2]))
                self.hourly_report_holder.append(str(line[0]) + '         | '+ str(line[1]) + '        | ' + str(line[2]))
            
            plog ("Night's total fitzgerald number: " + str(sum(hourly_fitzgerald_number)))
            

            self.night_fitzgerald_number = sum(hourly_fitzgerald_number)
            if len(hourly_fitzgerald_number) >= 1:
                average_fitzn_for_rest_of_night = sum(hourly_fitzgerald_number) / len(hourly_fitzgerald_number)
            else:
                average_fitzn_for_rest_of_night = 100
            
            plog("Night's average fitzgerald number: " + str(average_fitzn_for_rest_of_night))
            
            # Simplified decision array
            hours_bad_or_good=[]
            for entry in hourly_fitzgerald_number_by_hour:
                if entry[1] > 41:
                    hours_bad_or_good.append([entry[0],0])
                else:
                    hours_bad_or_good.append([entry[0],1])

           
            # If the first three hours are good, then open from the start
            self.weather_report_open_at_start = False
            if (hours_bad_or_good[0][1] + hours_bad_or_good[1][1] +hours_bad_or_good[2][1] ) == 3:
                plog("Looks like it is clear enough to open the observatory from the beginning.")
                self.weather_report_open_at_start = True
            elif (hours_bad_or_good[0][1]) == 0 and g_dev['enc'].mode == 'Automatic' and not \
            'closed' in enc_status['shutter_status'].lower() and self.owm_active:
                plog("Looks like the weather gets rough in the first hour, shutting up observatory.")
                self.park_enclosure_and_close()

            # Look for three hour gaps in the weather throughout the night
            self.times_to_open=[]
            self.times_to_close=[]
            for counter in range(len(hours_bad_or_good)):
                
                # A three hour gap after a bad hour is a good time to open.
                
                if (counter - len(hours_bad_or_good)) == -1:                   
                    pass
                elif (counter - len(hours_bad_or_good)) == -2:
                    sum_of_next_three_hours=int((hours_bad_or_good[counter][1]+hours_bad_or_good[counter+1][1])*1.5)
                else:
                    sum_of_next_three_hours = hours_bad_or_good[counter][1] + hours_bad_or_good[counter + 1][1] + \
                                          hours_bad_or_good[counter + 2][1]

                if sum_of_next_three_hours == 3 and hours_bad_or_good[counter-1][1] == 0:
                    plog ("good time to open")
                    self.times_to_open.append([hours_bad_or_good[counter][0]])

                # Simply a bad hour is a good time to close.
                if len(hours_bad_or_good) == counter + 1:                    
                    pass
                elif hours_bad_or_good[counter][1] == 1 and hours_bad_or_good[counter+1][1] == 0:
                    plog ("good time to close")
                    self.times_to_close.append([hours_bad_or_good[counter][0]])


            self.weather_text_report=[]
            # Construct the text!

            if len(self.hourly_report_holder) > 0:
                pasttitle = False
                firstentry = True
                for line in self.hourly_report_holder:
                    self.weather_text_report.append(str(line))

                    if pasttitle == True:
                        current_utc_hour = float(line.split(' ')[0])

                        if len(self.times_to_open) > 0:
                            for entry in self.times_to_open:

                                if int(current_utc_hour) == int(entry[0]) and not firstentry:
                                    self.weather_text_report.append("OWM would plan to open the roof")
                            
                        if len(self.times_to_close) > 0:
                            for entry in self.times_to_close:
                                
                                if int(current_utc_hour) == int(entry[0]):
                                    self.weather_text_report.append("OWM would plan to close the roof")
                        firstentry = False
                        
                    if 'Hour(UTC)' in line:
                        pasttitle = True
                        self.weather_text_report.append("-----------------------------")
                        if g_dev['events']['Cool Down, Open'] > ephem_now:
                            self.weather_text_report.append("Cool Down Open")
                        if self.weather_report_open_at_start:
                            self.weather_text_report.append("OWM would plan to open at this point.")
                        else:
                            self.weather_text_report.append("OWM would keep the roof shut at this point.")
                if g_dev['events']['Close and Park'] > ephem_now:
                    self.weather_text_report.append("Close and Park")
                self.weather_text_report.append("-----------------------------")

           
            status = {}
            status['owm_report'] = json.dumps(self.weather_text_report)
            lane = "owm_report"


            try:
                send_status(self.config['pipe_name'], lane, status)
            except:
                plog('could not send owm_report status')
                plog(traceback.format_exc())
                
        except Exception as e:
            plog ("OWN failed", e)
            plog ("Usually a connection glitch")
            plog(traceback.format_exc())
            
        # However, if the enclosure is under manual control, leave this switch on.
        if self.enc_status_custom==False:
            enc_status = g_dev['enc'].status
        else:
            enc_status = get_enc_status_custom()        
                    
        return
        
if __name__ == "__main__":
    pipe = PipeAgent(ptr_config.pipe_name, ptr_config.pipe_config)
    pipe.run()
