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

import configparser
import json
import math
import signal
import sys
import requests
import threading
import time

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import os
from azure.iot.device import IoTHubDeviceClient, Message

# Configuration parameters
device_id: int
target_host: str
data_retrieval_interval_seconds: float
data_cleanup_interval_minutes: int
device_connection_string: str

# Globals
nextfire = time.time()
done = False
done_event = threading.Event()
seen_flights = {}
device_client: None

@dataclass
class FlightInformationDto:
    """Struct to capture flight information."""
    ModeSCode: str = None
    Location: str = None
    FlightNumber: str = None
    Altitude: int = 0
    Latitude: float = None
    Longitude: float = None
    Heading: float = None
    AscentCount: int = 0
    TimeAtLocation: datetime = None
    UploadedTime: datetime = None

    def is_descending(self) -> bool:
        return self.AscentCount < 0

    def is_ascending(self) -> bool:
        return self.AscentCount > 0

    def is_level(self) -> bool:
        return self.AscentCount == 0

    def to_dictionary(self):
        my_fields = {
            "ModeSCode": self.ModeSCode,
            "Location": self.Location,
            "FlightNumber": self.FlightNumber,
            "Altitude": self.Altitude,
            "Latitude": self.Latitude,
            "Longitude": self.Longitude,
            "Heading": self.Heading,
            "AscentCount": self.AscentCount,
            "TimeAtLocation": self.TimeAtLocation.isoformat(),
            "UploadedTime": self.UploadedTime.isoformat()
        }
        return my_fields

def signal_handler(signum, frame):
    """ Handles termination signals from the keyboard or the OS"""
    global done

    if (signum == signal.SIGINT.value):
        print("ctr-c pressed")
    elif (signum == signal.SIGTERM.value):
        print("termination signal")

    done = True


def get_altitude(flight_record):
    """Gets the altitude from the flight record, preferring the barometric."""
    altitude = 0
    if ('alt_baro' in flight_record):
        if (flight_record['alt_baro'] != 'ground') and (flight_record['alt_baro'] != ''):
            altitude = flight_record['alt_baro']
    elif ('alt_geom' in flight_record):
        if (flight_record['alt_geom'] != 'ground') and (flight_record['alt_geom'] != ''):
            altitude = flight_record['alt_geom']
    return altitude


def update_flight_info(flight_info: FlightInformationDto, flight_record, now):
    """Updates the altitude, position, heading and time seen information from the flight record."""
    altitude = get_altitude(flight_record)

    if ('lat' in flight_record
        and 'lon' in flight_record
        and 'track' in flight_record
        and altitude != 0):
        flight_info.Latitude = flight_record["lat"]
        flight_info.Longitude = flight_record["lon"]
        flight_info.Heading = flight_record["track"]
        flight_info.Altitude = altitude
    
    flight_info.TimeAtLocation = (now - timedelta(seconds=flight_record["seen"]))

def cleanup_seen_flights():
    """Removes flights from the global dictionary after they have been uploaded and 5 minutes have passed."""
    global seen_flights

    remove_list = []
    for flight in seen_flights.values():
        if (flight.UploadedTime != None):
            uploaded_time = flight.UploadedTime
            if (datetime.now(timezone.utc) > uploaded_time + timedelta(minutes = data_cleanup_interval_minutes)):
                remove_list.append(flight.ModeSCode)

    for item in remove_list:
        del seen_flights[item]




def populate_flight_info(flight_info: FlightInformationDto, flight_record, now):
    """Populates a flight information structure from the raw flight record received."""
    flight_info.ModeSCode = flight_record['hex'].strip()
    flight_info.Location = device_id
    flight_info.FlightNumber = flight_record['flight'].strip()

    altitude = get_altitude(flight_record)

    if (flight_info.Altitude != 0): # not seeing this for the first time
        if (altitude != flight_info.Altitude):
            ascent_count = flight_info.AscentCount
            if (altitude < (flight_info.Altitude - 25 )): # Allow for jitter
                ascent_count -= 1
            elif (altitude > (flight_info.Altitude + 25 )):
                ascent_count += 1
            
            flight_info.AscentCount = ascent_count
            if (flight_info.is_descending() or flight_info.is_level()):
                if (flight_info.Latitude != None and flight_info.Longitude != None and flight_info.Heading != None):
                    return # all data is populated, using earliest complete record, so do not update
    
    update_flight_info(flight_info, flight_record, now)


