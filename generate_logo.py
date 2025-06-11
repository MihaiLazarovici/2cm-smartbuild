from PIL import Image, ImageDraw, ImageFont
import os

# Create images folder
os.makedirs('static/images', exist_ok=True)

# Create blank image
img = Image.new('RGBA', (300, 100), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw violet stripe
draw.rectangle((0, 40, 300, 60), fill=(111, 66, 193, 77))  # Violet with opacity

# Load font (use default or download Roboto)
try:
    font = ImageFont.truetype("arialbd.ttf", 40)
except:
    font = ImageFont.load_default()

# Draw text
draw.text((20, 30), "2CM", fill=(0, 123, 255), font=font)  # Blue
draw.text((100, 30), "SmartBuild", fill=(253, 126, 20), font=font)  # Orange

# Save
img.save('static/images/logo.png', 'PNG')