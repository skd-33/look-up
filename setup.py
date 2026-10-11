"""Download de421.bsp if it doesn't already exist."""
import os, urllib.request

BSP_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/a_old_versions/de421.bsp"
BSP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "de421.bsp")

if os.path.exists(BSP_PATH):
    print(f"de421.bsp already exists at {BSP_PATH}, skipping download.")
else:
    print("Downloading de421.bsp ...")
    urllib.request.urlretrieve(BSP_URL, BSP_PATH)
    print(f"Saved to {BSP_PATH}")
