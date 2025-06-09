"""
A simple monitoring app that organising pipeline processing
and data ingesting on a PIPE computer

"""

# Startup app line for ubuntu
# Generally use a lightweight terminal
# xfce4 -- bash -c "python3 ~/PycharmProjects/ptrpipeline/thewatcher.py"

##### For linux pipes, you need to edit /etc/samba/smb.conf and set the following
##### to make sure permissions work properly
# [shared-folder]
# path = /mnt/PipeArchive/localptrarchive/
# browsable = yes
# writable = yes
# guest ok = yes
# create mask = 0777
# directory mask = 0777
# force user = nobody
# force group = nogroup

# But you must also set samba to only consider local network drives.


import json
import glob
import time 
import traceback
import datetime
import shutil
import subprocess
import psutil
import os
import random
from dotenv import load_dotenv
env=load_dotenv(".env")
import resource

import requests
from ocs_ingester.ingester import  validate_fits_and_create_archive_record, upload_file_to_file_store, ingest_archive_record

import threading
import queue

# Nobody gonna be changing RAM while the computer is running, so this is global
total_ram = psutil.virtual_memory().total

# Create a thread-safe queue
ingester_queue = queue.Queue()
maximum_parallel_ingestions= 16

# Need to randomly space out parallel ingestions via random delays
# target total rate (requests per second across all threads)
TOTAL_RATE = 16.0  
# so per‐thread rate is:
RATE_PER_THREAD = TOTAL_RATE / 16.0  # → 1 req/s

# Start worker threads
# Function to execute ingester items
def ingester_worker():
    while True:
        ingester_item = ingester_queue.get()  # Blocks if queue is empty
        if ingester_item is None:
            break  # Graceful exit signal
        try:
            ingester_item()
        except Exception as e:
            print(f"Ingesting item raised an exception: {e}")
        finally:
            ingester_queue.task_done()
def start_worker_threads():
    for _ in range(maximum_parallel_ingestions):
        threading.Thread(target=ingester_worker, daemon=True).start()
# Start workers
start_worker_threads()


known_ingester_jsons=[]

def preexec_limit():
    # # We need to detach and limit each pipeline call.
    limit = int(total_ram * 0.8)

    # apply as the address-space limit
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def process_ingester_directory(
    ingester_directory: str,
    failed_ingestion_directory: str) :
    """
    Scan ingester_directory for new .json files, remove any 'variance_' files,
    and schedule ingestion for the rest.

    Parameters
    ----------
    ingester_directory : str
        Path to the directory containing ingester JSON files (should end with a slash).
    
    failed_ingestion_directory : str
        Path to the directory where failed ingestions should be moved/logged.
    add_ingester_item : Callable
        Function that takes a zero-argument callable and schedules it for ingestion.
    ingest_item : Callable
        Function that actually performs ingestion; called with [item, ingester_directory, failed_ingestion_directory].
    """
    print("reading ingester directory")
    # pattern = os.path.join(ingester_directory, '*.json')
    # ingester_files_list = glob.glob(pattern)

    # for item in ingester_files_list:
    #     if item in known_ingester_jsons:
    #         continue

    #     if 'variance_' in os.path.basename(item):
    #         print(f"removing variance item: {item}")
    #         try:
    #             os.remove(item)
    #         except OSError:
    #             pass
    #         # also remove the unpacked version if it exists
    #         unpacked = item.replace('.json', '')
    #         try:
    #             os.remove(unpacked)
    #         except OSError:
    #             pass
    #     else:
    #         # schedule this new item for ingestion
    #         add_ingester_item(lambda item=item: ingest_item([item, ingester_directory, failed_ingestion_directory]))
    #         known_ingester_jsons.append(item)
    
    # # Keep known_ingester_jsons tidy now that any known existing files are in the queue
    # for item in known_ingester_jsons:
    #     if not item in ingester_files_list:
    #         known_ingester_jsons.remove(item)
    
    # 1) scan for JSONs and get their mtime efficiently
    entries = [
        entry
        for entry in os.scandir(ingester_directory)
        if entry.name.endswith('.json')
    ]
    
    # 2) sort ascending by mtime → oldest first
    entries.sort(key=lambda e: e.stat().st_mtime)
    
    # 3) only look at the 500 oldest
    for entry in entries[:500]:
        item = entry.path
    
        if item in known_ingester_jsons:
            continue
    
        if 'variance_' in entry.name:
            print(f"removing variance item: {item}")
            try:
                os.remove(item)
            except OSError:
                pass
    
            # also remove the unpacked version if it exists
            unpacked = item[:-5]  # strip “.json”
            try:
                os.remove(unpacked)
            except OSError:
                pass
    
        else:
            # schedule this new item for ingestion
            add_ingester_item(lambda item=item: ingest_item([item,
                                                              ingester_directory,
                                                              failed_ingestion_directory]))
            known_ingester_jsons.append(item)
    
    # 4) clean up known_ingester_jsons in one go
    known_ingester_jsons[:] = [
        item for item in known_ingester_jsons
        if os.path.exists(item)
    ]

