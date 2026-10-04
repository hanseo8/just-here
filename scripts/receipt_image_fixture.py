"""Small real images for offline receipt tests."""
import hashlib
import io
from PIL import Image

def receipt_image(label="test", format="JPEG"):
    color = tuple(hashlib.sha256(str(label).encode()).digest()[:3])
    output = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(output, format=format)
    return output.getvalue()
