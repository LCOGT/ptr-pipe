# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
# Continuum Analytics Python ver 3.5.2-0.pyEphem __version__ = '3.7.6.0'
# Computer clock is UTC, Windows Time Zone is UTC, no Daylight slaving.
'''
This is also very old code just grafted on. Needs variable renaming, and a good scrub.

'''

#import shelve
#import pytz
# import skyfield
# from skyfield import api, almanac
# from skyfield.nutationlib import iau2000b
# plog('ObsImports:  ', config, '\n\'', config.site_config['site'])

#import sys

#from pprint import pprint

# NB Change these to hours not fractions of a day.  Should come from site config not be in code here.
from math import *
import ephem
from datetime import datetime, timezone, timedelta
from dateutil import tz
import time
from math import degrees
from global_yard import *
from astropy.time import Time
from wema_utility import plog
import traceback

import requests
from requests.adapters import HTTPAdapter, Retry
reqs = requests.Session()
retries = Retry(total=3,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504])
reqs.mount('http://', HTTPAdapter(max_retries=retries))


EVESCREENFLATDURATION = 60/1440  # 1.5 hours
BIASDARKDURATION = 120/1440  # 2.0 hours
EVESKYFLATDURATION = 105/1440
MORNSKYFLATDURATION = 0/1440
MORNBIASDARKDURATION = 0/1440  # 1.5 min
LONGESTSCREEN = 0/1440  # 1 min
LONGESTFLAT = 2.5/1440
LONGESTDARK = 5.5/1440  # 6 min

DAY_Directory = None  # NB this is an evil use of Globals by WER.  20200408   WER
Day_tomorrow = None
dayNow = None


