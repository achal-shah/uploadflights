import signal
import sys
import requests
import threading
import time

from datetime import datetime, timedelta, timezone

# Constants
DEFAULT_TARGET_HOST = "localhost"

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

def populate_flight_info(flight_info, flight_record):
    flight_info['ModeSCode'] = flight_record['hex'].strip()
    flight_info['Location'] = device_id
    flight_info['FlightNumber'] = flight_record['flight'].strip()

    altitude = 0
    if ('alt_baro' in flight_record): altitude = flight_record['alt_baro']
    elif ('alt_geom' in flight_record): altitude = flight_record['alt_geom']

    if ('Altitude' not in flight_info):
        flight_info["Altitude"] = altitude

        if ('lat' in flight_record): flight_info["Latitude"] = flight_record["lat"]
        if ('lon' in flight_record): flight_info["Longitude"] = flight_record["lon"]
        if ('track' in flight_record): flight_info["Heading"] = flight_record["track"]
        flight_info["TimeAtLocation"] = datetime.now(timezone.utc) + timedelta(seconds=flight_record["seen"])

def process_flight_records(records):
    current_flights = {}
    for value in records:
        if ('flight' not in value): continue
        if ('hex' not in value): continue
        if ('seen' not in value): continue
        
        seen_ago = value['seen']
        flight_info_dto = {}
        if (value['hex'] in seen_flights):  # have we already seen this flight?
            flight_info_dto = seen_flights[value['hex']]
            if ('UploadedTime' in info): continue # the record has already been uploaded, so ignore
            if (seen_ago > 10.0): # it's been 10s since we saw this plane, so start tracking it
                current_flights[value['hex']] = flight_info_dto
                continue
        
        populate_flight_info(flight_info_dto, value)
        print("*************")
        for it in datetime.now().timetuple(): print(it)
        print(flight_info_dto)



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
        process_flight_records(flights["aircraft"])
        
    
    nextfire += 10
    threading.Timer(nextfire - time.time(), handle_timer, [request_uri]).start()

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    target_ip = DEFAULT_TARGET_HOST
    if (len(sys.argv) > 0):
        target_ip = sys.argv[1]
    
    request_uri = 'http://{}:8080/data/aircraft.json'.format(target_ip)

    handle_timer(request_uri)

if __name__ == "__main__":
    main()