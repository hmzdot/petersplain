import os
import base64
import random
import argparse
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from moviepy import TextClip, CompositeVideoClip, VideoFileClip
from moviepy.video.fx import Crop
from moviepy.video.VideoClip import ImageClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

# Load environment variables from .env file
load_dotenv()
os.makedirs("out", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Initialize the ElevenLabs client
client: ElevenLabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

FONT_PATH = "./data/subtitle_font.otf"
PETER_GRIFFIN_VOICE_ID = "bPz3YmDohVKx47H3m07y"


def generate_voice_with_timestamps(text, voice_id=None):
    """
    Generate speech with word-level timestamps

    Args:
        text (str): The text to convert to speech
        voice_id (str, optional): The voice ID to use. Defaults to None (uses default voice).
        model (str, optional): The model to use. Defaults to "eleven_turbo_v2".

    Returns:
        tuple: (audio_bytes, timestamps_data)
    """
    # Generate audio with timestamps enabled
    generation_response = client.text_to_speech.convert_with_timestamps(
        text=text,
        voice_id=voice_id,
        output_format="mp3_44100_128",
    )

    # Extract audio bytes and timestamp data
    audio_base64 = generation_response.audio_base_64
    audio = base64.b64decode(audio_base64)
    alignment = generation_response.alignment

    print(f"Generated audio with {len(alignment.characters)} word timestamps")

    timestamps = {
        "characters": alignment.characters,
        "character_start_times_seconds": alignment.character_start_times_seconds,
        "character_end_times_seconds": alignment.character_end_times_seconds,
    }

    return audio, timestamps


def create_subtitle_clip(text, start_time, duration, video_size):
    subtitle = (
        TextClip(
            text=text,
            color="white",
            size=video_size,
            method="caption",
            font=FONT_PATH,
            font_size=70,
            stroke_color="black",
            stroke_width=2,
        )
        .with_position(("center", "bottom"))
        .with_start(start_time)
        .with_duration(duration)
    )
    return subtitle


def create_subtitle_list(alignment):
    """
    Generate a list of subtitle entries from alignment data

    Args:
        alignment (dict): The alignment data with characters and timestamps

    Returns:
        list: List of tuples in format (text, start_time, duration)
    """
    subtitles = []
    words = []
    start_time = None

    for i, char in enumerate(alignment["characters"]):
        if char.isspace() and char == " ":  # Only consider spaces as word separators
            if words and start_time is not None:
                end_time = alignment["character_start_times_seconds"][i]
                text = "".join(words)
                duration = end_time - start_time

                # Only add if we have valid timing and text
                if duration > 0 and text.strip():
                    subtitles.append((text, start_time, duration))

                words = []
                start_time = None
        else:
            if start_time is None and i < len(
                alignment["character_start_times_seconds"]
            ):
                start_time = alignment["character_start_times_seconds"][i]
            words.append(char)

    # Handle the last word if there is one
    if (
        words
        and start_time is not None
        and i < len(alignment["character_end_times_seconds"])
    ):
        end_time = alignment["character_end_times_seconds"][i]
        text = "".join(words)
        duration = end_time - start_time

        if duration > 0 and text.strip():
            subtitles.append((text, start_time, duration))

    return subtitles


def crop_video_to_tiktok(video: VideoFileClip) -> VideoFileClip:
    """
    Crop video to TikTok portrait dimensions (1080x1920)
    Centers the crop horizontally
    """
    aspect_ratio = 1080 / 1920

    # Calculate crop dimensions
    current_w = video.w
    current_h = video.h

    target_height = video.h
    target_width = target_height * aspect_ratio

    # Calculate x position to center the crop
    x_center = current_w / 2
    x1 = max(0, x_center - (target_width / 2))

    # If needed, also crop height
    y_center = current_h / 2
    y1 = max(0, y_center - (target_height / 2))

    crop_effect = Crop(x1=x1, y1=y1, width=target_width, height=target_height)
    cropped = crop_effect.apply(video)

    return cropped


def add_peter_image(video: VideoFileClip) -> CompositeVideoClip:
    """
    Add Peter Griffin image to the left side of the video
    """
    # Load and resize Peter's image
    peter_img = ImageClip("data/peter.png")

    target_height = video.h // 2
    peter_img = peter_img.resized(height=target_height)
    padding_x = -40
    padding_y = -100
    peter_img = peter_img.with_position(
        (padding_x, video.h - target_height - padding_y)
    )

    # Make the image last for the full video duration
    peter_img = peter_img.with_duration(video.duration)

    return CompositeVideoClip([video, peter_img])


if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Generate Peter Griffin videos")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument(
        "-o",
        "--output",
        default="default.mp4",
        help="Output file path (default: default.mp4)",
    )
    args = parser.parse_args()

    audio, timestamps = generate_voice_with_timestamps(
        args.text, voice_id=PETER_GRIFFIN_VOICE_ID
    )

    # Generate subtitle list
    subtitles = create_subtitle_list(timestamps)
    print(f"Generated {len(subtitles)} subtitle entries")

    # Select a random video from templates/
    try:
        video_path = random.choice(os.listdir("templates"))
    except IndexError:
        raise Exception("No templates found in templates/")

    video = VideoFileClip(f"templates/{video_path}")
    video = crop_video_to_tiktok(video)

    # Add Peter's image
    video = add_peter_image(video)

    # Create subtitle clips
    subtitle_clips = [
        create_subtitle_clip(text, start, duration, video.size)
        for text, start, duration in subtitles
    ]

    # Set video duration to match audio length plus 2 seconds
    last_subtitle_end = max(start + duration for _, start, duration in subtitles)
    video = video.with_duration(last_subtitle_end + 2)

    # Load the generated audio file
    with open("out/__temp.mp3", "wb") as f:
        f.write(audio)
    audio_clip = AudioFileClip("out/__temp.mp3")
    os.remove("out/__temp.mp3")

    # Combine video with subtitles and audio
    final_video = CompositeVideoClip([video, *subtitle_clips])
    final_video = final_video.with_audio(audio_clip)

    # Export the final video
    final_video.write_videofile(
        f"out/{args.output}",
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="out/__temp.m4a",
    )

    # Clean up
    audio_clip.close()
    video.close()
    final_video.close()
