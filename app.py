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
    prompt_doc = prompts_collection.find_one({"$or": [{"coach_prompt": {"$exists": True}}, {"parent_prompt": {"$exists": True}}]})
    if prompt_doc:
        return prompt_doc.get("coach_prompt", ""), prompt_doc.get("parent_prompt", "")
    else:
        raise ValueError("Prompts not found in the database")

def fetch_comments(player_id, start_date=None, end_date=None):
    start_date_obj = None
    end_date_obj = None
    
    if start_date and end_date:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        # If either start date or end date is not provided, fetch comments for the current month
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
    # print(comments)
    return comments

def summarize_comments(comments, prompt):
    # Filter out comments that do not have the 'Comment' field
    filtered_comments = [comment for comment in comments if 'Comment' in comment]
    
    if not filtered_comments:
        return "No valid comments to summarize."

    combined_comments = " ".join(comment['Comment'] for comment in filtered_comments)
    # print(f"Summarizing combined comments: {combined_comments}")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": combined_comments}
        ]
    )
    summary = response['choices'][0]['message']['content'].strip()
    
    print(f"Summary: {summary}")
    
    return summary

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
                "body": json.dumps({"error": "player_id and summary_type are required fields"})
            }

        coach_prompt, parent_prompt = fetch_prompts()
        
        comments = fetch_comments(player_id, start_date, end_date)
        if not comments:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "No comments found in the given date range"})
            }
            
        if summary_type.lower() == "coach":
            summary = summarize_comments(comments, coach_prompt)
        elif summary_type.lower() == "parent":
            summary = summarize_comments(comments, parent_prompt)
        else:
            return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Invalid summary type. Please specify 'coach' or 'parent'."})
                }

        response_body = {"summary": summary.replace("\n", "\\n")}
        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "headers": {
                "Content-Type": "application/json"
            }
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
