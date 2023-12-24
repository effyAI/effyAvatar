import cv2, os, sys, uuid, requests
from io import BytesIO
from PIL import Image
from body_detect import get_coordinate

def cropped_image(source, save_path, uuid1, if_url=True, scale=0.3):
    print('starting...')

    # Download Image from URL
    if if_url:
        input_url = source  # Input Image
        source = f'{save_path}/{uuid1}.png'

        try:
            response = requests.get(input_url)
        except:
            print('Invalid URL Response')
            return {'error': 404}
        if response.status_code == 200:
            # Open the image using PIL (Python Imaging Library)
            img = Image.open(BytesIO(response.content)).convert("RGB")
            print(f"Image Shape: {img.size[0]}x{img.size[1]} pixels")
            # Save the image locally
            img.save(source)
            print(f"Image downloaded and saved as '{uuid}.jpg'")
            print('Image Size: ', os.path.getsize(source))
        else:
            print("Failed to download the image. Status code:", response.status_code)
            return {'error': 404}

    # get body coordinates
    coordinates = get_coordinate(source, scale=scale)
    if coordinates == [0, 0, 0, 0]:
        return {'error': 405}
    if coordinates == [0, 0, 0, 1]:
        return {'error': 406}

    # read and crop the image
    image = cv2.imread(source)
    print('coordinates: ', coordinates)
    cropped_face = image[coordinates[0][1]:coordinates[1][1], coordinates[0][0]:coordinates[1][0]]
    cropped_face = cv2.resize(cropped_face, (256, 256), interpolation = cv2.INTER_LINEAR)

    # save the image
    save_file_path = f"{save_path}/cropped_{uuid1}.png"
    print(f"saved: {save_file_path}")
    cv2.imwrite(save_file_path, cropped_face)

    # return cropped_face
    return save_file_path

# #  For testing
# source = '/home/ubuntu/proj/image2avatar/app/src/input_images/08c63ef8-89fd-11ee-9726-7fa8f6bb819e.jpg'
# save_path = '/home/ubuntu/proj/image2avatar/app/src/cropped_images'
# cropped_image(source, save_path, if_url=False)

# # For Santa
# source_image = 'src/utils/Santa4_Nobg.png'
# print(cropped_image(source_image, 'src/utils/', 'Santa4_Nobg', if_url=False))