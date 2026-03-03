import sys
sys.path.append(r"C:\Program Files\Agisoft\Metashape Pro\python")
import Metashape

# Create a new document and chunk
doc = Metashape.Document()
chunk = doc.addChunk()

# Add photos (replace with your image paths)
photos = [r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025\100OMSYS\Ishi25_S001_0907_A1\P9070{:049}.jpg".format(i) for i in range(1, 66)]
chunk.addPhotos(photos)

# Align cameras
chunk.matchPhotos(accuracy=Metashape.HighAccuracy, generic_preselection=True, reference_preselection=True)
chunk.alignCameras()

# Save the project
doc.save(r"C:\path\to\project.psx")
print("Metashape run completed!")