import nvidia_smi
import requests
from elevenlabs import generate, play, set_api_key
import pymongo
import boto3, sys
from argparse import Namespace
import torch
import subprocess
# from profanity_check.profanity_check import predict
# Load Models
sys.path.append('src/sadTalker')
from src.utils.init_path import init_path
from src.utils.preprocess import CropAndExtract
from src.test_audio2coeff import Audio2Coeff  
from src.facerender.animate import AnimateFromCoeff


def get_sadtalker_args():
    default_args = {
        # "driven_audio": './examples/driven_audio/bus_chinese.wav',
        # "source_image": './examples/source_image/full_body_1.png',
        # "ref_eyeblink": None,
        "ref_pose": None,
        "checkpoint_dir": 'src/sadTalker/checkpoints',
        'current_root_path': 'src/sadTalker',
        "result_dir": '',
        "pose_style": 0,
        "batch_size": 13,
        "size": 256,
        "expression_scale": 1.0,
        "input_yaw": None,
        "input_pitch": None,
        "input_roll": None,
        "enhancer": None,
        "background_enhancer": None,
        "cpu": False,
        "face3dvis": False,
        "still": True,
        "preprocess": 'full',
        "verbose": False,
        "old_version": False,
        "net_recon": 'resnet50',
        "init_path": None,
        "use_last_fc": False,
        "bfm_folder": './checkpoints/BFM_Fitting/',
        "bfm_model": 'BFM_model_front.mat',
        "focal": 1015.0,
        "center": 112.0,
        "camera_d": 10.0,
        "z_near": 5.0,
        "z_far": 15.0
    }
    return default_args


def get_sadtalker_nets(default_args):
    sad_args = Namespace(**default_args)
    sad_args.device = "cuda" if torch.cuda.is_available() and not sad_args.cpu else "cpu"
    sadtalker_paths = init_path(sad_args.checkpoint_dir, 'src/sadTalker/src/config', sad_args.size, sad_args.old_version, sad_args.preprocess)
    preprocess_model = CropAndExtract(sadtalker_paths, sad_args.device)
    audio_to_coeff = Audio2Coeff(sadtalker_paths,  sad_args.device)
    animate_from_coeff = AnimateFromCoeff(sadtalker_paths, sad_args.device)
    nets = (preprocess_model, audio_to_coeff, animate_from_coeff)
    return sad_args, nets 


def gpu_stats():
    nvidia_smi.nvmlInit()
    handle = nvidia_smi.nvmlDeviceGetHandleByIndex(0)
    info = nvidia_smi.nvmlDeviceGetMemoryInfo(handle)

    free_memory =  info.free / (1024 ** 3)
    nvidia_smi.nvmlShutdown()
    return free_memory


def get_db():
    client = pymongo.MongoClient('mongodb+srv://effybizai:AhM2SPj8dKfLId89@cluster0.yfq6agh.mongodb.net/?retryWrites=true&w=majority')
    # Create the database for our example (we will use the same database throughout the tutorial
    db = client.effy_greetings
    return db


def upload_video_to_s3(aws_access_key_id, aws_secret_access_key, region_name, bucket_name, object_key, local_image_path, content_type='video/mp4'):
    try:
        # Initialize the S3 client
        s3 = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name)
        # Upload the image to S3
        s3.upload_file(local_image_path, bucket_name, object_key, ExtraArgs={'ContentType': content_type})
        
        print(f'Successfully uploaded {local_image_path} to S3 bucket {bucket_name} with key {object_key}')
        s3_url = f'https://{bucket_name}.s3.amazonaws.com/{object_key}'
        return s3_url
    except Exception as e:
        print(f'Error uploading the image: {e}')
        return False


def text_to_speech(text, file_path):
    url = "https://api.elevenlabs.io/v1/text-to-speech/knrPHWnBmmDHMoiMeP3l"
    payload = {"text": text}
    headers = {
        # "xi-api-key": "5317c125c53cf52edca2447421ce20ee",
        "xi-api-key": "080df7b4d80d1c57000c250ded20c575",
        "Content-Type": "application/json"
    }

    response = requests.request("POST", url, json=payload, headers=headers)
    if response.status_code == 200:
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        # print('\nSpeech Generated')
    elif response.status_code == 401:
        print("401: HTTPS Error maybe unable to connect to elevenlabs api")
    else:
        print(response.status_code)
    return response.status_code



def text_to_speech_indian(text, file_path):
    # Check the guide on how to get a free API key: https://docs.elevenlabs.io/authentication/01-xi-api-key
    set_api_key("080df7b4d80d1c57000c250ded20c575")  

    audio = generate(
        text=text,
        voice="Vijay - Expressive Indian male"
    )

    with open(file_path, 'wb') as file:
        file.write(audio)
    play(audio, notebook=True)


# if '__name__' == "__main__":
    # text_to_speech("praising your incredible friendship. You've consistently been a source of kindness and support. May your Christmas overflow with warmth, laughter, and unforgettable moments.Wishing you all the joys of the season and a magnificent New Year ahead!", "fixed_msg_audio.mp3")
    # text_to_speech_indian("Dear Random john, Your enemy doe have made a special request on your behalf, praising your incredible friendship. You've consistently been a source of kindness and support. May your Christmas overflow with warmth, laughter, and unforgettable moments.Wishing you all the joys of the season and a magnificent New Year ahead!", "generated_audio.mp3")

def foul_language_check(text):
    # return predict(["Hello, subprocess!"])
    # text = "Hello, subprocess!"
    result = subprocess.run(["profanity_check", text], capture_output=True, text=True)
    print("Foul Score: ", round(float(result.stdout.split('\n\n')[3].split(':')[-1]), 2)*100)
    return round(float(result.stdout.split('\n\n')[3].split(':')[-1]), 2)*100
# print('result: ', foul_language_check("you're a one of the biggest motherfucker in the world"))


def get_caption(video_file, res_dir, ext="srt"):
    # video_file = "src/utils/ref_audio/fixed_msg_audio.mp3"
    # res_dir = "src/results-1"
    # bash syntax: whisperx src/utils/pre_ready_videos/talking_santa1.mp4 --model large-v2 --align_model WAV2VEC2_ASR_LARGE_LV60K_960H \
    # --batch_size 4 --output_dir src/results-1 --output_format srt
    command = ["whisperx", video_file,
               "--model", "large-v2",
               "--align_model", "WAV2VEC2_ASR_LARGE_LV60K_960H",
               "--batch_size", "1",
               "--output_dir", res_dir,
               "--output_format", ext
              ]
    res_path = f"{res_dir}/{video_file.split('/')[-1].split('.')[0]}.{ext}"
    result = subprocess.run(command)
    return result.returncode, res_path

# print('subtitle result: ', get_caption('src/utils/pre_ready_videos/talking_santa1.mp4', 'src/results-1'))


def generation_image(prompt):
    api_key = "262abe547ef94cc98c28f5d7118391971d2a6da55da1091f35798356e283ae81" 
    endpoint = "https://api.midjourneyapi.xyz/mj/v2/imagine"
    headers = {
        "X-API-KEY": api_key
    }
    data = {
        "prompt": "262abe547ef94cc98c28f5d7118391971d2a6da55da1091f35798356e283ae81",
        "aspect_ratio": "1:1",
        "process_mode": "mixed",
        "webhook_endpoint": "",
        "webhook_secret": ""
    }
    response = requests.post(endpoint, headers=headers, json=data)
    print(response.status_code)
    print(response.json())
    return response.status_code, response.json()['task_result']['image_url']