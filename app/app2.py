from flask import Flask, render_template, request, jsonify
# from flask_cors import CORS
import os, sys, uuid, shutil, time
from threading import Thread
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')
# from src.utils.get_avatar import Get_Avatar
from src.utils.upload_data import get_db

# (1) Image Cropping
sys.path.append('src/image_cropping/')
from get_cropped_image import cropped_image
# (2) DAGAN
sys.path.append('src/dagan/')
from demo import get_talking_video
# (3) Text-to-Speech
from gtts import gTTS
# (4) Lip Sync
sys.path.append('src/sadTalker')
from inf2 import lip_sync
# (5) Upload to S3
from src.utils.upload_to_s3 import upload_video_to_s3
# (6) Directory Cleaning
def remove_files_in_directory(directory_path):
    for folder in os.listdir(directory_path):
        for filename in os.listdir(os.path.join(directory_path, folder)):
            file_path = os.path.join(directory_path, folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    print('Cleaning Directory Completed')

app = Flask(__name__)

def init_progress(uuid1, db, total_progress):
    collection = 'progress'
    status_json = {uuid1: {'status':0,'current_progress':0 ,'total_progress': total_progress}}
    
    mongo_id = db[collection].insert_one(status_json)
    return mongo_id

def update_by_mongo_id(db, collection_name, mongo_id, new_json):
    collection = db[collection_name]
    collection.update_one({"_id": mongo_id}, {"$set": new_json})

def update_log(db, mongo_id, uinq_id, status, current_progress, total_progress, s3_link=None):
    collection = 'progress'

    status_json = {}
    status_json[uinq_id] = {'status':status}
    status_json[uinq_id]['current_progress'] = current_progress
    status_json[uinq_id]['total_progress'] = total_progress
    if s3_link:
        status_json[uinq_id]['s3_link'] = s3_link
    update_by_mongo_id(db, collection, mongo_id, status_json)

class Get_Avatar():
    def __init__(self, request, db):
        self.uuid1 = str(uuid.uuid1())
        self.input = request.get_json()
        self.db = db
        
    def start(self):
    # def get_avatar():
        start_time = time.time()
        db = self.db
        try:
            input = self.input
            # print(input)
        except Exception as e:
            print("Post data reading error:", e) # Send error to server
            return {"error":403}
        
        # UUID for Images and Videos
        uuid1 = str(self.uuid1)

        ## init progress
        mongo_id = init_progress(uuid1, db, 100)

        # input = {image (Optional): '', text: '', santa: 1}
        print('user input: ', input)

        generate_video = True if input.get("input_image") != '' else False

        res_dir = '/home/ubuntu/image2avatar/app/src/results-1' if ((datetime.now().minute//4)%2) == 0 else '/home/ubuntu/image2avatar/app/src/results-2'
        print(f'\nWorking on {res_dir}')
        
        if (((datetime.now().minute+6)//4)%2) == 0 and res_dir != '/home/ubuntu/image2avatar/app/src/results-1':
            shutil.rmtree('/home/ubuntu/image2avatar/app/src/results-1', ignore_errors=True)
            print(f'\nDeleted src/results-1')
        else:
            if res_dir != '/home/ubuntu/image2avatar/app/src/results-2':
                shutil.rmtree('/home/ubuntu/image2avatar/app/src/results-2', ignore_errors=True)
                print(f'\nDeleted src/results-2')

        os.makedirs(res_dir, exist_ok=True)

        # try:
        if True:
            if generate_video:
                # (1) Image -> Image_cropping() -> Cropped_Image
                # input_image = 'src/results/input_images/001.jpg'
                input_image = str(input.get("input_image"))
                save_path = res_dir
                image = cropped_image(input_image, save_path, uuid1=uuid1, if_url=True)
                if image == {'error': 404}:
                    return {'status': 404, 'message': 'Invalid Image URL'}
                elif image == {'error': 405}:
                    return {'status': 405, 'message': 'Head not detected'}
                elif image == {'error': 406}:
                    return {'status': 406, 'message': 'Pose not detected'}

                # (2) Cropped_Image -> DAGAN -> Talking_Video
                driving_video = 'src/dagan/driving/stare3.mp4'
                result_video = get_talking_video(source_image=image, driving_video=driving_video, uuid1=uuid1, working_path=res_dir)
            else:
                santa_dict = {'1': 'Santa1.jpeg', '2': 'Santa2.png', '3': 'Santa3.jpeg', '4': 'Santa4.png'}
                if str(input.get("santa_id")) not in santa_dict.keys():
                    return {'status': 404, 'message': 'Chosen Santa not available'}
                image = f'src/utils/{santa_dict[str(input.get("santa_id"))]}'
                result_video = f'src/utils/{santa_dict[str(input.get("santa_id"))].split(".")[0]}.mp4'
                print(image, result_video)


            # (3) Result_Audio -> text-to-audio
            text = input.get("input_text")
            result_audio = f'{res_dir}/gtts_wish_msg.mp3'
            tts = gTTS(text, lang='en-us')
            tts.save(result_audio)

            # progress update 30%
            update_log(db=db, mongo_id=mongo_id, uinq_id=uuid1, status=0, current_progress=30, total_progress=100)
            # db['progress'].update_one({"request_id": self.uuid1}, {"$set": {"progress": "30"}})

            # (4) Taking_Video -> Lip_Sync -> lip_syned_talking_video
            # driven_audio = 'src/sadTalker/examples/driven_audio/bus_chinese.wav'
            # driven_audio = 'src/utils/wish_msg.mp4'
            driven_audio = result_audio
            # source_image = image
            source_image = result_video
            ref_eyeblink = None
            # ref_eyeblink = result_video
            talking_video = lip_sync(driven_audio, source_image, res_dir, ref_eyeblink)

            # progress update 90%
            update_log(db=db, mongo_id=mongo_id, uinq_id=uuid1, status=0, current_progress=90, total_progress=100)
            # db['progress'].update_one({"request_id": self.uuid1}, {"$set": {"progress": "90"}})

            # (5) Upload Video to S3
            s3_vid_name = str(uuid1) + '.mp4'
            res_url = upload_video_to_s3('AKIAVZBVXJWJLAWNRCWZ', 'SzjAgZQBhe7oPaQfqNgkWAe34aAHnBrd9CD1Kbjx', 'ap-southeast-1', 'effy-bandhan', s3_vid_name, talking_video)

            # (6) Clean Downloaded and Proceed Images and Video
            # remove_files_in_directory('src/results')
            # shutil.rmtree('src/results/', ignore_errors=True)
            # try:
            # if generate_video:
            #     os.remove(f'src/results/{uuid1}.png')
            #     os.remove(image)
            #     os.remove(result_video)
            # os.remove(result_audio)
            # os.remove(talking_video)
            # except Exception as e:
            #     print('File Deletion Error: ', e)
            
            # progress update 100%
            update_log(db=db, mongo_id=mongo_id, uinq_id=uuid1, status=1, current_progress=100, total_progress=100, s3_link=res_url)

            # print({'status': 200, 'message': 'Success', 'out_video_path': res_url, 'total_time_taken': time.time()-start_time})
            # res_url = {'satya': 'url', 'mahesh': 'url'}
            # return {'status': 200, 'message': 'Success', 'out_video_path': res_url}

@app.route('/')
def hello_world():
	return 'Hello World!'

@app.route('/test', methods=['POST'])
def test():
    db = get_db()
    get_avatar = Get_Avatar(request, db)
    return get_avatar.start()

@app.route('/get_avatar', methods=['POST'])
def get_avatar_video():

    db = get_db()
    get_avatar = Get_Avatar(request, db)
    print('\nuuid1: ', get_avatar.uuid1)

	
    res = {"request_id": get_avatar.uuid1, "progress": "progress_initiated", "exception": "", "status": 400} # This will be the return element

    # create progress object
    progress_object = {
        "request_id": get_avatar.uuid1,
        "progress": 10,
        "exception": '',
        "status": 400,
    }
    # new_res = db['progress'].insert_one(progress_object)
    # print("db['progress']: ", db['progress'].find_one({"request_id": get_avatar.uuid1}))

    # This following needs to be a thread so that we are able to receive the progress api request while we keep the dub process going
    Thread(target=get_avatar.start(), args=(get_avatar.input, get_avatar.uuid1)).start()
    return res

def get_all(db,collection_name):
    collection = db[collection_name]
    all_items = collection.find()
    return all_items

def find_one_by_uiqu_id( db, collection_name, id):
    all_items = get_all(db, collection_name)
    for item in all_items:
        if id in item:
            return item
    return None

@app.route('/get_progress', methods=['GET'])
def get_progress():
    json = request.get_json()
    db = get_db()
    print('\nSending Progress Status...')

    if 'request_id' not in json:
        return {"msg": "request id is missing", "msg_code": "request_id_missing", "status": "400"}

    # res = db['progress'].find_one({"request_id": json["request_id"]})
    # print('res: ', res)
	
    res = find_one_by_uiqu_id(db, 'progress', json["request_id"])
    print('res: ', res)
    if res is None:
            return ({"Error": "No Log Found for this ID"}, 400)
        
    return res 

    # if status is not complete then send the actual status
    # if res['progress'] != 100:
    #     if "exception" in res:
    #         return \
    #             {
    #                 "status": 500,
    #                 "msg": res['exception'],
    #                 "msg_code": "Progress API Error"
    #             }
    #     else:
    #         return {"progress": res['progress'], "status": "processing"}
    # else:
    #     # Delete the progress element as it is no longer needed and the main s3 url is pushed to the main table
    #     # db['progress'].delete_one({"request_id": json["request_id"]})
    #     return res['final_response']


# class New_Get_Avatar():
#     def __init__(self, request, db):
#         self.uuid1 = uuid.uuid1()
#         self.input = request.get_json()
#         self.db = db
        
    # def start(self):
def get_avatar(input, db, uuid1):
    start_time = time.time()
    # db = self.db  # HAVE TO BE UNCOMMENTED FOR CLASS
    # try:
    #     # input = self.input  # HAVE TO BE UNCOMMENTED FOR CLASS
    #     # print(input)
    # except Exception as e:
    #     print("Post data reading error:", e) # Send error to server
    #     return {"error":403}
    
    # UUID for Images and Videos
    # uuid1 = self.uuid1  # HAVE TO BE UNCOMMENTED FOR CLASS

    # input = {image (Optional): '', text: '', santa: 1}
    print('user input: ', input)

    generate_video = True if input.get("input_image") != '' else False

    res_dir = 'src/results-1' if ((datetime.now().minute//4)%2) == 0 else 'src/results-2'
    # print(f'\nWorking on {res_dir}')
    # if (((datetime.now().minute+6)//4)%2) == 0 and res_dir != 'src/results-1':
    #     shutil.rmtree('src/results-1', ignore_errors=True)
    #     print(f'\nDeleted src/results-1')
    # else:
    #     if res_dir != 'src/results-2':
    #         shutil.rmtree('src/results-2', ignore_errors=True)
    #         print(f'\nDeleted src/results-2')

    # os.makedirs(res_dir, exist_ok=True)

    # try:
    if True:
        if generate_video:
            # (1) Image -> Image_cropping() -> Cropped_Image
            # input_image = 'src/results/input_images/001.jpg'
            input_image = str(input.get("input_image"))
            save_path = res_dir
            image = cropped_image(input_image, save_path, uuid1=uuid1, if_url=True)
            if image == {'error': 404}:
                return {'status': 404, 'message': 'Invalid Image URL'}
            elif image == {'error': 405}:
                return {'status': 405, 'message': 'Head not detected'}
            elif image == {'error': 406}:
                return {'status': 406, 'message': 'Pose not detected'}

            # (2) Cropped_Image -> DAGAN -> Talking_Video
            driving_video = 'src/dagan/driving/stare3.mp4'
            result_video = get_talking_video(source_image=image, driving_video=driving_video, uuid1=uuid1, working_path=res_dir)
        else:
            santa_dict = {'1': 'Santa1.jpeg', '2': 'Santa2.png', '3': 'Santa3.jpeg', '4': 'Santa4.png'}
            if str(input.get("santa_id")) not in santa_dict.keys():
                return {'status': 404, 'message': 'Chosen Santa not available'}
            image = f'src/utils/{santa_dict[str(input.get("santa_id"))]}'
            result_video = f'src/utils/{santa_dict[str(input.get("santa_id"))].split(".")[0]}.mp4'
            print(image, result_video)


        # (3) Result_Audio -> text-to-audio
        text = input.get("input_text")
        result_audio = f'{res_dir}/gtts_wish_msg.mp3'
        tts = gTTS(text, lang='en-us')
        tts.save(result_audio)

        # progress update 30%
        db['progress'].update_one({"request_id": self.uuid1}, {"$set": {"progress": "30"}})

        # (4) Taking_Video -> Lip_Sync -> lip_syned_talking_video
        # driven_audio = 'src/sadTalker/examples/driven_audio/bus_chinese.wav'
        # driven_audio = 'src/utils/wish_msg.mp4'
        driven_audio = result_audio
        # source_image = image
        source_image = result_video
        ref_eyeblink = None
        # ref_eyeblink = result_video
        talking_video = lip_sync(driven_audio, source_image, res_dir, ref_eyeblink)

        # progress update 90%
        db['progress'].update_one({"request_id": self.uuid1}, {"$set": {"progress": "90"}})

        # (5) Upload Video to S3
        s3_vid_name = str(uuid1) + '.mp4'
        res_url = upload_video_to_s3('AKIAVZBVXJWJLAWNRCWZ', 'SzjAgZQBhe7oPaQfqNgkWAe34aAHnBrd9CD1Kbjx', 'ap-southeast-1', 'effy-bandhan', s3_vid_name, talking_video)

        # (6) Clean Downloaded and Proceed Images and Video
        # remove_files_in_directory('src/results')
        # shutil.rmtree('src/results/', ignore_errors=True)
        # try:
        # if generate_video:
        #     os.remove(f'src/results/{uuid1}.png')
        #     os.remove(image)
        #     os.remove(result_video)
        # os.remove(result_audio)
        # os.remove(talking_video)
        # except Exception as e:
        #     print('File Deletion Error: ', e)
        

        print({'status': 200, 'message': 'Success', 'out_video_path': res_url, 'total_time_taken': time.time()-start_time})
        res_url = {'satya': 'url', 'mahesh': 'url'}
        return {'status': 200, 'message': 'Success', 'out_video_path': res_url}


# (6) Directory Cleaning
def remove_files_in_directory(directory_path):
    for folder in os.listdir(directory_path):
        for filename in os.listdir(os.path.join(directory_path, folder)):
            file_path = os.path.join(directory_path, folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    print('Cleaning Directory Completed')

if __name__ == "__main__":
	app.run(debug=True, port=5000)
