#!/usr/bin/env python
#
# 17/02/2019
# Juan M. Casillas <juanm.casillas@gmail.com>
# https://github.com/juanmcasillas/gopro2gpx.git
#
# Released under GNU GENERAL PUBLIC LICENSE v3. (Use at your own risk)
# added some code by mlpxpro
# https://github.com/mlpxpro/Gopro2gpx.git


import argparse
import array
import os
import platform
import re
import struct
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime

from .config import setup_environment
from . import fourCC
from . import gpmf
from . import gpshelper


def BuildGPSPoints(data, skip=False):
    """
    Data comes UNSCALED so we have to do: Data / Scale.
    Do a finite state machine to process the labels.
    GET
     - SCAL     Scale value
     - GPSF     GPS Fix
     - GPSU     GPS Time
     - GPS5     GPS Data
    """

    points = []
    SCAL = fourCC.XYZData(1.0, 1.0, 1.0)
    GPSU = None
    GPSP = None
    SYST = fourCC.SYSTData(0, 0)

    stats = {
        'ok': 0,
        'badfix': 0,
        'badfixskip': 0,
        'empty' : 0
    }

    GPSFIX = 0 # no lock.
    for d in data:
        
        if d.fourCC == 'SCAL':
            SCAL = d.data
        elif d.fourCC == 'GPSU':
            GPSU = d.data
        elif d.fourCC == 'GPSP':
            GPSP = d.data
            #print(GPSP)
        elif d.fourCC == 'GPSF':
            if d.data != GPSFIX:
                print("GPSFIX change to %s [%s]" % (d.data,fourCC.LabelGPSF.xlate[d.data]))
            GPSFIX = d.data
        elif d.fourCC == 'GPS5':
            # we have to use the REPEAT value.

            for item in d.data:

                if item.lon == item.lat == item.alt == 0:
                    print("Warning: Skipping empty point")
                    stats['empty'] += 1
                    continue

                if GPSFIX == 0:
                    stats['badfix'] += 1
                    if skip:
                        print("Warning: Skipping point due GPSFIX==0")
                        stats['badfixskip'] += 1
                        continue

                retdata = [ float(x) / float(y) for x,y in zip( item._asdict().values() ,list(SCAL) ) ]
                

                gpsdata = fourCC.GPSData._make(retdata)
                #p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, GPSU, gpsdata.speed)
                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, GPSU, GPSP, gpsdata.speed)
                points.append(p)
                stats['ok'] += 1

        elif d.fourCC == 'SYST':
            data = [ float(x) / float(y) for x,y in zip( d.data._asdict().values() ,list(SCAL) ) ]
            if data[0] != 0 and data[1] != 0:
                SYST = fourCC.SYSTData._make(data)


        elif d.fourCC == 'GPRI':
            # KARMA GPRI info

            if d.data.lon == d.data.lat == d.data.alt == 0:
                print("Warning: Skipping empty point")
                stats['empty'] += 1
                continue

            if GPSFIX == 0:
                stats['badfix'] += 1
                if skip:
                    print("Warning: Skipping point due GPSFIX==0")
                    stats['badfixskip'] += 1
                    continue

            data = [ float(x) / float(y) for x,y in zip( d.data._asdict().values() ,list(SCAL) ) ]
            gpsdata = fourCC.KARMAGPSData._make(data)

            if SYST.seconds != 0 and SYST.miliseconds != 0:
                #p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, datetime.fromtimestamp(SYST.miliseconds), gpsdata.speed)
                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, datetime.fromtimestamp(SYST.miliseconds), GPSP, gpsdata.speed)
                points.append(p)
                stats['ok'] += 1




    print("-- stats -----------------")
    total_points = 0
    for i in stats.keys():
        total_points += stats[i]
    print("- Ok:              %5d" % stats['ok'])
    print("- GPSFIX=0 (bad):  %5d (skipped: %d)" % (stats['badfix'], stats['badfixskip']))
    print("- Empty (No data): %5d" % stats['empty'])
    print("Total points:      %5d" % total_points)
    print("--------------------------")
    return(points)

def parseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count")
    parser.add_argument("-b", "--binary", help="read data from bin file", action="store_true")
    parser.add_argument("-s", "--skip", help="Skip bad points (GPSFIX=0)", action="store_true", default=False)
    parser.add_argument("file", help="Video file or binary metadata dump")
    parser.add_argument("outputfile", help="output file. builds KML and GPX")
    parser.add_argument("max_limits", help="maximum valid speed in m/s or kmh")
    parser.add_argument("unit", help="m/s or kmh")
    parser.add_argument("max_precision", help="maximum precision")
    args = parser.parse_args()
    
    return args

def main():
    args = parseArgs()
    
    global max_limit
    global max_precision 
    if args.unit == "kmh":
        max_limit = round(float(args.max_limits)/3.6, 2)
    else:
        max_limit = round(float(args.max_limits),2)
    max_precision = round(float(args.max_precision),0)
        
    config = setup_environment(args)
    parser = gpmf.Parser(config)

    if not args.binary:
        data = parser.readFromMP4()
    else:
        data = parser.readFromBinary()

    # build some funky tracks from camera GPS

    points = BuildGPSPoints(data, skip=args.skip)

    if len(points) == 0:
        print("Can't create file. No GPS info in %s. Exitting" % args.file)
        sys.exit(0)

    kml = gpshelper.generate_KML(max_precision, max_limit, points)
    with open("%s.kml" % args.outputfile , "w+") as fd:
        fd.write(kml)
    print("KML file sucessfully created")

    gpx = gpshelper.generate_GPX(max_precision, max_limit, points, trk_name="gopro7-track")
    with open("%s.gpx" % args.outputfile , "w+") as fd:
        fd.write(gpx)
    print("GPX file sucessfully created")
    
    csv = gpshelper.generate_CSV(max_precision, max_limit, points, trk_name="gopro7-track")
    with open("%s.csv" % args.outputfile , "w+") as fd:
        fd.write(csv)
    print("CSV file sucessfully created")

if __name__ == "__main__":
    main()
