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
from pathlib import Path
import socket
import requests
import traceback

import ptr_config
from api_calls import API_calls

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

        

        
        self.last_request = None
        self.stopped = False
        self.site_message = "-"
        self.device_types = config["pipe_types"]
        #self.astro_events = pipe_events.Events(self.config)
        #self.astro_events.compute_day_directory()
        #self.astro_events.calculate_events()
        #self.astro_events.display_events()

        

        self.pipe_pid = os.getpid()
        print("Fresh pipe_PID:  ", self.pipe_pid)
        
        self.update_config()
        #self.create_devices(config)
        self.time_last_status = time.time() - 60  #forces early status on startup.
        self.loud_status = False
        #self.blocks = None
        #self.projects = None
        #self.events_new = None
        #immed_time = time.time()
        #self.obs_time = immed_time
        #self.pipe_start_time = immed_time
        #self.cool_down_latch = False

        #obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()
        self.scan_requests_check_period = 4
        self.pipe_settings_upload_period = 10

        # Timers rather than time.sleeps
        self.scan_requests_timer=time.time() -2 * self.scan_requests_check_period
        self.pipe_settings_upload_timer=time.time() -2 * self.pipe_settings_upload_period

      

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


    # def create_devices(self, config: dict):
    #     self.all_devices = {}
    #     for (
    #         dev_type
    #     ) in self.device_types:  # This has been set up for pipe to be ocn and enc.
    #         self.all_devices[dev_type] = {}
    #         devices_of_type = config.get(dev_type, {})
    #         device_names = devices_of_type.keys()
    #         if dev_type == "camera":
    #             pass
    #         for name in device_names:
    #             driver = devices_of_type[name]["driver"]
 
    #             if dev_type == "observing_conditions" and not self.config['observing_conditions']['observing_conditions1']['ocn_is_custom']:

    #                 device = ObservingConditions(
    #                     driver, name, self.config, self.astro_events
    #                 )
    #                 self.ocn_status_custom=False
    #             elif dev_type == "observing_conditions" and self.config['observing_conditions']['observing_conditions1']['ocn_is_custom']:
                    
    #                 device=None
    #                 self.ocn_status_custom=True
                    
                    
    #             elif dev_type == "enclosure" and not self.config['enclosure']['enclosure1']['encl_is_custom']:
    #                 device = Enclosure(driver, name, self.config, self.astro_events)
    #                 self.enc_status_custom=False
    #             elif dev_type == "enclosure" and self.config['enclosure']['enclosure1']['encl_is_custom']:
                    
    #                 device=None
    #                 self.enc_status_custom=True
                   
    #             else:
    #                 print(f"Unknown device: {name}")
    #             self.all_devices[dev_type][name] = device
    #     print("Finished creating devices.")

    def update_config(self):
        """Sends the config to AWS."""

        uri = f"{self.config['pipe_name']}/config/"
        #self.config["events"] = g_dev["events"]
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
        
       
        pipe = self.config['pipe_name']  
        
        pipeline_ip = requests.get('https://checkip.amazonaws.com').text.strip()
        
        # pipe Settings
        if time.time() > self.pipe_settings_upload_timer + self.pipe_settings_upload_period:
            self.pipe_settings_upload_timer = time.time()

            status = {}
            status['pipe_settings']={}
            status['pipe_settings']['pipeline_ip']=pipeline_ip
            
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


        

    # def nightly_reset_script(self, enc_status):
        
    #     if g_dev['enc'].mode == 'Automatic':
    #         self.park_enclosure_and_close()
        
    #     # Set weather report to false because it is daytime anyways.
    #     self.weather_report_open_at_start=False
        
    #     #events = g_dev['events']
    #     obs_win_begin, sunZ88Op, sunZ88Cl, ephem_now = self.astro_events.getSunEvents()

    #     # Reopening config and resetting all the things.
    #     self.astro_events.compute_day_directory()
    #     self.astro_events.calculate_events()
    #     self.astro_events.display_events()
        
    #     # sending this up to AWS
    #     '''
    #     Send the config to aws.
    #     '''
    #     uri = f"{self.config['pipe_name']}/config/"
    #     self.config['events'] = g_dev['events']
    #     response = self.api.authenticated_request("PUT", uri, self.config)
    #     if response:
    #         plog("Config uploaded successfully.")

    #     self.cool_down_latch = False
    #     self.nightly_reset_complete = True
    #     self.opens_this_evening=0
        
    #     self.keep_open_all_night = False
    #     self.keep_closed_all_night   = False          
    #     self.open_at_specific_utc = False
    #     self.specific_utc_when_to_open = -1.0  
    #     self.manual_weather_hold_set = False
    #     self.manual_weather_hold_duration = -1.0
        
    #     return



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

            
if __name__ == "__main__":
    pipe = PipeAgent(ptr_config.pipe_name, ptr_config.pipe_config)
    pipe.run()