# Function to add ingester items to the queue
def add_ingester_item(item):
    ingester_queue.put(item)

def ingest_item(item):
    file, ingester_directory, failed_ingestion_directory = item
    print ("Starting ingestion of " + str(file.replace('.pickle','').replace(ingester_directory,'')))
    
    try:
    
        tempfilename=str(file.replace('.json',''))
        # An empty sek, sea or psx file is actually size 50... so consider any file bigger than that. 
        if os.path.exists(tempfilename):
            if os.path.getsize(tempfilename) > 51:
                with open(file, 'r') as tempfile:
                    headerdict = json.load(tempfile)             
                
                with open(tempfilename, "rb") as fileobj:
                    try:
                        if not 'thumbnail' in tempfilename:
                            
                            record=validate_fits_and_create_archive_record(fileobj, file_metadata=headerdict)
                            time.sleep(random.expovariate(RATE_PER_THREAD))
                            s3_version=upload_file_to_file_store(fileobj, file_metadata=headerdict)
                            time.sleep(random.expovariate(RATE_PER_THREAD))
                            ingest_archive_record(s3_version,record)
                            time.sleep(random.expovariate(RATE_PER_THREAD))
                            try:
                                os.remove(file)
                            except:
                                print(traceback.format_exc())
                            try:
                                os.remove(tempfilename)
                            except:
                                print(traceback.format_exc())
                        else:
                            print ("OCS Ingester doesn't like thumbnail image: " + str(tempfilename))
                            # if dst exists, delete it                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+file.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+file.split('/')[-1])
                                shutil.move(file, failed_ingestion_directory+'/'+file.split('/')[-1])
                                try:
                                    os.remove(file)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())                 
                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+tempfilename.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+tempfilename.split('/')[-1])                              
                                shutil.move(tempfilename, failed_ingestion_directory+'/'+tempfilename.split('/')[-1])
                                try:
                                    os.remove(tempfilename)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())
                    except:
                       
                        if 'thumbnail' in tempfilename:
                            print ("Problematic thumbnail image: " + str(tempfilename))
                            # if dst exists, delete it                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+file.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+file.split('/')[-1])
                                shutil.move(file, failed_ingestion_directory+'/'+file.split('/')[-1])
                                try:
                                    os.remove(file)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())                 
                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+tempfilename.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+tempfilename.split('/')[-1])                              
                                shutil.move(tempfilename, failed_ingestion_directory+'/'+tempfilename.split('/')[-1])
                                try:
                                    os.remove(tempfilename)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())
                        
                        elif ('Version with this md5 already exists') in traceback.format_exc() and not 'thumbnail' in tempfilename:
                            print ("Version with this md5 already exists: " + str(tempfilename))
                            try:
                                os.remove(file)
                            except:
                                print(traceback.format_exc())
                            try:
                                os.remove(tempfilename)
                            except:
                                print(traceback.format_exc())
                        elif ('502 Server Error') in traceback.format_exc() and not 'thumbnail' in tempfilename:
                            print ("502 Server Error. Backing off and waiting. Putting file back into queue: "+ str(tempfilename))
                            time.sleep(1)
                            add_ingester_item(lambda item=file: ingest_item([item, ingester_directory, failed_ingestion_directory]))
                        elif ('500 Server Error') in traceback.format_exc() and not 'thumbnail' in tempfilename:
                            print ("500 Server Error. Backing off and waiting. Putting file back into queue: "+ str(tempfilename))
                            time.sleep(1)
                            add_ingester_item(lambda item=file: ingest_item([item, ingester_directory, failed_ingestion_directory]))
                        elif ('400 Client Error') in traceback.format_exc() and not 'thumbnail' in tempfilename:
                            print ("400 Server Error. Copying file to fails directory")
                                                                                   
                            # if dst exists, delete it                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+file.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+file.split('/')[-1])
                                shutil.move(file, failed_ingestion_directory+'/'+file.split('/')[-1])
                                try:
                                    os.remove(file)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())                 
                            
                            try:
                                if os.path.exists(failed_ingestion_directory +'/'+tempfilename.split('/')[-1]):
                                    os.remove(failed_ingestion_directory +'/'+tempfilename.split('/')[-1])                              
                                shutil.move(tempfilename, failed_ingestion_directory+'/'+tempfilename.split('/')[-1])
                                try:
                                    os.remove(tempfilename)
                                except:
                                    pass
                            except:
                                print(traceback.format_exc())
                            
                        elif ('Max retries exceeded') in traceback.format_exc() and not 'thumbnail' in tempfilename:
                            print ("Max retries error. Backing off and waiting. Putting file back into queue: "+ str(tempfilename))
                            time.sleep(1)
                            add_ingester_item(lambda item=file: ingest_item([item, ingester_directory, failed_ingestion_directory]))
            else:
                print (tempfilename + " too small, skipping ingestion.")
                try:
                    os.remove(file)
                    os.remove(tempfilename)
                except:
                    print(traceback.format_exc())
        else:
            print (tempfilename + " not found, skipping ingestion.")
            try:
                os.remove(file)
                os.remove(tempfilename)
            except:
                print(traceback.format_exc())
        
    except:
        print(traceback.format_exc())
    
