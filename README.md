# uploadflights
A way to upload flight data from a PiAware receiver to an Azure IoT system for offline processing.

## Why?
I have a couple of Raspberry Pi based devices which can pick up [ADS-B](https://www.faa.gov/nextgen/programs/adsb/) (Automatic Dependent Surveillance - Broadcast) transmissions sent out by all modern planes.  These transmissions are sent via radio at 1090 MHz and typically contain the position, heading and altitude of the plane among other
data.  Anyone with the appropriate hardware can receive the transmissions.

The company [FlightAware](www.flightaware.com) crowd sources these transmissions from hobbyists which are then made available used to provide flight tracking information on their free website and mobile app.  They make available a Pi-based [system](https://flightaware.com/adsb/piaware/build/) to anyone who wishes to build a receiver.  The system picks up the transmissions and sends them to FlightAware.

I wanted to know what flights my receivers had seen on a particular day.  So I wanted to save one flight record from each unique flight that my receivers see
on any particular day.  The way I did this is to write a small program, which would run on the Pi, to tap into the small lighttpd based API that runs on the Pi and is part of the stock FlightAware software.  The API is normally used to serve a local web interface displaying planes seen in real time, overlaid on a map.

### Motivation
Originally (1-2 years ago), this was an opportunity to learn how to run a .Net Core application on a Raspberry Pi and I wrote a small program to get the flight information.  I decided to treat the device as an IoT device and so it was also an opportunity to learn Azure IoT Hub which receives data from the receivers and then invokes an Azure function to process it.  Finally, the system is completed with a small website which displays the data in a tabular form.  So now when I am not watching planes in real time, the system keeps track of what is being seen.  At any time, I can just go to my website to see how many unique flights were seen and to find interesting ones.  For example, since I live close to Seattle, I see frequent Boeing test flights, and at times, the first delivery flights when a customer picks up their brand new plane and takes it home.  This is what the system looks like:

![Image](piaware_system.jpg "System")

Recently I built another PiAware system on a Raspberry Pi Zero.  The Zero has an Arm v6 processor (as opposed to Arm v7 on the more muscular Pis).  DotNet Core
is not supported on these processors, so I had to find another way to collect and send the data.  I considered C, Node.js and Python. I quickly eliminated C as I wanted
something more high level.  Node.js was eliminated because it is also not fully supported on Arm v6 processors.  That left me with Python, which is supported - another learning
opportunity!  Fortunately Azure IoT supports a variety of high level languages on devices, including [Python](https://github.com/Azure/azure-iot-sdk-python).  This project is essentially a port of my original C# code to Python.

## Other Learnings
As is always when you try something new, I learnt a lot along the way, mainly about tooling and working with WSL and Debian.  I had picked the Debian distribution for WSL since the Pi runs Raspabian which is a port of Debian for the Pi.

### Visual Studio Code and WSL
I learnt how to use VS Code (running in Windows) so that it interacts directly with WSL.  You first have to install the Visual Studio Code Remote Development Extension [pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack).  Then you fire up your Debian Bash shell and navigate to the location of your project and type in "code .".  The first time you do this, it will install a small server to allow VS Code to interact with WSL.

Using this arrangement, I am able to code using VS Code and then directly execute the code in WSL.  This made running and testing my code easy as I was working directly in Debian instead of Windows.  Of course, one can do the same running Python directly on Windows, but I wanted the Linux experience.

### Python
In WSL, Python and it's package manager can be installed by:

    sudo apt update
    sudo apt install python3 python3-pip

Next, the Python device libraries can be installed (and listed) by:

    pip3 install azure-iot-device
    pip3 list
    
### Requests library
This is a high level HTTP [library](https://2.python-requests.org/en/latest/) for Python. It makes writing HTTP request-response code in Python a breeze.  It has a built-in JSON decoder.  If there is a warning about dependencies, follow:

    sudo apt remove chardet
    pip3 install charset-normalizer
    pip3 install requests
    
### Pip installs as a non-root account
In order for the Python program to start running automatically on a reboot, I added this line to /etc/rc.local (the same method as for the .Net version):

    python3 /home/pi/uploadflights/uploadflights.py /home/pi/uploadflights/uploadflights.ini &
    
However, it would not run.  To debug this, the following commands can start the service and query its status:

    sudo systemctl start  rc-local.service
    sudo systemctl status  rc-local.service

From this I could see the program bailing because it could not find the requests module.  Running the command "pip3 list" I could see that it was there.  However, running "sudo pip3 list" gave a much shorter list and requests was missing.  So the install location matters (as the modules are script files) and since different users have different home directories, and the system was trying to run the script as root, it makes sense that the module was not being found.  To fix this, I changed the /etc/rc.local entry to:

    sudo -b -u pi python3 /home/pi/uploadflights/uploadflights.py /home/pi/uploadflights/uploadflights.ini
    
 This executes the script as the pi user and the -b flag puts it in the background.
 
 ### Upgrading Debian on WSL
 The Debian install in WSL is fairly old - "stretch".  To get to parity with Raspabian, I upgraded it to "buster" by executing the following steps using the instructions [here](https://davidsmith.is/2019/07/11/updating-your-wsl-debian-image-to-buster/).
 
     sudo apt-get update
     sudo apt-get upgrade
     sudo vi /etc/apt/sources.list # replace "stretch" with "buster"
     sudo apt-get update
     sudo apt-get upgrade
     sudo apt full-upgrade
     
There is a recommendation to do a full backup by running this command in an administrative PowerShell: "wsl --export Debian debian-wsl.tar".

## Resources
1. Python style [guide](https://www.python.org/dev/peps/pep-0008/#comments).
1. Python [documentation](https://docs.python.org/3/)



