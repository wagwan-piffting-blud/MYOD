# Make Your Own DASDEC (MYOD) - Fork that works with Windows and Linux, with audio capabilities, supports EAS_Listener

## Overview
Make Your Own DASDEC (MYOD) is an open-source project that allows users to build their own DASDEC-looking screen using a Raspberry Pi, Linux Server, or any other suitably capable hardware. This fork of the original MYOD project has been modified to work on both Windows and Linux systems, and includes audio capabilities for playing EAS audio through the DASDEC.

## Features
- Cross-platform support for Windows and Linux
- Audio playback capabilities for EAS alerts
- Web-based control panel for easy management
- Support for EAS_Listener to receive and process EAS alerts directly through the DASDEC

## Requirements
- Modern Python, 3.6-3.13 (tested with Python 3.13, **Python 3.14+ does NOT work** due to a dependency issue with `pygame`)
- Required Python libraries and pip (see `requirements.txt`)
- A compatible audio output device (for audio playback)
- Any web browser to access the control panel
- [ffmpeg/ffprobe Binaries](https://ffmpeg.org/download.html) installed on your system for audio processing

## Installation
1. Clone the repository:
```bash
git clone -b cross-platform-with-audio https://github.com/wagwan-piffting-blud/MYOD.git
cd MYOD
```

2. Install the required Python libraries (most likely in a [virtual environment](https://docs.python.org/3/tutorial/venv.html)):
```bash
py -3.13 -m venv venv  # Create a virtual environment
.\venv\Scripts\activate.bat  # Activate the virtual environment on Windows
source venv/bin/activate  # Activate the virtual environment on Linux
pip install -r requirements.txt
```

3. Ensure ffmpeg/ffprobe are installed and accessible in your system's PATH. Otherwise, you can drop the binaries in the same directory as `main.py`. Get the binaries from the [ffmpeg official website](https://ffmpeg.org/download.html) and follow the installation instructions for your operating system. For Windows, use the Gyan build, and for Linux, you can typically install ffmpeg through your package manager (e.g., `sudo apt install ffmpeg` on Debian-based systems).

4. Run the application:
```bash
python main.py
```

5. Open your web browser and navigate to `http://localhost:5000` to access the control panel.

## EAS_Listener support
This fork also includes support for EAS_Listener, allowing you to receive and process EAS alerts directly through the DASDEC. To enable this feature, ensure that you have the EAS_Listener Docker container set up and configured to send alerts to the MYOD application. You can find more information about EAS_Listener and how to set it up on its [GitHub repository](https://github.com/wagwan-piffting-blud/EAS_Listener). Make sure to configure the EAS_Listener to send alerts to the correct endpoint in the MYOD application (e.g., `http://localhost:5000/send`), the endpoint will always be `/send`, and configure your .env file for MYOD to handle incoming alerts with your authentication token, setting USE_AUTH to `true`.

Example .env configuration inside MYOD for EAS_Listener support:
```
USE_AUTH=true
AUTH_TOKEN=dGVzdDp0ZXN0 # This is a base64 encoded token for "test:test". Replace with your actual token for authentication with EAS_Listener.
```

## License
This project is licensed under the GNU General Public License v3.0 License like the parent repo this fork is under - see the [LICENSE](LICENSE) file for details.

## Credits
- [playsamay4 - Upstream MYOD repo this fork is based on](https://github.com/playsamay4/MYOD)
