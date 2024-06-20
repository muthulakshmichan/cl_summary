import json
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, date, timedelta
import pytz
import openai
import os

client = MongoClient(os.environ['MONGODB_URI'])
db = client['CoachLife']
player_learning_collection = db['Player Learning']
prompts_collection = db['Prompts']

# Set up the OpenAI API key
openai.api_key = os.environ['OPENAI_API_KEY']

def fetch_prompts():
    prompt_doc = prompts_collection.find_one(
        {"$or": [
            {"coach_prompt": {"$exists": True}}, 
            {"parent_prompt": {"$exists": True}}, 
            {"overall_prompt": {"$exists": True}}
        ]}
    )
    if prompt_doc:
        return (
            prompt_doc.get("coach_prompt", ""), 
            prompt_doc.get("parent_prompt", ""), 
            prompt_doc.get("overall_prompt", "")
        )
    else:
        raise ValueError("Prompts not found in the database")

def fetch_comments(player_id, start_date=None, end_date=None):
    try:
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # Fetch comments for the current month if no date range provided
            today = date.today()
            start_date_obj = datetime(today.year, today.month, 1)
            end_date_obj = datetime(today.year, today.month + 1, 1) - timedelta(days=1)

        start_date_ist = pytz.timezone('Asia/Kolkata').localize(start_date_obj)
        end_date_ist = pytz.timezone('Asia/Kolkata').localize(end_date_obj).replace(hour=23, minute=59, second=59)

        # Convert IST to UTC
        start_date_utc = start_date_ist.astimezone(pytz.utc)
        end_date_utc = end_date_ist.astimezone(pytz.utc)
        
        print(f"Fetching comments for player {player_id} from {start_date_utc} to {end_date_utc}")

        pipeline = [
            {'$match': {'playerId': ObjectId(player_id)}},
            {'$unwind': '$Comments'},
            {'$addFields': {
                'Comments.CommentedOn': {
                    '$dateFromString': {
                        'dateString': '$Comments.CommentedOn',
                        'format': '%Y-%m-%d %H:%M:%S',
                        'timezone': 'Asia/Kolkata'
                    }
                }
            }},
            {'$match': {
                'Comments.CommentedOn': {
                    '$gte': start_date_utc,
                    '$lte': end_date_utc
                }
            }},
            {'$project': {
                'CommentId': {'$toString': '$Comments._id'},  # Convert ObjectId to string
                'Comment': '$Comments.Comment_En',
                'CommentedBy': '$Comments.CommentedBy',
                'CommentedOn': '$Comments.CommentedOn',
                '_id': 0
            }}
        ]

        comments = list(player_learning_collection.aggregate(pipeline))
        print(f"Found {len(comments)} comments")
        return comments
    except Exception as e:
        print(f"Error fetching comments: {e}")
        raise

def fetch_activities(player_id, start_date=None, end_date=None):
    try:
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # Fetch activities for the current month if no date range provided
            today = date.today()
            start_date_obj = datetime(today.year, today.month, 1)
            end_date_obj = datetime(today.year, today.month + 1, 1) - timedelta(days=1)

        start_date_ist = pytz.timezone('Asia/Kolkata').localize(start_date_obj)
        end_date_ist = pytz.timezone('Asia/Kolkata').localize(end_date_obj).replace(hour=23, minute=59, second=59)

        # Convert IST to UTC
        start_date_utc = start_date_ist.astimezone(pytz.utc)
        end_date_utc = end_date_ist.astimezone(pytz.utc)
        
        print(f"Fetching activities for player {player_id} from {start_date_utc} to {end_date_utc}")

        pipeline = [
            {'$match': {'playerId': ObjectId(player_id)}},
            {'$unwind': '$Activities'},
            {'$addFields': {
                'Activities.Date': {
                    '$dateFromString': {
                        'dateString': '$Activities.Date',
                        'format': '%Y-%m-%d %H:%M:%S',
                        'timezone': 'Asia/Kolkata'
                    }
                }
            }},
            {'$match': {
                'Activities.Date': {
                    '$gte': start_date_utc,
                    '$lte': end_date_utc
                }
            }},
            {'$project': {
                'ActivityId': {'$toString': '$Activities._id'},  # Convert ObjectId to string
                'Activity': '$Activities.Description',
                'Date': '$Activities.Date',
                '_id': 0
            }}
        ]

        activities = list(player_learning_collection.aggregate(pipeline))
        print(f"Found {len(activities)} activities")
        return activities
    except Exception as e:
        print(f"Error fetching activities: {e}")
        raise

def summarize_comments(comments, prompt):
    try:
        # Filter out comments that do not have the 'Comment' field
        filtered_comments = [comment for comment in comments if 'Comment' in comment]
        
        if not filtered_comments:
            return "No valid comments to summarize."

        combined_text = " ".join(comment['Comment'] for comment in filtered_comments)
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": combined_text}
            ]
        )
        summary = response['choices'][0]['message']['content'].strip()
        
        print(f"Summary: {summary}")
        
        return summary
    except Exception as e:
        print(f"Error summarizing comments: {e}")
        raise

def summarize_comments_and_activities(comments, activities, prompt):
    try:
        # Filter out comments that do not have the 'Comment' field
        filtered_comments = [comment for comment in comments if 'Comment' in comment]
        filtered_activities = [activity for activity in activities if 'Activity' in activity]
        
        if not filtered_comments and not filtered_activities:
            return "No valid comments or activities to summarize."

        combined_text = "Comments: " + " ".join(comment['Comment'] for comment in filtered_comments)
        combined_text += " Activities: " + " ".join(activity['Activity'] for activity in filtered_activities)
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": combined_text}
            ]
        )
        summary = response['choices'][0]['message']['content'].strip()
        
        print(f"Summary: {summary}")
        
        return summary
    except Exception as e:
        print(f"Error summarizing comments and activities: {e}")
        raise

def lambda_handler(event, context):
    print("Received event:", event)
    try:
        # Check if the input is coming from API Gateway where the body might be a JSON string
        if 'body' in event:
            body = event['body']
            # If body is a string, parse it as JSON
            if isinstance(body, str):
                body = json.loads(body)
        else:
            body = event

        player_id = body.get("player_id")
        summary_type = body.get("summary_type")
        start_date = body.get("start_date")
        end_date = body.get("end_date")

        if not player_id or not summary_type:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "player_id and summary_type are required fields"}),
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Max-Age": "3600"
                }
            }

        coach_prompt, parent_prompt, overall_prompt = fetch_prompts()
        
        comments = fetch_comments(player_id, start_date, end_date)
        activities = fetch_activities(player_id, start_date, end_date)
        
        if not comments and not activities:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "No comments or activities found in the given date range"}),
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Max-Age": "3600"
                }
            }

        if summary_type.lower() == "coach":
            summary = summarize_comments(comments, coach_prompt)
        elif summary_type.lower() == "parent":
            summary = summarize_comments(comments, parent_prompt)
        elif summary_type.lower() == "overall":
            summary = summarize_comments_and_activities(comments, activities, overall_prompt)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid summary type. Please specify 'coach', 'parent', or 'overall'."}),
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Max-Age": "3600"
                }
            }

        response_body = {"summary": summary}
        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Max-Age": "3600"
            }
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Max-Age": "3600"
            }
        }
