import os
import boto3
import pymongo

def get_db():
    client = pymongo.MongoClient('mongodb+srv://effybizai:AhM2SPj8dKfLId89@cluster0.yfq6agh.mongodb.net/?retryWrites=true&w=majority')
    # Create the database for our example (we will use the same database throughout the tutorial
    db = client.effy_greetings
    return db