def wait_for_resources(memory_fraction=40, cpu_fraction=40, wait_for_harddrive=False, workdrive='none', ingester_directory='none',failed_ingestion_directory='none'):
    
    # A delaying mechanism that will random push itself forward in the future
    # but at some point... the show must go on! So it will release itself. 
    # It is possible for things to stall for hours if it just waits forever
    # But if it barges itself into the proceedings it can at least keep moving
    # and get there in the end. 
        
    random_timeout_period= random.randint(1800, 7200)
    
    file_wait_timeout_timer=time.time()
    vert_timer=time.time()
    if wait_for_harddrive:
        
        cpu_usage=psutil.cpu_percent(interval=1)
        memory_usage=psutil.virtual_memory().percent
        hard_drive_usage=hard_drive_activity(workdrive)
        
        
        while memory_usage > memory_fraction or cpu_usage > cpu_fraction and (time.time()-file_wait_timeout_timer < random_timeout_period) and hard_drive_usage > 10000:       
            
            if time.time()-vert_timer > 30:
                print('Waiting: Mem: ' + str(memory_usage) + ' CPU: '+ str(cpu_usage) + "HD: "+str(hard_drive_usage) + " " + str(datetime.datetime.now()))
                vert_timer=time.time()
                # We want to still be ingesting stuff while we are waiting!
                process_ingester_directory(ingester_directory,failed_ingestion_directory)
            time.sleep(1)
            cpu_usage=psutil.cpu_percent(interval=1)
            memory_usage=psutil.virtual_memory().percent
            hard_drive_usage=hard_drive_activity(workdrive)
            
    else:
        cpu_usage=psutil.cpu_percent(interval=1)
        memory_usage=psutil.virtual_memory().percent
        while memory_usage > memory_fraction or cpu_usage > cpu_fraction and (time.time()-file_wait_timeout_timer < random_timeout_period):       
            
            if time.time()-vert_timer > 30:
                print('Waiting: Mem: ' + str(memory_usage) + ' CPU: '+ str(cpu_usage)+ " " + str(datetime.datetime.now()))
                # We want to still be ingesting stuff while we are waiting!
                process_ingester_directory(ingester_directory,failed_ingestion_directory)
                vert_timer=time.time()
            time.sleep(1)
            cpu_usage=psutil.cpu_percent(interval=1)
            memory_usage=psutil.virtual_memory().percent

