# -*- coding: utf-8 -*-
"""
Created on Sun Dec 11 23:27:31 2016

@author: obs

This code is confusing because it is mixing degree, hour and radian measure in
a way that is not obvious.  Hungarian might help here or append _d, _r, _h, _am, _as, _m, _s
Conversion constants could be CAP-case as in R2D, R2AS, H2S, etc.

"""

from collections import namedtuple
from datetime import datetime, date
import math
import os
import shelve
import time

from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, ICRS, EarthLocation
from astroquery.simbad import Simbad
import ephem
#from ptr_events import compute_day_directory
#breakpoint()
from wema_config import wema_config
from global_yard import g_dev

from datetime import datetime, timezone, timedelta
from dateutil import tz

siteCoordinates = EarthLocation(
    lat=wema_config["latitude"] * u.deg,
    lon=wema_config["longitude"] * u.deg,
    height=wema_config["elevation"] * u.m,
)

# siteCoordinates = EarthLocation(
#     lat=wema_config["site_latitude"] * u.deg,
#     lon=wema_config["site_longitude"] * u.deg,
#     height=wema_config["site_elevation"] * u.m,
# )

Target = namedtuple(
    "Target", ["ra", "dec", "name", "simbad", "obj", "mag", "size", "pa", "ly", "cdist"]
)  # last a string with unit

DEG_SYM = "°"
PI = math.pi
TWOPI = math.pi * 2
PIOVER2 = math.pi / 2.0
DTOR = math.pi / 180.0
RTOD = 180 / math.pi
STOR = math.pi / 180.0 / 3600.0
RTOS = 3600.0 * 180.0 / math.pi
RTOH = 12.0 / math.pi
HTOR = math.pi / 12.0
HTOS = 15 * 3600.0
DTOS = 3600.0
STOD = 1 / 3600.0
STOH = 1 / 3600 / 15.0
SecTOH = 1 / 3600.0
APPTOSID = 1.00273811906  # USNO Supplement
MOUNTRATE = 15 * APPTOSID  # 15.0410717859
KINGRATE = 15.029

try:
    RefrOn = wema_config["mount"]["mount1"]["settings"]["refraction_on"]
    ModelOn = wema_config["mount"]["mount1"]["settings"]["model_on"]
    RatesOn = wema_config["mount"]["mount1"]["settings"]["rates_on"]
except:
    RefrOn = False
    ModelOn = False
    RatesOn = False

HORIZON = 9.999  # Lower than actual mrc values.
ALTAZ = False

if ALTAZ:
    MOUNT = "PW L500"
    INTEGRATOR_SIZE = 3
else:
    MOUNT = "AP1600GOTO"
    INTEGRATOR_SIZE = 3

model = {}  # Note model starts out zero, need to persist actual model.
wmodel = {}

# NB Currently this is where the working model is stored.
model["IH"] = 0
model["ID"] = 0
model["WH"] = 0
model["WD"] = 0
model["MA"] = 0
model["ME"] = 0
model["CH"] = 0  # Value not clear after a flip.
model["NP"] = 0
model["TF"] = 0
model["TX"] = 0
model["HCES"] = 0
model["HCEC"] = 0
model["DCES"] = 0.0
model["DCEC"] = 0.0

wmodel["IH"] = 0.0
wmodel["ID"] = 0.0
wmodel["WH"] = 0.0
wmodel["WD"] = 0.0
wmodel["MA"] = 0.0
wmodel["ME"] = 0.0
wmodel["CH"] = 0.0
wmodel["NP"] = 0.0
wmodel["TF"] = 0.0
wmodel["TX"] = -0.0
wmodel["HCES"] = 0.0
wmodel["HCEC"] = 0.0
wmodel["DCES"] = 0.0
wmodel["DCEC"] = 0.0

model["IA"] = 0
model["IE"] = 0
model["AN"] = 0
model["AW"] = 0
model["CA"] = 0
model["NPAE"] = 0
model["ACES"] = 0
model["ACEC"] = 0
model["ECES"] = 0
model["ECEC"] = 0

modelChanged = False

# Transfer globals for G_ptr_utility. This is terrible form!
raCorr = 0.0
decCorr = 0.0
raRefr = 0.0
decRefr = 0.0
refAsec = 0.0
raVel = 0.0
decVel = 0.0

# A series of useful module globals:
jYear = None
JD = None
MJD = None
unixEpochOf = None
jEpoch = 2018.3
gSimulationOffset = 0
gSimulationFlag = False
gSimulationStep = 120  # seconds.



# intDay = int(ephem.now())
# dayFrac = ephem.now() - intDay
# if dayFrac < 0.20833:
#     dayNow = intDay - 0.55
# else:
#     dayNow = intDay + 0.45
# ephem.date = ephem.Date(dayNow)
# dayStr = str(ephem.date).split()[0]
# dayStr = dayStr.split("/")
# #print("Day String", dayStr)
# if len(dayStr[1]) == 1:
#     dayStr[1] = "0" + dayStr[1]
# if len(dayStr[2]) == 1:
#     dayStr[2] = "0" + dayStr[2]

#DAY_Directory = dayStr[0] + dayStr[1] + dayStr[2]



DAY_Directory= g_dev['day']


now_utc = datetime.now(timezone.utc) # timezone aware UTC, shouldn't depend on clock time.
to_zone = tz.gettz(wema_config['TZ_database_name'])
now_here = now_utc.astimezone(to_zone)
int_sunrise_hour=ephem.Observer().next_rising(ephem.Sun()).datetime().hour + 1
if int(now_here.hour) < int_sunrise_hour:
    now_here = now_here - timedelta(days=1)
DAY_Directory = str(now_here.year) + str(now_here.month) + str(now_here.day)

try:
    if not os.path.exists(wema_config['plog_path']  + 'plog/'):
        os.makedirs(wema_config['plog_path']  + 'plog/')
    plog_path = wema_config['plog_path']  + 'plog/' + DAY_Directory + '/'

except KeyError:
    try:
        #plog_path = wema_config['archive_path'] + '/' + wema_config['obs_id'] + '/' + DAY_Directory + '/'
        if not g_dev['obs'].obsid_path  + 'plog/':
            os.makedirs(g_dev['obs'].obsid_path + 'plog/')
        plog_path = g_dev['obs'].obsid_path + 'plog/' + DAY_Directory + '/'
    except:
        if not wema_config['archive_path'] + '/' + wema_config['obs_id'] + '/'  + 'plog/':
            os.makedirs(wema_config['archive_path'] + '/' + wema_config['obs_id'] + '/' + 'plog/')
        plog_path = wema_config['archive_path'] + '/' + wema_config['obs_id'] + '/' + 'plog/' + DAY_Directory + '/'

os.makedirs(plog_path, exist_ok=True)

print (plog_path)


# Here is the key code to update a parallel GUI module. These are
# referenced via GUI module via a dedicated import of utility as _ptr_utility.
# NOTE these must be set up by the Gui

ui = None  # for reference to GUI elements
doEvents = None  # path to QApplication.updateEvent function.
modelChanged = False
last_args = ()

def plog(*args, loud = True):
    '''
    loud not used, consider adding an optional incoming module
    and error level, also make file format compatible with csv.
    '''

    try:
        if len(args) == 1 and args[0] in ['.', '>']:
            print(args[0])
            return
        args_to_str = ''
        exposure_report = False
        for item in args:
            item_to_string = str(item)
            if item_to_string[-1] == ' ':
                args_to_str += str(item)
            else:
                args_to_str += str(item) + ' '  #  Add space between fields
        args_to_str = args_to_str.strip()   #Eliminate trailing space.
        # ToDo  Need to strip unnecessary line feeds  '\n'
        if args_to_str[:4] == '||  ':
            exposure_report = True
            args_to_str = args_to_str[4:]
        print(args_to_str)
        if not exposure_report:
            d_t = str(datetime.utcnow()) + ' '
            with open(plog_path + 'nightlog.txt', 'a') as file:
                file.write(d_t + " " + args_to_str +'\n')

    except:
        print("plog failed to convert to string:  ", args)

    #Add logging here.

    return

def zeroModel():
    global modelChanged
    model = {}  # Note model starts out zero
    model["IH"] = 0
    model["ID"] = 0
    model["WH"] = 0
    model["WD"] = 0
    model["MA"] = 0
    model["ME"] = 0
    model["CH"] = 0
    model["NP"] = 0
    model["TF"] = 0
    model["TX"] = 0
    model["HCES"] = 0
    model["HCEC"] = 0
    model["DCES"] = 0
    model["DCEC"] = 0
    model["IA"] = 0
    model["IE"] = 0
    model["AN"] = 0
    model["AW"] = 0
    model["CA"] = 0
    model["NPAE"] = 0
    model["ACES"] = 0
    model["ACEC"] = 0
    model["ECES"] = 0
    model["ECEC"] = 0
    modelChanged = False
    return model


modelChanged = False


def ephemSimNow(offset=None):
    local = ephem.now()
    if gSimulationFlag:
        local += gSimulationOffset / 86400.0
    if offset is not None:
        local += float(offset) / 86400.0
    return round(local, 5)


def updateGui():  # What to call from non-GUI modules.
    if doEvents is not None:
        doEvents()


def sleepEvents(pTime):  # Updates GUI often but still returns the required
    st = time.time()  # delay to caller. Essentially a non-blocking sleep.
    try:
        updateGui()
    except:
        pass
    # pTime = round(pTime, 2)
    while time.time() < st + pTime:
        time.sleep(0.05)
        try:
            updateGui()
        except:
            pass
        continue
    try:
        updateGui()
    except:
        pass


# the init>>> below take a list, query Simbad and assemble currently accurate
# are discarded becuase they are never visible. The point of these lists
# to to chache the Simbad lookup for speed.

targetList = []
typeList = []
sky2000_list = []


