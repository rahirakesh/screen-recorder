import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import time
from PIL import ImageGrab
import cv2
import numpy as np
import datetime
import os
import sys
import pyautogui # For getting mouse position

import pyaudio # For audio recording
import wave    # For saving audio to WAV file
import subprocess # For calling FFmpeg to merge video and audio

# ScreenRecorderApp class for the main application window
class ScreenRecorderApp:
    def __init__(self, master):
        self.master = master
        master.title("Enhanced Screen Recorder")
        master.geometry("450x450") # Larger initial window size to accommodate new options
        master.resizable(False, False) # Prevent resizing

        # Configure styles for a more modern look
        self.style = ttk.Style()
        self.style.theme_use('clam') # Use 'clam' theme for a flatter, modern look
        self.style.configure('TButton',
                             font=('Inter', 10, 'bold'),
                             background='#4CAF50',
                             foreground='white',
                             relief='flat',
                             padding=10)
        self.style.map('TButton',
                       background=[('active', '#45a049')])

        self.style.configure('Stop.TButton',
                             background='#f44336',
                             foreground='white')
        self.style.map('Stop.TButton',
                       background=[('active', '#da190b')])

        self.style.configure('OpenFolder.TButton',
                             background='#2196F3',
                             foreground='white')
        self.style.map('OpenFolder.TButton',
                       background=[('active', '#1976D2')])

        self.is_recording = False
        self.is_paused = False
        self.recording_thread = None
        self.audio_thread = None # New: Thread for audio recording
        self.out = None  # VideoWriter object
        self.video_filename_raw = "" # New: Path for raw video before merging
        self.audio_filename_temp = "" # New: Path for temporary audio file
        self.final_output_filename = "" # New: Path for final merged video
        self.recording_area = None # (x, y, width, height) of selected area
        self.countdown_active = False

        # Variables for new options
        self.fps_var = tk.StringVar(value="20") # Default FPS
        self.highlight_mouse_var = tk.BooleanVar(value=False) # Default to no mouse highlight
        self.audio_source_var = tk.StringVar(value="No Audio") # New: Default to no audio
        self.audio_device_var = tk.StringVar(value="No Microphone Detected") # New: Stores selected audio device
        self.p = None # PyAudio instance
        self.audio_stream = None
        self.audio_frames = []
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100 # Standard sample rate
        self.CHUNK = 1024 # Audio buffer size

        # --- UI Elements ---

        # Status Label
        self.status_label = ttk.Label(master, text="Ready to record", font=("Inter", 12))
        self.status_label.pack(pady=10)

        # Frame for main action buttons
        button_frame = ttk.Frame(master)
        button_frame.pack(pady=5)

        # Start Recording Button
        self.start_button = ttk.Button(button_frame, text="Start Recording", command=self.start_recording)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        # Pause/Resume Button
        self.pause_button = ttk.Button(button_frame, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_button.grid(row=0, column=1, padx=5, pady=5)

        # Stop Recording Button
        self.stop_button = ttk.Button(button_frame, text="Stop Recording", command=self.stop_recording, state=tk.DISABLED, style='Stop.TButton')
        self.stop_button.grid(row=0, column=2, padx=5, pady=5)

        # Frame for settings/options
        options_frame = ttk.LabelFrame(master, text="Recording Options", padding="10 10")
        options_frame.pack(pady=10, padx=10, fill=tk.X)

        # FPS Selection
        ttk.Label(options_frame, text="Frame Rate (FPS):", font=("Inter", 10)).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.fps_combobox = ttk.Combobox(options_frame, textvariable=self.fps_var,
                                        values=[10, 15, 20, 25, 30, 40, 50, 60], width=5, state="readonly")
        self.fps_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.fps_combobox.set("20") # Set initial value

        # Mouse Highlight Checkbox
        self.highlight_mouse_checkbox = ttk.Checkbutton(options_frame, text="Highlight Mouse Cursor",
                                                        variable=self.highlight_mouse_var)
        self.highlight_mouse_checkbox.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        # Audio Options LabelFrame
        audio_options_frame = ttk.LabelFrame(options_frame, text="Audio Source", padding="5 5")
        audio_options_frame.grid(row=2, column=0, columnspan=2, pady=5, padx=5, sticky="ew")

        # Audio Source Radiobuttons
        self.no_audio_radio = ttk.Radiobutton(audio_options_frame, text="No Audio", variable=self.audio_source_var, value="No Audio", command=self._update_audio_controls)
        self.no_audio_radio.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        self.mic_audio_radio = ttk.Radiobutton(audio_options_frame, text="Microphone", variable=self.audio_source_var, value="Microphone", command=self._update_audio_controls)
        self.mic_audio_radio.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        # Microphone Device Selection
        ttk.Label(audio_options_frame, text="Mic Device:", font=("Inter", 9)).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.mic_device_combobox = ttk.Combobox(audio_options_frame, textvariable=self.audio_device_var,
                                                width=30, state="disabled") # Disabled initially
        self.mic_device_combobox.grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        self._initialize_pyaudio() # Initialize PyAudio and populate devices on startup

        # Open Output Folder Button
        self.open_folder_button = ttk.Button(master, text="Open Output Folder", command=self.open_output_folder, state=tk.DISABLED, style='OpenFolder.TButton')
        self.open_folder_button.pack(pady=5)

        # Protocol for handling window closing
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _initialize_pyaudio(self):
        """Initializes PyAudio and populates the microphone device list."""
        try:
            self.p = pyaudio.PyAudio()
            info = self.p.get_host_api_info_by_index(0)
            num_devices = info.get('deviceCount')
            mic_devices = []
            for i in range(0, num_devices):
                if (self.p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                    device_name = self.p.get_device_info_by_host_api_device_index(0, i).get('name')
                    mic_devices.append((device_name, i)) # Store (name, index)
            
            if mic_devices:
                self.mic_device_combobox['values'] = [name for name, _ in mic_devices]
                self.audio_device_var.set(mic_devices[0][0]) # Set first device as default
                self.mic_devices_map = {name: index for name, index in mic_devices}
            else:
                self.mic_device_combobox['values'] = ["No Microphones Found"]
                self.audio_device_var.set("No Microphones Found")
                self.mic_audio_radio.config(state=tk.DISABLED) # Disable mic option if none found
                messagebox.showwarning("Audio Warning", "No microphone input devices found. Audio recording will be disabled.")
        except Exception as e:
            messagebox.showerror("PyAudio Error", f"Could not initialize PyAudio or find devices. Audio recording may not work: {e}")
            self.mic_audio_radio.config(state=tk.DISABLED) # Disable mic option on error
            self.mic_device_combobox.config(state=tk.DISABLED)
            self.audio_source_var.set("No Audio") # Fallback to no audio
            self.p = None # Ensure p is None if initialization failed

        self._update_audio_controls() # Update initial state of controls

    def _update_audio_controls(self):
        """Enables/disables microphone device selection based on audio source."""
        if self.audio_source_var.get() == "Microphone" and self.mic_devices_map:
            self.mic_device_combobox.config(state="readonly")
        else:
            self.mic_device_combobox.config(state="disabled")

    def start_recording(self):
        """Initiates the screen recording process by showing the area selection window."""
        if self.is_recording:
            messagebox.showwarning("Warning", "Recording is already in progress.")
            return

        # Update FPS based on user selection
        try:
            self.fps = int(self.fps_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid FPS value. Using default (20 FPS).")
            self.fps = 20
            self.fps_var.set("20") # Reset combobox to default

        self.master.withdraw() # Hide main window
        self.area_selector = AreaSelectionWindow(self.master, self._on_area_selected)

    def _on_area_selected(self, area):
        """Callback from AreaSelectionWindow when an area is selected or cancelled."""
        self.master.deiconify() # Show main window again

        if area:
            self.recording_area = area
            self._start_countdown_and_record()
        else:
            self.status_label.config(text="Recording cancelled (no area selected)")
            messagebox.showinfo("Cancelled", "Screen recording setup cancelled.")

    def _start_countdown_and_record(self):
        """Starts a countdown before actual recording begins."""
        self.countdown_active = True
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.open_folder_button.config(state=tk.DISABLED)
        self.fps_combobox.config(state=tk.DISABLED) # Disable options during countdown/recording
        self.highlight_mouse_checkbox.config(state=tk.DISABLED)
        self.no_audio_radio.config(state=tk.DISABLED) # Disable audio options
        self.mic_audio_radio.config(state=tk.DISABLED)
        self.mic_device_combobox.config(state=tk.DISABLED)


        countdown_seconds = 3
        self._update_countdown(countdown_seconds)

    def _update_countdown(self, count):
        """Updates the countdown label."""
        if count > 0:
            self.status_label.config(text=f"Recording starts in {count}...")
            self.master.after(1000, self._update_countdown, count - 1)
        else:
            self.status_label.config(text="Starting recording...")
            self.countdown_active = False
            self._start_recording_process() # Start the actual recording

    def _start_recording_process(self):
        """Starts the actual screen recording after countdown."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Paths for raw video and temporary audio
        self.video_filename_raw = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_video_{timestamp}.avi")
        self.audio_filename_temp = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_audio_{timestamp}.wav")
        # Final output filename will be .mp4
        default_final_filename = f"screen_recording_{timestamp}.mp4"

        # Ask user for final output file location (will be .mp4)
        self.final_output_filename = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialfile=default_final_filename,
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            title="Save Recorded Video As"
        )

        if not self.final_output_filename:
            self.status_label.config(text="Recording cancelled (no file selected)")
            self.start_button.config(state=tk.NORMAL)
            self.fps_combobox.config(state="readonly") # Re-enable options
            self.highlight_mouse_checkbox.config(state=tk.NORMAL)
            self.no_audio_radio.config(state=tk.NORMAL) # Re-enable audio options
            self.mic_audio_radio.config(state=tk.NORMAL)
            self._update_audio_controls() # Update mic device combobox state
            return

        self.is_recording = True
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.open_folder_button.config(state=tk.DISABLED) # Disable while recording
        self.fps_combobox.config(state=tk.DISABLED) # Keep disabled during recording
        self.highlight_mouse_checkbox.config(state=tk.DISABLED)
        self.no_audio_radio.config(state=tk.DISABLED) # Keep audio options disabled
        self.mic_audio_radio.config(state=tk.DISABLED)
        self.mic_device_combobox.config(state=tk.DISABLED)

        self.status_label.config(text="Recording...")

        # Start video recording thread
        self.recording_thread = threading.Thread(target=self._record_screen)
        self.recording_thread.start()

        # Start audio recording thread if selected
        if self.audio_source_var.get() == "Microphone" and self.p:
            self.audio_frames = [] # Clear previous audio frames
            self.audio_thread = threading.Thread(target=self._record_audio)
            self.audio_thread.start()
        elif self.audio_source_var.get() == "Microphone" and not self.p:
            messagebox.showwarning("Audio Warning", "PyAudio was not initialized. Audio recording will be skipped.")
            self.audio_source_var.set("No Audio") # Fallback

    def toggle_pause(self):
        """Toggles the recording between paused and resumed states."""
        if not self.is_recording:
            messagebox.showwarning("Warning", "No recording in progress to pause/resume.")
            return

        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.config(text="Resume")
            self.status_label.config(text="Recording Paused.")
            if self.audio_stream:
                self.audio_stream.stop_stream() # Pause audio stream
        else:
            self.pause_button.config(text="Pause")
            self.status_label.config(text="Recording Resumed.")
            if self.audio_stream:
                self.audio_stream.start_stream() # Resume audio stream

    def _record_screen(self):
        """
        Captures screen frames from the selected area and writes them to a video file.
        This method runs in a separate thread.
        """
        x, y, width, height = self.recording_area
        print(f"Recording area: x={x}, y={y}, w={width}, h={height}") # Debugging

        try:
            # Define the codec and create VideoWriter object
            fourcc = cv2.VideoWriter_fourcc(*'MJPG') # MJPG for broad AVI compatibility
            self.out = cv2.VideoWriter(self.video_filename_raw, fourcc, self.fps, (width, height))

            start_time = time.time()
            frame_count = 0

            while self.is_recording:
                if not self.is_paused:
                    # Capture screenshot of the defined area
                    img = ImageGrab.grab(bbox=(x, y, x + width, y + height))

                    # Convert PIL Image to numpy array (RGB to BGR for OpenCV)
                    frame = np.array(img)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    # Highlight mouse cursor if option is enabled
                    if self.highlight_mouse_var.get():
                        mouse_x, mouse_y = pyautogui.position()
                        # Adjust mouse coordinates relative to the recording area
                        relative_mouse_x = mouse_x - x
                        relative_mouse_y = mouse_y - y

                        # Ensure mouse is within the captured frame boundaries
                        # We also check if the mouse position is reasonable within the desktop bounds
                        # to avoid drawing a highlight if cursor is on an uncaptured monitor area.
                        if 0 <= relative_mouse_x < width and 0 <= relative_mouse_y < height:
                            # Draw a red circle around the mouse pointer
                            cv2.circle(frame, (relative_mouse_x, relative_mouse_y), 15, (0, 0, 255), 2) # Red circle, 2px thickness

                    # Write the frame to the video file
                    self.out.write(frame)

                    frame_count += 1
                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        current_fps = frame_count / elapsed_time
                        self.master.after(0, self.status_label.config, {"text": f"Recording... ({current_fps:.1f} FPS)"})

                # Maintain desired FPS by sleeping for the remaining time
                time_per_frame = 1.0 / self.fps
                sleep_duration = time_per_frame - (time.time() - start_time - (frame_count -1) * time_per_frame)
                if sleep_duration > 0 and not self.is_paused: # Only sleep if not paused
                    time.sleep(sleep_duration)
                elif self.is_paused:
                    time.sleep(0.1) # Small sleep to prevent busy-waiting when paused


        except Exception as e:
            messagebox.showerror("Recording Error", f"An error occurred during video recording: {e}")
            self.stop_recording() # Ensure stop_recording cleans up even on error

    def _record_audio(self):
        """
        Captures audio from the selected microphone and appends to a list.
        This method runs in a separate thread.
        """
        if not self.p: # Check if PyAudio initialized successfully
            return

        try:
            device_name = self.audio_device_var.get()
            device_index = self.mic_devices_map.get(device_name)
            if device_index is None:
                messagebox.showerror("Audio Error", "Selected microphone device not found.")
                return

            self.audio_stream = self.p.open(format=self.FORMAT,
                                            channels=self.CHANNELS,
                                            rate=self.RATE,
                                            input=True,
                                            input_device_index=device_index,
                                            frames_per_buffer=self.CHUNK)

            while self.is_recording or self.is_paused: # Keep running even if paused to collect frames
                if not self.is_paused:
                    data = self.audio_stream.read(self.CHUNK)
                    self.audio_frames.append(data)
                else:
                    time.sleep(0.1) # Small sleep during pause

        except Exception as e:
            messagebox.showerror("Audio Recording Error", f"An error occurred during audio recording: {e}")
        finally:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            # PyAudio instance should only be terminated on app close
            # self.p.terminate() # DO NOT terminate here, only on app close

    def stop_recording(self):
        """Stops the screen recording process and finalizes the video file."""
        if not self.is_recording:
            messagebox.showwarning("Warning", "No recording in progress.")
            return

        self.is_recording = False
        self.is_paused = False # Reset pause state
        self.status_label.config(text="Stopping recording...")

        # Wait for both video and audio threads to finish
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join()
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join()

        # Release the VideoWriter object
        if self.out:
            self.out.release()
            self.out = None

        # Save audio if recorded
        if self.audio_source_var.get() == "Microphone" and self.audio_frames:
            try:
                wf = wave.open(self.audio_filename_temp, 'wb')
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
                wf.setframerate(self.RATE)
                wf.writeframes(b''.join(self.audio_frames))
                wf.close()
            except Exception as e:
                messagebox.showerror("Audio Save Error", f"Could not save audio file: {e}")
                self.audio_filename_temp = "" # Invalidate temp audio file path

        self.status_label.config(text="Processing video and audio...")
        self.master.update_idletasks() # Force UI update

        # Merge video and audio using FFmpeg if audio was recorded
        if self.audio_source_var.get() == "Microphone" and os.path.exists(self.audio_filename_temp):
            self._merge_video_audio()
        else:
            # If no audio or audio failed, just rename the raw video
            try:
                os.rename(self.video_filename_raw, self.final_output_filename)
                messagebox.showinfo("Recording Finished", f"Screen recording saved successfully to:\n{self.final_output_filename}")
            except OSError as e:
                messagebox.showerror("File Error", f"Could not rename video file: {e}. Raw video might be in {self.video_filename_raw}")

        # Cleanup temporary files
        if os.path.exists(self.video_filename_raw):
            os.remove(self.video_filename_raw)
        if os.path.exists(self.audio_filename_temp):
            os.remove(self.audio_filename_temp)

        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.open_folder_button.config(state=tk.NORMAL) # Enable after recording stops
        self.fps_combobox.config(state="readonly") # Re-enable options
        self.highlight_mouse_checkbox.config(state=tk.NORMAL)
        self.no_audio_radio.config(state=tk.NORMAL) # Re-enable audio options
        self.mic_audio_radio.config(state=tk.NORMAL)
        self._update_audio_controls() # Update mic device combobox state

        self.status_label.config(text=f"Recording stopped. Final output:\n{self.final_output_filename}")


    def _merge_video_audio(self):
        """Merges the recorded video and audio using FFmpeg."""
        try:
            # FFmpeg command:
            # -i video_input.avi (input video)
            # -i audio_input.wav (input audio)
            # -c:v copy (copy video stream without re-encoding)
            # -c:a aac (encode audio to AAC, a common codec for MP4)
            # -strict experimental (needed for older AAC encoders, can often be removed)
            # -b:a 192k (audio bitrate)
            # final_output.mp4 (output file)

            command = [
                'ffmpeg',
                '-i', self.video_filename_raw,
                '-i', self.audio_filename_temp,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-strict', 'experimental', # May not be needed on newer FFmpeg, but good for compatibility
                '-b:a', '192k',
                self.final_output_filename
            ]

            self.status_label.config(text="Merging video and audio...")
            self.master.update_idletasks() # Force UI update

            # Execute FFmpeg command
            # Use `creationflags=subprocess.CREATE_NO_WINDOW` on Windows to hide console window
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         startupinfo=startupinfo)
            else:
                process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if process.returncode == 0:
                messagebox.showinfo("Recording Finished", f"Screen recording saved successfully to:\n{self.final_output_filename}")
            else:
                error_message = process.stderr.decode(errors='ignore')
                messagebox.showerror("FFmpeg Error", f"Failed to merge video and audio. FFmpeg output:\n{error_message}\n\n"
                                                      f"Ensure FFmpeg is installed and accessible in your system's PATH. "
                                                      f"The raw video is at: {self.video_filename_raw}")
                # If merging failed, keep the raw video for user
                self.final_output_filename = self.video_filename_raw
        except FileNotFoundError:
            messagebox.showerror("FFmpeg Not Found", "FFmpeg is not installed or not found in your system's PATH. "
                                                    "Please install FFmpeg to enable audio recording. "
                                                    f"Raw video saved to:\n{self.video_filename_raw}")
            # If FFmpeg is not found, keep the raw video for user
            self.final_output_filename = self.video_filename_raw
        except Exception as e:
            messagebox.showerror("Merging Error", f"An unexpected error occurred during merging: {e}\n"
                                                  f"Raw video saved to:\n{self.video_filename_raw}")
            self.final_output_filename = self.video_filename_raw # Keep raw video if merging fails


    def open_output_folder(self):
        """Opens the folder where the last recorded video was saved."""
        if not self.final_output_filename or not os.path.exists(self.final_output_filename):
            messagebox.showwarning("No Video", "No video has been recorded yet or the final file does not exist.")
            return

        folder_path = os.path.dirname(self.final_output_filename)
        if not folder_path: # If filename is just a file in current dir
            folder_path = os.getcwd()

        try:
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin": # macOS
                subprocess.Popen(["open", folder_path])
            else: # Linux
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    def on_closing(self):
        """Handles the window closing event, stopping recording if active."""
        if self.is_recording or self.countdown_active:
            if messagebox.askyesno("Quit", "Recording/countdown is in progress. Do you want to stop and quit?"):
                if self.countdown_active:
                    self.countdown_active = False # Stop countdown if active
                    self.master.after_cancel(self._update_countdown) # Cancel pending after call
                self.stop_recording()
                if self.p:
                    self.p.terminate() # Terminate PyAudio instance
                self.master.destroy()
            else:
                pass # Do nothing, keep the window open
        else:
            if self.p:
                self.p.terminate() # Terminate PyAudio instance
            self.master.destroy()


# AreaSelectionWindow class for selecting a screen region
class AreaSelectionWindow:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.root = tk.Toplevel(parent)
        self.root.overrideredirect(True) # Remove window decorations (border, title bar)
        self.root.attributes('-alpha', 0.3) # Make it transparent
        self.root.attributes('-topmost', True) # Keep it on top

        # Attempt to get the virtual screen dimensions by taking a full screenshot.
        # On Windows, ImageGrab.grab() without bbox typically captures the entire virtual desktop across monitors.
        # On macOS/Linux, its behavior might be limited to the primary display or require specific display settings.
        try:
            full_screen_img = ImageGrab.grab()
            virtual_screen_width, virtual_screen_height = full_screen_img.size
            # For simplicity, assume the virtual desktop's top-left is at (0,0) for the purpose of placing the transparent window.
            # IMPORTANT LIMITATION: If you have monitors with negative coordinates (e.g., a monitor to the left or above the primary display),
            # this transparent window might not extend to cover those areas. Tkinter's ability to precisely query
            # and position windows across a complex multi-monitor setup (especially with negative coordinates) is limited
            # without additional platform-specific libraries or detailed system queries.
            x_offset, y_offset = 0, 0
        except Exception as e:
            # Fallback to primary screen dimensions if full screen grab fails or isn't appropriate
            messagebox.showwarning("Screen Detection Error", f"Could not determine full virtual screen size: {e}. "
                                                            "Defaulting to primary monitor for selection area. "
                                                            "Multi-monitor selection may be limited.")
            virtual_screen_width = parent.winfo_screenwidth()
            virtual_screen_height = parent.winfo_screenheight()
            x_offset, y_offset = 0, 0

        self.root.geometry(f"{virtual_screen_width}x{virtual_screen_height}+{x_offset}+{y_offset}")

        self.canvas = tk.Canvas(self.root, bg='gray', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.current_x = 0
        self.current_y = 0
        self.current_width = self.root.winfo_screenwidth()
        self.current_height = self.root.winfo_screenheight()

        self.root.bind("<ButtonPress-1>", self.on_button_press)
        self.root.bind("<B1-Motion>", self.on_mouse_drag)
        self.root.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", self.on_cancel)

        # Add control frame for buttons at the bottom right
        control_frame = ttk.Frame(self.root)
        control_frame.place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-10)

        self.confirm_button = ttk.Button(control_frame, text="Confirm", command=self.confirm_selection)
        self.confirm_button.pack(side=tk.LEFT, padx=5)
        self.cancel_button = ttk.Button(control_frame, text="Cancel", command=self.on_cancel, style='Stop.TButton')
        self.cancel_button.pack(side=tk.LEFT, padx=5)

        self.root.update_idletasks() # Update window state for accurate geometry

    def on_button_press(self, event):
        """Records the starting point of the drag."""
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                    outline='red', width=2, dash=(5, 2))

    def on_mouse_drag(self, event):
        """Updates the rectangle as the mouse is dragged."""
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x_root, event.y_root)

    def on_button_release(self, event):
        """Finalizes the selected area on mouse release."""
        if self.start_x is not None and self.start_y is not None:
            x1, y1, x2, y2 = self.canvas.coords(self.rect_id)
            # Normalize coordinates to ensure x1 < x2 and y1 < y2
            self.current_x = min(int(x1), int(x2))
            self.current_y = min(int(y1), int(y2))
            self.current_width = abs(int(x2) - int(x1))
            self.current_height = abs(int(y2) - int(y1))

            if self.current_width == 0 or self.current_height == 0:
                messagebox.showwarning("Selection Error", "Selected area is too small. Please drag to create a valid rectangle.")
                self.canvas.delete(self.rect_id)
                self.rect_id = None
                self.start_x = None
                self.start_y = None
                return

            # Draw a solid, highlighted rectangle over the transparent one
            self.canvas.delete(self.rect_id)
            self.rect_id = self.canvas.create_rectangle(self.current_x, self.current_y,
                                                        self.current_x + self.current_width,
                                                        self.current_y + self.current_height,
                                                        outline='blue', width=3) # Highlight final selection

            # Make the window non-transparent temporarily to make the controls more visible
            self.root.attributes('-alpha', 0.9)
            # Reposition the control frame to be visible within the selected area, or always bottom-right
            # If the selected area is very small, placing controls within might be hard.
            # Keeping them at the bottom-right of the full screen for now.

    def confirm_selection(self):
        """Confirms the selected area and passes it back to the main app."""
        if self.rect_id and self.current_width > 0 and self.current_height > 0:
            self.callback((self.current_x, self.current_y, self.current_width, self.current_height))
            self.root.destroy()
        else:
            messagebox.showwarning("No Selection", "Please select an area by dragging your mouse before confirming.")

    def on_cancel(self, event=None):
        """Cancels the selection and returns to the main app."""
        self.callback(None) # Pass None to indicate cancellation
        self.root.destroy()

# Main entry point for the application
if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorderApp(root)
    root.mainloop()
