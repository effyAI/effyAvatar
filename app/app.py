from flask import Flask, render_template, request, jsonify
# from flask_cors import CORS
import os, sys, uuid, shutil, time
from threading import Thread
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')
from src.utils.get_avatar import Get_Avatar
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

app = Flask(__name__)

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
    get_avatar = Get_Avatar(db)
    print('\nuuid1: ', get_avatar.uuid1)
    # res = {"request_id": get_avatar.uuid1, "progress": "progress_initiated", "exception": "", "status": 400} # This will be the return element

    # This following needs to be a thread so that we are able to receive the progress api request while we keep the dub process going
    user_request = request.get_json()
    print('user_request: ', user_request)
    try:
        thread = Thread(target=get_avatar.start, args=(user_request,))
        thread.start()
    except RuntimeError as e:
        print('error: ', e)
        return {"request_id": get_avatar.uuid1, "error": "CUDA out of Memory, Please Try After Sometime", "status": 503}
    
    # create progress object
    progress_object = {
        "request_id": get_avatar.uuid1,
        "progress": 10,
        "exception": '',
        "status": 200,
        "s3_url": '',
    }
    new_res = db['progress'].insert_one(progress_object)
    print('progress_object: ', progress_object)
    # print("db['progress']: ", db['progress'].find_one({"request_id": get_avatar.uuid1}))

    return {
        "request_id": get_avatar.uuid1,
        "progress": 10,
        "exception": '',
        "status": 200,
        "s3_url": '',
    }

@app.route('/get_progress', methods=['GET'])
def get_progress():
    json = request.get_json()
    db = get_db()
    print('\n')
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