def initNavStars():
    """
    Get a list of very bright stars, plus a few others, and cull any too
    low to be visible.

    Also obtain official Simbad star name
    """
    global targetList
    targetList = []
    nav = open("navigation.txt", "r")
    j = Simbad()
    j.add_votable_fields("pmra", "pmdec")
    for line in nav:
        entry = line.split(",")
        sub = None
        # The following names are not regognized by Simbad. So we fake them.
        if entry[0] == "Eltanin":
            sub = "Eltanin"
            entry[0] = "gam Dra"
        if entry[0] == "Rigil Kentaurus":
            sub = "Rigil Kentaurus"
            entry[0] = "alpha Cen"
        if entry[0] == "Hadar":
            sub = "Hadar"
            entry[0] = "bet Cen"
        if entry[0] == "Gienah":
            sub = "Geinah"
            entry[0] = "gam Crv"

        h = j.query_object(entry[0])
        time.sleep(0.250)
        if sub is not None:
            entry[0] = sub

        cullDec = -(90 - siteLatitude - HORIZON / 2.0)
        if float(fromTableDMS(h["DEC"].data[0])) <= cullDec:
            continue
        targetList.append(
            (
                fromTableHMS(h["RA"].data[0]),
                fromTableDMS(h["DEC"].data[0]),
                "*" + entry[0],
                h["MAIN_ID"].data[0].decode(),
            )
        )
    make_target_list("Navigation Stars")
    return targetList


def initSky2000():
    global target_list
    target_list = []
    sky2000_handle = open("Q:\\astrocatalogs\\skycat\\SKYCAT.DAT", "rb")
    sky_names_handle = open("Q:\\astrocatalogs\\skycat\\NAMES.DAT", "rb")
    line_count = 1
    equator_count = 0
    named = 0
    eq = float(equinox_now[3:])
    for line in range(45269):  # 45269
        SAO = sky2000_handle.read(6).decode()
        ra = sky2000_handle.read(7).decode()
        ras = float(ra[-3:]) / 36000.0  # 36000 is correct.
        ram = float(ra[2:4]) / 60.0
        ra = float(ra[0:2]) + ram + ras

        dec = sky2000_handle.read(7).decode().strip()
        decsgn = dec.split("-")
        if len(decsgn) == 2:
            ds = -1
            decmag = int(decsgn[1])
        else:
            ds = 1
            decmag = int(decsgn[0])
        des = decmag % 100.0
        decmag = (decmag - des) // 100
        dem = decmag % 100
        decmag = (decmag - dem) // 100
        dec = ds * (decmag + dem / 60 + des / 3600)

        radot = sky2000_handle.read(5).decode()
        decdot = sky2000_handle.read(4).decode()

        vmag = sky2000_handle.read(4).decode()
        vmag = vmag[0:2] + "." + vmag[3:]
        try:
            fvmag = float(vmag)
        except:
            print("Err:  ", line)
        if vmag[0] == "-":
            pass
        inList = False
        if -0.2 <= int(dec) <= 0.2 and fvmag <= 6:

            if radot == "     ":
                radot = 0.0
            if decdot == "    ":
                decdot = 0.0
            radot = float(radot) * jNow / 1000 / 3600
            decdot = float(decdot) * jNow / 100 / 3600
            ra = reduceRa(ra + radot)
            dec = reduceDec(dec + decdot)
            print(equator_count, ra, ra + radot, dec, dec + decdot, vmag)
            target_list.append((ra, dec, str(equator_count), str(vmag).strip()))
            equator_count += 1

            inList = True
        b_v = sky2000_handle.read(4).decode()
        spec = sky2000_handle.read(2).decode()
        rv = sky2000_handle.read(4).decode()
        dist = sky2000_handle.read(4).decode()
        dist_flag = sky2000_handle.read(1).decode()
        index = sky2000_handle.read(4).decode()
        entry = ""
        if index != "    ":
            int_index = int(index)
            rec_size = 33
            vector = (int_index - 1) * rec_size
            sky_names_handle.seek(vector, 0)
            entry = sky_names_handle.read(rec_size).decode()
            if entry[0] != "A" and inList:
                named += 1

                print("         ", entry, named)  # , vmag, ra,  radot, dec, decdot)
                inList = False
        line_count += 1
        if line >= 45269:
            break
    sky2000_handle.close()
    sky_names_handle.close()
    return target_list


def init200stars():
    global targetList
    targetList = []
    big = open("TwoHundredStars.txt", "r+b")
    for line in big:
        entry = line.decode().strip().split()
        print(entry)
        h = Simbad.query_object(entry[0])
        cullDec = -(90 - siteLatitude - HORIZON / 2.0)
        print(h, "\n", cullDec, fromTableDMS(h["DEC"].data[0]))
        if float(fromTableDMS(h["DEC"].data[0])) <= cullDec:
            continue
        if "*" + entry[1] == "* ":
            targetList.append(
                (
                    fromTableHMS(h["RA"].data[0]),
                    fromTableDMS(h["DEC"].data[0]),
                    h["MAIN_ID"].data[0].decode(),
                    h["MAIN_ID"].data[0].decode(),
                    entry[-3],
                    entry[-2],
                    entry[-1],
                )
            )
        else:
            targetList.append(
                (
                    fromTableHMS(h["RA"].data[0]),
                    fromTableDMS(h["DEC"].data[0]),
                    "*" + entry[1],
                    h["MAIN_ID"].data[0].decode(),
                    entry[-3],
                    entry[-2],
                    entry[-1],
                )
            )
    make_target_list("200 Stars")
    return targetList


def init300stars():
    global targetList
    targetList = []
    big = open("ThreeHundredStars.txt", "r+b")
    triples = ("Majoris", "Minoris", "Borealis", "Australis", "Austrini", "Venaticorum")
    for line in big:
        entry = line.decode().strip().split()
        if len(entry) == 18:
            bayer = entry[1] + " " + entry[2]
            name = entry[3] + " " + entry[4] + " " + entry[5] + " " + entry[6]
            entry = entry[-11:]
        if len(entry) == 17:
            if entry[3] in triples:
                bayer = entry[1] + " " + entry[2] + " " + entry[3]
                name = entry[4] + " " + entry[5]
            else:
                bayer = entry[1] + " " + entry[2]
                name = entry[3] + " " + entry[4] + " " + entry[5]
            entry = entry[-11:]
        if len(entry) == 16:
            if entry[3] in triples:
                bayer = entry[1] + " " + entry[2] + " " + entry[3]
                name = entry[4]
            else:
                bayer = entry[1] + " " + entry[2]
                name = entry[3] + " " + entry[4]
            entry = entry[-11:]
        if len(entry) == 15:
            if entry[3] in triples:
                bayer = entry[1] + " " + entry[2] + " " + entry[3]
                name = None
            else:
                bayer = entry[1] + " " + entry[2]
                name = entry[3]
            entry = entry[-11:]
        if len(entry) == 14:
            if entry[3] in triples:
                bayer = entry[1] + " " + entry[2]
                name = None
            else:
                bayer = entry[1] + " " + entry[2]
                name = None
            entry = entry[-11:]
        if len(entry) == 13:
            if entry[3] in triples:
                bayer = entry[1] + " " + entry[2]
                name = "None"
            else:
                bayer = entry[1] + " " + entry[2]
                name = None
            entry = entry[-11:]
        h = Simbad.query_object(bayer)
        cullDec = -(90 - siteLatitude - HORIZON / 2.0)
        if float(fromTableDMS(h["DEC"].data[0])) <= cullDec:
            continue
        simName = h["MAIN_ID"].data[0].decode()
        if simName[0:4] == "NAME":
            simName = simName[4:]
        if simName[0] == "V":
            simName = simName[1:]
            if entry[5][-1] != "v":
                entry[-5] = entry[-5] + "v"
        if name is None:
            targetList.append(
                (
                    fromTableHMS(h["RA"].data[0]),
                    fromTableDMS(h["DEC"].data[0]),
                    simName,
                    simName,
                    " *",
                    entry[-6],
                    entry[-5],
                )
            )
        else:
            targetList.append(
                (
                    fromTableHMS(h["RA"].data[0]),
                    fromTableDMS(h["DEC"].data[0]),
                    name,
                    simName,
                    " *",
                    entry[-6],
                    entry[-5],
                )
            )
    big.close()
    make_target_list("300 Stars")
    return targetList


def initMessier():
    global targetList, typeList
    targetList = []
    mess = open("Messier.txt", "r")
    count = 0
    for obj in mess:
        entry = obj.split()
        if count < 19:
            ab = entry[0][:2]
            out = ""
            for word in range(len(entry[1:])):
                out += entry[1 + word] + " "
            out = out.strip()
            typeList.append((ab, out))
        if 19 <= count <= 128:
            h = Simbad.query_object(entry[0])
            cullDec = -(90 - siteLatitude - HORIZON / 2.0)
            if float(fromTableDMS(h["DEC"].data[0])) <= cullDec:
                continue
            if len(entry[12:]) > 0:
                out = ""
                for word in range(len(entry[12:])):
                    out += entry[12 + word] + " "
                targetList.append(
                    (
                        fromTableHMS(h["RA"].data[0]),
                        fromTableDMS(h["DEC"].data[0]),
                        out.strip(),
                        entry[0],
                        entry[2],
                        entry[3],
                        entry[4],
                    )
                )
            else:
                out = ""
                targetList.append(
                    (
                        fromTableHMS(h["RA"].data[0]),
                        fromTableDMS(h["DEC"].data[0]),
                        entry[0],
                        entry[0],
                        entry[2],
                        entry[3],
                        entry[4],
                    )
                )
        if 129 <= count:
            skip = False
            s = entry[1][0]
            if s == "*" or s == "-":
                skip = True
            elif s == "I":
                query = "IC " + entry[1][1:]
            elif s == "S":
                query = entry[1]
            else:
                query = "NGC " + entry[1]
            if not skip:
                h = Simbad.query_object(query)
                dec = float(fromTableDMS(h["DEC"].data[0]))
                ha = fromTableHMS(h["RA"].data[0])
            else:
                sgn = 1
                if entry[8][0] == "-":
                    sgn = -1
                dec = round(sgn * (float(entry[8][1:]) + float(entry[9]) / 60.0), 4)
                ha = round(float(entry[6]) + float(entry[7]) / 60.0, 5)
            cullDec = -(90 - siteLatitude - HORIZON / 2)
            if dec <= cullDec:
                continue
            if len(entry[12:]) > 0:
                out = ""
                for word in range(len(entry[12:])):
                    out += entry[12 + word] + " "
                if out.strip()[0:7] == "winter ":
                    out = out.strip()[7:]
                if not skip:
                    targetList.append(
                        (
                            fromTableHMS(h["RA"].data[0]),
                            fromTableDMS(h["DEC"].data[0]),
                            out.strip(),
                            query,
                            entry[2],
                            entry[3],
                            entry[4],
                        )
                    )
                else:
                    targetList.append(
                        (ha, dec, out.strip(), query, entry[2], entry[3], entry[4])
                    )
            else:
                out = ""
                if not skip:
                    targetList.append(
                        (
                            fromTableHMS(h["RA"].data[0]),
                            fromTableDMS(h["DEC"].data[0]),
                            entry[0],
                            query,
                            entry[2],
                            entry[3],
                            entry[4],
                        )
                    )
                else:
                    print(count, entry)
                    targetList.append((ha, dec, query, entry[2], entry[3], entry[4]))
        count += 1
    make_target_list("Messier-Caldwell")
    return targetList


