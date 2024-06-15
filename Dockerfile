# Use the official AWS Lambda Python 3.8 base image
FROM public.ecr.aws/lambda/python:3.12

# Copy the requirements file into the container
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application directory into the container
COPY app.py ${LAMBDA_TASK_ROOT}

# Set the entry point for the Lambda function
CMD ["app.lambda_handler"]
