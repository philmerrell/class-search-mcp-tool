# Lambda-compatible Python container image
FROM public.ecr.aws/lambda/python:3.12

# Copy requirements first for better layer caching
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application code
COPY app.py ${LAMBDA_TASK_ROOT}/
COPY opensearch_client.py ${LAMBDA_TASK_ROOT}/

# Set the handler for Lambda
CMD ["app.lambda_handler"]
