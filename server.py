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


# ===== 1️⃣ 新規インスタンス起動 =====
@app.tool("launch_instance", description="新しいEC2インスタンスを起動する")
def launch_instance(instance_type: str = "t3.micro"):
    ami_id = "ami-xxxxxxxx"  # あなたのAMI IDに置き換え
    response = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": "EC2ClaudeRunnerRole"},
    )
    instance_id = response["Instances"][0]["InstanceId"]
    return {"message": f"EC2インスタンスを起動しました: {instance_id}", "instance_id": instance_id}

# ===== 2️⃣ 既存インスタンスの開始 =====
@app.tool("start_instance_by_id", description="指定したEC2インスタンスを開始する")
def start_instance_by_id(instance_id: str):
    try:
        response = ec2.start_instances(InstanceIds=[instance_id])
        state = response["StartingInstances"][0]["CurrentState"]["Name"]
        return {"message": f"インスタンス {instance_id} を開始しました。状態: {state}"}
    except Exception as e:
        return {"error": str(e)}

# ===== 3️⃣ 既存インスタンスの停止 =====
@app.tool("stop_instance_by_id", description="指定したEC2インスタンスを停止する")
def stop_instance_by_id(instance_id: str):
    try:
        response = ec2.stop_instances(InstanceIds=[instance_id])
        state = response["StoppingInstances"][0]["CurrentState"]["Name"]
        return {"message": f"インスタンス {instance_id} を停止しました。状態: {state}"}
    except Exception as e:
        return {"error": str(e)}

# ===== 4️⃣ 既存インスタンスの終了（削除） =====
@app.tool("terminate_instance_by_id", description="指定したEC2インスタンスを終了（削除）する")
def terminate_instance_by_id(instance_id: str):
    try:
        response = ec2.terminate_instances(InstanceIds=[instance_id])
        state = response["TerminatingInstances"][0]["CurrentState"]["Name"]
        return {"message": f"インスタンス {instance_id} を終了しました。状態: {state}"}
    except Exception as e:
        return {"error": str(e)}

# ===== 5️⃣ 稼働中インスタンス一覧取得 =====
@app.tool("list_instances", description="現在のEC2インスタンス一覧を取得する")
def list_instances():
    try:
        response = ec2.describe_instances()
        instances = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instances.append({
                    "InstanceId": instance["InstanceId"],
                    "State": instance["State"]["Name"],
                    "Type": instance["InstanceType"],
                    "PublicIp": instance.get("PublicIpAddress", "N/A"),
                    "Name": next(
                        (tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"),
                        "(no name)"
                    )
                })
        return {"instances": instances}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
