import cloudinary
import cloudinary.uploader
import cloudinary.api

# ── 1. Configure Cloudinary ──
cloudinary.config(
    cloud_name="dlhv9d3jo",
    api_key="329518554126186",
    api_secret="EDQa0Id8gf5_Xm2Dm_8X7vxwHY8",
    secure=True,
)

# ── 2. Upload a sample image from Cloudinary's demo domain ──
print("Uploading sample image...")
result = cloudinary.uploader.upload("https://res.cloudinary.com/demo/image/upload/sample.jpg")
secure_url = result["secure_url"]
public_id = result["public_id"]
print(f"Secure URL: {secure_url}")
print(f"Public ID:  {public_id}")
print()

# ── 3. Get image details ──
print("Fetching image metadata...")
details = cloudinary.api.resource(public_id)
width = details["width"]
height = details["height"]
fmt = details["format"]
bytes_ = details["bytes"]
print(f"Width:      {width} px")
print(f"Height:     {height} px")
print(f"Format:     {fmt}")
print(f"File size:  {bytes_} bytes")
print()

# ── 4. Generate transformed URL (f_auto + q_auto) ──
# f_auto = automatically serves the most efficient format (e.g. WebP, AVIF)
#          based on the requesting browser's capabilities.
# q_auto = automatically adjusts compression quality to balance file size
#          and visual quality — no hardcoded quality level needed.
transformed_url = cloudinary.CloudinaryImage(public_id).build_url(
    transformation=[{"fetch_format": "auto", "quality": "auto"}]
)

print("Done! Click link below to see optimized version of the image.")
print("Check the size and the format.")
print(transformed_url)
