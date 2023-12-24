import boto3

def upload_video_to_s3(aws_access_key_id, aws_secret_access_key, region_name, bucket_name, object_key, local_image_path):
    try:
        # Initialize the S3 client
        s3 = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name)
        # Upload the image to S3
        s3.upload_file(local_image_path, bucket_name, object_key, ExtraArgs={'ContentType': 'video/mp4'})
        
        print(f'Successfully uploaded {local_image_path} to S3 bucket {bucket_name} with key {object_key}')
        s3_url = f'https://{bucket_name}.s3.amazonaws.com/{object_key}'
        return s3_url
    except Exception as e:
        print(f'Error uploading the image: {e}')
        return False