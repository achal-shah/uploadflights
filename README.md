# uploadflights
A way to upload flight data from a PiAware receiver to an Azure IoT system for offline processing.

## Why?
I have a couple of Raspberry Pi based devices which can pick up ADS-B (Automatic Dependence Surveillance - Broadcast) transmissions sent out by all
modern planes.  These transmissions are sent via radio at 1090 MHz and typically contain the position, heading and altitude of the plane among other
data.  Anyone with the appropriate hardware can receive the transmissions.

The company [FlightAware](www.flightaware.com) crowd sources these transmissions from hobbyists which are then made available on their free website and
mobile app.  They have a Pi-based system (search GitHub for it) which is available to for anyone to create a receiver.  The system picks up the transmissions
and sends them to FlightAware.

I wanted to know what flights my receivers had seen on a particular day.  So I wanted to save one flight record from each unique flight that my receivers see
on any particular day.  The way I did this is to tap into the small lighttpd based API that runs on the Pi to serve a local web interface for watching planes
in real time overlaid on a map.

## How?
I took the opportunity to learn how to run a .Net Core application on a Raspberry Pi and wrote a small program to get the flight information.  I also took
the opportunity to learn Azure IoT Hub which receives the data from the program and then invokes an Azure function to process it.  Finally, I have a small
website which displays this data in a tabular form.  So now I don't have to watch planes in real time.  Once a day, I can just go to my website to find
out interesting flights.  This is what the system looks like:



## Motivation

