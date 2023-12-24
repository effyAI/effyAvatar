import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import importlib
from head_detect import new_detect_custom
from PIL import Image
import numpy as np

# model_path = '/content/pose_landmarker.task'
def get_coordinate(source, scale):
    coor = new_detect_custom(source)
    # coor = [0, 0, 0, 0]
    if coor == [0, 0, 0, 0]:
      return [0, 0, 0, 0]

    model_path = 'src/image_cropping/pose_landmarker.task'
    # STEP 2: Create an PoseLandmarker object.
    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=True)
    detector = vision.PoseLandmarker.create_from_options(options)

    # STEP 3: Load the input image.
    image = mp.Image.create_from_file(source)
    img = Image.open(source)

    # STEP 4: Detect pose landmarks from the input image.
    detection_result = detector.detect(image)
    if len(detection_result.pose_landmarks) == 0:
      return [0, 0, 0, 1]

    top = int(coor[1])
    bottom = int(max(detection_result.pose_landmarks[0][11].y*img.size[1], detection_result.pose_landmarks[0][12].y*img.size[1]))
    left = int(detection_result.pose_landmarks[0][12].x*img.size[0])
    right = int(detection_result.pose_landmarks[0][11].x*img.size[0])
    coordinates = [(left, top), (right, bottom)]
    # print(coordinates)
    coordinates = extent_crop(img.size, coordinates, scale)
    # print(coordinates)

    return coordinates

def extent_crop(image_size, coordinates, scale=0.2):
    width = abs(coordinates[1][0] - coordinates[0][0])
    height = abs(coordinates[0][1] - coordinates[1][1])

    center_coor = (coordinates[0][0] + width/2, coordinates[0][1] + height/2)
    length = min(height, width)/2

    # print(scale, (center_coor[1] - length)/length, (center_coor[0] - length)/length, (image_size[1] - (center_coor[1] + length))/length, (image_size[0] - (center_coor[0] + length))/length)
    scale = max(0, min(scale, (center_coor[1] - length)/length, (center_coor[0] - length)/length, (image_size[1] - (center_coor[1] + length))/length, (image_size[0] - (center_coor[0] + length))/length))
    print('\nselected cropping scale: ', scale)
    new_x_start = int(center_coor[0] - length - length*scale)
    new_y_start = int(center_coor[1] - length - length*scale)
    new_x_end = int(center_coor[0] + length + length*scale)
    new_y_end = int(center_coor[1] + length + length*scale)

    new_height = new_y_end - new_y_start
    new_width = new_x_end - new_x_start
    # print(new_width, new_height)

    return [(new_x_start, new_y_start), (new_x_end, new_y_end)]