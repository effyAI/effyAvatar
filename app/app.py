from flask import Flask, render_template, request, jsonify
# from flask_cors import CORS
import os, sys, uuid, shutil, time, nvidia_smi
import asyncio
from threading import Thread
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')
from src.utils.get_avatar import Get_Avatar
from src.utils.utils import gpu_stats, get_db, get_sadtalker_args, get_sadtalker_nets, foul_language_check
import torch


# Load LipSync Models
sad_args, nets = get_sadtalker_nets(get_sadtalker_args())

app = Flask(__name__)

@app.route('/')
def hello_world():
	return 'Hello World!'

@app.route('/get_avatar', methods=['POST'])
def get_avatar_video():
    # This following needs to be a thread so that we are able to receive the progress api request while we keep the dub process going
    user_request = request.get_json()
    print('user_request: ', user_request)

    # Check for any foul language
    foul_score = foul_language_check(user_request.get('input_text'))
    if foul_score > 40:
        print('Foul Language Detected!!!')
        return {"request_id": 'undefined', "progress": 0, "exception": 'Foul Language Detected!!!', "status": 400, "s3_url": ''}

    db = get_db()
    get_avatar = Get_Avatar(db, sad_args, nets)
    print('\nuuid1: ', get_avatar.uuid1)


    # create progress object
    progress_object = {
        "request_id": get_avatar.uuid1,
        "progress": 0,
        "exception": '',
        "status": 200,
        "s3_url": '',
    }
    db['progress'].insert_one(progress_object)

    try:
        thread = Thread(target=get_avatar.start, args=(user_request,))
        thread.start()
    except RuntimeError as e:
        # Clear the memory cache
        torch.cuda.empty_cache()
        print('error: ', e)
        return {"request_id": get_avatar.uuid1, "error": "CUDA out of Memory, Please Try After Sometime", "status": 503}
    
    print('progress_object: ', progress_object)
    # print("db['progress']: ", db['progress'].find_one({"request_id": get_avatar.uuid1}))
    return {"request_id": get_avatar.uuid1, "progress": 0, "exception": '', "status": 200, "s3_url": '', }

@app.route('/get_progress', methods=['GET'])
def get_progress():
    json = request.get_json()
    db = get_db()
    print('\nSending Progress Status...')


    res = db['progress'].find_one({"request_id": json["request_id"]})
    print('res: ', res)
    if res == None:
        return {"msg": "request id is missing", "msg_code": "request_id_missing", "status": 400}
	
    # if status is not complete then send the actual status
    if res['progress'] != 100:
        if "exception" in res and res['exception'] != '':
            return \
                {
                    "status": 500,
                    "msg": res['exception'],
                    "msg_code": "Progress API Error"
                }
        else:
            return {"request_id": res["request_id"], "progress": res['progress'], "status": 200, "msg": "still processing", "msg_code": "OK"}
    else:
        # Delete the progress element as it is no longer needed and the main s3 url is pushed to the main table
        db['progress'].delete_one({"request_id": json["request_id"]})
        print({"request_id": res["request_id"], "exception": res["exception"], "status": 200, "progress": res['progress'], "s3_url": res['s3_url']})
        return {"request_id": res["request_id"], "exception": res["exception"], "status": 200, "progress": res['progress'], "s3_url": res['s3_url']}
    
if __name__ == "__main__":
	app.run(debug=False, port=5000)
