# Make Your Own DASDEC (MYOD) - Fork that works with Windows and Linux, with audio capabilities

## Overview
Make Your Own DASDEC (MYOD) is an open-source project that allows users to build their own DASDEC-looking screen using a Raspberry Pi, Linux Server, or any other suitably capable hardware. This fork of the original MYOD project has been modified to work on both Windows and Linux systems, and includes audio capabilities for playing EAS audio through the DASDEC.

## Features
- Cross-platform support for Windows and Linux
- Audio playback capabilities for EAS alerts
- Web-based control panel for easy management

## Requirements
- Modern Python, 3.6 or higher (tested with Python 3.12)
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
2. Install the required Python libraries (preferably in a [virtual environment](https://docs.python.org/3/tutorial/venv.html)):
    ```bash
    pip install -r requirements.txt
    ```
3. Ensure ffmpeg/ffprobe are installed and accessible in your system's PATH. Otherwise, you can drop the binaries in the same directory as `main.py`.
4. Run the application:
    ```bash
    python main.py
    ```
5. Open your web browser and navigate to `http://localhost:5000` to access the control panel.

## License
This project is licensed under the GNU General Public License v3.0 License like the parent repo this fork is under - see the [LICENSE](LICENSE) file for details.

## Credits
- [playsamay4 - Upstream MYOD repo this fork is based on](https://github.com/playsamay4/MYOD)
