import sys
sys.path.append(r"C:\Program Files\Agisoft\Metashape Pro\python")
import Metashape

# Create a new document and chunk
doc = Metashape.Document()
chunk = doc.addChunk()

# Add photos (replace with your image paths)
photos = [r"C:\Users\Arumando\Pictures\Last Da\PB120{:03d}.jpg".format(i) for i in range(1, 66)]
chunk.addPhotos(photos)

# Align cameras
chunk.matchPhotos(accuracy=Metashape.HighAccuracy, generic_preselection=True, reference_preselection=True)
chunk.alignCameras()

# Save the project
doc.save(r"C:\path\to\project.psx")
print("Metashape run completed!")