def initParty():
    global targetList, typeList
    targetList = []
    mess = open("HRW20180408.txt", "r")
    count = 0
    for obj in mess:
        entry = obj.split()
        if count < 19:
            ab = entry[0][:2]
            out = ""
            for word in range(len(entry[1:])):
                out += entry[1 + word] + " "
            out = out.strip()
            typeList.append((ab, out))
        if 19 <= count <= 36:
            h = Simbad.query_object(entry[0])
            cullDec = -(90 - siteLatitude - HORIZON / 2.0)
            if float(fromTableDMS(h["DEC"].data[0])) <= cullDec:
                continue
            if len(entry[12:]) > 0:
                out = ""
                for word in range(len(entry[12:])):
                    out += entry[12 + word] + " "
                targetList.append(
                    (
                        fromTableHMS(h["RA"].data[0]),
                        fromTableDMS(h["DEC"].data[0]),
                        out.strip(),
                        entry[0],
                        entry[2],
                        entry[3],
                        entry[4],
                    )
                )
            else:
                out = ""
                targetList.append(
                    (
                        fromTableHMS(h["RA"].data[0]),
                        fromTableDMS(h["DEC"].data[0]),
                        entry[0],
                        entry[0],
                        entry[2],
                        entry[3],
                        entry[4],
                    )
                )
        if 37 <= count:
            skip = False
            s = entry[1][0]
            if s == "*" or s == "-":
                skip = True
            elif s == "I":
                query = "IC " + entry[1][1:]
            elif s == "S":
                query = entry[1]
            else:
                query = "NGC " + entry[1]
            if not skip:
                h = Simbad.query_object(query)
                dec = float(fromTableDMS(h["DEC"].data[0]))
                ha = fromTableHMS(h["RA"].data[0])
            else:
                sgn = 1
                if entry[8][0] == "-":
                    sgn = -1
                dec = round(sgn * (float(entry[8][1:]) + float(entry[9]) / 60.0), 4)
                ha = round(float(entry[6]) + float(entry[7]) / 60.0, 5)
            cullDec = -(90 - siteLatitude - HORIZON / 2)
            if dec <= cullDec:
                continue
            if len(entry[8:]) > 0:
                out = ""
                for word in range(len(entry[12:])):
                    out += entry[12 + word] + " "
                if out.strip()[0:7] == "winter ":
                    out = out.strip()[7:]
                if not skip:
                    targetList.append(
                        (
                            fromTableHMS(h["RA"].data[0]),
                            fromTableDMS(h["DEC"].data[0]),
                            out.strip(),
                            query,
                            entry[2],
                            entry[3],
                            entry[4],
                        )
                    )
                else:
                    targetList.append(
                        (ha, dec, entry[0], out.strip(), entry[2], entry[3], entry[4])
                    )
            else:
                out = ""
                if not skip:
                    targetList.append(
                        (
                            fromTableHMS(h["RA"].data[0]),
                            fromTableDMS(h["DEC"].data[0]),
                            entry[0],
                            query,
                            entry[2],
                            entry[3],
                            entry[4],
                        )
                    )
                else:
                    targetList.append(
                        (ha, dec, entry[0], query, entry[2], entry[3], entry[4])
                    )
        count += 1
    make_target_list("HRW20180408")
    return targetList


# Creates a shelved preculled target list.
def make_target_list(targetListName):
    global targetList
    targetShelf = shelve.open("Q:\\ptr_night_shelf\\" + str(targetListName))
    targetShelf["Targets"] = targetList
    targetShelf.close()
    return targetList


def get_target_list(targetListName):
    global targetList
    targetShelf = shelve.open("Q:\\ptr_night_shelf\\" + str(targetListName))
    targetList = targetShelf["Targets"]
    targetShelf.close()
    return targetList


def distSortTargets(pRa, pDec, pSidTime):
    """
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    """
    global targetList

    c1 = SkyCoord(ra=pRa * u.hr, dec=pDec * u.deg)
    sortedTargetList = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            c2 = SkyCoord(ra=star[0] * u.hr, dec=star[1] * u.deg)
            sep = c1.separation(c2)
            sortedTargetList.append((sep.degree, star))
    sortedTargetList.sort()
    return sortedTargetList


def zSortTargets(pRa, pDec, pSidTime):
    """
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    """
    global targetList
    c1 = SkyCoord(ra=pRa * u.hr, dec=pDec * u.deg)
    sortedNavList = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            c2 = SkyCoord(ra=star[0] * u.hr, dec=star[1] * u.deg)
            sep = c1.separation(c2)
            sortedNavList.append((sep.degree, star))
    sortedNavList.sort()
    return sortedNavList


def haSortTargets(pSidTime):
    """
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    """
    global targetList
    haSortedTargets = []
    for star in targetList:
        if horizonCheck(star[0], star[1], pSidTime):
            ha = reduceHa(pSidTime - star[0])
            haSortedTargets.append((ha, star))
    haSortedTargets.sort()
    haSortedTargets.reverse()
    return haSortedTargets


def riseSortTargets(pRa, pDec, pSidTime):
    """
    Given incoming Ra and Dec produce a list of tuples sorted by distance
    of Nav Star from that point, closest first. In additon full site
    Horizon cull is applied.
    """
    global targetList
    riseSortedTargets = []
    for star in targetList:
        up, rise, set = riseHorizonCheck(star[0], star[1], pSidTime)
        if up or rise:
            ha = reduceHa(pSidTime - star[0])
            riseSortedTargets.append((ha, rise, set, star))
    riseSortedTargets.sort()
    return riseSortedTargets


def horizonCheck(pRa, pDec, pSidTime):
    """
    Check if incoming Ra and Dec object is visible applying the site horizon,
    returning True if it is.  Note temporary added restriction on HA.
    """
    iHa = reduceHa(pSidTime - pRa)
    if abs(iHa) <= 9:
        az, alt = transform_haDec_to_azAlt(iHa, pDec)
        horizon = calculate_ptr_horizon(az, alt)
        if alt >= horizon:
            return True
        else:
            return False
    else:
        return False


def riseHorizonCheck(pRa, pDec, pSidTime):
    """
    Check if incoming Ra and Dec object is visible applying the site horizon,
    returning True if it is.  differnt criteria E vs. W.
    """
    iHa = reduceHa(pSidTime - pRa)
    az, alt = transform_haDec_to_azAlt(iHa, pDec, siteLatitude)
    horizon = calculate_ptr_horizon(az, alt)
    rise = False
    set = False
    up = False
    if alt >= horizon:
        up = True
    if az < 180 and (horizon - 15) <= alt < horizon:
        rise = True
    if az >= 180 and horizon < alt <= (horizon + 15):
        set = True
    return up, rise, set


lastBright = 0


def getSkyBright():

    """
    Correct Unihedron to be linear compared to
    calculated sky, with one breakpoint at about 7150 Unihedron counts.

    Light leakage is a farily complex function of brightness and is
    basically not predicable.
    data taken June 28, 2017
    """
    global lastBright
    skyBright = c1r.get("unihedron1").decode().split(",")
    if len(skyBright) == 2:
        lastBright = int(skyBright[0])
        return lastBright, float(skyBright[1])
    else:
        print("this code needs fixing!  Returned: ", skyBright)
        #        bright = open('Q:\\unihedron1\\uniBright.txt', 'r')
        #        skyBright = bright.read().split(',')
        #        #print('SKYBRIGHT:  ', skyBright)
        #        bright.close()
        #        lastBright = int(skyBright[1])
        #        print('getSkyBright  second try, using:  ', skyBright)
        ##        if len(skyBright) == 2:
        ##            return int(skyBright[1][:-1])
        ##        else:
        return lastBright, "999999."


lastBoltReading = [
    "2016-11-10",
    "18:19:10.27",
    "C",
    "K",
    "",
    "-99.9",
    "",
    "",
    "33.8",
    "",
    "",
    "48.7",
    "",
    "",
    "",
    "0.0",
    "",
    "23",
    "",
    "",
    "",
    "9.5",
    "",
    "",
    "0",
    "0",
    "0",
    "00002",
    "042684.76331",
    "1",
    "1",
    "1",
    "3",
    "1\n",
]


def getBoltwood():
    global lastBoltReading
    bolt = open("Q:\\boltwood1\\boltwood1.txt", "r")
    boltSky = bolt.read().split(" ")
    bolt.close()
    if len(boltSky) == 33:
        lastBoltReading = boltSky
        return boltSky
    else:
        bolt = open("Q:\\boltwood1\\boltwood1.txt", "r")
        boltSky = bolt.read().split(" ")
        bolt.close()
        lastBoltReading = boltSky
        return lastBoltReading


