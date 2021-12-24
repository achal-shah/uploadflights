"""
MIT License

Copyright (c) 2021 Achal Shah

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import math
import signal
import sys
import requests
import threading
import time

from datetime import datetime, timedelta, timezone

# Constants
DEFAULT_TARGET_HOST = "localhost"
DATA_TIME_INTERVAL_SECONDS = 10
DATA_TTL_AFTER_UPLOAD_MINUTES = 5

device_id = 166244
nextfire = time.time()
done = False
seen_flights = {}

def signal_handler(signum, frame):
    """ Handles termination signals from the keyboard or the OS
    """
    global done

    if (signum == signal.SIGINT.value):
        print("ctr-c pressed")
    elif (signum == signal.SIGTERM.value):
        print("termination signal")

    done = True


def get_altitude(flight_record):
    altitude = 0
    if ('alt_baro' in flight_record): altitude = flight_record['alt_baro']
    elif ('alt_geom' in flight_record): altitude = flight_record['alt_geom']
    return altitude


def update_flight_info(flight_info, flight_record, now):
    altitude = get_altitude(flight_record)

    if ('lat' in flight_record): flight_info["Latitude"] = flight_record["lat"]
    if ('lon' in flight_record): flight_info["Longitude"] = flight_record["lon"]
    if ('track' in flight_record): flight_info["Heading"] = flight_record["track"]
    flight_info["TimeAtLocation"] = (now + timedelta(seconds=flight_record["seen"])).isoformat()

def cleanup_seen_flights():
    global seen_flights

    remove_list = []
    for flight in seen_flights.values():
        if ('UploadedTime' in flight):
            uploaded_time = flight['UploadedTime']
            if (datetime.now(timezone.utc) > uploaded_time + timedelta(minutes=DATA_TTL_AFTER_UPLOAD_MINUTES)):
                print(flight["FlightNumber"])
                remove_list.append(flight["ModeSCode"])

    print(remove_list)
    for item in remove_list:
        del seen_flights[item]




def populate_flight_info(flight_info, flight_record, now):
    flight_info['ModeSCode'] = flight_record['hex'].strip()
    flight_info['Location'] = device_id
    flight_info['FlightNumber'] = flight_record['flight'].strip()

    altitude = get_altitude(flight_record)

    if ('Altitude' not in flight_info): # first time seeing this
        flight_info["Altitude"] = altitude
        update_flight_info(flight_info, flight_record, now)
    else:
        if (altitude != flight_info["Altitude"]):
            ascent_count = 0
            if ('AscentCount' in flight_info): ascent_count = flight_info["AscentCount"]
            if (altitude < (flight_info["Altitude"] - 25 )): # Allow for jitter
                ascent_count -= 1
            elif (altitude > (flight_info["Altitude"] + 25 )):
                ascent_count += 1
            
            flight_info["AscentCount"] = ascent_count
            if (ascent_count <= 0): # descending or level - earliest complete record
                if ('Latitude' not in flight_info or 'Longitude' not in flight_info or 'Heading' not in flight_info):
                    update_flight_info(flight_info, flight_record, now)
            else: # ascending - latest complete record
                update_flight_info(flight_info, flight_record, now)


def process_flight_records(flights):
    global seen_flights

    records = flights["aircraft"]
    epoch_time = flights["now"]
    now = datetime.fromtimestamp(math.floor(epoch_time), timezone.utc)

    current_flights = {}
    for value in records:
        if ('flight' not in value): continue
        if ('hex' not in value): continue
        if ('seen' not in value): continue
        
        seen_ago = value['seen']
        flight_info_dto = {}
        if (value['hex'] in seen_flights):  # have we already seen this flight?
            flight_info_dto = seen_flights[value['hex']]
            if ('UploadedTime' in flight_info_dto): continue # the record has already been uploaded, so ignore
            if (seen_ago > DATA_TIME_INTERVAL_SECONDS): # it's been over 10s since we saw this plane in a previous frame, no fresh data
                current_flights[value['hex']] = flight_info_dto
                continue
        
        populate_flight_info(flight_info_dto, value, now)
        current_flights[flight_info_dto["ModeSCode"]] = flight_info_dto

        if (flight_info_dto["ModeSCode"] not in seen_flights):
            seen_flights[flight_info_dto["ModeSCode"]] = flight_info_dto

    upload_list = []
    print("************* seen ******************")
    for flight in seen_flights.values():
        print(flight["FlightNumber"])
        if ('UploadedTime' not in flight) and (flight["ModeSCode"] not in current_flights):
            upload_list.append(flight)
            flight['UploadedTime'] = datetime.now(timezone.utc)
    
    print("************* upload ******************")
    for flight in upload_list:
        print(flight["FlightNumber"] + " " + flight["UploadedTime"].isoformat())

    print("************* clean ******************")
    cleanup_seen_flights()



def handle_timer(request_uri):
    """Handle the periodic timer callback
    This function is called every 10 seconds to retrieve and
    process plane data.
    """
    global nextfire
    global done

    if (done):
        print ('Exiting...')
        return
    print(time.time())
    r = requests.get(request_uri)
    if (r.status_code == requests.codes.ok):
        flights = r.json()
        print(flights)
        process_flight_records(flights)
        
    
    nextfire += DATA_TIME_INTERVAL_SECONDS
    threading.Timer(nextfire - time.time(), handle_timer, [request_uri]).start()

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    target_ip = DEFAULT_TARGET_HOST
    if (len(sys.argv) > 1):
        target_ip = sys.argv[1]
    
    request_uri = 'http://{}:8080/data/aircraft.json'.format(target_ip)

    handle_timer(request_uri)

if __name__ == "__main__":
    main()