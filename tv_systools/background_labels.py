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
import sys
from pathlib import Path

import exifread
from PIL import Image, ImageDraw, ImageFont

from cyclopts import App, Parameter

app = App()
app.register_install_completion_command(add_to_startup=False)


def get_image_description(image_path):
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

    except Exception as e:
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
    except Exception:
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


def add_text_to_image(image_path, output_path, description):
    """Add description text to image with proper positioning for 16:9 compatibility."""

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
        except Exception:
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


def process_images(input_dir, output_dir):
    """Process all JPEG images in input directory."""

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Create output directory
    output_path.mkdir(exist_ok=True)

    # Find all JPEG files
    jpeg_extensions = {".jpg", ".jpeg", ".JPG", ".JPEG"}
    jpeg_files = []

    for ext in jpeg_extensions:
        jpeg_files.extend(input_path.glob(f"*{ext}"))

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
            output_file = output_path / f"labeled_{image_file.name}"

            # Process image
            add_text_to_image(image_file, output_file, description)

        except Exception as e:
            print(f"Error processing {image_file.name}: {e}")

    print(f"\nProcessing complete! Labeled images saved to: {output_dir}")


def main():
    if len(sys.argv) == 1:
        # No arguments - use current directory
        input_dir = "."
        output_dir = "labeled"
    elif len(sys.argv) == 2:
        # One argument - input directory, output to labeled subdirectory
        input_dir = sys.argv[1]
        output_dir = os.path.join(input_dir, "labeled")
    elif len(sys.argv) == 3:
        # Two arguments - input and output directories
        input_dir = sys.argv[1]
        output_dir = sys.argv[2]
    else:
        print("Usage: python add_background_labels.py [input_dir] [output_dir]")
        sys.exit(1)

    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist")
        sys.exit(1)

    process_images(input_dir, output_dir)


if __name__ == "__main__":
    main()