def getBoltwood2():
    bws = getBoltwood()
    time = bws[1]
    sky = bws[5]
    temp = bws[8]
    wind = float(bws[15])
    if wind < 0:
        wind = "0.0"
    else:
        wind = bws[15]
    hum = bws[17]
    dew = bws[20]
    cld = bws[28]
    wc = bws[29]
    rc = bws[30]
    d = bws[31]
    close = bws[32][0]
    if close == "1":
        close = "True"
    else:
        close = "False"
    return time, sky, temp, dew, hum, wind, close


##FOLOWING ARE MOSTLY STRING FORMAT COVERSIONS

DEGSPLIT = [
    "d",
    "D",
    "*",
    "°",
    ":",
    ";",
    "   ",
    "  ",
    " ",
    "'",
    '"',
    "M",
    "m",
    "S",
    "s",
]
HOURSPLIT = ["h", "H", ":", ";", "   ", "  ", " ", "M", "m", "S", "s", "'", '"']


def clean(p):
    return p.strip("#")


def multiSplit(pStr, pChrList):
    # This function is intended to return a split list retruning
    # parsed numeric fields with varoius possible seperators.
    for splitChr in pChrList:
        s_str = pStr.split(splitChr)
        if len(s_str) > 1:
            return (s_str, splitChr)
    return [s_str]


def zFill(pNum, sign=False, left=0, mid=0, right=0):
    # Assume an incoming string with truncated leading zero, leading +, or
    # or trailing 0 to fill out a length.
    if right > 1:
        fFactor = right - len(str(pNum))
        return str(pNum) + "0" * fFactor
    elif mid > 1:
        fFactor = mid - len(str(pNum))
        return "0" * fFactor + str(pNum)
    elif left > 1:
        fFactor = left - len(str(pNum))
        return "0" * fFactor + str(pNum)


def fromTableDMS(p):
    sgn = 1
    if p[0] == "-":
        sgn = -1
    p = p[1:].split()
    if len(p) == 2:
        p.append("00")
    d = sgn * (abs(float(p[0])) + (float(p[2]) / 60.0 + float(p[1])) / 60)
    return round(d, 4)


def fromTableHMS(p):
    p = p.split()
    if len(p) == 2:
        p.append("00")
    h = abs(float(p[0])) + (float(p[2]) / 60.0 + float(p[1])) / 60
    if h > 24:
        h -= 24
    if h < 0:
        h += 24
    return round(h, 5)


def getBlankZero(p):
    try:
        bz = float(p)
    except:
        bz = 0.0
        print("ptest: ", "|" + p + "|", len(p))
        if len(p) >= 1 and p[0] == "-":
            bz = bz  # This code can be eliminated
    return bz


def fromDMS(p):

    #    #NBNBNB THIS CODE NEEDS FIXING AS BELOW WAS repaired.
    #
    #    d_ms = multiSplit(clean(p), DEGSPLIT)
    #    d = d_ms[0][0]
    #    ds = d_ms[0][0][0]
    #    dr = abs(float(d))
    #    #print(d[0]
    #    m=0
    #    s = 0
    #    if len(d_ms[0]) >= 2:
    #        m = float(d_ms[0][1])
    #    if len(d_ms[0]) == 3:
    #        m = float(d_ms[0][2])
    #    if ds != '-':
    #        deg = float(dr) + float(m)/60. + float(s)/3600.
    #    else:
    #        deg = -(float(dr) + float(m)/60. + float(s)/3600.)
    #    return deg
    sign = 1
    d_ms = multiSplit(clean(p.strip()), DEGSPLIT)
    if d_ms[0][0][0] == "-":
        sign = -1
        d_ms[0][0] = d_ms[0][0][1:]

    if len(d_ms[0]) == 3:
        # This is an h m s format
        if d_ms[0][0][-1] in DEGSPLIT:
            d_ms[0][0] = d_ms[0][0][:-1]
        if d_ms[0][1][-1] in DEGSPLIT:
            d_ms[0][1] = d_ms[0][1][:-1]
        if d_ms[0][2][-1] in DEGSPLIT:
            d_ms[0][2] = d_ms[0][2][:-1]
        hr = (
            getBlankZero(d_ms[0][0])
            + getBlankZero(d_ms[0][1]) / 60
            + getBlankZero(d_ms[0][2]) / 3600
        )
    if len(d_ms[0]) == 2:
        m_s = multiSplit(clean(d_ms[0][1]), DEGSPLIT)
        if m_s[0][0] == "":
            m_s = (m_s[0][1:], m_s[1])

        if len(m_s[0]) == 2:
            if m_s[0][0][-1] in DEGSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            if m_s[0][1][-1] in DEGSPLIT:
                m_s[0][1] = m_s[0][1][:-1]
            hr = (
                getBlankZero(d_ms[0][0])
                + getBlankZero(m_s[0][0]) / 60
                + getBlankZero(m_s[0][1]) / 3600
            )
        if len(m_s[0]) == 1:
            if d_ms[0][0][-1] in DEGSPLIT:
                d_ms[0][0] = d_ms[0][0][:-1]
            if m_s[0][0][-1] in DEGSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            hr = getBlankZero(d_ms[0][0]) + getBlankZero(m_s[0][0]) / 60
        if len(d_ms[0]) == 1:
            if d_ms[0][0][-1] in DEGSPLIT:
                d_ms[0][0] = d_ms[0][0][:-1]
            hr = getBlankZero(d_ms[0][0])

    return round(sign * hr, 4)


def fromHMS(p):
    # get frome one to three fields.
    # leading with + or - indicates HA  NOT IMPLEMENTED
    # Empty input means -- Enter LST for RA or Ha = 0  NOT IMPLEMENTED

    h_ms = multiSplit(clean(p.strip()), HOURSPLIT)

    if len(h_ms[0]) == 3:
        # This is an h m s format
        if h_ms[0][0][-1] in HOURSPLIT:
            h_ms[0][0] = h_ms[0][0][:-1]
        if h_ms[0][1][-1] in HOURSPLIT:
            h_ms[0][1] = h_ms[0][1][:-1]
        if h_ms[0][2][-1] in HOURSPLIT:
            h_ms[0][2] = h_ms[0][2][:-1]
        hr = (
            getBlankZero(h_ms[0][0])
            + getBlankZero(h_ms[0][1]) / 60
            + getBlankZero(h_ms[0][2]) / 3600
        )
    if len(h_ms[0]) == 2:
        m_s = multiSplit(clean(h_ms[0][1]), HOURSPLIT)
        if m_s[0][0] == "":
            m_s = (m_s[0][1:], m_s[1])

        if len(m_s[0]) == 2:
            if m_s[0][0][-1] in HOURSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            if m_s[0][1][-1] in HOURSPLIT:
                m_s[0][1] = m_s[0][1][:-1]
            hr = (
                getBlankZero(h_ms[0][0])
                + getBlankZero(m_s[0][0]) / 60
                + getBlankZero(m_s[0][1]) / 3600
            )
        if len(m_s[0]) == 1:
            if h_ms[0][0][-1] in HOURSPLIT:
                h_ms[0][0] = h_ms[0][0][:-1]
            if m_s[0][0][-1] in HOURSPLIT:
                m_s[0][0] = m_s[0][0][:-1]
            hr = getBlankZero(h_ms[0][0]) + getBlankZero(m_s[0][0]) / 60
        if len(h_ms[0]) == 1:
            if h_ms[0][0][-1] in HOURSPLIT:
                h_ms[0][0] = h_ms[0][0][:-1]
            hr = getBlankZero(h_ms[0][0])

    return round(hr, 5)


def fromDate(p):
    m_d_y = clean(p).split("/")
    y = int(m_d_y[2])
    if y >= 97:
        y += 1900
    else:
        y += 2000
    d = int(m_d_y[1])
    m = int(m_d_y[0])
    return str(y * 10000 + m * 100 + d)


def dToHMS(p, short=False):
    while p < 0:
        p += 360
    signed = ""
    if p < 0:
        signed = "-"
    h = abs(p)
    h = h / 15.0
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h * 1000) / 1000.0
    return signed + str(ih) + "h" + str(im) + "m" + zFill(s, left=2) + "s"


def hToHMS(p, short=False):
    while p >= 24:
        p -= 24.0
    signed = ""
    if p < 0:
        signed = "-"
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h * 1000) / 1000.0
    return signed + str(ih) + "h" + str(im) + "m" + zFill(s, left=2) + "s"


def hToH_MS(p, short=False):
    while p >= 24:
        p -= 24.0
    signed = ""
    if p < 0:
        signed = "-"
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h * 1000) / 1000.0
    return signed + str(ih) + " " + str(im) + " " + zFill(s, left=2)


def hToH_MStup(p, short=False):
    while p >= 24:
        p -= 24.0
    signed = ""
    if p < 0:
        signed = "-"
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h * 1000) / 1000.0
    return (signed + str(ih), str(im), str(s))


def hToH_M(p, short=False):
    while p >= 24:
        p -= 24.0
    signed = ""
    if p < 0:
        signed = "-"
    h = abs(p)
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    return signed + str(ih) + " " + str(im)  # + " " + str(s)


