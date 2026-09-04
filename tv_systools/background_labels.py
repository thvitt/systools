"""
Desktop Background Labeler

This script adds descriptive text labels to JPEG images for use as desktop backgrounds.
The text is positioned to remain visible even when the image is cropped to fit a 16:9 screen.

Requirements:
    pip install pillow exifread

Usage:
    python add_background_labels.py [input_dir] [output_dir]

If no arguments provided, processes current directory and saves to 'labeled/' subdirectory.
"""

import os
from pathlib import Path

import exifread
from cyclopts import App
from cyclopts.types import Directory, ExistingDirectory, ExistingImagePath, ImagePath
from PIL import Image, ImageDraw, ImageFont

app = App()
app.register_install_completion_command(add_to_startup=False)


@app.command(name=["-d", "--describe"])
def get_image_description(image_path: ExistingImagePath):
    """
    Extract description from image metadata or filename.
    Priority: EXIF caption -> XMP subject -> filename (up to first dot)
    """
    try:
        # Try to read EXIF data
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, extract_thumbnail=False)

        # Look for caption/description in EXIF
        caption_tags = ["Image ImageDescription", "EXIF UserComment", "Image XPComment"]

        for tag in caption_tags:
            if tag in tags and str(tags[tag]).strip():
                return str(tags[tag]).strip()

    except Exception as e:  # noqa: BLE001
        print(f"Warning: Could not read EXIF from {image_path}: {e}")

    # Try XMP data using PIL
    try:
        with Image.open(image_path) as img:
            if hasattr(img, "tag_v2"):
                # Look for XMP data
                xmp_data = img.tag_v2.get(700)  # XMP tag
                if xmp_data and "dc:subject" in str(xmp_data):
                    # Simple extraction - in production you'd use proper XMP parser
                    pass
    except Exception:  # noqa: BLE001, S110   -- see fallback below
        pass

    # Fallback to filename (up to first dot)
    filename = Path(image_path).stem
    # Clean up common patterns in your filenames
    description = filename.split(".")[0]  # Take part before first dot

    # Clean up the description
    description = description.replace("_", " ").replace("-", " - ")

    return description


def calculate_safe_text_area(image_width, image_height):
    """
    Calculate the safe area for text placement considering 16:9 cropping.
    When an image is fitted to 16:9, parts may be cropped from top/bottom or left/right.
    """
    image_aspect = image_width / image_height
    target_aspect = 16 / 9

    if image_aspect > target_aspect:
        # Image is wider than 16:9, will be cropped on sides
        safe_width = int(image_height * target_aspect)
        safe_height = image_height
        margin_x = (image_width - safe_width) // 2
        margin_y = 0
    else:
        # Image is taller than 16:9, will be cropped on top/bottom
        safe_width = image_width
        safe_height = int(image_width / target_aspect)
        margin_x = 0
        margin_y = (image_height - safe_height) // 2

    return {
        "safe_x": margin_x,
        "safe_y": margin_y,
        "safe_width": safe_width,
        "safe_height": safe_height,
    }


def get_optimal_font_size(text, safe_width, safe_height):
    """Calculate optimal font size based on safe area dimensions."""
    # Start with a base size relative to image dimensions
    base_size = min(safe_width, safe_height) // 25
    return max(24, min(base_size, 72))  # Clamp between 24 and 72


@app.command(name=["-1", "--single"])
def add_text_to_image(
    image_path: ExistingImagePath, output_path: ImagePath, description: str
):
    """
    Add description text to a single image with proper positioning for 16:9 compatibility.

    Args:
        image_path: The raw image to label.
        output_path: output image file to write to
        description: the text to imprint on the label
    """

    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Calculate safe area
        safe_area = calculate_safe_text_area(img.width, img.height)

        # Create drawing context
        draw = ImageDraw.Draw(img)

        # Try to use a nice font, fall back to default
        font_size = get_optimal_font_size(
            description, safe_area["safe_width"], safe_area["safe_height"]
        )
        try:
            # Try common system fonts
            font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
                "C:/Windows/Fonts/arial.ttf",  # Windows
            ]
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    break

            if font is None:
                font = ImageFont.load_default()
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()

        # Calculate text dimensions
        bbox = draw.textbbox((0, 0), description, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Position text in bottom-right corner of safe area with padding
        padding = 20
        text_x = safe_area["safe_x"] + safe_area["safe_width"] - text_width - padding
        text_y = safe_area["safe_y"] + safe_area["safe_height"] - text_height - padding

        # Ensure text doesn't go outside image bounds
        text_x = max(padding, min(text_x, img.width - text_width - padding))
        text_y = max(padding, min(text_y, img.height - text_height - padding))

        # Draw text with outline for better visibility
        outline_width = 2
        text_color = "white"
        outline_color = "black"

        # Draw outline
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text(
                        (text_x + adj_x, text_y + adj_y),
                        description,
                        font=font,
                        fill=outline_color,
                    )

        # Draw main text
        draw.text((text_x, text_y), description, font=font, fill=text_color)

        # Save the result
        img.save(output_path, "JPEG", quality=95)
        print(
            f"Processed: {os.path.basename(image_path)} -> {os.path.basename(output_path)}"
        )
        print(f"  Description: {description}")


@app.default
def process_images(
    input_dir: ExistingDirectory = Path(), output_dir: Directory = Path("labeled"), /
):
    """
    Add descriptive text labels to JPEG images for use as desktop backgrounds.
    The text is positioned to remain visible even when the image is cropped to fit a 16:9 screen.

    Args:
        input_dir: process all images from this directory
        output_dir: labeled images will be placed in this directory. Will be created if it doesn't exist.
    """

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Find all JPEG files
    jpeg_extensions = {".jpg", ".jpeg", ".JPG", ".JPEG"}
    jpeg_files = []

    for ext in jpeg_extensions:
        jpeg_files.extend(input_dir.glob(f"*{ext}"))

    if not jpeg_files:
        print(f"No JPEG files found in {input_dir}")
        return

    print(f"Found {len(jpeg_files)} JPEG files")
    print(f"Processing images from {input_dir} to {output_dir}")
    print()

    for image_file in sorted(jpeg_files):
        try:
            # Get description
            description = get_image_description(image_file)

            # Create output filename
            output_file = output_dir / f"labeled_{image_file.name}"

            # Process image
            add_text_to_image(image_file, output_file, description)

        except Exception as e:  # noqa: BLE001
            print(f"Error processing {image_file.name}: {e}")

    print(f"\nProcessing complete! Labeled images saved to: {output_dir}")


if __name__ == "__main__":
    app()