def process_flight_records(flights):
    """Processes flight records received from the Pi.

    The records are extracted from the json and each is processed. If it is not complete, it is passed over.
    """
    global seen_flights
    global device_client

    records = flights["aircraft"]
    epoch_time = flights["now"]
    now = datetime.fromtimestamp(math.floor(epoch_time), timezone.utc)

    current_flights = {}
    for value in records:
        if ('flight' not in value): continue
        if ('hex' not in value): continue
        if ('seen' not in value): continue
        
        seen_ago = value['seen']
        flight_info_dto = FlightInformationDto()
        if (value['hex'] in seen_flights):  # have we already seen this flight?
            flight_info_dto = seen_flights[value['hex']]
            if (flight_info_dto.UploadedTime != None): continue # the record has already been uploaded, so ignore
            if (seen_ago > data_retrieval_interval_seconds): # it's been over 10s since we saw this plane - there is no fresh data
                current_flights[value['hex']] = flight_info_dto
                continue
        
        populate_flight_info(flight_info_dto, value, now)
        current_flights[flight_info_dto.ModeSCode] = flight_info_dto

        if (flight_info_dto.ModeSCode not in seen_flights):
            seen_flights[flight_info_dto.ModeSCode] = flight_info_dto

    upload_list = []
    # Get upload list ready - flight is uploaded if we can't see it any more, i.e. it is not in current_flights
    for flight in seen_flights.values():
        if (flight.UploadedTime == None) and (flight.ModeSCode not in current_flights):
            flight.UploadedTime = datetime.now(timezone.utc)
            upload_list.append(flight.to_dictionary())
    
    # Upload
    try:
        if (len(upload_list) > 0):
            message = Message(json.dumps(upload_list))
            message.content_encoding = "utf-8"
            message.content_type = "application/json"
            device_client.send_message(message)
    except Exception as e:
        print(e)
        #reset so the records will be processed the next time around
        for fd in upload_list:
            missed_flight = next(f for f in seen_flights.values() if (f.FlightNumber == fd['FlightNumber']))
            missed_flight.UploadedTime = None

    # Cleanup
    cleanup_seen_flights()


def handle_timer(request_uri):
    """Handle the periodic timer callback
    This function is called every 10 seconds to retrieve and
    process plane data.
    """
    global nextfire
    global done
    global done_event

    if (done):
        print ('Exiting...')
        done_event.set()
        return
    r = requests.get(request_uri)
    if (r.status_code == requests.codes.ok):
        flights = r.json()
        process_flight_records(flights)
        
    
    nextfire += data_retrieval_interval_seconds
    threading.Timer(nextfire - time.time(), handle_timer, [request_uri]).start()

def get_configuration(config_file):
    global device_id
    global target_host
    global data_retrieval_interval_seconds
    global data_cleanup_interval_minutes
    global device_connection_string

    config = configparser.ConfigParser()
    config.read(config_file)

    target_host = config['DEFAULT']['TargetHost']
    data_retrieval_interval_seconds = int(config['DEFAULT']['DataRetrievalIntervalSeconds'])
    data_cleanup_interval_minutes = float(config['DEFAULT']['DataCleanupIntervalMinutes'])
    device_id = config['DEVICE']['DeviceId']
    device_connection_string = config['DEVICE']['DeviceConnectionString']

def main():
    global device_client
    global device_connection_string

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if (len(sys.argv) > 1):
        config_file = sys.argv[1]
        get_configuration(config_file)
        device_client = IoTHubDeviceClient.create_from_connection_string(device_connection_string)
    else:
        print("Missing configuration file.")
        exit(0)
    
    request_uri = 'http://{}:8080/data/aircraft.json'.format(target_host)

    handle_timer(request_uri)
    done_event.wait()
    device_client.shutdown()

if __name__ == "__main__":
    main()