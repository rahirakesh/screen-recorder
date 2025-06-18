# screen-recorder
Screen Recording Application: Introductory Notes
Core Functionality
Screen Capture: Records a user-defined region using Pillow (ImageGrab).

Video Encoding: Saves frames as .avi via OpenCV (MJPG codec).

Audio Recording: Optional microphone input via PyAudio (saved as .wav).

Merge & Export: Combines video/audio with FFmpeg → Final .mp4.

Key Features
Modern GUI (tkinter):

Start/Pause/Stop controls.

FPS selection (5-60 fps).

Mouse cursor highlighting.

Microphone device selection.

Area Selection:

Transparent overlay for region selection.

Cross-monitor support.

Safety & UX:

3-second countdown before recording.

Pause/resume functionality.

Output folder quick-access button.

Cleanup of temporary files.



![dfd](https://github.com/user-attachments/assets/15db5a31-cf83-4685-9d3f-449b9e3987b6)



Dependencies
GUI: tkinter

Screen: Pillow

Video: opencv-python

Audio: PyAudio

Merging: FFmpeg (external CLI tool)

Usage
Select recording area.

Configure FPS/audio settings.

Record → Pause/Resume as needed.

Stop → Auto-save .mp4 to chosen location.

Note: Ensure FFmpeg is installed and in PATH for audio merging.