def hard_drive_activity(drive):
    output = subprocess.check_output(["iostat","-y" ,"5","1","|","grep",drive])#, shell=True)
    output = str(output).split(drive)[-1].split(' ')
    while("" in output):
         output.remove("")
    print ("Hard Drive activity at " + str(drive) + " : " + str(float(output[2])))
    return float(output[2])
     
def find_and_delete_oldest_file(directory):
    oldest_file = None
    oldest_time = float('inf')

    # Use scandir for faster traversal
    for root, dirs, files in os.walk(directory):
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.is_file():
                    try:
                        # Get the file's modification time directly from DirEntry
                        file_time = entry.stat().st_mtime

                        # Check if this is the oldest file
                        if file_time < oldest_time:
                            oldest_time = file_time
                            oldest_file = entry.path
                    except FileNotFoundError:
                        continue

    # Delete the oldest file
    if oldest_file:
        print(f"Oldest file: {oldest_file}")
        os.remove(oldest_file)
        print(f"Deleted: {oldest_file}")
    else:
        print("No files found in the directory.")
    
def launch_eva_pipeline(token: str,
                        requested_task_content: list[str],
                        processing_temp_directory: str,
                        pipeid: str,
                        EVA_py_directory: str,
                        local_calibrations_directory: str,
                        site_name: str):
    """
    Prepare a per-token temp dir, dump info_for_EVA.json, copy code, write a runner script,
    and launch EVApipeline.py in its own process group.
    Returns (subprocess.Popen, info_for_EVA dict).
    """
    # Build & clean temp dir
    token_temp_directory = os.path.join(processing_temp_directory, token.split('/')[-1])
    if os.path.isdir(token_temp_directory):
        shutil.rmtree(token_temp_directory)
    os.makedirs(token_temp_directory, mode=0o777, exist_ok=True)

    # Build info dict
    first_file = requested_task_content[0]
    parts = first_file.split('-')
    info_for_EVA = {
        'filter': 'na',
        'calib_directory': local_calibrations_directory,
        'files_to_process': requested_task_content,
        'run_date': parts[2],
        'telescope': parts[0],
        'camera_name': parts[1].split('_')[0],
        'is_osc': 'mono',
        'pipeid': pipeid,
        'token_temp_directory': token_temp_directory,
        'original_token_file': token,
        'file_location_expected': 'ptrarchive'
    }

    # Dump settings
    info_path = os.path.join(token_temp_directory, 'info_for_eva.json')
    with open(info_path, 'w') as f:
        json.dump(info_for_EVA, f, indent=2)

    # 4) Copy pipeline code & resources
    shutil.copy(os.path.join(EVA_py_directory, 'EVApipeline.py'),
                token_temp_directory)
    shutil.copy(os.path.join(EVA_py_directory, 'modules/archive_file_input_classes.py'),
                token_temp_directory)
    shutil.copytree(os.path.join(EVA_py_directory, 'modules'),
                    os.path.join(token_temp_directory, 'modules'),
                    dirs_exist_ok=True)
    shutil.copytree(os.path.join(EVA_py_directory, 'configs'),
                    os.path.join(token_temp_directory, 'configs'),
                    dirs_exist_ok=True)

    # Write the bash runner
    runner_path = os.path.join(token_temp_directory, 'EVAscriptrunner')
    with open(runner_path, 'w') as f:
        f.write('#!/bin/bash\n')
        if site_name != 'eco':
            f.write('source ~/.bash_profile\n')
        f.write('/usr/bin/python3 EVApipeline.py na na generic na na na '+str(pipeid)+' >> log.txt\n')
    os.chmod(runner_path, 0o755)
    
    popen = subprocess.Popen(
        ["/bin/bash", runner_path],
        cwd=token_temp_directory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=preexec_limit,     
        start_new_session=True       
    )

    return popen, info_for_EVA

