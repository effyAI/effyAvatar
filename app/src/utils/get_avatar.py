import os, sys, uuid, shutil, time
from threading import Thread
from datetime import datetime

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

class Get_Avatar():
    def __init__(self, db):
        self.uuid1 = str(uuid.uuid1())
        # self.input = request
        self.db = db

    def working_n_cleaning_dirs(self, working_interval, deletion_interval):
            working_time = (datetime.now().minute//working_interval)%2
            dir = [os.path.join(os.getcwd(), 'src/results-1'), os.path.join(os.getcwd(), 'src/results-2')]
            res_dir = dir[0] if working_time == 0 else dir[1]
            print(f'\nWorking on {res_dir}')
            
            deletion_time = ((datetime.now().minute+working_interval+deletion_interval)//4)%2
            if deletion_time == 0 and res_dir != dir[0]:
                shutil.rmtree(dir[0], ignore_errors=True)
                print(f'\nDeleted src/results-1')
            else:
                if res_dir != dir[1]:
                    shutil.rmtree(dir[1], ignore_errors=True)
                    print(f'\nDeleted src/results-2')

            os.makedirs(res_dir, exist_ok=True)
            return res_dir
        
    def start(self, user_input):
        start_time = time.time()
        db = self.db
        progress = 10
        try:
            # Demo Input = {'santa_id': '2', 'input_text': 'Dear {{Name}}, Wishing you and your family a joyful Christmas.', 
            #               'recipients': {'from_name': 'Ridheena', 'recipients': [['42', 'Mahesh Das']]}}
            input = user_input
            # print(input)
        except Exception as e:
            print("Post data reading error:", e) # Send error to server
            return {"error":403}
        
        
        uuid1 = self.uuid1 # UUID for Images and Videos
        # generate_video = True if input.get("input_image") != '' else False
        generate_video = False
        res_dir = self.working_n_cleaning_dirs(20, 10)

        try:
        # if True:
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
                image = f'src/utils/ref_images/{santa_dict[str(input.get("santa_id"))]}'
                result_video = f'src/utils/ref_videos/{santa_dict[str(input.get("santa_id"))].split(".")[0]}.mp4'
                print(image, result_video)

            # progress update 30%
            progress = 30
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": progress}})

            s3_res_url = {}
            saved_video_path = []
            for idx, user in enumerate(user_input['recipients']['recipients']):
                # (3) Result_Audio -> text-to-audio
                text = input.get("input_text")
                text = text.replace('{{Name}}', user[1])
                text = text.replace('{{fromName}}', user_input['recipients']['from_name'])
                print(text)
                result_audio = f'{res_dir}/gtts_wish_msg_{uuid1}.mp3'
                tts = gTTS(text, lang='en-us')
                tts.save(result_audio)

                # (4) Taking_Video -> Lip_Sync -> lip_syned_talking_video
                # if len(user_input['recipients']) > 1:
                driven_audio = result_audio
                # source_image = image
                source_image = result_video
                ref_eyeblink = None
                # ref_eyeblink = result_video
                talking_video = lip_sync(driven_audio, source_image, res_dir, ref_eyeblink)
                saved_video_path.append(talking_video)

                # (5) Upload Video to S3
                s3_vid_name = str(uuid1)+ '_' + str(idx) + '.mp4'
                res_url = upload_video_to_s3('AKIAVZBVXJWJLAWNRCWZ', 'SzjAgZQBhe7oPaQfqNgkWAe34aAHnBrd9CD1Kbjx', 'ap-southeast-1', 'effy-bandhan', s3_vid_name, talking_video)

                s3_res_url[user[1]] = res_url
                progress += (60//(len(user_input['recipients']['recipients'])))
                print('\nprogress update: ', progress)
                db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": progress}})
            
            # progress update 95%
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": 95}})


            # (6) Clean Downloaded and Proceed Images and Video
            # remove_files_in_directory('src/results')
            # shutil.rmtree('src/results/', ignore_errors=True)
            try:
                if generate_video:
                    os.remove(f'src/results/{uuid1}.png')
                    os.remove(image)
                    os.remove(result_video)
                os.remove(result_audio)
                for path in saved_video_path:
                    os.remove(path)
            except Exception as e:
                print('File Deletion Error: ', e)
            
            # s3_res_url = {'satya': res_url, 'mahesh': res_url}
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": 100, "s3_url": s3_res_url}})
            print({'status': 200, 'message': 'Success', 'out_video_path': s3_res_url, 'total_time_taken': time.time()-start_time})
            # return ('{'status': 200, 'message': 'Success', 'out_video_path': res_url}')

        except Exception as e:
            error_message = f'Error: {e}'
            print({'status': 404, 'message': error_message})
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"exception": 'Unknown Error during Video Generation', "status": 400}})
            # return {'status': 404, 'message': error_message}












# res = {'from': 'mahesh das', 'recipient': [['id', 'name'], [23, 'mahesh'], [24, 'satya']]}
# ano_res = {"from_name":"Mahesh Das","recipients":[["26","Mahesh Nair"],["27","Sunish"],["28","Ridheena"]]}
# new_res = {"santa_id":"1","input_text":"Demo text","recipients":{"from_name":"Mahesh Das","recipients":[["29","Mahesh Nair"],["30","Sunish"],["31","Ridheena"]]}}

# an_res = {'status': 200, 'message': 'Success', 'out_video_path': {["29","Mahesh Nair"]: 'url', ["30","Sunish"]: 'url'}}
            
        