# NBNB Does anyone call this?
def toDMS(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return signed + str(ideg) + "*" + str(im) + "m" + zFill(s, left=2) + "s"


def dToDMS(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return signed + str(ideg) + DEG_SYM + str(im) + "m" + zFill(s, left=2) + "s"


def dToDMSdsym(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return signed + str(ideg) + DEG_SYM + str(im) + "m" + zFill(s, left=2) + "s"


def dToD_MS(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return signed + str(ideg) + " " + str(im) + " " + zFill(s, left=2)


def dToD_MStup(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return (signed + str(ideg), str(im), str(s))


def toPier(pSideOfPier):
    if pSideOfPier == False:
        return "WEST"
    else:
        return "EAST"


# NBNBNB THis should be a configuration
def toTel(pSideOfPier):
    if pSideOfPier == EASTSIDE:
        return EastSideDesc
    else:
        return WestSideDesc


def toMechHMS(p, short=False):
    while p < 0:
        p += 360
    signed = " "
    if p < 0:
        signed = "-"
    h = abs(p)
    h = h / 15.0
    ih = int(h)
    h -= ih
    h *= 60
    im = int(h)
    h -= im
    h *= 60
    if short:
        s = int(h)
    else:
        s = int(h * 1000) / 1000.0
    return signed + str(ih) + ":" + str(im) + ":" + str(s)


def toMechDMS(p, short=False):
    signed = "+"
    if p < 0:
        signed = "-"
    d = abs(p)
    ideg = int(d)
    d -= ideg
    d *= 60
    im = int(d)
    d -= im
    d *= 60
    s = int(d * 10) / 10.0
    if short:
        s = int(d)
    else:
        s = int(d * 100) / 100.0
    return signed + str(ideg) + ":" + str(im) + ":" + str(s)


def fixTail(p):
    while p[-1] == "#":
        p.pop(-1)
    return p


# These function do not work for mechanical coordinates.
def reduce_ha_h(pHa):
    while pHa <= -12:
        pHa += 24.0
    while pHa > 12:
        pHa -= 24.0
    return pHa


def reduce_ra_h(pRa):
    while pRa < 0:
        pRa += 24.0
    while pRa >= 24:
        pRa -= 24.0
    return pRa


def reduce_dec_d(pDec):
    if pDec > 90.0:
        pDec = 90.0
    if pDec < -90.0:
        pDec = -90.0
    return pDec


def reduce_alt_(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt


def reduce_az_d(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz


def reduce_ha_r(pHa):
    while pHa <= -PI:
        pHa += TWOPI
    while pHa > PI:
        pHa -= TWOPI
    return pHa


def reduce_ra_r(pRa):
    while pRa < 0:
        pRa += TWOPI
    while pRa >= TWOPI:
        pRa -= TWOPI
    return pRa


def reduce_dec_r(pDec):
    if pDec > PIOVER2:
        pDec = PIOVER2
    if pDec < -PIOVER2:
        pDec = -PIOVER2
    return pDec


def reduce_alt_r(pAlt):
    if pAlt > PIOVER2:
        pAlt = PIOVER2
    if pAlt < -PIOVER2:
        pAlt = -PIOVER2
    return pAlt


def reduce_az_r(pAz):
    while pAz < 0.0:
        pAz += TWOPI
    while pAz >= TWOPI:
        pAz -= TWOPI
    return pAz


def ra_avg_h(pFirst, pNext):
    """Creates a correct average over 0 to 23.999 hour transition."""

    # Note to average RAa/Dec pairs requires considering overpole travel.
    # That is best done with direction cosines and report the average vector.

    delta = abs(pFirst - pNext)
    if delta >= 12:
        small = min(pFirst, pNext)
        small += 24
        avg = (small + max(pFirst, pNext)) / 2.0
        while avg >= 24:
            avg -= 24
        return avg
    else:
        return (
            pFirst + pNext
        ) / 2.0  # Note there are two possible answers in this situation.


def az_avg_deg(pFirst, pNext):
    """Creates a correct average over 0 to 359.999 hour transition."""
    delta = abs(pFirst - pNext)
    if delta >= 180:
        small = min(pFirst, pNext)
        small += 360
        avg = (small + max(pFirst, pNext)) / 2.0
        while avg >= 360:
            avg -= 360
        return avg
    else:
        return (pFirst + pNext) / 2.0
    return


class Pointing(object):
    def __init__(self):
        self.ra = 0.0  # hours
        self.raDot = 0.0  # asec/s
        self.raDotDot = 0.0  # asec/s/s  Dot-Dots computed over end period
        self.dec = 0.0  # degrees
        self.decDot = 0.0  # asec/s
        self.decDotDot = 0.0  # asec/s/s
        self.sys = "ICRS"  # The coordinate system
        self.epoch = None  # eg ephem.now()  When the pointing was last
        # computed exactly with Dot
        self.end = None  # seconds, eg 3600 implies valid for 1 hour.
        self.name = "undefined"  # The name of the pointing.
        self.cat = None  # The catalog Name
        self.cat_no = ""  # A string representing catalog entry

    def haAltAz(self):
        pass  # Some calculations here
        return (ha, alt, az)  # hours, degrees, degrees

    def haAltAzDot(self):
        pass  # Some calculations here
        return (haDot, altDot, azDot)  # asec/s, asec/s, asec/ss


def get_current_times():
    ut_now = Time(datetime.now(), scale="utc", location=siteCoordinates)
    sid_now = ut_now.sidereal_time("apparent")  # Should convert this to a value.
    sidTime = sid_now
    # =============================================================================
    #     THIS NEEDS FIXING! Sloppy
    # =============================================================================
    iso_day = date.today().isocalendar()
    doy = (iso_day[1] - 1) * 7 + (iso_day[2])
    equinox_now = "J" + str(
        round((iso_day[0] + ((iso_day[1] - 1) * 7 + (iso_day[2])) / 365), 2)
    )
    return (ut_now, sid_now, equinox_now, doy)


def calculate_ptr_horizon_d(pAz, pAlt):
    if pAz <= 30:
        hor = 35.0
    elif pAz <= 36.5:
        hor = 39
    elif pAz <= 43:
        hor = 42.7
    elif pAz <= 59:
        hor = 32.7
    elif pAz <= 62:
        hor = 28.6
    elif pAz <= 65:
        hor = 25.2
    elif pAz <= 74:
        hor = 22.6
    elif pAz <= 82:
        hor = 20
    elif pAz <= 95.5:
        hor = 17.2
    elif pAz <= 101.5:
        hor = 14
    elif pAz <= 107.5:
        hor = 10
    elif pAz <= 130:
        hor = 11
    elif pAz <= 150:
        hor = 20
    elif pAz <= 172:
        hor = 28
    elif pAz <= 191:
        hor = 25
    elif pAz <= 213:
        hor = 20
    elif pAz <= 235:
        hor = 15.3
    elif pAz <= 260:
        hor = 10.5
    elif pAz <= 272:
        hor = 17
    elif pAz <= 294:
        hor = 16.5
    elif pAz <= 298.5:
        hor = 18.6
    elif pAz <= 303:
        hor = 20.6
    elif pAz <= 309:
        hor = 27
    elif pAz <= 315:
        hor = 32
    elif pAz <= 360.1:
        hor = 32
    else:
        hor = 15
    if hor < 17:
        hor = 17  # Temporary fix for L500
    return hor


def convert_to_mechanical_h_d(pRa, pDec, pFlip):
    if pFlip == "East":
        return (pRa, pDec)
    else:
        fDec = 180.0 - pDec
        pRa += 12.0
        while pRa >= 24:
            pRa -= 24.0
        while pRa < 0.0:
            pRa += 24.0
        return (pRa, fDec)


def rect_sph_d(pX, pY, pZ):
    rSq = pX * pX + pY * pY + pZ * pZ
    return math.degrees(math.atan2(pY, pX)), math.degrees(math.asin(pZ / rSq))


def sph_rect_d(pRoll, pPitch):
    pRoll = math.radians(pRoll)
    pPitch = math.radians(pPitch)
    cPitch = math.cos(pPitch)
    return math.cos(pRoll) * cPitch, math.sin(pRoll) * cPitch, math.sin(pPitch)


def rotate_r(pX, pY, pTheta):
    cTheta = math.cos(pTheta)
    sTheta = math.sin(pTheta)
    return pX * cTheta - pY * sTheta, pX * sTheta + pY * cTheta


def centration_d(theta, a, b):
    theta = math.radians(theta)
    return math.degrees(
        math.atan2(math.sin(theta) - STOR * b, math.cos(theta) - STOR * a)
    )


def centration_r(theta, a, b):
    return math.atan2(math.sin(theta) - STOR * b, math.cos(theta) - STOR * a)


def transform_raDec_to_haDec_r(pRa, pDec, pSidTime):

    return (reduce_ha_r(pSidTime - pRa), reduce_dec_r(pDec))


def transform_haDec_to_raDec_r(pHa, pDec, pSidTime):
    return (reduce_ra_r(pSidTime - pHa), reduce_dec_r(pDec))


def transform_haDec_to_azAlt_r(pLocal_hour_angle, pDec, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = pDec
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = pLocal_hour_angle
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.asin(sinLat * sinDec + cosLat * cosDec * cosHa)
    y = sinHa
    x = cosHa * sinLat - math.tan(decr) * cosLat
    azimuth = math.atan2(y, x) + PI
    azimuth = reduce_az_r(azimuth)
    altitude = reduce_alt_r(altitude)
    return (azimuth, altitude)


def transform_haDec_to_azAlt(pLocal_hour_angle, pDec, lat):
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = math.radians(pDec)
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = math.radians(15.0 * pLocal_hour_angle)
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.degrees(math.asin(sinLat * sinDec + cosLat * cosDec * cosHa))
    y = sinHa
    x = cosHa * sinLat - math.tan(decr) * cosLat
    azimuth = math.degrees(math.atan2(y, x)) + 180
    # azimuth = reduceAz(azimuth)
    # altitude = reduceAlt(altitude)
    return (azimuth, altitude)  # , local_hour_angle)


def reduceAlt(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt


def reduceAz(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz


def transform_haDec_to_azAlt(pLocal_hour_angle, pDec, lat):
    latr = math.radians(lat)
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    decr = math.radians(pDec)
    sinDec = math.sin(decr)
    cosDec = math.cos(decr)
    mHar = math.radians(15.0 * pLocal_hour_angle)
    sinHa = math.sin(mHar)
    cosHa = math.cos(mHar)
    altitude = math.degrees(math.asin(sinLat * sinDec + cosLat * cosDec * cosHa))
    y = sinHa
    x = cosHa * sinLat - math.tan(decr) * cosLat
    azimuth = math.degrees(math.atan2(y, x)) + 180
    # azimuth = reduceAz(azimuth)
    # altitude = reduceAlt(altitude)
    return (azimuth, altitude)  # , local_hour_angle)


def reduceAlt(pAlt):
    if pAlt > 90.0:
        pAlt = 90.0
    if pAlt < -90.0:
        pAlt = -90.0
    return pAlt


def reduceAz(pAz):
    while pAz < 0.0:
        pAz += 360
    while pAz >= 360.0:
        pAz -= 360.0
    return pAz


def transform_azAlt_to_haDec_r(pAz, pAlt, latr):
    sinLat = math.sin(latr)
    cosLat = math.cos(latr)
    alt = pAlt
    sinAlt = math.sin(alt)
    cosAlt = math.cos(alt)
    az = pAz - PI
    sinAz = math.sin(az)
    cosAz = math.cos(az)
    if abs(abs(alt) - PIOVER2) < 1.0 * STOR:
        return (
            0.0,
            reduce_dec_r(latr),
        )  # by convention azimuth points South at local zenith
    else:
        dec = math.asin(sinAlt * sinLat - cosAlt * cosAz * cosLat)
        ha = math.atan2(sinAz, (cosAz * sinLat + math.tan(alt) * cosLat))
        return (reduce_ha_r(ha), reduce_dec_r(dec))


def transform_azAlt_to_raDec_r(pAz, pAlt, pLatitude, pSidTime):
    ha, dec = transform_azAlt_to_haDec_r(pAz, pAlt, pLatitude)
    return transform_haDec_to_raDec_r(ha, dec, pSidTime)


def test_haDec_altAz_haDec():
    lHa = [-12, -11.99, -6, -5, -4, -3, -2, -1, 0, 1, 3, 5, 7, 9, 11.999, 12]
    lDec = [-50, -40, -30, -10, 0, 30, siteLatitude, 40, 70, 89.99, 90]
    for ha in lHa:
        for dec in lDec:
            print("Starting:  ", ha, dec)
            site_latitude = config["latitude"]
            lAz, lAlt = transform_haDec_to_azAlt(ha, dec, siteLatitude)
            tHa, tDec = transform_azAlt_to_HaDec(lAz, lAlt, siteLatitude)
            print(ha, tHa, dec, tDec)


def apply_refraction_inEl_r(pAppEl, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg
    global RefrOn
    # From Astronomical Algorithms.  Max error 0.89" at 0 elev.
    # 20210328 This code does not the right thing if star is below the Pole and is refracted above it.
    if not RefrOn:
        return pAppEl, 0.0
    elif pAppEl > 0:
        pAppEl *= RTOD  # Formulas assume elevation in degrees
        ref = (
            1 / math.tan(DTOR * (pAppEl + 7.31 / (pAppEl + 4.4))) + 0.001351521673756295
        )
        ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        obsEl = pAppEl + ref / 60.0
        obsEl *= DTOR
        return reduce_alt_r(obsEl), ref * 60.0
    else:
        ref = 1 / math.tan(DTOR * (7.31 / (pAppEl + 4.4))) + 0.001351521673756295
        ref -= 0.06 * math.sin((14.7 * ref + 13.0) * DTOR) - 0.0134970632606319
        ref *= 283 / (273 + pSiteRefTemp)
        ref *= pSiteRefPress / 1010.0
        obsEl = pAppEl + ref / 60.0
        obsEl *= DTOR
        return reduce_alt_r(obsEl), ref * 60.0


def correct_refraction_inEl_r(pObsEl, pSiteRefTemp, pSiteRefPress):  # Deg, C. , mmHg
    global RefrOn
    if not RefrOn:
        return pObsEl, 0.0
    else:
        ERRORlimit = 0.01 * STOR
        count = 0
        error = 10
        trial = pObsEl
        while abs(error) > ERRORlimit:
            appTrial, ref = apply_refraction_inEl_r(trial, pSiteRefTemp, pSiteRefPress)
            error = appTrial - pObsEl
            trial -= error
            count += 1
            if count > 25:  # count about 12 at-0.5 deg. 3 at 45deg.
                return reduce_dec_r(pObsEl)
        return reduce_dec_r(trial), reduce_dec_r(pObsEl - trial) * RTOD * 3600.0


def test_refraction():
    for el in range(90, -1, -1):
        siteRefTemp = 0.0
        siteRefPress = 1010
        refEl, ref = apply_refraction_inEl_r(el, siteRefTemp, siteRefPress)
        resultEl, ref2 = correct_refraction_inEl_r(refEl, siteRefTemp, siteRefPress)
        print(el, refEl, resultEl, (el - resultEl) * DTOS, ref, ref2)


def appToObsRaHa(appRa, appDec, pSidTime):
    global raRefr, decRefr, refAsec
    try:
        g_dev["ocn"].get_proxy_temp_press()
    except:
        pass
    appHa, appDec = transform_raDec_to_haDec_r(appRa, appDec, pSidTime)
    appAz, appAlt = transform_haDec_to_azAlt_r(
        appHa, appDec, wema_config["latitude"] * DTOR
    )
    obsAlt, refAsec = apply_refraction_inEl_r(
        appAlt, g_dev["ocn"].temperature, g_dev["ocn"].pressure
    )
    obsHa, obsDec = transform_azAlt_to_haDec_r(
        appAz, obsAlt, wema_config["latitude"] * DTOR
    )
    raRefr = reduce_ha_r(appHa - obsHa) * HTOS
    decRefr = -reduce_dec_r(appDec - obsDec) * DTOS
    return reduce_ha_r(obsHa), reduce_dec_r(obsDec), refAsec


def obsToAppHaRa(obsHa, obsDec, pSidTime):
    global raRefr, decRefr
    try:
        g_dev["ocn"].get_proxy_temp_press()
    except:
        pass
    obsAz, obsAlt = transform_haDec_to_azAlt_r(
        obsHa, obsDec, wema_config["latitude"] * DTOR
    )
    refr = 0.0
    try:
        appAlt, refr = correct_refraction_inEl_r(
            obsAlt, g_dev["ocn"].temperature, g_dev["ocn"].pressure
        )
    except:
        appAlt = 0
        pass
    appHa, appDec = transform_azAlt_to_haDec_r(
        obsAz, appAlt, wema_config["latitude"] * DTOR
    )
    appRa, appDec = transform_haDec_to_raDec_r(appHa, appDec, pSidTime)
    raRefr = reduce_ha_r(-appHa + obsHa) * HTOS
    decRefr = -reduce_dec_r(-appDec + obsDec) * DTOS
    return reduce_ra_r(appRa), reduce_dec_r(appDec), refr


def appToObsRaDec(appRa, appDec, pSidTime):
    obsHa, obsDec, refR = appToObsRaHa(appRa, appDec, pSidTime)
    obsRa, obsDec = transform_haDec_to_raDec_r(obsHa, obsDec, pSidTime)
    return reduce_ra_r(obsRa), reduce_dec_r(obsDec), refR


def obsToAppRaDec(obsRa, obsDec, pSidTime):
    obsHa, obsDec = transform_raDec_to_haDec_r(obsRa, obsDec, pSidTime.value)
    appRa, appDec, refr = obsToAppHaRa(obsHa, obsDec, pSidTime.value)
    return reduce_ra_r(appRa), reduce_dec_r(appDec), refr


def test_app_obs_app():
    ra = [0, 5, 4, 3, 2, 1, 0, 24, 23, 22, 21, 21, 20]
    dec = [0, -35, -20, -5, 0, 10, 25, siteLatitude, 40, 55, 70, 85, 89.999, 90]
    for pRa in ra:
        for pDec in dec:
            pHa, pDec = transform_raDec_to_haDec(pRa, pDec, 0)
            az, alt = transform_haDec_to_azAlt(pHa, pDec, 34)
            if alt > 0:
                oRa, oDec = appToObs(pRa, pDec, 0.0, 34)
                aRa, aDec = obsToApp(oRa, oDec, 0.0, 34)


def transform_mount_to_observed_r(pRoll, pPitch, pPierSide, loud=False):
    global ModelOn
    # I am amazed this works so well even very near the celestrial pole.
    # input is Ha in hours and pitch in degrees.
    if not ModelOn:
        return (pRoll, pPitch)
    else:

        cosDec = math.cos(pPitch)
        ERRORlimit = 0.01 * STOR
        count = 0
        error = 10
        rollTrial = pRoll
        pitchTrial = pPitch
        while abs(error) > ERRORlimit:
            obsRollTrial, obsPitchTrial = transform_observed_to_mount_r(
                rollTrial, pitchTrial, pPierSide
            )
            errorRoll = reduce_ha_r(obsRollTrial - pRoll)
            errorPitch = reduce_dec_r(obsPitchTrial - pPitch)
            # TODO this needs a unit checkout.
            error = math.sqrt(
                cosDec * (errorRoll) ** 2 + (errorPitch) ** 2
            )  # Removed *15 from errorRoll
            rollTrial -= errorRoll
            pitchTrial -= errorPitch
            count += 1
            if count > 500:  # count about 12 at-0.5 deg. 3 at 45deg.
                if loud:
                    print("transform_mount_to_observed_r() FAILED!")
                return pRoll, pPitch
        return reduce_ha_r(rollTrial), reduce_dec_r(pitchTrial)


def transform_observed_to_mount_r(pRoll, pPitch, pPierSide, loud=False, enable=False):
    """
    Long-run probably best way to do this in inherit a model dictionary.

    NBNBNB improbable minus sign of ID, WD

    This implements a basic 7 term TPOINT transformation.
    This routine is directly invertible. Input in radians.
    """

    global raCorr, decCorr, model, ModelOn

    if enable:
        pass
    if not ModelOn:
        return (pRoll, pPitch)
    else:
        if True:  # TODO needs to specify, else statement unreachable.
            ih = model["IH"]
            idec = model["ID"]
            Wh = model["WH"]
            Wd = model["WD"]
            ma = model["MA"]
            me = model["ME"]
            ch = model["CH"]
            np = model["NP"]
            tf = model["TF"]
            tx = model["TX"]
            hces = model["HCES"]
            hcec = model["HCEC"]
            dces = model["DCES"]
            dcec = model["DCEC"]
        else:
            ih = wmodel["IH"]
            idec = wmodel["ID"]
            Wh = wmodel["WH"]
            Wd = wmodel["WD"]
            ma = wmodel["MA"]
            me = wmodel["ME"]
            ch = wmodel["CH"]
            np = wmodel["NP"]
            tf = wmodel["TF"]
            tx = wmodel["TX"]
            hces = wmodel["HCES"]
            hcec = wmodel["HCEC"]
            dces = wmodel["DCES"]
            dcec = wmodel["DCEC"]
        ia = model["IA"]
        ie = model["IE"]
        an = model["AN"]
        aw = model["AW"]
        ca = model["CA"]
        npae = model["NPAE"]
        aces = model["ACES"]
        acec = model["ACEC"]
        eces = model["ECES"]
        ecec = model["ECEC"]
        # R to HD convention
        pRoll *= RTOH
        pPitch *= RTOD
        # Apply IJ and ID to incoming coordinates, and if needed GEM correction.
        rRoll = math.radians(pRoll * 15 - ih / 3600.0)
        rPitch = math.radians(pPitch - idec / 3600.0)
        siteLatitude = wema_config["latitude"]

        if not ALTAZ:
            if pPierSide == 0:
                ch = -ch / 3600.0
                np = -np / 3600.0
                rRoll += math.radians(Wh / 3600.0)
                rPitch -= math.radians(
                    Wd / 3600.0
                )  # NB Adjust signs to normal EWNS view
            if loud:
                print(ih, idec, Wh, Wd, ma, me, ch, np, tf, tx, hces, hcec, dces, dcec)

            # This is exact trigonometrically:
            if loud:
                print("Pre CN; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
            cnRoll = rRoll + math.atan2(
                math.cos(math.radians(np)) * math.tan(math.radians(ch))
                + math.sin(math.radians(np)) * math.sin(rPitch),
                math.cos(rPitch),
            )
            cnPitch = math.asin(
                math.cos(math.radians(np))
                * math.cos(math.radians(ch))
                * math.sin(rPitch)
                - math.sin(math.radians(np)) * math.sin(math.radians(ch))
            )
            if loud:
                print("Post CN; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
            x, y, z = sph_rect_d(math.degrees(cnRoll), math.degrees(cnPitch))
            if loud:
                print("To spherical:  ", x, y, z, x * x + y * y + z * z)
            # Apply MA error:
            y, z = rotate_r(y, z, math.radians(-ma / 3600.0))
            # Apply ME error:
            x, z = rotate_r(x, z, math.radians(-me / 3600.0))
            if loud:
                print("Post ME:       ", x, y, z, x * x + y * y + z * z)
            # Apply latitude
            x, z = rotate_r(x, z, math.radians(90.0 - siteLatitude))
            if loud:
                print("Post-Lat:  ", x, y, z, x * x + y * y + z * z)
            # Apply TF, TX
            az, el = rect_sph_d(x, y, z)  # math.pi/2. -
            if loud:
                print("Az El:  ", az + 180.0, el)
            # flexure causes mount to sag so a shift in el, apply then
            # move back to other coordinate system
            zen = 90 - el
            if zen >= 89:
                clampedTz = 57.289961630759144  # tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl = (
                math.radians(tf / 3600.0) * math.sin(math.radians(zen))
                + math.radians(tx / 3600.0) * clampedTz
            )
            el += defl * RTOD
            if loud:
                print(
                    "Post Tf,Tx; az, el, z, defl:  ",
                    az + 180.0,
                    el,
                    z * RTOD,
                    defl * RTOS,
                )
            # The above is dubious but close for small deflections.
            # Unapply Latitude

            x, y, z = sph_rect_d(az, el)
            x, z = rotate_r(x, z, -math.radians(90.0 - siteLatitude))
            fRoll, fPitch = rect_sph_d(x, y, z)
            cRoll = centration_d(fRoll, -hces, hcec)
            cPitch = centration_d(fPitch, -dces, dcec)
            if loud:
                print("Back:  ", x, y, z, x * x + y * y + z * z)
                print("Back-Lat:  ", x, y, z, x * x + y * y + z * z)
                print("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
                print("f,c Roll: ", fRoll, cRoll)
                print("f, c Pitch: ", fPitch, cPitch)
            corrRoll = reduce_ha_h(cRoll / 15.0)
            corrPitch = reduce_dec_d(cPitch)
            if loud:
                print("Final:   ", fRoll * RTOH, fPitch * RTOD)
            raCorr = reduce_ha_h(corrRoll - pRoll) * 15 * 3600
            decCorr = reduce_dec_d(corrPitch - pPitch) * 3600
            # 20210328  Note this may not work at Pole.
            #if enable:
            #    print("Corrections in asec:  ", raCorr, decCorr)
            return (corrRoll * HTOR, corrPitch * DTOR)
        elif ALTAZ:
            if loud:
                print(
                    ih, idec, ia, ie, an, aw, tf, tx, ca, npae, aces, acec, eces, ecec
                )

            # Convert Incoming Ha, Dec to Alt-Az system, apply corrections then
            # convert back to equitorial. At this stage we assume positioning of
            # the mounting is still done in Ra/Dec coordinates so the canonical
            # velocities are generated by the mounting, not any Python level code.

            loud = False
            az, alt = transform_haDec_to_azAlt_r(pRoll, pPitch)
            # Probably a units problem here.
            rRoll = math.radians(az + ia / 3600.0)
            rPitch = math.radians(alt - ie / 3600.0)
            ch = ca / 3600.0
            np = npae / 3600.0
            # This is exact trigonometrically:

            cnRoll = rRoll + math.atan2(
                math.cos(math.radians(np)) * math.tan(math.radians(ch))
                + math.sin(math.radians(np)) * math.sin(rPitch),
                math.cos(rPitch),
            )
            cnPitch = math.asin(
                math.cos(math.radians(np))
                * math.cos(math.radians(ch))
                * math.sin(rPitch)
                - math.sin(math.radians(np)) * math.sin(math.radians(ch))
            )
            if loud:
                print("Pre CANPAE; roll, pitch:  ", rRoll * RTOH, rPitch * RTOD)
                print("Post CANPAE; roll, pitch:  ", cnRoll * RTOH, cnPitch * RTOD)
            x, y, z = sph_rect_d(math.degrees(cnRoll), math.degrees(cnPitch))

            # Apply AN error:
            y, z = rotate_r(y, z, math.radians(-aw / 3600.0))
            # Apply AW error:
            x, z = rotate_r(x, z, math.radians(an / 3600.0))
            az, el = rect_sph_d(x, y, z)
            if loud:
                print("To spherical:  ", x, y, z, x * x + y * y + z * z)
                print("Pre  AW:       ", x, y, z, math.radians(aw / 3600.0))
                print("Post AW:       ", x, y, z, x * x + y * y + z * z)
                print("Pre  AN:       ", x, y, z, math.radians(an / 3600.0))
                print("Post AN:       ", x, y, z, x * x + y * y + z * z)
                print("Az El:  ", az + 180.0, el)
            # flexure causes mount to sag so a shift in el, apply then
            # move back to other coordinate system
            zen = 90 - el
            if zen >= 89:
                clampedTz = 57.289961630759144  # tan(89)
            else:
                clampedTz = math.tan(math.radians(zen))
            defl = (
                math.radians(tf / 3600.0) * math.sin(math.radians(zen))
                + math.radians(tx / 3600.0) * clampedTz
            )
            el += defl * RTOD
            if loud:
                print(
                    "Post Tf,Tx; az, el, z, defl:  ",
                    az + 180.0,
                    el,
                    z * RTOD,
                    defl * RTOS,
                )
            # The above is dubious but close for small deflections.
            # Unapply Latitude

            x, y, z = sph_rect_d(az, el)
            if loud:
                print("Back:  ", x, y, z, x * x + y * y + z * z)
            fRoll, fPitch = rect_sph_d(x, y, z)
            if loud:
                print("Back-Sph:  ", fRoll * RTOH, fPitch * RTOD)
            cRoll = centration_d(fRoll, aces, acec)
            if loud:
                print("f,c Roll: ", fRoll, cRoll)
            cPitch = centration_d(fPitch, -eces, ecec)
            if loud:
                print("f, c Pitch: ", fPitch, cPitch)
            corrRoll = reduce_az_r(cRoll)
            corrPitch = reduce_alt_r(cPitch)
            if loud:
                print("Final Az, ALT:   ", corrRoll, corrPitch)
            haH, decD = transform_azAlt_to_haDec_r(corrRoll, corrPitch)
            raCorr = reduce_ha_h(haH - pRoll) * 15 * 3600
            decCorr = reduce_dec_d(decD - pPitch) * 3600
            if loud:
                print("Corrections:  ", raCorr, decCorr)
            return (haH, decD)


def seedAltAzModel():
    global ALTAZ
    model["IH"] = 0
    model["ID"] = 0
    model["WH"] = 0
    model["WD"] = 0
    model["MA"] = 0
    model["ME"] = 0
    model["CH"] = 0
    model["NP"] = 0
    model["TF"] = 70
    model["TX"] = -10
    model["HCES"] = 0
    model["HCEC"] = 0
    model["DCES"] = 0
    model["DCEC"] = 0
    model["IA"] = 100
    model["IE"] = -100
    model["AN"] = 30
    model["AW"] = -40
    model["CA"] = 50
    model["NPAE"] = 60
    model["ACES"] = 80
    model["ACEC"] = -90
    model["ECES"] = -85
    model["ECEC"] = 74
    ALTAZ = True
    test_misAlign()


def seedEquModel():
    global ALTAZ
    model["IH"] = 35
    model["ID"] = -30
    model["WH"] = 4
    model["WD"] = 0
    model["MA"] = 50
    model["ME"] = -70
    model["CH"] = 85
    model["NP"] = -40
    model["TF"] = 20
    model["TX"] = 5
    model["HCES"] = 100
    model["HCEC"] = -80
    model["DCES"] = 125
    model["DCEC"] = -45
    model["IA"] = 0
    model["IE"] = 0
    model["AN"] = 0
    model["AW"] = 0
    model["CA"] = 0
    model["NPAE"] = 0
    model["ACES"] = 0
    model["ACEC"] = 0
    model["ECES"] = 0
    model["ECEC"] = 0
    ALTAZ = False
    test_misAlign()


def getTpointModel(pDDmod=None):
    """
    This fetches a model from TPOINT directory. Note Toint does NOT produce
    EH ED. This can be sorted by deciding if there is one model and an EH ED
    correction, or a model per flip side. TPOINT can be set up to script
    those calculations.
    """
    global model, modelChanged

    try:
        if pDDmod == None:
            pPath = os.path.normpath(os.path.join(os.getcwd(), "/TPOINT/ptr_mod.dat"))
            WHP = 0.0
            WDP = 0.0
            print("Using ptr-Mod from TPOINT.")
        else:
            pPath = (
                os.path.normpath(os.path.join(os.getcwd(), "/TPOINT/"))
                + pDDmod
                + ".dat"
            )
            # NOTE assumed a custom model deals with WHP
        modelf = open(pPath, "r")
        print("Model: " + pPath + "\n", modelf.readline(), modelf.readline())
        for line in modelf:
            if line != "END" or len(line) > 7:
                print(line)
                items = line.split()
                try:
                    items[1] = float(items[1])
                    if abs(items[1] / float(items[2])) >= 2:  # reject low sigma terms
                        # store as needed.
                        if items[0] == "IH":
                            model["IH"] = items[1]
                        if items[0] == "ID":
                            model["ID"] = items[1]
                        if items[0] == "WH":
                            model["WH"] = items[1]
                        if items[0] == "WD":
                            model["WD"] = items[1]
                        if items[0] == "MA":
                            model["MA"] = items[1]
                        if items[0] == "ME":
                            model["ME"] = items[1]
                        if items[0] == "CH":
                            model["CH"] = items[1]
                        if items[0] == "NP":
                            model["NP"] = items[1]
                        if items[0] == "TF":
                            model["TF"] = items[1]
                        if items[0] == "TX":
                            model["TX"] = items[1]
                        if items[0] == "HCES":
                            model["HCES"] = items[1]
                        if items[0] == "HCEC":
                            model["HCEC"] = items[1]
                        if items[0] == "DCES":
                            model["DCES"] = items[1]
                        if items[0] == "DCEC":
                            model["DCEC"] = items[1]
                        if items[0] == "IA":
                            model["IA"] = items[1]
                        if items[0] == "IE":
                            model["IE"] = items[1]
                        if items[0] == "AN":
                            model["AN"] = items[1]
                        if items[0] == "AW":
                            model["AW"] = items[1]
                        if items[0] == "CA":
                            model["CA"] = items[1]
                        if items[0] == "NPAE":
                            model["NPAE"] = items[1]
                        if items[0] == "ACES":
                            model["ACES"] = items[1]
                        if items[0] == "ACEC":
                            model["ACEC"] = items[1]
                        if items[0] == "ECES":
                            model["ECES"] = items[1]
                        if items[0] == "ECEC":
                            model["ECEC"] = items[1]
                except:
                    pass
        modelf.close()

    except:
        print("No model file found!  Please look elsewhere.")
    modelChanged = False


def writeTpointModel():
    global model, modelChanged
    pPath = "C:\\Users\\User\\Dropbox\\PyWork\\PtrObserver\\PTR\\TPOINT\\ptr_mod.dat"
    modelf = open(pPath, "w")
    modelf.write("0.18m AP Starfire on  AP-1600 \n")
    modelf.write("T  0  0.00    0.000   0.0000\n")
    modelf.write("     IH       " + str(round(float(model["IH"]), 2)) + "     3.0  \n")
    modelf.write("     ID       " + str(round(float(model["ID"]), 2)) + "     3.0  \n")
    modelf.write("     WH       " + str(round(float(model["WH"]), 2)) + "     3.0  \n")
    modelf.write("     WD       " + str(round(float(model["WD"]), 2)) + "     3.0  \n")
    modelf.write("     MA       " + str(round(float(model["MA"]), 2)) + "     3.0  \n")
    modelf.write("     ME       " + str(round(float(model["ME"]), 2)) + "     3.0  \n")
    modelf.write("     CH       " + str(round(float(model["CH"]), 2)) + "     3.0  \n")
    modelf.write("     NP       " + str(round(float(model["NP"]), 2)) + "     3.0  \n")
    modelf.write("     TF       " + str(round(float(model["TF"]), 2)) + "     3.0  \n")
    modelf.write("     TX       " + str(round(float(model["TX"]), 2)) + "     3.0  \n")
    modelf.write(
        "     HCES     " + str(round(float(model["HCES"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     HCEC     " + str(round(float(model["HCEC"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     DCES     " + str(round(float(model["DCES"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     DCEC     " + str(round(float(model["DCEC"]), 2)) + "     3.0  \n"
    )
    modelf.write("     IA       " + str(round(float(model["IA"]), 2)) + "     3.0  \n")
    modelf.write("     IE       " + str(round(float(model["IE"]), 2)) + "     3.0  \n")
    modelf.write("     AN       " + str(round(float(model["AN"]), 2)) + "     3.0  \n")
    modelf.write("     AW       " + str(round(float(model["AW"]), 2)) + "     3.0  \n")
    modelf.write("     CA       " + str(round(float(model["CA"]), 2)) + "     3.0  \n")
    modelf.write(
        "     NPAE     " + str(round(float(model["NPAE"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     ACES     " + str(round(float(model["ACES"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     ACEC     " + str(round(float(model["ACEC"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     ECES     " + str(round(float(model["ECES"]), 2)) + "     3.0  \n"
    )
    modelf.write(
        "     ECEC     " + str(round(float(model["ECEC"]), 2)) + "     3.0  \n"
    )
    modelf.write("END\n")
    modelf.close()


def getCorrs():
    global raCorr, decCorr, raRefr, decRefr, refAsec
    return (raCorr, decCorr, raRefr, decRefr, refAsec)


def getVels():
    global raVel, decVel
    return (raVel, decVel)


def setVels(pRaVel, pDecVel):
    global raVel, decVel
    raVel = pRaVel
    decVel = pDecVel


def test_misAlign():
    stars = open("C:\\Users\\obs\\Dropbox\\a_wer\\TPOINT\\perfct_ptr.dat", "r")
    out = open("C:\\Users\\obs\\Dropbox\\a_wer\\TPOINT\\misalign.dat", "w")
    for line in stars:
        if len(line) < 53:
            out.write(line)
            continue
        entry = line[:]
        entry = entry.split()
        h = float(entry[0]) + (float(entry[1]) / 60.0 + float(entry[2]) / 3600.0)
        d = float(entry[3][1:]) + (float(entry[4]) / 60.0 + float(entry[5]) / 3600.0)
        sid = float(entry[12]) + float(entry[13]) / 60.0
        if entry[3][0] == "-":
            d = -d
        ha = reduceHa(sid - h)
        iroll, npitch = transformObsToMount(ha, d, 0)
        nroll = reduceRa(sid - iroll)

        mh, mm, ms = hToH_MStup(nroll)
        md, dm, ds = dToD_MStup(npitch)
        entry[6] = mh
        entry[7] = mm
        entry[8] = ms
        entry[9] = md
        entry[10] = dm
        entry[11] = ds
        outStr = ""
        for field in range(len(entry)):
            outStr += entry[field] + "  "
        outStr = outStr[:-2]
        # NBNBNB Fix to copy over Sidtime and Aux variables.
        out.write(outStr + "\n")
    stars.close()
    out.close()


def transform_mount_to_Icrs(pCoord, pCurrentPierSide, pLST=None, loud=False):

    if pLST is not None:
        lclSid = pLST
    else:
        lclSid = sidTime  # @)@!)#@*  Wild global refernce here.
    if loud:
        print("Pcoord:  ", pCoord)
    roll, pitch = transform_raDec_to_haDec_r(pCoord[0], pCoord[1], sidTime)
    if loud:
        print("MountToICRS1")
    obsHa, obsDec = transform_mount_to_observed_hd(roll, pitch, pCurrentPierSide)
    if loud:
        print("MountToICRS2")
    appRa, appDec = obsToAppHaRa(obsHa, obsDec, sidTime)
    if loud:
        print("Out:  ", appRa, appDec, jYear)
    pCoordJnow = SkyCoord(
        appRa * u.hour, appDec * u.degree, frame="fk5", equinox=equinox_now
    )
    if loud:
        print("pCoord:  ", pCoordJnow)
    t = pCoordJnow.transform_to(ICRS)
    if loud:
        print("returning ICRS:  ", t)
    return (
        reduce_ra_r(fromHMS(str(t.ra.to_string(u.hour)))),
        reduce_dec_r(fromDMS(str(t.dec.to_string(u.degree)))),
    )


def test_icrs_mount_icrs():
    ra = [11]  # 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    dec = [0]  # -40, -31, -20, -10, -5, 0, 10, 25, 40, 55, 70, 85, 88]
    for pRa in ra:
        for pDec in dec:
            for lst in [11]:  # 0.0001, 0, 24, 24.9999]:
                print("Starting:  ", pRa, pDec)
                Coord = (pRa, pDec)
                pierSide = 0
                toMount = transform_icrs_to_mount(Coord, pierSide, pLST=lst)
                print("ToMount:  ", toMount)

                back = transform_mount_to_Icrs(toMount, pierSide, pLST=lst)
                ra_err = reduceHa(back[0] - Coord[0]) * HTOS
                dec_err = reduceDec(back[1] - Coord[1]) * DTOS
                if abs(ra_err) > 0.1 or abs(dec_err) > 0.1:
                    print(pRa, pDec, lst, ra_err, dec_err)

#plog('day_directory:  ', '20221105', '\n')
ut_now, sid_now, equinox_now, day_of_year = get_current_times()
sidTime = round(sid_now.hour, 7)

plog("Ut, Sid, Jnow:  ", ut_now, sid_now, equinox_now)
press = 970 * u.hPa
temp = 10 * u.deg_C
hum = 0.5  # 50%

plog("Utility module loaded at: ", ephem.now(), round((ephem.now()), 4))
plog("Local system Sidereal time is:  ", sidTime)

if __name__ == "__main__":
    print("Welcome to the utility module.")