from fastmcp import MCPServer, mcp_handler
from fastapi import Request
import boto3
import json
import requests
import os

app = MCPServer()
ec2 = boto3.client("ec2", region_name="ap-northeast-1")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-mcp-server.com/webhook/result")
AMI_ID = os.getenv("AMI_ID", "ami-xxxxxxxx")  # Claude CLI入りAMI

@app.mcp_handler("run_claude")
def run_claude(prompt: str, instance_type: str = "t3.medium"):
    """Claudeを別インスタンスで実行する"""
    print(f"Launching EC2 for Claude: prompt={prompt}")

    user_data_script = f"""#!/bin/bash
    set -e
    apt-get update -y
    apt-get install -y curl jq
    echo "Running Claude task..."
    claude --prompt '{prompt}' > /tmp/output.txt
    RESULT=$(cat /tmp/output.txt | jq -Rs .)
    curl -X POST -H 'Content-Type: application/json' \\
         -d '{{"instance_id": "$(curl -s http://169.254.169.254/latest/meta-data/instance-id)", "result": $RESULT}}' \\
         {WEBHOOK_URL}
    """

    response = ec2.run_instances(
        ImageId=AMI_ID,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        UserData=user_data_script,
        IamInstanceProfile={"Name": "EC2ClaudeRunnerRole"},
    )

    instance_id = response["Instances"][0]["InstanceId"]
    return {"status": "launched", "instance_id": instance_id}


@app.post("/webhook/result")
async def webhook_result(request: Request):
    """EC2-2からClaudeの実行結果を受け取るWebhook"""
    data = await request.json()
    instance_id = data.get("instance_id")
    result = data.get("result")

    print(f"Received result from {instance_id}: {result[:200]}...")

    # Claudeに返却する形式に整形
    return {"status": "ok", "summary": f"Result from {instance_id}", "result": result}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
