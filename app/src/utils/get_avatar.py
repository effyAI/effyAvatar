import os, sys, uuid, shutil, time
from threading import Thread
from datetime import datetime
import subprocess
from src.utils.utils import gpu_stats, get_caption

# (1) Image Cropping
sys.path.append('src/image_cropping/')
from get_cropped_image import cropped_image
# (2) DAGAN
sys.path.append('src/dagan/')
from demo import get_talking_video
# (3) Text-to-Speech
from gtts import gTTS
sys.path.append('src/utils/')
from src.utils.utils import text_to_speech, text_to_speech_indian
# (4) Lip Sync
sys.path.append('src/sadTalker')
from inf2 import lip_sync
# (5) Upload to S3
from src.utils.utils import upload_video_to_s3

class Get_Avatar():
    def __init__(self, db, sad_args, nets):
        self.uuid1 = str(uuid.uuid1())
        self.db = db
        self.sad_args = sad_args
        self.nets = nets

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

    def concat_videos(self, video_files, output_file):
        """Concatenates videos side by side using FFmpeg.
        Args:
            video_files: A list of video files to concatenate.
            output_file: The output video file.
        """

        command = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "src/utils/concat_videos.txt",
            "-c:v",
            "libx264",  # Specify H.264 codec
            output_file,
        ]

        with open("src/utils/concat_videos.txt", "w") as f:
            for video_file in video_files:
                f.write(f"file '{video_file}'\n")

        subprocess.run(command)
    
    def convert_video_to_h264(self, video_file, output_file):
        # FFmpeg command to convert from MP4V to H.264
        command = [
            "ffmpeg",
            "-i",
            video_file,
            "-c:v",
            "libx264",  # Specify H.264 codec
            "-c:a",
            "aac",  # Specify AAC audio codec
            output_file,
        ]
        # Run the FFmpeg command
        subprocess.run(command)

    def start(self, user_input):
        db = self.db
        while True:
            print('\nWaiting for memory to free...')
            if gpu_stats() >= 0:
                print('Got Free Memory :)')
                thread = Thread(target=self.start_generation, args=(user_input,))
                thread.start()
                db['progress'].update_one({"request_id": self.uuid1}, {"$set": {"progress": 10}})
                break
            time.sleep(2)

    def start_generation(self, user_input):
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
                santa_dict = {'1': 'Santa1.jpeg', '2': 'Santa2.png', '3': 'Santa3.jpeg', '4': 'Santa4.png', 'male1': 'male1.jpeg', 'male2': 'male2.jpeg', 'female1': 'female1.jpeg', 'female2': 'female2.jpeg'}
                if str(input.get("santa_id")) not in santa_dict.keys():
                    return {'status': 404, 'message': 'Chosen Santa not available'}
                image = f'src/utils/ref_images/{santa_dict[str(input.get("santa_id"))]}'
                result_video = f'src/utils/ref_videos/{santa_dict[str(input.get("santa_id"))].split(".")[0]}.mp4'
                print(image, result_video)

            s3_res_url = {}
            saved_video_path = []
            saved_audio_path = []
            output_videos_path = []
            for idx, user in enumerate(user_input['recipients']['recipients']):
                # (3) Result_Audio -> text-to-audio
                text = input.get("input_text")
                if str(input.get("text")) == 'default':
                    if text.find("{{fromName}}") != -1:
                        text = "Dear {{Name}}, Your friend {{fromName}} have a special request on your behalf,"
                    elif text.find("{{Name}}") != -1:
                        text = "Dear {{Name}}, Wishing you and your family a joyful Christmas."
                text = text.replace('{{Name}}', user[1])
                text = text.replace('{{fromName}}', user_input['recipients']['from_name'])
                result_audio = f'{res_dir}/gtts_wish_msg_{uuid1}.mp3'
                print('\nFinal text: ', text)
                # try:
                #     res_status = text_to_speech(text, result_audio)
                #     if res_status != 200:
                #         print({'status': res_status, 'exception': 'API Error during Text-to-speech Genertaion'})
                #         db['progress'].update_one({"request_id": uuid1}, {"$set": {"exception": 'API Error during Text-to-speech Genertaion', "status": res_status}})
                #         return
                #     # text_to_speech_indian(text, result_audio)
                #     print('\nSpeech Generated')
                # except Exception as e:
                #     error_message = f'Error: {e}'
                #     print({'status': 400, 'message': error_message, 'exception': 'Unknown Error during Text-to-speech Generation'})
                #     db['progress'].update_one({"request_id": uuid1}, {"$set": {"exception": 'Unknown Error during Text-to_speech Generation', "status": 400}})
                #     return
                tts = gTTS(text, lang='en-us')
                tts.save(result_audio)

                # (4) Taking_Video -> Lip_Sync -> lip_syned_talking_video
                driven_audio = result_audio
                source_image = image
                # source_image = result_video
                ref_eyeblink = None
                # ref_eyeblink = result_video
                if progress < 30:
                    # progress update 30%
                    progress = 30
                    db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": progress}})
                    print('\nprogress update: ', progress)
                talking_video = lip_sync(driven_audio, source_image, res_dir, ref_eyeblink, enhance=input.get("enhance"), nets=self.nets, sad_args=self.sad_args)
                saved_video_path.append(talking_video)

                # if Text Type Default
                output_video_path = f'{res_dir}/{str(uuid1)}_{str(idx)}.mp4'
                if str(input.get("text")) == 'default':
                    self.concat_videos([talking_video, f'pre_ready_videos/talking_santa{str(input.get("santa_id"))}.mp4'], output_video_path)
                    # output_videos_path.append(output_video_path)
                else:
                    self.convert_video_to_h264(talking_video, output_video_path)

                # (5) Upload Video to S3
                # e.g. s3_vid_name = videos/310b8d8c-a56e-11ee-9bce-3d75ccdf8f90_0.mp4
                s3_vid_name = 'videos/' + str(uuid1)+ '_' + str(idx) + '.mp4'
                res_url = upload_video_to_s3('AKIAVZBVXJWJLAWNRCWZ', 'SzjAgZQBhe7oPaQfqNgkWAe34aAHnBrd9CD1Kbjx', 'ap-southeast-1', 'effy-greetings', s3_vid_name, output_video_path)

                progress += (60//(len(user_input['recipients']['recipients'])))
                print('\nprogress update: ', progress)
                db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": progress}})

                res_sub_url = ''
                if input.get('caption'):
                    res_code, subtitle_path = get_caption(output_video_path, res_dir)
                    if res_code == 0:
                        s3_sub_name = 'videos/' + subtitle_path.split('/')[-1]
                        res_sub_url = upload_video_to_s3('AKIAVZBVXJWJLAWNRCWZ', 'SzjAgZQBhe7oPaQfqNgkWAe34aAHnBrd9CD1Kbjx', 'ap-southeast-1', 'effy-greetings', s3_sub_name, subtitle_path, content_type='Text/srt')
                    else:
                        print('Subtitle Generation Error')
            
                s3_res_url[user[1]] = [res_url, res_sub_url]
            # progress update 95%
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": 95}})

            # (6) Clean Downloaded and Proceed Images and Video
            try:
                if generate_video:
                    os.remove(f'src/results/{uuid1}.png')
                    os.remove(image)
                    os.remove(result_video)
                os.remove(result_audio)
                # os.remove(output_video_path)
                for idx in range(len(saved_video_path)):
                    os.remove(saved_video_path[idx])
                print('\nSuccessfully Deleted All Files')
            except Exception as e:
                print('\nFile Deletion Error: ', e)
            
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"progress": 100, "s3_url": s3_res_url}})
            print('Result: ', {'status': 200, 'message': 'Success', 'out_video_path': s3_res_url, 'total_time_taken': time.time()-start_time})

        except Exception as e:
            error_message = f'Error: {e}'
            print({'status': 400, 'message': error_message, 'exception': 'Unknown Error during Video Generation'})
            db['progress'].update_one({"request_id": uuid1}, {"$set": {"exception": 'Unknown Error during Video Generation', "status": 400}})