class Events:

    def __init__(self, config: dict):
        self.config = config
        g_dev['evnt'] = self


        self.dark_exposure_in_minutes = 99999
        self.eve_skyFlatBegin = 99999
        for obsid in config['obsp_ids']:
            # Grab relevant info from OBS
            #obsconfig = config['wema_name']
            """Sends an update to the status endpoint."""
            uri_status = f"https://api.photonranch.org/api/{obsid}/config/"
            try:
                obs_config=reqs.get(uri_status, timeout=20).json()
            except:
                plog ("Failed to get obs_config for " + str(obsid))
                plog(traceback.format_exc())
            
            temp_dark_exposure=obs_config['configuration']['camera']['camera_1_1']['settings']['dark_exposure']
            plog (obsid + " dark exposure: " + str(temp_dark_exposure))
            if temp_dark_exposure < (self.dark_exposure_in_minutes):
                self.dark_exposure_in_minutes = temp_dark_exposure
            
            
            
            temp_eve_offset = obs_config['configuration']['eve_sky_flat_sunset_offset']
            plog (obsid + " eve flat offset: " + str(temp_eve_offset))
            #breakpoint()
            if temp_eve_offset < self.eve_skyFlatBegin:
                self.eve_skyFlatBegin = temp_eve_offset
                
            
        plog ("Used dark exposure: " + str(self.dark_exposure_in_minutes))
        plog ("Used eve flat time: " + str(self.eve_skyFlatBegin ))  
        #breakpoint()

        self.dark_exposure_in_minutes = self.dark_exposure_in_minutes / 60

        # we want the end of eve bias dark to be at least 2* dark exposure before the roof opens
        #self.dark_exposure_in_minutes = self.config['camera']['camera_1_1']['settings']['dark_exposure'] /60
        #self.eve_skyFlatBegin

        self.siteLatitude = round(float(self.config['latitude']), 8)  # 34 20 34.569   #34 + (20 + 34.549/60.)/60.
        self.siteLongitude = round(float(self.config['longitude']), 8)  # -(119 + (40 + 52.061/60.)/60.) 119 40 52.061 W
        self.siteElevation = round(float(self.config['elevation']), 3)

        self.siteRefTemp = round(float(self.config['reference_ambient']), 2)  # These should be a monthly average data.
        self.siteRefPress = round(float(self.config['reference_pressure']), 2)
        #self.flat_offset = self.config['eve_sky_flat_sunset_offset']    # -35 min for SRO

    ###############################
    ###    Internal Methods    ####
    ###############################

    def _sortTuple(self, tup):
        ''' Function to sort the list by second item of tuple '''
        # reverse = None (Sorts in Ascending order)
        # key is set to sort using second element of
        # sublist lambda has been used
        return(sorted(tup, key=lambda x: x[1]))

    def _reduceHa(self, pHa):
        while pHa <= -12:
            pHa += 24.0
        while pHa > 12:
            pHa -= 24.0
        return pHa

    def _getJulianDateTime(self):
        global jYear, JD, MJD, unixEpochOf, localEpoch
        e = Time(datetime.now().isoformat())
        unixEpochOf = time.time()
        jYear = 'J'+str(round(e.jyear, 3))
        JD = e.jd
        MJD = e.mjd
        localEpoch = datetime.now()  # .isoformat()

    def _illumination(self, sunRa, sunDec, sunElev, sunDia, moonRa, moonDec, moonElev, moonDia):
        '''
        Returns illumination on a flat surface in lux. (lumens/m^2. Visual 555nm
        centered light distribution.)      From Supplement to Astro. Almanac,
        Seidelman et al.
        This routine is good to 0.01 lux.  Note low end star and skyglow is
        approximate.

        History
        2011/03/04    WER    First coded.
                            A real test routine should be added.
        2011/10/18    WER    Cleaned up for inclusion in pubSub
        20120911      WER    Clean up more decimal trig. Note Lunar diameter not included.
        '''

        # Enter above with  sunDia, moonDia in degrees., rest are radians
        #sunElev = degrees(sunElev)
        #lmoonElev = degrees(moonElev)

        if sunElev >= -18:
            if sunElev >= 20:
                il = (3.74, 3.97, -4.07, 1.47)
            elif sunElev >= 5:
                il = (3.05, 13.28, -45.98, 64.33)
            elif sunElev >= -0.8:
                il = (2.88, 22.26, -207.64, 1034.3)
            elif sunElev >= -5:
                il = (2.88, 21.81, -258.11, -858.36)
            elif sunElev >= -12:
                il = (2.7, 12.17, -431.69, -1899.93)
            else:
                il = (13.84, 262.72, 1447.42, 2797.93)
            x = sunElev / 90.
            i = 10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) +
                     2 * log10(sunDia/0.50664))
        else:
            i = 0
        if i < 0:
            i = 0
        f = 0
        if moonElev >= -0.8:
            if moonElev >= 20:
                il = (-1.95, 4.06, -4.24, 1.56)
            elif moonElev >= 5:
                il = (-2.58, 12.58, -42.58, 59.06)
            else:
                il = (-2.79, 24.27, -252.95, 1321.29)
            x = moonElev / 90
            raDist = radians(self._reduceHa(degrees(moonRa - sunRa)))
            e = degrees(acos(sin(sunDec) * sin(moonDec) + cos(sunDec) *
                             cos(moonDec) * cos(raDist)))
            f = 180 - e
            if f > 180:
                f = 180
            if f < 0:
                f = 0
            j = 10**(il[0] + x * (il[1] + x * (il[2] + x * il[3])) +
                     (-0.00868 * f - 0.0000000022 * (f ** 4))) + \
                2*log10(moonDia/0.951)  # This should be ckecked - moon dia
        else:
            j = 0
        if j < 0:
            j = 0
        #sunIllum = i
        #moonIllum = j
        illuminance = i + j + 0.002
        #   0.002 = stars and galaxy -- averaged; rest is Airglow,
        #   2e-3 lux is brightness of stars + airglow. Ratio is relative to that number.
        skyBrightRatio = illuminance/0.002
        if skyBrightRatio < 1:
            skyBrightRatio = 1
        skyMag = 22-2.5*log10(skyBrightRatio)
        return illuminance,  skyMag  # Units are lux, dimensionless ratio, approx mag/sq-asec

    def _sunNow(self):
        sun = ephem.Sun()
        sun.compute()
        moon = ephem.Moon()
        moon.compute()
        #if loud: plog('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()  # Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        sun.compute(ptr)
        #if loud: plog('Sun Now: ', sun.ra, sun.dec, sun.az, sun.alt, ptr.date)
        moon.compute(ptr)
        # if loud: plog('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)
        return sun.ra, sun.dec, degrees(sun.alt), degrees(sun.az), moon.ra, moon.dec,\
            degrees(moon.alt), moon.size/3600

    def sun_az_now(self):
        sun = ephem.Sun()
        sun.compute()
        moon = ephem.Moon()
        moon.compute()
        #if loud: plog('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()  # Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        sun.compute(ptr)
        #if loud: plog('Sun Now: ', sun.ra, sun.dec, sun.az, sun.alt, ptr.date)
        moon.compute(ptr)
        # if loud: plog('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)
        return degrees(sun.az)

    def _calcEveFlatValues(self, ptr, sun, pWhen, skyFlatEnd, loud=False, now_spot=False):
        # NB This needs to deal with the Moon being too close!
        ptr.date = pWhen
        sun.compute(ptr)
        if loud:
            plog('Sunset, sidtime:  ', pWhen, ptr.sidereal_time())
        if loud:
            plog('Eve Open  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) - 180
        while SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        if loud:
            plog('Flat spot at az alt:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        if loud:
            plog('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = skyFlatEnd
        sun.compute(ptr)
        if loud:
            plog('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)  # SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)
        if loud:
            plog('Flatspots:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
        FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
        if loud:
            plog('Eve Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
        span = 86400*(skyFlatEnd - pWhen)
        if loud:
            plog('Duration:  ', str(round(span/60, 2)) + 'min')
        RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
        DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
        if loud:
            plog('Eve Rates:  ', RaDot, DecDot)
        if now_spot:
            if loud:
                plog(type(FlatStartRa))
            if loud:
                plog('ReturningRa/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
            return degrees(FlatStartRa)/15, degrees(FlatStartDec)
        else:
            return (degrees(FlatStartRa)/15, degrees(FlatStartDec),
                    degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

    def _calcMornFlatValues(self, ptr, sun, pWhen,  sunrise, loud=False):
        ptr.date = pWhen
        sun.compute(ptr)
        if loud:
            plog()
        if loud:
            plog('Morn Flat Start, sidtime:  ', pWhen, ptr.sidereal_time())
        if loud:
            plog('Morn Flat Start Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        SunAz1 = degrees(sun.az) + 180
        while SunAz1 < 0:
            SunAz1 += 360
        SunAlt1 = degrees(sun.alt) + 105
        if SunAlt1 > 90.:
            SunAlt1 = 180 - SunAlt1
        else:
            SunAz1 = degrees(sun.az)
        plog('Flat spot at:  ', SunAz1, SunAlt1)
        FlatStartRa, FlatStartDec = ptr.radec_of(str(SunAz1), str(SunAlt1))
        plog('Ra/Dec of Flat spot:  ', FlatStartRa, FlatStartDec)
        ptr.date = sunrise
        sun.compute(ptr)
        if loud:
            plog('Flat End  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)  # SunRa = float(sun.ra)
        SunAz2 = degrees(sun.az) - 180
        while SunAz2 < 0:
            SunAz2 += 360
        SunAlt2 = degrees(sun.alt) + 105
        if SunAlt2 > 90:
            SunAlt2 = 180 - SunAlt2
        else:
            SunAz2 = degrees(sun.az)
        if loud:
            plog('Flatspot:  ', SunAz1, SunAlt1, SunAz2, SunAlt2)
        FlatEndRa, FlatEndDec = ptr.radec_of(str(SunAz2), str(SunAlt2))
        plog('Morn Flat:  ', FlatStartRa, FlatStartDec, FlatEndRa, FlatEndDec)
        span = 86400*(sunrise - pWhen)
        plog('Duration:  ', str(round(span/60, 2)) + 'min')
        RaDot = round(3600*degrees(FlatEndRa - FlatStartRa)/span, 4)
        DecDot = round(3600*degrees(FlatEndDec - FlatStartDec)/span, 4)
        plog('Morn Rates:  ', RaDot, DecDot, '\n')
        return (degrees(FlatStartRa)/15, degrees(FlatStartDec),
                degrees(FlatEndRa)/15, degrees(FlatEndDec), RaDot, DecDot)

    def _sunPhaseAngle(self, offsetHrs=0.0):
        dayNow = ephem.now()
        ptr = ephem.Observer()  # Photon Ranch
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        ptr.date = ephem.Date(dayNow + offsetHrs*ephem.hour)
        sun = ephem.Sun()
        sun.compute(ptr)
        moon = ephem.Moon()
        moon.compute(ptr)
        saz = reduceAz(degrees(sun.az) + 180)
        sal = degrees(sun.alt)
        if sal > 0.5:
            saz = 0
            # NBNBNB this needs to be improved to implement sun earth eclipse shadow.
        maz = degrees(moon.az)
        mal = degrees(moon.alt)

        if loud:
            plog('Sun Now: ', saz, degrees(sun.alt))
        moon.compute(ptr)
        if loud:
            plog('Moon Now: ', degrees(moon.az), degrees(moon.alt))
        return round(saz, 2)

    #############################
    ###     Public Methods   ####
    #############################

    def getSunEvents(self):
        '''
        This is used in the enclosure module to determine if is a good time
        of day to open.
        '''
        sun = ephem.Sun()
        # sun.compute(dayNow)
        #moon = ephem.Moon()
        # moon.compute(dayNow)
        #if loud: plog('Sun: ', sun.ra, sun.dec, 'Moon: ', moon.ra, moon.dec)
        ptr = ephem.Observer()  # Photon Ranch
        ptr.date = dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp
        ptr.horizon = '-0:34'
        sunset = ptr.next_setting(sun)
        #middleNight = ptr.next_antitransit(sun)
        sunrise = ptr.next_rising(sun)
        ptr.horizon = '-6'
        sun.compute(ptr)
        #if loud: plog('Sun -6: ', sun.ra, sun.dec, sun.az, sun.alt)
        civilDusk = ptr.next_setting(sun)
        ops_win_begin = civilDusk - 121/1440
        return (ops_win_begin, sunset, sunrise, ephem.now())

    def flat_spot_now(self):
        '''
        Return a tuple with the (az, alt) of the flattest part of the sky.
        '''
        ra, dec, sun_alt, sun_az, *other = self._sunNow()
        #plog('Sun:  ', sun_az, sun_alt)
        sun_az2 = sun_az - 180.  # Opposite az of the Sun
        if sun_az2 < 0:
            sun_az2 += 360.
        sun_alt2 = sun_alt + 105  # 105 degrees along great circle through zenith
        if sun_alt2 > 90:   # Over the zenith so specify alt at above azimuth
            sun_alt2 = 180 - sun_alt2
        else:
            sun_az2 = sun_az  # The sun is >15 degrees below horizon, use its az

        return(sun_az2, sun_alt2)

    def sun_az_alt_now(self):
        '''
        Return a tuple with the (az, alt) of the flattest part of the sky.
        '''
        ra, dec, sun_alt, sun_az, *other = self._sunNow()
        #plog('Sun:  ', sun_az, sun_alt)
        return sun_az, sun_alt

    def illuminationNow(self):

        sunRa, sunDec, sunElev, sunAz, moonRa, moonDec, moonElev, moonDia \
            = self._sunNow()
        illuminance, skyMag = self._illumination(sunRa, sunDec, sunElev, 0.5,
                                                 moonRa, moonDec, moonElev, moonDia)
        return round(illuminance, 3), round(skyMag, 2)
        #if loud: plog('Moon Now: ', moon.ra, moon.dec, moon.az, moon.alt, ptr.date)

    def compute_day_directory(self, loud=False):
        '''
        Mandatory:  The day_directory is the datestring for the Julian day as defined
        by the local astronomical Noon.  Restating the software any time within that
        24 hour period resultin in the Same day_directory.    Site restarts may occur
        at any time but automatic ones will normally occur somewhat after the prior
        night's  final reductions and the upcoming local Noon.

        '''
        global dayNow

        # Checking the local time to check if it is setting up for tonight or tomorrow night.
        now_utc = datetime.now(timezone.utc)  # timezone aware UTC, shouldn't depend on clock time.
        to_zone = tz.gettz(self.config['TZ_database_name'])
        now_here = now_utc.astimezone(to_zone)
        int_sunrise_hour = ephem.Observer().next_rising(ephem.Sun()).datetime().hour + 1
        if int(now_here.hour) < int_sunrise_hour:
            now_here = now_here - timedelta(days=1)
        dayNow = (ephem.now())
        if len(str(now_here.day)) == 1:
            nowhereday = '0' + str(now_here.day)
        else:
            nowhereday = str(now_here.day)
        if len(str(now_here.month)) == 1:
            nowheremonth = '0' + str(now_here.month)
        else:
            nowheremonth = str(now_here.month)

        DAY_Directory = str(now_here.year) + str(nowheremonth) + str(nowhereday)
        #plog('Day_Directory:  ', DAY_Directory)
        g_dev['day'] = DAY_Directory
        
        g_dev['dayhyphened'] = str(now_here.year) + '-' + str(nowheremonth) + '-' + str(nowhereday)

        return DAY_Directory

    def calculate_events(self, endofnightoverride='no'):   # Routine above needs to be called first.
        global dayNow
        loud = True

        # Creating ephem objects to use to calculate timings.
        sun = ephem.Sun()
        moon = ephem.Moon()
        ptr = ephem.Observer()
        ptr.date = dayNow
        ptr.lat = str(self.siteLatitude)
        ptr.lon = str(self.siteLongitude)
        ptr.elev = self.siteElevation
        ptr.compute_pressure()
        ptr.temp = self.siteRefTemp

        # Calculating relevant times according to the sun and the moon.
        ptr.horizon = '-0:34'
        self.sunset = ptr.next_setting(sun)
        self.middleNight = ptr.next_antitransit(sun)
        self.sunrise = ptr.next_rising(sun)
        self.next_moonrise = ptr.next_rising(moon)
        self.next_moontransit = ptr.next_transit(moon)
        self.next_moonset = ptr.next_setting(moon)
        self.last_moonrise = ptr.previous_rising(moon)
        self.last_moontransit = ptr.previous_transit(moon)
        self.last_moonset = ptr.previous_setting(moon)

        # Calculating civil twilight times
        ptr.horizon = '-6'
        sun.compute(ptr)
        self.civilDusk = ptr.next_setting(sun)
        self.civilDawn = ptr.next_rising(sun)

        # Calculating nautical twilight times
        ptr.horizon = '-12'
        sun.compute(ptr)
        self.nauticalDusk = ptr.next_setting(sun)  # Can start clocking and autofocus.
        self.nauticalDawn = ptr.next_rising(sun)

        # Calculating astronomical twilight times
        ptr.horizon = '-18'
        sun.compute(ptr)
        self.astroDark = ptr.next_setting(sun)
        self.astroEnd = ptr.next_rising(sun)

        # A bit of a contorted way of making sure the timings calculate the correct days and times
        # at certain peculiar times of the day that ephem finds tricky to interpret.
        if (self.nauticalDusk - self.astroDark) > 0.5:
            self.nautDusk_plus_half = dayNow
        else:
            self.nautDusk_plus_half = (self.nauticalDusk + self.astroDark)/2  # observing starts
        if (self.nauticalDawn - self.astroEnd) > 0.5:
            self.nautDawn_minus_half = dayNow
        else:
            self.nautDawn_minus_half = (self.nauticalDawn + self.astroEnd)/2  # Observing ends.

        self.duration = (self.astroEnd - self.astroDark)*24
        ptr.date = self.middleNight
        moon.compute(ptr)
        sun = ephem.Sun()
        sun.compute(ptr)
        #if loud: plog('Middle night  Sun:  ', sun.ra, sun.dec, sun.az, sun.alt)
        self.mid_moon_ra = moon.ra
        self.mid_moon_dec = moon.dec
        self.mid_moon_phase = moon.phase
        #if loud:
        #    plog('Middle night Moon Ra Dec Phase:  ', moon.ra, moon.dec, moon.phase)  # , moon.az, moon.alt)

        # The end of the night is when "End Morn Bias Dark" occurs. All timings must end with that
        # as this is when the night ends and the schedule gets reconfigured. So anything scheduled AFTER
        # then needs to be pulled back a day. Primarily because it sometimes does weird things.....
        self.endNightTime = ephem.Date(self.sunrise + 120/1440.)
        #endNightTime = ephem.Date(nautDawn_minus_half + 10/1440.)
        self.cool_down_open = self.sunset + self.config['eve_cool_down_open']/1440        
        self.close_and_park = self.sunrise + self.config['morn_close_and_park']/1440
        self.eve_skyFlatBegin = self.sunset + self.eve_skyFlatBegin/1440

        if endofnightoverride == 'no':
            #if ephem.Date(self.eve_skyFlatBegin) > self.endNightTime:
            #    self.eve_skyFlatBegin = self.eve_skyFlatBegin - 24*ephem.hour
            if ephem.Date(self.sunset) > self.endNightTime:
                self.sunset = self.sunset - 24*ephem.hour
            if ephem.Date(self.civilDusk) > self.endNightTime:
                self.civilDusk = self.civilDusk - 24*ephem.hour
            if ephem.Date(self.nauticalDusk) > self.endNightTime:
                self.nauticalDusk = self.nauticalDusk - 24*ephem.hour
            if ephem.Date(self.nautDusk_plus_half) > self.endNightTime:
                self.nautDusk_plus_half = self.nautDusk_plus_half - 24*ephem.hour
            if ephem.Date(self.astroDark) > self.endNightTime:
                self.astroDark = self.astroDark - 24*ephem.hour
            if ephem.Date(self.middleNight) > self.endNightTime:
                self.middleNight = self.middleNight - 24*ephem.hour
            if ephem.Date(self.astroEnd) > self.endNightTime:
                self.astroEnd = self.astroEnd - 24*ephem.hour
            if ephem.Date(self.nautDawn_minus_half) > self.endNightTime:
                self.nautDawn_minus_half = self.nautDawn_minus_half - 24*ephem.hour
            if ephem.Date(self.nauticalDawn) > self.endNightTime:
                self.nauticalDawn = self.nauticalDawn - 24*ephem.hour
            if ephem.Date(self.civilDawn) > self.endNightTime:
                self.civilDawn = self.civilDawn - 24*ephem.hour
            if ephem.Date(self.sunrise) > self.endNightTime:
                self.sunrise = self.sunrise - 24*ephem.hour
            if ephem.Date(self.cool_down_open) > self.endNightTime:
                self.cool_down_open = self.cool_down_open - 24*ephem.hour

        
        self.evnt = [('Eve Bias Dark      ', ephem.Date(self.cool_down_open- 125/1440)),
                     ('End Eve Bias Dark  ', ephem.Date(self.cool_down_open - (2*self.dark_exposure_in_minutes)/1440)),
                     ('Ops Window Start   ', ephem.Date(self.eve_skyFlatBegin)),  # Enclosure may open.
                     ('Cool Down, Open    ', ephem.Date(self.cool_down_open)),
                     ('Eve Sky Flats      ', ephem.Date(self.eve_skyFlatBegin)),  # Nominally -35 for SRO
                     ('Sun Set            ', ephem.Date(self.sunset)),
                     ('Civil Dusk         ', ephem.Date(self.civilDusk)),
                     ('Naut Dusk          ', ephem.Date(self.nauticalDusk)),
                     #('End Eve Sky Flats  ', ephem.Date(self.nauticalDusk - 10/1440)),
                     ('End Eve Sky Flats  ', ephem.Date(self.civilDusk + 5/1440)),
                     #('Clock & Auto Focus ', ephem.Date(self.nautDusk_plus_half - 8/1440.)),
                     ('Clock & Auto Focus ', ephem.Date(self.civilDusk + 8/1440)),
                     #('Observing Begins   ', ephem.Date(self.nautDusk_plus_half)),
                     ('Observing Begins   ', ephem.Date(self.civilDusk + 18/1440)),
                     ('Astro Dark         ', ephem.Date(self.astroDark)),
                     ('Middle of Night    ', ephem.Date(self.middleNight)),
                     ('End Astro Dark     ', ephem.Date(self.astroEnd)),
                     #('Observing Ends     ', ephem.Date(self.nautDawn_minus_half)),
                     ('Observing Ends     ', ephem.Date(self.civilDawn - 18/1440)),
                     ('Naut Dawn          ', ephem.Date(self.nauticalDawn)),
                     ('Morn Sky Flats     ', ephem.Date(self.nauticalDawn + 30/1440.)),
                     ('Civil Dawn         ', ephem.Date(self.civilDawn)),
                     ('End Morn Sky Flats ', ephem.Date(self.close_and_park - 5/1440.)),  # SRO drving this
                     # Enclosure must close 5 min after sunrise
                     ('Ops Window Closes  ', ephem.Date(self.close_and_park - 2/1440.)),
                     ('Close and Park     ', ephem.Date(self.close_and_park)),
                     ('Sun Rise           ', ephem.Date(self.sunrise)),
                     ('Morn Bias Dark     ', ephem.Date(self.close_and_park + 10/1440.)),
                     ('End Morn Bias Dark ', ephem.Date(self.close_and_park + 120/1440.)),
                     ('Nightly Reset      ', ephem.Date(self.close_and_park + 150/1440.)),
                     ('End Nightly Reset  ', ephem.Date(self.close_and_park + 200/1440.)),
                     ('Prior Moon Rise    ', ephem.Date(self.last_moonrise)),
                     ('Prior Moon Transit ', ephem.Date(self.last_moontransit)),
                     ('Prior Moon Set     ', ephem.Date(self.last_moonset)),
                     ('Moon Rise          ', ephem.Date(self.next_moonrise)),
                     ('Moon Transit       ', ephem.Date(self.next_moontransit)),
                     ('Moon Set           ', ephem.Date(self.next_moonset))]



        # self.evnt = [#('Eve Bias Dark      ', ephem.Date(self.eve_skyFlatBegin - 125/1440)),
        #              #('End Eve Bias Dark  ', ephem.Date(self.eve_skyFlatBegin - 5/1440)),
        #              #('Ops Window Start   ', ephem.Date(self.eve_skyFlatBegin)),  # Enclosure may open.
        #              ('Cool Down, Open    ', ephem.Date(self.cool_down_open)),
        #              #('Eve Sky Flats      ', ephem.Date(self.eve_skyFlatBegin)),  # Nominally -35 for SRO
        #              ('Sun Set            ', ephem.Date(self.sunset)),
        #              ('Civil Dusk         ', ephem.Date(self.civilDusk)),
        #              ('Naut Dusk          ', ephem.Date(self.nauticalDusk)),
        #              #('End Eve Sky Flats  ', ephem.Date(self.nauticalDusk - 10/1440)),
        #              ('End Eve Sky Flats  ', ephem.Date(self.civilDusk + 5/1440)),
        #              #('Clock & Auto Focus ', ephem.Date(self.nautDusk_plus_half - 8/1440.)),
        #              ('Clock & Auto Focus ', ephem.Date(self.civilDusk + 8/1440)),
        #              #('Observing Begins   ', ephem.Date(self.nautDusk_plus_half)),
        #              ('Observing Begins   ', ephem.Date(self.civilDusk + 18/1440)),
        #              ('Astro Dark         ', ephem.Date(self.astroDark)),
        #              ('Middle of Night    ', ephem.Date(self.middleNight)),
        #              ('End Astro Dark     ', ephem.Date(self.astroEnd)),
        #              #('Observing Ends     ', ephem.Date(self.nautDawn_minus_half)),
        #              ('Observing Ends     ', ephem.Date(self.civilDawn - 18/1440)),
        #              ('Naut Dawn          ', ephem.Date(self.nauticalDawn)),
        #              #('Morn Sky Flats     ', ephem.Date(self.nauticalDawn + 30/1440.)),
        #              ('Civil Dawn         ', ephem.Date(self.civilDawn)),
        #              #('End Morn Sky Flats ', ephem.Date(self.sunrise + 30/1440.)),  # SRO drving this
        #              # Enclosure must close 5 min after sunrise
        #              ('Ops Window Closes  ', ephem.Date(self.sunrise + 31/1440.)),
        #              ('Close and Park     ', ephem.Date(self.sunrise + 32/1440.)),
        #              ('Sun Rise           ', ephem.Date(self.sunrise)),
        #              #('Morn Bias Dark     ', ephem.Date(self.sunrise + 34/1440.)),
        #              #('End Morn Bias Dark ', ephem.Date(self.sunrise + 140/1440.)),
        #              ('Nightly Reset      ', ephem.Date(self.sunrise + 180/1440.)),
        #              ('End Nightly Reset  ', ephem.Date(self.sunrise + 200/1440.)),
        #              ('Prior Moon Rise    ', ephem.Date(self.last_moonrise)),
        #              ('Prior Moon Transit ', ephem.Date(self.last_moontransit)),
        #              ('Prior Moon Set     ', ephem.Date(self.last_moonset)),
        #              ('Moon Rise          ', ephem.Date(self.next_moonrise)),
        #              ('Moon Transit       ', ephem.Date(self.next_moontransit)),
        #              ('Moon Set           ', ephem.Date(self.next_moonset))]

        self.evnt_sort = self._sortTuple(self.evnt)
        day_dir = self.compute_day_directory()

        self.timezone = "  " + self.config['timezone'] + ": "
        self.offset = self.config['time_offset']

        event_dict = {}
        for item in self.evnt_sort:
            event_dict[item[0].strip()] = item[1]
        event_dict['use_by'] = ephem.Date(self.sunrise + 4/24.)
        event_dict['day_directory'] = str(day_dir)
        g_dev['events'] = event_dict

    def display_events(self, endofnightoverride='no'):

        plog('Events module reporting for duty. \n')
        plog('Ephem date     :    ', dayNow)
        #plog("Julian Day     :    ")
        #plog("MJD            :    ")
        #plog('Day_Directory  :    ', DAY_Directory)
        #plog('Next day       :    ', Day_tomorrow)
        #breakpoint()

        plog('Night Duration :    ', str(round(self.duration, 2)) + ' hr')
        plog('Moon Ra; Dec   :    ', round(self.mid_moon_ra, 2), ";  ", round(self.mid_moon_dec, 1))
        plog('Moon phase %   :    ', round(self.mid_moon_phase, 1), '%\n')
        plog("Key events for the evening, presented by the Solar System: \n")

        for self.evnt in self.evnt_sort:
            plog(self.evnt[0], 'UTC: ', self.evnt[1], self.timezone, ephem.Date(self.evnt[1] + float(self.offset)/24.))
            # plog(self.evnt[0], 'UTC: ', self.evnt[1], self.timezone)    # NB Additon of local times would be handy here.

    # def display_events(self, endofnightoverride='no'):
    #     breakpoint()
    #     plog('Events module reporting for duty. \n')
    #     plog('Ephem date     :    ', dayNow)
    #     #plog("Julian Day     :    ")
    #     #plog("MJD            :    ")
    #     #plog('Day_Directory  :    ', DAY_Directory)
    #     #plog('Next day       :    ', Day_tomorrow)
    #     plog('Night Duration :    ', str(round(self.duration, 2)) + ' hr')
    #     plog('Moon Ra; Dec   :    ', round(self.mid_moon_ra, 2), ";  ", round(self.mid_moon_dec, 1))
    #     plog('Moon phase %   :    ', round(self.mid_moon_phase, 1), '%\n')
    #     plog("Key events for the evening, presented by the Solar System: \n")

    #     for self.evnt in self.evnt_sort:
    #         # NB Additon of local times would be handy here.
    #         plog(self.evnt[0], 'UTC: ', self.evnt[1], self.timezone, ephem.Date(self.evnt[1] + float(self.offset)/24.))
    #         # plog(self.evnt[0], 'UTC: ', self.evnt[1], self.timezone)    # NB Additon of local times would be handy here.