def main():

    # Expand '~' to the user's home directory
    # home_directory = os.path.expanduser("~")

    # # Use the expanded path in glob
    # files = glob.glob(f"{home_directory}/watcher*")

    # site_name=files[0].split('_')[-1]

    script_dir = os.path.dirname(os.path.abspath(__file__))  
    config_path = os.path.join(script_dir, 'config.json')
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    pipe_id = config['pipe_id'] 

    pipe_queue_timer=time.time() - 300

    if pipe_id=='arolinux':
        with open('/home/mrcpipeline/.bash_profile') as f:
            lines = f.readlines()
        
        archive_base_directory = '/archive'
        
        #Which pipe is this running on
        # Makes a different to the EVA settings
        evapipeid = 'arolinux'
     
        # link to github directory with latest pipeline file
        EVA_py_directory= '/home/mrcpipeline/Documents/GitHub/EVA_Pipeline/'
        ingester_directory= '/archive/Ingestion/'
        failed_ingestion_directory= '/archive/FailedIngestion/'
        
    elif pipe_id=='mrc':
        with open('/home/mrcpipeline/.bash_profile') as f:
            lines = f.readlines()
        
        archive_base_directory = '/archive'
        #Which pipe is this running on
        # Makes a different to the EVA settings
        evapipeid = 'mrcpipe'
     
        # link to github directory with latest pipeline file
        EVA_py_directory= '/home/mrcpipeline/PycharmProjects/EVA_Pipeline/'
        ingester_directory= '/archive/Ingestion/'
        failed_ingestion_directory= '/archive/FailedIngestion/'
        
    elif pipe_id=='eco':
        try: 
            with open('/home/ecopipeline/.bash_profile') as f:
                lines = f.readlines()
        except:
            pass
            
        archive_base_directory = '/mnt/PipeArchive/'
        #Which pipe is this running on
        # Makes a different to the EVA settings
        evapipeid = 'ecopipe'
     
        # link to github directory with latest pipeline file
        EVA_py_directory= '/home/ecopipeline/PycharmProjects/EVA_Pipeline/'
        ingester_directory= '/mnt/PipeArchive/Ingestion/'
        failed_ingestion_directory= '/mnt/PipeArchive/FailedIngestion/'
                
    try:
        for line in lines:
            goog = line.replace('export ','').replace('\n','').split('=')
            #print (goog)
            os.environ[goog[0]]=goog[1]  
    except:
        print(traceback.format_exc())
        breakpoint()
    
    
    processing_temp_directory=archive_base_directory + '/realtime_temp/'
    local_calibrations_directory=archive_base_directory + '/localptrarchive/calibrations/'
    
    # Base paths
    base = archive_base_directory
    monitor_directories = [f"{base}/localptrarchive/tokens"]
    
    # All directories you need to create
    dirs = [
        f"{base}/localptrarchive",
        *monitor_directories,
        ingester_directory,
        failed_ingestion_directory,
        processing_temp_directory,
        local_calibrations_directory,
        f"{base}/realtime_temp",
        f"{base}/localptrarchive/calibrations",
    ]
    
    # Create them with one-liners
    for d in dirs:
        os.makedirs(d, mode=0o777, exist_ok=True)
    
    # Array of completed tokens
    completed_tokens=[]
    
    check_archive_hard_drive_usage_period= 300
    check_archive_hard_drive_usage_timer=time.time() - (2*check_archive_hard_drive_usage_period)
    
    # Simple watcher loop    
    while True:
                    
        # Check archive hard drive and cull.
        if time.time() - check_archive_hard_drive_usage_timer > check_archive_hard_drive_usage_period:
            print ("checking archive usage")
            # reset timer
            check_archive_hard_drive_usage_timer=time.time() 
            # Check disk space
            total, used, free =shutil.disk_usage(archive_base_directory)
            diskspace_Free=free/total
            print ("Diskspace Free: " + str(diskspace_Free * 100) + '%')
            while diskspace_Free < 0.2:
                find_and_delete_oldest_file(archive_base_directory+'/localptrarchive')
                find_and_delete_oldest_file(archive_base_directory+'/EVAreducedfiles')
                total, used, free =shutil.disk_usage(archive_base_directory)
                diskspace_Free=free/total    
        
        if pipe_id=='mrc':
            current_date_for_folder_construction= str(datetime.datetime.now()).split(' ')[0].replace('-','')
            if not os.path.exists(archive_base_directory +'/localptrarchive/sq003ms'):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/sq003ms', mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/sq003ms/'+current_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/sq003ms/'+current_date_for_folder_construction, mode=0o777)
                
            if not os.path.exists(archive_base_directory +'/localptrarchive/sq101sm'):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/sq101sm', mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/sq101sm/'+current_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/sq101sm/'+current_date_for_folder_construction, mode=0o777)
        
        
        if pipe_id=='eco':
            current_date_for_folder_construction= str(datetime.datetime.now()).split(' ')[0].replace('-','')
            tomorrows_date_for_folder_construction= str(datetime.datetime.now() + datetime.timedelta(days=1)).split(' ')[0].replace('-','')
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec002cs'):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec002cs', mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec002cs/'+current_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec002cs/'+current_date_for_folder_construction, mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec002cs/'+tomorrows_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec002cs/'+tomorrows_date_for_folder_construction, mode=0o777)
        
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec003zwo'):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec003zwo', mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec003zwo/'+current_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec003zwo/'+current_date_for_folder_construction, mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/ec003zwo/'+tomorrows_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/ec003zwo/'+tomorrows_date_for_folder_construction, mode=0o777)
            
            
            if not os.path.exists(archive_base_directory +'/localptrarchive/eco3zwo'):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/eco3zwo', mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/eco3zwo/'+current_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/eco3zwo/'+current_date_for_folder_construction, mode=0o777)
            if not os.path.exists(archive_base_directory +'/localptrarchive/eco3zwo/'+tomorrows_date_for_folder_construction):
                os.umask(0)
                os.makedirs(archive_base_directory +'/localptrarchive/eco3zwo/'+tomorrows_date_for_folder_construction, mode=0o777) 
        
        
        # Make sure we don't go over the diskspace limit while downloading
        while True:
            total, used, free = shutil.disk_usage(processing_temp_directory)
            if (used / total) < 0.8:
                break        
            print("Waiting for diskspace to clear.")
            print("Total: %d GiB" % (total // (2 ** 30)))
            print("Used: %d GiB" % (used // (2 ** 30)))
            print("Free: %d GiB" % (free // (2 ** 30)))      
            time.sleep(30)    
        
        
        # Here is the testing area for the PIPE communication code
        # CURRENTLY NOT UNDER OPERATION, BUT WE CAN USE IT IN THE FUTURE
        if False and pipe_id=='eco' and (time.time()- pipe_queue_timer) > 30:
            pipe_queue_timer=time.time()
            print ("Checking PIPE QUUEUE")
            #Here check if queue exists and if not, create it.
            if False:
                uri_status = "https://api.photonranch.org/api/pipe/queue"
                # NB None of the strings can be empty. Otherwise this put faults.
                payload = {"queue_name": "lcs1"}
            
                data = json.dumps(payload)
                try:                
                    response = requests.post(uri_status, data=data, timeout=20)        
                    if response.ok:
                       # pass
                       print("~")
                       print (response)
                except:
                    print ("Whoaeut")     
    
            try:
                # Check in on the queues
                uri_status = "https://api.photonranch.org/api/pipe/queue/lcs1/dequeue"
                response = requests.post(uri_status,timeout=20)# allow_redirects=False, headers=close_headers)
                print (response)
                print (response.content)
                            
                print ('404' in str(response))  
                  
                if not '404' in str(response):
                    print ("WE GOT SOMETHING!")
                    pipe_queue_timer=time.time()-300
                    json_string = response.content.decode('utf-8')
                    data = json.loads(json_string)
                    token = data['id']
                    requested_task=data['payload']['request']
                    requested_task_content=data['payload']['request_content']
                    
                    print (requested_task)
                    print (requested_task_content)
                    
                    if len(requested_task_content) == 1:
                        if requested_task_content[0] == '':
                            print ("we have found a blank one!!")
                    
                    elif requested_task == 'EVA_process_files':
                        popen, info = launch_eva_pipeline(
                            token=token,
                            requested_task_content=requested_task_content,
                            processing_temp_directory=processing_temp_directory,
                            pipeid=evapipeid,
                            EVA_py_directory=EVA_py_directory,
                            local_calibrations_directory=local_calibrations_directory,
                            site_name=pipe_id
                        )
                        print("Launched PID:", popen.pid)
                        print("EVA info:", info)
            except:
                print ("Hit a snag somewhere? ")
                print(traceback.format_exc())
                                
        process_ingester_directory(ingester_directory,failed_ingestion_directory)
        
        print ("reading tokens")
        print (datetime.datetime.now())
        
        # # Check there is new stuff in the local directory
        # tokens_in_directory=glob.glob(monitor_directories[0]+ '/*')
        # # If so, chuck them in the queue and keep track of the completed tokens
        # # Queue items: list of filenames, links to calibration frames, telescope, cameraname, filterlist, mono, aropipe
        # wait_for_resources(ingester_directory=ingester_directory,failed_ingestion_directory=failed_ingestion_directory)
        # for token in tokens_in_directory:
            
        #     if not token in completed_tokens:
        #         try:
        #             with open(token, 'r') as f:
        #                 token_contents = json.load(f)
        #             if len(token_contents) > 0:
                        
        #                 print (len(token_contents))
        #                 print ("*************")
        #                 print (token)
        #                 print (token_contents)                    
                    
        #                 popen, info = launch_eva_pipeline(
        #                     token=token,
        #                     requested_task_content=token_contents,
        #                     processing_temp_directory=processing_temp_directory,
        #                     pipeid=evapipeid,
        #                     EVA_py_directory=EVA_py_directory,
        #                     local_calibrations_directory=local_calibrations_directory,
        #                     site_name=pipe_id
        #                 )
                        
        #                 completed_tokens.append(token)
        #                 break # Only do one token at a time, after each non-zero token go through the activity checker
                        
        #             completed_tokens.append(token)
                    
        #         except:
        #             print ("Bug with this particular token")
        #             print (token)
        #             print(traceback.format_exc())
        #             completed_tokens.append(token)
        
        monitor_dir = monitor_directories[0]
        completed = set(completed_tokens)
        
        # find the one oldest file not yet done
        with os.scandir(monitor_dir) as it:
            # generator of DirEntry objects for files not in completed
            candidates = (
                entry for entry in it
                if entry.is_file() and entry.path not in completed
            )
            try:
                oldest = min(candidates, key=lambda e: e.stat().st_mtime)
            except ValueError:
                # no new files
                oldest = None
        
        if oldest:
            token = oldest.path
            try:
                with open(token) as f:
                    token_contents = json.load(f)
                if token_contents:
                    print(len(token_contents))
                    print("*************")
                    print(token)
                    print(token_contents)
        
                    popen, info = launch_eva_pipeline(
                        token=token,
                        requested_task_content=token_contents,
                        processing_temp_directory=processing_temp_directory,
                        pipeid=evapipeid,
                        EVA_py_directory=EVA_py_directory,
                        local_calibrations_directory=local_calibrations_directory,
                        site_name=pipe_id
                    )
        
                # mark done regardless of contents
                completed.add(token)
        
            except Exception:
                print("Bug with this particular token:", token)
                traceback.print_exc()
                completed.add(token)
                
if __name__ == "__main__":
    main()
