from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, CompositeAudioClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import tempfile
import time
import os
from PIL import Image, ImageFilter, ImageDraw
import io
import numpy as np
import requests

app = Flask(__name__)
CORS(app)

# Global list to track temporary files for cleanup
temp_files = []

VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.45,
    "style": 0.40,
}
SOUND_EFFECTS = {
    'vineboom': os.path.join('static', 'sfx', 'vineboom.mp3'),
    'notification': os.path.join('static', 'sfx', 'notification.mp3'),
    'rizz': os.path.join('static', 'sfx', 'rizz.mp3'),
    'imessage_text': os.path.join('static', 'sfx', 'iMessage Text.mp3'),
}

@app.route('/')
def index():
    return render_template('index.html')

def capture_chat_interface(messages, show_header=True, header_data=None):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--hide-scrollbars')
    chrome_options.add_argument('--force-device-scale-factor=1')
    chrome_options.add_argument('--window-size=414,900')
    
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get('http://127.0.0.1:8080')
        
        # Wait for elements
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "dynamic-container"))
        )
        
        # Apply theme if provided
        if header_data and header_data.get('theme') == 'dark':
            driver.execute_script("""
                document.querySelector('.container').classList.add('dark-theme');
            """)
            time.sleep(0.5)  # Wait for theme to apply
        
        # Apply header data if provided
        if header_data:
            # First, set the profile image
            if header_data.get('profileImage'):
                driver.execute_script("""
                    const imgElement = document.getElementById('profileImage');
                    if (imgElement) {
                        imgElement.src = arguments[0];
                        // Ensure image is loaded before proceeding
                        return new Promise((resolve) => {
                            imgElement.onload = resolve;
                            imgElement.onerror = resolve;
                        });
                    }
                """, header_data.get('profileImage', ''))
                time.sleep(1)  # Wait for image to load
            
            # Then, set the header name with forced DOM updates
            if header_data.get('headerName'):
                driver.execute_script("""
                    const headerNameElement = document.getElementById('headerName');
                    if (headerNameElement) {
                        // First, set the text content
                        headerNameElement.textContent = arguments[0];
                        // Force style recalculation
                        headerNameElement.offsetHeight;
                        // Force DOM update by toggling visibility
                        headerNameElement.style.display = 'none';
                        headerNameElement.offsetHeight;
                        headerNameElement.style.display = '';
                        // Force another style recalculation
                        headerNameElement.offsetHeight;
                    }
                """, header_data.get('headerName', 'John Doe'))
                time.sleep(0.5)  # Wait for name to update
        
        # Set transparent background
        driver.execute_script("""
            document.body.style.background = 'transparent';
            document.documentElement.style.background = 'transparent';
        """)
        
        # Modified JavaScript to properly handle sound effects
        driver.execute_script("""
            const messages = arguments[0];
            const showHeader = arguments[1];
            
            // Remove input area
            const inputArea = document.querySelector('.input-area');
            if (inputArea) inputArea.remove();
            
            const container = document.querySelector('.container');
            const messageContainer = document.getElementById('messageContainer');
            const header = document.querySelector('.header');
            const dynamicContainer = messageContainer.querySelector('.dynamic-container');
            
            // Show/hide header
            if (header) {
                header.style.display = showHeader ? 'flex' : 'none';
            }
            
            // Reset container styles
            container.style.minHeight = 'unset';
            container.style.height = 'auto';
            messageContainer.style.height = 'auto';
            messageContainer.style.maxHeight = 'none';
            messageContainer.style.minHeight = 'unset';
            
            // Clear existing messages
            dynamicContainer.innerHTML = '';
            
            messages.forEach(msg => {
                if (msg && msg.text) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message ${msg.is_sender ? 'sender' : 'receiver'} ${msg.type === 'picture' ? 'picture' : ''}`;
                    messageDiv.setAttribute('data-id', msg.id);
                    
                    if (msg.type === 'picture') {
                        const img = document.createElement('img');
                        img.src = msg.text;
                        img.style.maxWidth = '100%';
                        img.style.borderRadius = '12px';
                        messageDiv.appendChild(img);
                    } else {
                        messageDiv.textContent = msg.text.trim();
                    }
                    
                    if (msg.soundEffect) {
                        messageDiv.setAttribute('data-sound-effect', msg.soundEffect);
                    }
                    
                    dynamicContainer.appendChild(messageDiv);
                }
            });

            // Force layout recalculation
            container.offsetHeight;
        """, messages, show_header)
        
        # Wait for messages to render
        time.sleep(1.5)
        
        # Take screenshot
        container = driver.find_element(By.CLASS_NAME, "container")
        screenshot = container.screenshot_as_png
        image = Image.open(io.BytesIO(screenshot))
        
        # Convert to RGBA to handle transparency
        image = image.convert('RGBA')
        
        # Create a mask for rounded corners
        mask = Image.new('L', image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([(0, 0), (image.size[0]-1, image.size[1]-1)], 20, fill=255)
        
        # Apply the mask
        output = Image.new('RGBA', image.size, (0, 0, 0, 0))
        output.paste(image, mask=mask)
        
        # Crop to content
        bbox = output.getbbox()
        if bbox:
            output = output.crop(bbox)
        
        return output
        
    except Exception as e:
        print(f"Error capturing chat interface: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        driver.quit()

def generate_audio_eleven_labs(text, voice_id, api_key):
    """Generate audio using ElevenLabs API"""
    print(f"\nGenerating audio for voice_id: {voice_id}")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"  # Changed to v1
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": VOICE_SETTINGS
    }
    
    print("Making API request...")
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 200:
        temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        temp_files.append(temp_audio.name)
        temp_audio.write(response.content)
        temp_audio.close()
        return temp_audio.name
    else:
        print(f"Error response: {response.text}")
        raise Exception(f"ElevenLabs API error: {response.text}")


def generate_video(messages, header_data):
    try:
        # Get voice settings from header data
        voice_settings = header_data.get('voiceSettings', {})
        api_key = voice_settings.get('apiKey')
        
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
            
        # Voice IDs are now provided directly from frontend - no need to fetch voice map
        
        # Get selected voice IDs from frontend (optional)
        sender_voice_id = voice_settings.get('sender')
        receiver_voice_id = voice_settings.get('receiver')
        
        # Check if voices are provided and valid
        voices_enabled = bool(sender_voice_id and receiver_voice_id and 
                             isinstance(sender_voice_id, str) and isinstance(receiver_voice_id, str))
        
        if voices_enabled:
            print(f"Using voice IDs - Sender: {sender_voice_id}, Receiver: {receiver_voice_id}")
        else:
            print("No voices selected - generating video without voice audio")
        
        # Cloudinary video URLs (replace with your actual URLs)
        CLOUDINARY_VIDEOS = {
            'background': 'https://res.cloudinary.com/ddlor3m74/video/upload/v1757605975/videoplayback_qsachy.mp4',
            'background_1': 'https://res.cloudinary.com/dicyxkb4t/video/upload/v1738448707/f1bhluhc6si77uapdawe.mp4',
            'background_2': 'https://res.cloudinary.com/dicyxkb4t/video/upload/v1738448708/dxo2rlb7kckps0fnfvv4.mp4',
            'background_3': 'https://res.cloudinary.com/dicyxkb4t/video/upload/v1738448706/pytgss2oi9idgch1xhrw.mp4',
            'background_4': 'https://res.cloudinary.com/dicyxkb4t/video/upload/v1738448705/y4k8pbdv6gwi06fo3feg.mp4'
        }
        
        # Get the selected background video
        selected_bg = header_data.get('backgroundVideo', 'background')
        bg_url = CLOUDINARY_VIDEOS.get(selected_bg)
        
        if not bg_url:
            raise ValueError(f"Invalid background video: {selected_bg}")

        # Download the video using requests with retry logic to properly handle chunked download errors
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
            headers = {
                'User-Agent': 'Mozilla/5.0',     # Mimic a typical browser
                'Connection': 'keep-alive'
            }
            # Attempt the download up to 3 times
            for attempt in range(3):
                try:
                    response = requests.get(bg_url, stream=True, headers=headers, timeout=30)
                    if response.status_code != 200:
                        raise Exception(f"Failed to download video from Cloudinary: {response.status_code}")
                    response.raw.decode_content = True  # Ensure decompression is handled
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filter out keep-alive chunks
                            temp_video.write(chunk)
                    print("Download succeeded")
                    break  # Exit the retry loop upon success
                except requests.exceptions.ChunkedEncodingError as e:
                    print(f"Attempt {attempt + 1}: ChunkedEncodingError encountered: {e}")
                    if attempt < 2:
                        print("Retrying download...")
                        time.sleep(5)  # Wait a little before retrying
                    else:
                        raise Exception("Failed to download video after multiple attempts due to ChunkedEncodingError")
            temp_video_path = temp_video.name
            temp_files.append(temp_video_path)

        background = VideoFileClip(temp_video_path, audio=False)
        
        video_clips = []
        audio_clips = []
        current_time = 0
        message_count = 0

        # Process messages in sequences of 5
        for i in range(0, len(messages), 5):
            sequence = messages[i:i+5]
            
            for j in range(len(sequence)):
                current_window = sequence[:j+1]
                message_count += 1
                
                msg = sequence[j]
                
                # Handle text messages with voice over (if voices are enabled)
                if msg.get('type') == 'text':
                    if voices_enabled:
                        try:
                            voice_id = sender_voice_id if msg['is_sender'] else receiver_voice_id
                            audio_path = generate_audio_eleven_labs(msg['text'], voice_id, api_key)
                            voice_audio = AudioFileClip(audio_path)
                            
                            # Add sound effect if specified
                            if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                                print(f"Adding sound effect: {msg['soundEffect']}")
                                effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                                # Combine voice and effect (effect plays slightly before voice)
                                combined_audio = CompositeAudioClip([
                                    effect_audio.with_start(0),
                                    voice_audio.with_start(0.1)  # Slight delay for voice
                                ])
                                audio_duration = max(voice_audio.duration + 0.1, effect_audio.duration)
                            else:
                                combined_audio = voice_audio
                                audio_duration = voice_audio.duration
                            
                            clip_duration = audio_duration + 0.09  # Reduced pause between messages
                        except Exception as e:
                            print(f"Error generating voice audio: {e}")
                            # Fallback to no voice
                            combined_audio = None
                            audio_duration = 1.0
                            clip_duration = audio_duration + 0.09
                    else:
                        # No voices enabled - only handle sound effects
                        if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                            try:
                                print(f"Adding sound effect: {msg['soundEffect']}")
                                effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                                combined_audio = effect_audio
                                audio_duration = effect_audio.duration
                            except Exception as e:
                                print(f"Error loading sound effect: {e}")
                                combined_audio = None
                                audio_duration = 1.0
                        else:
                            combined_audio = None
                            audio_duration = 1.0  # Default duration for text without voice
                        
                        clip_duration = audio_duration + 0.09
                
                # Handle picture messages with sound effects only
                elif msg.get('type') == 'picture':
                    if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                        try:
                            print(f"Adding sound effect: {msg['soundEffect']}")
                            effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                            combined_audio = effect_audio
                            audio_duration = effect_audio.duration
                        except Exception as e:
                            print(f"Error loading sound effect: {e}")
                            combined_audio = None
                            audio_duration = 0.5
                    else:
                        combined_audio = None
                        audio_duration = 0.5  # Default duration for picture messages
                    
                    clip_duration = audio_duration + 0.04
                
                # Ensure clip_duration is valid
                if not isinstance(clip_duration, (int, float)) or clip_duration <= 0:
                    print(f"Invalid clip_duration: {clip_duration}, using default 1.0")
                    clip_duration = 1.0
                
                # Show header only for the first five messages
                show_header = (message_count <= 5)
                
                # Capture current chat interface
                current_image = capture_chat_interface(current_window, show_header=show_header, header_data=header_data)
                if current_image is None:
                    print(f"Failed to capture chat interface for message {i + 1}")
                    continue

                # Resize image to fit the background
                target_width = int(background.w * 0.85)
                width_scale = target_width / current_image.width
                new_height = int(current_image.height * width_scale)
                current_image = current_image.resize((target_width, new_height), Image.LANCZOS)
                current_array = np.array(current_image)

                # Calculate position to center
                x_center = background.w // 2 - target_width // 2
                y_top = background.h // 8  # Position moved higher
                
                # Create clip for current message state
                current_clip = (ImageClip(current_array)
                                .with_duration(clip_duration)
                                .with_position((x_center, y_top)))
                
                video_clips.append(current_clip.with_start(current_time))
                if combined_audio:
                    try:
                        # Validate audio clip before adding
                        if hasattr(combined_audio, 'duration') and combined_audio.duration > 0:
                            audio_clips.append(combined_audio.with_start(current_time))
                        else:
                            print(f"Invalid audio clip duration: {getattr(combined_audio, 'duration', 'No duration')}")
                    except Exception as e:
                        print(f"Error adding audio clip: {e}")

                current_time += clip_duration

        if not video_clips:
            raise Exception("No valid messages to generate video.")

        if current_time > background.duration:
            n_loops = int(np.ceil(current_time / background.duration))
            bg_clips = [background] * n_loops
            background_extended = concatenate_videoclips(bg_clips)
            background_extended = background_extended.subclipped(0, current_time)
        else:
            background_extended = background.subclipped(0, current_time)

        final = CompositeVideoClip(
            [background_extended] + video_clips,
            size=background_extended.size
        )

        if audio_clips:
            try:
                # Validate all audio clips before composition
                valid_audio_clips = []
                for clip in audio_clips:
                    if hasattr(clip, 'duration') and clip.duration > 0:
                        valid_audio_clips.append(clip)
                    else:
                        print(f"Skipping invalid audio clip with duration: {getattr(clip, 'duration', 'No duration')}")
                
                if valid_audio_clips:
                    final = final.with_audio(CompositeAudioClip(valid_audio_clips))
                else:
                    print("No valid audio clips found, creating video without audio")
            except Exception as e:
                print(f"Error creating audio composition: {e}")
                print("Creating video without audio")

        output_path = "output_video.mp4"
        final.write_videofile(output_path, 
                            fps=30, 
                            codec='libx264',
                            audio_codec='aac',
                            bitrate="8000k",
                            preset='slower',
                            threads=4,
                            audio_bitrate="192k")
        
        return output_path
        
    except Exception as e:
        print(f"Error generating video: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

@app.route('/api/generate', methods=['POST'])
def generate_endpoint():
    try:
        data = request.json
        print("Received data:", data)  # Debug log
        messages = data['messages']
        
        # Validate voice settings
        voice_settings = data.get('voiceSettings', {})
        if not voice_settings.get('apiKey'):
            return jsonify({
                'error': 'ElevenLabs API key is required'
            }), 400
        
        # Voice settings are now optional - no validation required
        
        # Debug log for messages and sound effects
        print("Processing messages in generate_endpoint:")
        for msg in messages:
            print(f"Message: {msg.get('text', 'NO TEXT')} | "
                  f"Sender: {msg.get('is_sender', 'NO SENDER')} | "
                  f"Sound Effect: {msg.get('soundEffect', 'NONE')}")
        
        header_data = {
            'profileImage': data.get('profileImage', ''),
            'headerName': data.get('headerName', 'John Doe'),
            'voiceSettings': voice_settings,  # Pass the validated voice settings
            'backgroundVideo': data.get('backgroundVideo', 'background'),
            'theme': data.get('theme', 'light')
        }
        
        video_path = generate_video(messages, header_data)
        return send_file(video_path, as_attachment=True)
    except Exception as e:
        print(f"Error in generate endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fetch-voices', methods=['POST'])
def fetch_voices():
    try:
        data = request.json
        api_key = data.get('apiKey')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
            
        print(f"\nFetching all voices from ElevenLabs account with API key: {api_key[:10]}...")
        
        # Fetch all voices from the user's account
        response = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key}
        )
        
        if response.status_code != 200:
            error_msg = f"Failed to fetch voices: {response.text}"
            print(f"Error response: {error_msg}")
            return jsonify({'error': error_msg}), response.status_code
            
        voices = response.json()
        print(f"Successfully fetched {len(voices['voices'])} total voices from API")
        
        # Include ALL voices from the user's account (no filtering)
        all_voices = []
        for voice in voices['voices']:
            voice_info = {
                'name': voice['name'],
                'id': voice['voice_id'],
                'category': voice.get('category', 'unknown'),
                'description': voice.get('description', ''),
                'labels': voice.get('labels', {}),
                'preview_url': voice.get('preview_url', ''),
                'available_for_tiers': voice.get('available_for_tiers', []),
                'settings': voice.get('settings', {})
            }
            all_voices.append(voice_info)
        
        # Sort voices by name for better UX
        all_voices.sort(key=lambda x: x['name'].lower())
        
        print(f"Found {len(all_voices)} voices in your ElevenLabs account")
        
        if len(all_voices) == 0:
            return jsonify({
                'voices': [],
                'count': 0,
                'message': 'No voices found in your ElevenLabs account.'
            })
        
        return jsonify({
            'voices': all_voices,
            'count': len(all_voices),
            'message': f'Successfully fetched {len(all_voices)} voices from your ElevenLabs account'
        })
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error while fetching voices: {str(e)}"
        print(f"Request error: {error_msg}")
        return jsonify({'error': error_msg}), 500
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"Unexpected error: {error_msg}")
        return jsonify({'error': error_msg}), 500

if __name__ == '__main__':
    # Run Flask on all interfaces with port 8080 for Google Cloud
    app.run(debug=True, host='0.0.0.0', port=8080) 